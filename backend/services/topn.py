"""
Top-N candidate selection for the Phase 5 agent orchestration layer.

Public surface:
    select_top_n(candidates, mode='composite', n=30, max_n=50) -> list[dict]

Modes:
    'composite' — preserve the sort order from /candidates (already ranked by
                  weighted composite score); simple head-slice.
    'f_score'   — re-sort by f_score descending before slicing; None sorts last.
"""

from __future__ import annotations


def select_top_n(
    candidates: list[dict],
    mode: str = "composite",
    n: int = 30,
    max_n: int = 50,
) -> list[dict]:
    """Return the top N candidates from the filtered list.

    Args:
        candidates: Flat candidate property dicts from /candidates (already sorted
                    by composite descending when mode='composite').
        mode: 'composite' (preserve existing order) or 'f_score' (re-sort by
              f_score descending, None last).
        n: Candidates to return. Silently capped at max_n.
        max_n: Hard cap on n (default 50).

    Returns:
        Slice of up to min(n, max_n, len(candidates)) dicts.

    Raises:
        ValueError: If mode is not 'composite' or 'f_score'.
    """
    if mode not in {"composite", "f_score"}:
        raise ValueError(f"Unknown mode {mode!r}; expected 'composite' or 'f_score'")

    n = min(n, max_n)

    if mode == "f_score":
        candidates = sorted(
            candidates,
            key=lambda c: c.get("f_score") if c.get("f_score") is not None else -1.0,
            reverse=True,
        )

    return candidates[:n]
