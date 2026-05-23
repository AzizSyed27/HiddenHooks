"""
Pure-stdlib utility functions for classifying a local date-time into discrete
categories used by the Phase 5 multi-agent reasoning layer.

Public surface:
    get_day_category(dt=None)   -> str    'weekday' | 'saturday' | 'sunday'
    get_season(dt=None)         -> str    'spring' | 'summer' | 'fall' | 'winter'
    get_time_of_day(dt=None)    -> str    'dawn' | 'morning' | 'midday' |
                                          'evening' | 'dusk' | 'night'
    get_all_conditions(dt=None) -> dict   all three plus the resolved datetime

Naive datetime contract (all four functions):
    Naive datetimes are treated as already in America/Toronto local time; their
    tzinfo is attached without conversion. Convert UTC inputs to Toronto local
    before passing — e.g. dt.astimezone(ZoneInfo("America/Toronto")).

No external dependencies — zoneinfo is stdlib (Python 3.9+).

Time-of-day boundary note:
    Boundaries are fishing-context-aligned with Ontario seasonal light patterns,
    not office hours. See CLAUDE.md: "Phase 5 Part 2 time-of-day boundaries
    deviate from the checklist by design."
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

_TORONTO_TZ: Final = ZoneInfo("America/Toronto")

# ── Season boundaries (month, day) ──────────────────────────────────────────
# Approximate astronomical season starts. Exact equinox/solstice dates shift
# ±1 day by year; fixed values are accurate enough for LLM condition analysis.
_SPRING_START: Final = (3, 20)   # ~March equinox
_SUMMER_START: Final = (6, 21)   # ~June solstice
_FALL_START:   Final = (9, 23)   # ~September equinox
_WINTER_START: Final = (12, 21)  # ~December solstice

# ── Time-of-day boundaries (start_hour, start_minute, label) ────────────────
# Checked in ascending order; default label is 'night' (covers 21:00–04:59
# including the midnight wrap). Each entry is the inclusive start of that window.
_TIME_BOUNDARIES: Final = (
    ( 5, 0, "dawn"),     # 05:00–06:59
    ( 7, 0, "morning"),  # 07:00–11:59
    (12, 0, "midday"),   # 12:00–15:59
    (16, 0, "evening"),  # 16:00–17:59
    (18, 0, "dusk"),     # 18:00–20:59
    (21, 0, "night"),    # 21:00–04:59
)


def _as_toronto(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(tz=_TORONTO_TZ)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_TORONTO_TZ)
    return dt.astimezone(_TORONTO_TZ)


def get_day_category(dt: datetime | None = None) -> str:
    """Return the day-of-week category for dt.

    Returns:
        'weekday'  — Monday through Friday
        'saturday' — Saturday
        'sunday'   — Sunday

    Args:
        dt: Datetime to classify. When None, uses current America/Toronto time.
            Naive datetimes are treated as already in America/Toronto local time;
            convert UTC inputs to Toronto local before passing.
    """
    local = _as_toronto(dt)
    weekday = local.weekday()  # 0=Monday … 6=Sunday
    if weekday == 5:
        return "saturday"
    if weekday == 6:
        return "sunday"
    return "weekday"


def get_season(dt: datetime | None = None) -> str:
    """Return the astronomical season for dt.

    Returns:
        'spring'  — March 20 – June 20
        'summer'  — June 21 – September 22
        'fall'    — September 23 – December 20
        'winter'  — December 21 – March 19  (wraps the calendar year)

    Args:
        dt: Datetime to classify. When None, uses current America/Toronto time.
            Naive datetimes are treated as already in America/Toronto local time;
            convert UTC inputs to Toronto local before passing.
    """
    local = _as_toronto(dt)
    md = (local.month, local.day)
    if _SPRING_START <= md < _SUMMER_START:
        return "spring"
    if _SUMMER_START <= md < _FALL_START:
        return "summer"
    if _FALL_START <= md < _WINTER_START:
        return "fall"
    return "winter"


def get_time_of_day(dt: datetime | None = None) -> str:
    """Return the time-of-day category for dt.

    Boundaries are aligned with Ontario fishing light conditions, not office hours.
    Dawn and dusk bracket the productive low-light periods; midday captures the
    characteristically slow mid-afternoon window.

    Returns:
        'dawn'    — 05:00–06:59
        'morning' — 07:00–11:59
        'midday'  — 12:00–15:59
        'evening' — 16:00–17:59
        'dusk'    — 18:00–20:59
        'night'   — 21:00–04:59

    Args:
        dt: Datetime to classify. When None, uses current America/Toronto time.
            Naive datetimes are treated as already in America/Toronto local time;
            convert UTC inputs to Toronto local before passing.
    """
    local = _as_toronto(dt)
    hm = (local.hour, local.minute)
    label = "night"  # default: covers 21:00–04:59 including midnight wrap
    for start_h, start_m, category in _TIME_BOUNDARIES:
        if hm >= (start_h, start_m):
            label = category
    return label


def get_all_conditions(dt: datetime | None = None) -> dict[str, Any]:
    """Return all condition categories plus the resolved Toronto-aware datetime.

    Resolves dt once and passes the resulting aware datetime to each classifier,
    so all four values are consistent even when dt=None (no mid-call clock drift).

    Returns:
        {
            "day_category":     str       # 'weekday' | 'saturday' | 'sunday'
            "season":           str       # 'spring' | 'summer' | 'fall' | 'winter'
            "time_of_day":      str       # 'dawn' | 'morning' | 'midday' |
                                          #  'evening' | 'dusk' | 'night'
            "datetime_toronto": datetime  # aware datetime in America/Toronto
        }

    Args:
        dt: Datetime to classify. When None, uses current America/Toronto time.
            Naive datetimes are treated as already in America/Toronto local time;
            convert UTC inputs to Toronto local before passing.
    """
    local = _as_toronto(dt)
    return {
        "day_category":     get_day_category(local),
        "season":           get_season(local),
        "time_of_day":      get_time_of_day(local),
        "datetime_toronto": local,
    }
