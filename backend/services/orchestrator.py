"""
Orchestration layer for the Phase 5 multi-agent reasoning system.

Implements the 3-round pattern:
    Round 1 — parallel specialist calls (Weather, Timing, Species)
    Round 2 — parallel peer-review calls (each specialist reviews its peers)
    Round 3 — single coordinator call (synthesises R2 revised outputs)

Public surface:
    run_rerank_orchestration(top_n_candidates, weather_ctx, conditions) -> dict
    run_trip_plan_orchestration(candidate, weather_ctx, conditions)      -> dict
    OrchestrationError

Failure policy:
    R1: 1 failure → log + continue; ≥2 failures → OrchestrationError.
    R2: skipped entirely when any R1 output is None (peer prompts assume two peers).
        Any individual R2 failure or empty-peer case → None for that role.
        Coordinator falls back to R1 via _build_coordinator_inputs.
    R3: coordinator failure → OrchestrationError.

Result dict includes 'timings' with per-round wall-clock seconds for diagnostics.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from services.agents import (
    run_coordinator_rerank,
    run_coordinator_trip_plan,
    run_peer_review,
    run_species_agent,
    run_timing_agent,
    run_weather_agent,
)
from services.weather import compute_water_temp_estimate

_log = logging.getLogger(__name__)

_ROLES = ("weather_agent", "timing_agent", "species_agent")


class OrchestrationError(Exception):
    """Raised when orchestration cannot proceed (≥2 R1 failures or coordinator failure)."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _run_round1(
    candidates: list[dict],
    conditions: dict[str, Any],
    weather_ctx: dict[str, Any],
    water_temp_c: float | None,
) -> tuple[dict[str, list[dict] | None], list[str]]:
    """Run all three specialists in parallel. Returns (outputs, errors)."""
    outputs: dict[str, list[dict] | None] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            "weather_agent": executor.submit(
                run_weather_agent, candidates, conditions, weather_ctx
            ),
            "timing_agent": executor.submit(
                run_timing_agent, candidates, conditions
            ),
            "species_agent": executor.submit(
                run_species_agent, candidates, conditions, weather_ctx, water_temp_c
            ),
        }
        for role, future in futures.items():
            try:
                outputs[role] = future.result()
            except Exception as exc:
                _log.warning(
                    "%s failed in Round 1: %s: %s", role, type(exc).__name__, exc
                )
                outputs[role] = None
                errors.append(f"R1 {role}: {type(exc).__name__}: {exc}")

    failed = [role for role, out in outputs.items() if out is None]
    if len(failed) >= 2:
        raise OrchestrationError(
            f"Round 1 aborted: {len(failed)} of 3 specialists failed: "
            + ", ".join(failed)
        )

    return outputs, errors


def _run_round2(
    r1_outputs: dict[str, list[dict] | None],
) -> tuple[dict[str, dict | None], list[str]]:
    """Run peer review for each specialist.

    Skips R2 entirely when any R1 output is None — peer-review prompts assume
    two peers and silently break with only one. Returns all-None dict with a
    skip note in errors when this occurs.

    Also skips an individual specialist's peer review when all peers' R1 outputs
    are None (empty peer_out).
    """
    if not all(v is not None for v in r1_outputs.values()):
        return (
            {role: None for role in _ROLES},
            ["Round 2 skipped: incomplete Round 1"],
        )

    r2_outputs: dict[str, dict | None] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures: dict[str, Any] = {}
        for role in _ROLES:
            peer_out = {
                r: r1_outputs[r]
                for r in _ROLES
                if r != role and r1_outputs.get(r) is not None
            }
            if not peer_out:
                r2_outputs[role] = None
                continue
            futures[role] = executor.submit(
                run_peer_review, role, r1_outputs[role], peer_out
            )

        for role, future in futures.items():
            try:
                r2_outputs[role] = future.result()
            except Exception as exc:
                _log.warning(
                    "%s peer review failed in Round 2: %s: %s",
                    role, type(exc).__name__, exc,
                )
                errors.append(f"R2 {role}: {type(exc).__name__}: {exc}")
                r2_outputs[role] = None

    # Fill None for any role skipped due to empty peers
    for role in _ROLES:
        r2_outputs.setdefault(role, None)

    return r2_outputs, errors


def _build_coordinator_inputs(
    r1_outputs: dict[str, list[dict] | None],
    r2_outputs: dict[str, dict | None],
) -> tuple[dict[str, Any], list[dict]]:
    """Build specialist_outputs and peer_review_changes for the coordinator.

    Uses my_revised_position from R2 when available; falls back to R1 output.
    """
    specialist_outputs: dict[str, Any] = {}
    peer_review_changes: list[dict] = []

    for role in _ROLES:
        r2 = r2_outputs.get(role)
        if r2 is not None and "my_revised_position" in r2:
            specialist_outputs[role] = r2["my_revised_position"]
            peer_review_changes.extend(r2.get("what_changed_from_round_1", []))
        else:
            specialist_outputs[role] = r1_outputs.get(role)

    return specialist_outputs, peer_review_changes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_rerank_orchestration(
    top_n_candidates: list[dict],
    weather_ctx: dict[str, Any],
    conditions: dict[str, Any],
) -> dict[str, Any]:
    """Run the 3-round rerank orchestration for a list of candidates.

    Args:
        top_n_candidates: Candidate property dicts selected by select_top_n().
        weather_ctx: Output of get_weather_context().
        conditions: Output of get_all_conditions().

    Returns:
        {
            "coordinator_output": dict,
            "round1": {"weather_agent": list|None, ...},
            "round2": {"weather_agent": dict|None, ...},
            "water_temp_c": float|None,
            "errors": list[str],
            "timings": {"round1_s": float, "round2_s": float, "round3_s": float, "total_s": float},
        }

    Raises:
        OrchestrationError: ≥2 R1 failures or coordinator failure.
    """
    t_start = time.perf_counter()
    water_temp_c = compute_water_temp_estimate(weather_ctx, conditions["season"])

    t1 = time.perf_counter()
    r1_outputs, r1_errors = _run_round1(
        top_n_candidates, conditions, weather_ctx, water_temp_c
    )
    t2 = time.perf_counter()
    _log.info("Round 1 complete in %.2fs", t2 - t1)

    r2_outputs, r2_errors = _run_round2(r1_outputs)
    t3 = time.perf_counter()
    _log.info("Round 2 complete in %.2fs", t3 - t2)

    specialist_outputs, peer_review_changes = _build_coordinator_inputs(
        r1_outputs, r2_outputs
    )

    try:
        coordinator_output = run_coordinator_rerank(
            top_n_candidates, conditions, water_temp_c,
            specialist_outputs, peer_review_changes,
        )
    except Exception as exc:
        raise OrchestrationError(
            f"Coordinator (rerank) failed: {type(exc).__name__}: {exc}"
        ) from exc

    t4 = time.perf_counter()
    _log.info("Round 3 (coordinator) complete in %.2fs", t4 - t3)

    return {
        "coordinator_output": coordinator_output,
        "round1": r1_outputs,
        "round2": r2_outputs,
        "water_temp_c": water_temp_c,
        "errors": r1_errors + r2_errors,
        "timings": {
            "round1_s": round(t2 - t1, 3),
            "round2_s": round(t3 - t2, 3),
            "round3_s": round(t4 - t3, 3),
            "total_s":  round(t4 - t_start, 3),
        },
    }


def run_trip_plan_orchestration(
    candidate: dict,
    weather_ctx: dict[str, Any],
    conditions: dict[str, Any],
) -> dict[str, Any]:
    """Run the 3-round trip-plan orchestration for a single candidate.

    Args:
        candidate: Single candidate property dict.
        weather_ctx: Output of get_weather_context().
        conditions: Output of get_all_conditions().

    Returns:
        Same shape as run_rerank_orchestration.

    Raises:
        OrchestrationError: ≥2 R1 failures or coordinator failure.
    """
    t_start = time.perf_counter()
    water_temp_c = compute_water_temp_estimate(weather_ctx, conditions["season"])
    candidates_list = [candidate]  # specialists expect list[dict]

    t1 = time.perf_counter()
    r1_outputs, r1_errors = _run_round1(
        candidates_list, conditions, weather_ctx, water_temp_c
    )
    t2 = time.perf_counter()
    _log.info("Round 1 complete in %.2fs", t2 - t1)

    r2_outputs, r2_errors = _run_round2(r1_outputs)
    t3 = time.perf_counter()
    _log.info("Round 2 complete in %.2fs", t3 - t2)

    specialist_outputs, peer_review_changes = _build_coordinator_inputs(
        r1_outputs, r2_outputs
    )

    # Coordinator trip-plan expects a single dict per specialist, not a list of one.
    specialist_outputs = {
        role: out[0] if isinstance(out, list) and len(out) == 1 else out
        for role, out in specialist_outputs.items()
    }

    try:
        coordinator_output = run_coordinator_trip_plan(
            candidate, conditions, weather_ctx, water_temp_c,
            specialist_outputs, peer_review_changes,
        )
    except Exception as exc:
        raise OrchestrationError(
            f"Coordinator (trip_plan) failed: {type(exc).__name__}: {exc}"
        ) from exc

    t4 = time.perf_counter()
    _log.info("Round 3 (coordinator) complete in %.2fs", t4 - t3)

    return {
        "coordinator_output": coordinator_output,
        "round1": r1_outputs,
        "round2": r2_outputs,
        "water_temp_c": water_temp_c,
        "errors": r1_errors + r2_errors,
        "timings": {
            "round1_s": round(t2 - t1, 3),
            "round2_s": round(t3 - t2, 3),
            "round3_s": round(t4 - t3, 3),
            "total_s":  round(t4 - t_start, 3),
        },
    }
