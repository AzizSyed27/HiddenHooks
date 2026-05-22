"""
Thin synchronous client for the Open-Meteo Forecast and Archive APIs.

Public surface:
    get_weather_context(lat, lon) -> dict
    WeatherAPIError                          (base; HTTP errors, bad shape)
    WeatherTimeoutError(WeatherAPIError)     (request timeout specifically)

Caller responsibility:
    - Catch WeatherTimeoutError and WeatherAPIError separately if needed;
      WeatherTimeoutError is a subclass of WeatherAPIError so a single
      `except WeatherAPIError` catches both.
    - Returned dict contains 'current', 'forecast_48h', and 'historical_7d' keys.
    - All numeric fields are float | None — the API returns JSON null for
      unmeasured values. Do NOT coerce None to 0.0; distinguish "no data"
      from "no precipitation."

Caching:
    - Two module-level dicts (_forecast_cache, _historical_cache) keyed on
      (round(lat, 2), round(lon, 2), date_str) where date_str is today's ISO date.
    - Forecast TTL: 3600 seconds (1 hour) — forecasts change; refresh hourly.
    - Historical TTL: 86400 seconds (24 hours) — ERA5 reanalysis does not
      change within a day; the 24h TTL is largely redundant with the
      date_str key component (which invalidates automatically at midnight)
      but is retained for correctness when the process runs across midnight.
    - Thread safety: plain dict is safe for single-process uvicorn. Add
      threading.Lock around each cache access before using under multi-process
      or multi-threaded concurrency.

Partial-success caching (intentional):
    - get_weather_context makes two API calls per cache miss: forecast first,
      then historical. Each is cached immediately on success.
    - If the historical call fails after the forecast call succeeds, the
      forecast result IS kept in _forecast_cache. The raised WeatherAPIError
      propagates to the caller, but a subsequent call for the same (lat, lon)
      on the same day will find the forecast cached and only retry historical.
    - Do NOT "fix" this by clearing the forecast cache on historical failure —
      that would force a redundant forecast re-fetch on every retry, burning
      API calls and adding latency for no benefit.

ERA5 archive lag:
    - Historical data is fetched via the forecast endpoint's `past_days=7`
      parameter (not via archive-api.open-meteo.com, which has unreliable
      connectivity). This returns ERA5 reanalysis, which has a ~5-day
      publication delay. Requesting past 7 days may return only 2–3 populated
      items; `historical_7d` length is variable (typically 2–7). Callers must
      not assume exactly 7 items.

Open-Meteo hourly array semantics:
    - With forecast_days=2 and timezone=America/Toronto, the hourly array
      starts at today 00:00 local time (not "current time + 48 hours").
    - forecast_48h always slices [:48] from this array — today + tomorrow,
      hour-by-hour, regardless of current wall-clock time.

Hygiene:
    - Open-Meteo requires no auth key; there is nothing to leak.
    - Request URLs are never included in exception messages (consistent with
      services/mapbox.py convention).
    - Response text in error messages is capped at 200 characters.
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (  # noqa: E402  (sys.path-insert pattern matches other backend modules)
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_HTTP_TIMEOUT_SECONDS,
)

_FORECAST_TTL_SECONDS: Final[int] = 3600    # 1 hour
_HISTORICAL_TTL_SECONDS: Final[int] = 86400 # 24 hours

# Cache stores (stored_at: float, payload: dict) tuples.
# Key: (round(lat, 2), round(lon, 2), date.today().isoformat())
# Rounding to 2 d.p. = ~1.1 km grid; prevents unbounded cache growth for
# nearly-identical coordinates (e.g. consecutive candidates in the same area).
_forecast_cache: dict[tuple[float, float, str], tuple[float, dict]] = {}
_historical_cache: dict[tuple[float, float, str], tuple[float, dict]] = {}


class WeatherAPIError(Exception):
    """HTTP error, invalid response shape, or misconfiguration."""


class WeatherTimeoutError(WeatherAPIError):
    """The Open-Meteo request did not return within the configured timeout."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _cache_key(lat: float, lon: float) -> tuple[float, float, str]:
    return (round(lat, 2), round(lon, 2), date.today().isoformat())


def _fetch_forecast(lat: float, lon: float) -> dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "America/Toronto",
        "forecast_days": 2,
        "current": (
            "temperature_2m,precipitation,windspeed_10m,cloudcover,"
            "weathercode,apparent_temperature,relative_humidity_2m"
        ),
        "hourly": "temperature_2m,precipitation,windspeed_10m,cloudcover",
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "windspeed_10m_max,sunrise,sunset"
        ),
    }
    try:
        response = requests.get(
            OPEN_METEO_FORECAST_URL, params=params, timeout=OPEN_METEO_HTTP_TIMEOUT_SECONDS
        )
    except requests.exceptions.Timeout as exc:
        raise WeatherTimeoutError(
            f"Open-Meteo forecast request timed out after {OPEN_METEO_HTTP_TIMEOUT_SECONDS}s"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise WeatherAPIError(f"Open-Meteo request failed: {type(exc).__name__}") from exc

    if response.status_code != 200:
        snippet = response.text[:200] if response.text else ""
        raise WeatherAPIError(f"Open-Meteo returned status {response.status_code}: {snippet}")

    try:
        return response.json()
    except ValueError as exc:
        raise WeatherAPIError("Open-Meteo forecast response was not valid JSON") from exc


def _fetch_historical(lat: float, lon: float) -> dict[str, Any]:
    # Uses the forecast endpoint's `past_days` parameter rather than the separate
    # archive-api.open-meteo.com domain. The archive subdomain has unreliable
    # connectivity; the main forecast domain is accessible and returns the same
    # ERA5 reanalysis data for past days. `forecast_days=1` is the minimum
    # accepted value; the extra today entry is filtered out in get_weather_context.
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "America/Toronto",
        "past_days": 7,
        "forecast_days": 1,
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max"
        ),
    }
    try:
        response = requests.get(
            OPEN_METEO_FORECAST_URL, params=params, timeout=OPEN_METEO_HTTP_TIMEOUT_SECONDS
        )
    except requests.exceptions.Timeout as exc:
        raise WeatherTimeoutError(
            f"Open-Meteo historical request timed out after {OPEN_METEO_HTTP_TIMEOUT_SECONDS}s"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise WeatherAPIError(f"Open-Meteo historical request failed: {type(exc).__name__}") from exc

    if response.status_code != 200:
        snippet = response.text[:200] if response.text else ""
        raise WeatherAPIError(f"Open-Meteo returned status {response.status_code}: {snippet}")

    try:
        return response.json()
    except ValueError as exc:
        raise WeatherAPIError("Open-Meteo historical response was not valid JSON") from exc


def _zip_hourly(hourly: dict[str, list]) -> list[dict[str, Any]]:
    """Zip Open-Meteo's parallel hourly arrays into a list of per-hour dicts."""
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    precips = hourly.get("precipitation", [])
    winds = hourly.get("windspeed_10m", [])
    clouds = hourly.get("cloudcover", [])
    result = []
    for i, t in enumerate(times):
        result.append({
            "hour": t,
            "temperature_c": temps[i] if i < len(temps) else None,
            "precipitation_mm": precips[i] if i < len(precips) else None,
            "windspeed_kmh": winds[i] if i < len(winds) else None,
            "cloudcover_pct": clouds[i] if i < len(clouds) else None,
        })
    return result


def _zip_daily(daily: dict[str, list]) -> list[dict[str, Any]]:
    """Zip Open-Meteo's parallel daily arrays into a list of per-day dicts."""
    times = daily.get("time", [])
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])
    precip_sum = daily.get("precipitation_sum", [])
    wind_max = daily.get("windspeed_10m_max", [])
    result = []
    for i, t in enumerate(times):
        result.append({
            "date": t,
            "temp_max_c": temp_max[i] if i < len(temp_max) else None,
            "temp_min_c": temp_min[i] if i < len(temp_min) else None,
            "precipitation_sum_mm": precip_sum[i] if i < len(precip_sum) else None,
            "windspeed_max_kmh": wind_max[i] if i < len(wind_max) else None,
        })
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_weather_context(lat: float, lon: float) -> dict[str, Any]:
    """Return current, 48-hour forecast, and 7-day historical weather for (lat, lon).

    Args:
        lat: Latitude in WGS84 decimal degrees.
        lon: Longitude in WGS84 decimal degrees.

    Returns:
        {
            "current": {
                "temperature_c": float | None,
                "apparent_temperature_c": float | None,
                "humidity_pct": float | None,
                "precipitation_mm": float | None,
                "windspeed_kmh": float | None,
                "cloudcover_pct": float | None,
                "weathercode": int | None,    # WMO weather interpretation code
            },
            "forecast_48h": [
                # Up to 48 items; starts at today 00:00 America/Toronto,
                # not "now + 48 hours."
                {
                    "hour": str,              # ISO e.g. "2026-05-22T14:00"
                    "temperature_c": float | None,
                    "precipitation_mm": float | None,
                    "windspeed_kmh": float | None,
                    "cloudcover_pct": float | None,
                },
                ...
            ],
            "historical_7d": [
                # Typically 2–7 items due to ERA5 ~5-day publication lag.
                # DO NOT assume exactly 7 items.
                {
                    "date": str,              # ISO e.g. "2026-05-15"
                    "temp_max_c": float | None,
                    "temp_min_c": float | None,
                    "precipitation_sum_mm": float | None,
                    "windspeed_max_kmh": float | None,
                },
                ...
            ],
        }

    Raises:
        WeatherTimeoutError: Either API request did not complete within
                             OPEN_METEO_HTTP_TIMEOUT_SECONDS.
        WeatherAPIError: HTTP non-200, malformed JSON, or missing required
                         response structure. Both API calls must succeed;
                         if historical fails after forecast succeeded, the
                         forecast result remains in cache and WeatherAPIError
                         is raised (see module docstring: "Partial-success
                         caching").
    """
    key = _cache_key(lat, lon)
    now = time.time()

    # --- Forecast cache check ---
    cached = _forecast_cache.get(key)
    if cached is not None and now - cached[0] < _FORECAST_TTL_SECONDS:
        forecast_payload = cached[1]
    else:
        forecast_payload = _fetch_forecast(lat, lon)
        _forecast_cache[key] = (time.time(), forecast_payload)

    # --- Historical cache check ---
    cached = _historical_cache.get(key)
    if cached is not None and now - cached[0] < _HISTORICAL_TTL_SECONDS:
        historical_payload = cached[1]
    else:
        # Historical failure propagates; forecast cache is intentionally kept.
        historical_payload = _fetch_historical(lat, lon)
        _historical_cache[key] = (time.time(), historical_payload)

    # --- Validate and transform ---
    current_raw = forecast_payload.get("current")
    if not isinstance(current_raw, dict):
        raise WeatherAPIError("Open-Meteo forecast response missing 'current' block")

    hourly_raw = forecast_payload.get("hourly")
    if not isinstance(hourly_raw, dict):
        raise WeatherAPIError("Open-Meteo forecast response missing 'hourly' block")

    daily_raw = historical_payload.get("daily")
    if not isinstance(daily_raw, dict):
        raise WeatherAPIError("Open-Meteo historical response missing 'daily' block")

    current = {
        "temperature_c": current_raw.get("temperature_2m"),
        "apparent_temperature_c": current_raw.get("apparent_temperature"),
        "humidity_pct": current_raw.get("relative_humidity_2m"),
        "precipitation_mm": current_raw.get("precipitation"),
        "windspeed_kmh": current_raw.get("windspeed_10m"),
        "cloudcover_pct": current_raw.get("cloudcover"),
        "weathercode": current_raw.get("weathercode"),
    }

    # Filter historical daily to past entries only: _fetch_historical uses
    # forecast_days=1 (the API minimum), which adds today's entry to the daily
    # array. Exclude today so historical_7d contains only completed past days.
    today_str = date.today().isoformat()
    historical_7d = [d for d in _zip_daily(daily_raw) if d["date"] < today_str]

    return {
        "current": current,
        "forecast_48h": _zip_hourly(hourly_raw)[:48],
        "historical_7d": historical_7d,
    }
