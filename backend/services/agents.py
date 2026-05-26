"""
Agent runner functions for the Phase 5 multi-agent reasoning layer.

Each function:
1. Loads the appropriate prompt(s) via services/prompts.load_prompt
2. Serializes input data as JSON for the user message
3. Calls call_claude and returns the parsed result

Callers (the orchestrator in api/) are responsible for:
- Fetching weather_ctx via services/weather.get_weather_context
- Computing conditions via services/conditions.get_all_conditions
- Computing water_temp_c via services/weather.compute_water_temp_estimate
- Passing peer_outputs with real agent name keys (not placeholders)

Public surface:
    run_weather_agent(candidates, conditions, weather_ctx)               -> list[dict]
    run_timing_agent(candidates, conditions)                             -> list[dict]
    run_species_agent(candidates, conditions, weather_ctx, water_temp_c) -> list[dict]
    run_peer_review(agent_role, round1_output, peer_outputs)             -> dict
    run_coordinator_rerank(candidates, conditions, water_temp_c,
                           specialist_outputs, peer_review_changes)      -> dict
    run_coordinator_trip_plan(candidate, conditions, weather_ctx,
                              water_temp_c, specialist_outputs,
                              peer_review_changes)                       -> dict
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from services.anthropic_client import call_claude
from services.prompts import load_prompt


def _serialize_conditions(conditions: dict[str, Any]) -> dict[str, Any]:
    """Convert datetime_toronto to ISO string for JSON serialization."""
    result = dict(conditions)
    dt = result.get("datetime_toronto")
    if isinstance(dt, datetime):
        result["datetime_toronto"] = dt.isoformat()
    return result


def run_weather_agent(
    candidates: list[dict],
    conditions: dict[str, Any],
    weather_ctx: dict[str, Any],
) -> list[dict]:
    """Run the Weather Specialist agent (Round 1).

    Args:
        candidates: List of candidate dicts with h_score, a_score, f_score, e_score,
                    candidate_type, fmz_zone, name.
        conditions: Output of get_all_conditions() — day_category, season,
                    time_of_day, datetime_toronto.
        weather_ctx: Output of get_weather_context() — current, forecast_48h,
                     historical_7d.

    Returns:
        List of weather assessment dicts, one per candidate.
    """
    system_prompt = load_prompt("weather_agent")
    user_message = json.dumps(
        {
            "conditions": _serialize_conditions(conditions),
            "weather": weather_ctx,
            "candidates": candidates,
        },
        indent=2,
    )
    return call_claude(system_prompt, user_message, max_tokens=8192)


def run_timing_agent(
    candidates: list[dict],
    conditions: dict[str, Any],
) -> list[dict]:
    """Run the Timing/Pressure Specialist agent (Round 1).

    Args:
        candidates: List of candidate dicts with h_score, a_score, f_score, e_score,
                    candidate_type, fmz_zone, name.
        conditions: Output of get_all_conditions().

    Returns:
        List of timing assessment dicts, one per candidate.
    """
    system_prompt = load_prompt("timing_agent")
    user_message = json.dumps(
        {
            "conditions": _serialize_conditions(conditions),
            "candidates": candidates,
        },
        indent=2,
    )
    return call_claude(system_prompt, user_message, max_tokens=8192)


def run_species_agent(
    candidates: list[dict],
    conditions: dict[str, Any],
    weather_ctx: dict[str, Any],
    water_temp_c: float | None,
) -> list[dict]:
    """Run the Species Specialist agent (Round 1).

    Args:
        candidates: List of candidate dicts including f_species, f_confidence, f_tier.
        conditions: Output of get_all_conditions().
        weather_ctx: Output of get_weather_context() (used for precipitation/clarity).
        water_temp_c: Output of compute_water_temp_estimate() — pass None if unavailable.

    Returns:
        List of species assessment dicts, one per candidate.
    """
    system_prompt = load_prompt("species_agent")
    user_message = json.dumps(
        {
            "conditions": _serialize_conditions(conditions),
            "water_temp_estimate_c": water_temp_c,
            "weather": weather_ctx,
            "candidates": candidates,
        },
        indent=2,
    )
    return call_claude(system_prompt, user_message, max_tokens=8192)


def run_peer_review(
    agent_role: str,
    round1_output: list[dict],
    peer_outputs: dict[str, list[dict]],
) -> dict:
    """Run Round 2 peer review for one specialist.

    The system prompt is the specialist's own prompt with peer_review.md appended.
    The user message includes the agent's Round 1 output and the peer outputs keyed
    by agent name. The orchestrator must pass real agent names as keys in peer_outputs
    (e.g. {"weather_agent": [...], "species_agent": [...]}).

    Args:
        agent_role: 'weather_agent', 'timing_agent', or 'species_agent'.
        round1_output: This agent's Round 1 output array.
        peer_outputs: Dict of {agent_name: round1_output} for the other two agents.

    Returns:
        Dict with 'critique_of_peers', 'my_revised_position', 'what_changed_from_round_1'.
    """
    system_prompt = load_prompt(agent_role) + "\n\n---\n\n" + load_prompt("peer_review")
    user_message = json.dumps(
        {
            "your_round1_output": round1_output,
            "peer_outputs": peer_outputs,
        },
        indent=2,
    )
    return call_claude(system_prompt, user_message, max_tokens=8192)


def run_coordinator_rerank(
    candidates: list[dict],
    conditions: dict[str, Any],
    water_temp_c: float | None,
    specialist_outputs: dict[str, list[dict]],
    peer_review_changes: list[dict],
) -> dict:
    """Run the Coordinator agent in re-rank mode.

    Args:
        candidates: List of candidate dicts with Phase 2 scores.
        conditions: Output of get_all_conditions().
        water_temp_c: Output of compute_water_temp_estimate().
        specialist_outputs: Dict of {agent_name: revised_round2_output} for all three
                            specialists (after peer review).
        peer_review_changes: Aggregated list of what_changed_from_round_1 entries
                             from all three specialists.

    Returns:
        Dict with 'weighting', 'ranked_candidates', 'synthesis_note'.
    """
    system_prompt = load_prompt("coordinator_rerank")
    user_message = json.dumps(
        {
            "conditions": _serialize_conditions(conditions),
            "water_temp_estimate_c": water_temp_c,
            "candidates": candidates,
            "specialist_outputs": specialist_outputs,
            "peer_review_changes": peer_review_changes,
        },
        indent=2,
    )
    return call_claude(system_prompt, user_message)


def run_coordinator_trip_plan(
    candidate: dict,
    conditions: dict[str, Any],
    weather_ctx: dict[str, Any],
    water_temp_c: float | None,
    specialist_outputs: dict[str, Any],
    peer_review_changes: list[dict],
) -> dict:
    """Run the Coordinator agent in trip-plan mode (single locked candidate).

    Args:
        candidate: Single candidate dict with Phase 2 scores and species data.
        conditions: Output of get_all_conditions().
        weather_ctx: Output of get_weather_context().
        water_temp_c: Output of compute_water_temp_estimate().
        specialist_outputs: Dict of {agent_name: revised_round2_output} for all three
                            specialists, each filtered to the single candidate.
        peer_review_changes: What changed from Round 1, filtered to this candidate.

    Returns:
        Dict with 'overall_call', 'best_window', 'expected_species',
        'conditions_summary', 'things_to_watch', 'key_risks', 'confidence'.
    """
    system_prompt = load_prompt("coordinator_trip_plan")
    user_message = json.dumps(
        {
            "candidate": candidate,
            "conditions": _serialize_conditions(conditions),
            "weather": weather_ctx,
            "water_temp_estimate_c": water_temp_c,
            "specialist_outputs": specialist_outputs,
            "peer_review_changes": peer_review_changes,
        },
        indent=2,
    )
    return call_claude(system_prompt, user_message)
