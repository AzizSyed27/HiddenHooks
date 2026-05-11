"""
Thin synchronous client for the Mapbox Isochrones API.

Public surface:
    get_drive_isochrone(lat, lon, minutes) -> Polygon | MultiPolygon
    MapboxAPIError                          (base; HTTP errors, bad shape)
    MapboxTimeoutError(MapboxAPIError)      (request timeout specifically)

Caller responsibility:
    - Catch MapboxTimeoutError and MapboxAPIError separately if needed;
      MapboxTimeoutError is a subclass of MapboxAPIError so a single
      `except MapboxAPIError` catches both.
    - The returned polygon is in EPSG:4326. Reproject in SQL via
      ST_Transform(..., 3161) when filtering against the candidates table.

Hygiene:
    - The API key is never included in exception messages.
    - No URL containing the token is ever stringified into an error.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

import requests
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (  # noqa: E402  (sys.path-insert pattern matches other backend modules)
    MAPBOX_API_KEY,
    MAPBOX_HTTP_TIMEOUT_SECONDS,
    MAPBOX_ISOCHRONE_URL,
)

_MIN_MINUTES: Final[int] = 1
_MAX_MINUTES: Final[int] = 60


class MapboxAPIError(Exception):
    """HTTP error, invalid response shape, or misconfiguration. Never carries the API key."""


class MapboxTimeoutError(MapboxAPIError):
    """The Mapbox request did not return within the configured timeout."""


def get_drive_isochrone(lat: float, lon: float, minutes: int) -> Polygon | MultiPolygon:
    """Return the drive-time isochrone polygon for (lat, lon, minutes) in EPSG:4326.

    Args:
        lat: Latitude in EPSG:4326 (decimal degrees).
        lon: Longitude in EPSG:4326 (decimal degrees).
        minutes: Drive time in minutes, 1..60 inclusive (Mapbox per-contour cap).

    Returns:
        A Shapely Polygon or MultiPolygon in EPSG:4326.

    Raises:
        MapboxTimeoutError: Request did not complete within MAPBOX_HTTP_TIMEOUT_SECONDS.
        MapboxAPIError: Misconfiguration (no API key), input out of range, HTTP non-200,
                        malformed JSON, missing/empty features, or unexpected geometry type.
    """
    if not MAPBOX_API_KEY:
        raise MapboxAPIError("MAPBOX_API_KEY environment variable is not set")
    if not (_MIN_MINUTES <= minutes <= _MAX_MINUTES):
        raise MapboxAPIError(
            f"minutes must be between {_MIN_MINUTES} and {_MAX_MINUTES}; got {minutes}"
        )

    url = f"{MAPBOX_ISOCHRONE_URL}/{lon},{lat}"
    params = {
        "contours_minutes": minutes,
        "polygons": "true",
        "access_token": MAPBOX_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=MAPBOX_HTTP_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout as exc:
        raise MapboxTimeoutError(
            f"Mapbox isochrone request timed out after {MAPBOX_HTTP_TIMEOUT_SECONDS}s"
        ) from exc
    except requests.exceptions.RequestException as exc:
        # str(exc) can include the request URL with params; only the class name is safe.
        raise MapboxAPIError(f"Mapbox request failed: {type(exc).__name__}") from exc

    if response.status_code != 200:
        snippet = response.text[:200] if response.text else ""
        raise MapboxAPIError(
            f"Mapbox returned status {response.status_code}: {snippet}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise MapboxAPIError("Mapbox response was not valid JSON") from exc

    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise MapboxAPIError("Mapbox response missing or empty 'features'")

    geometry_dict = features[0].get("geometry")
    if not geometry_dict:
        raise MapboxAPIError("Mapbox response missing 'geometry'")

    try:
        geom: BaseGeometry = shape(geometry_dict)
    except (ValueError, KeyError, TypeError) as exc:
        raise MapboxAPIError(f"Could not parse Mapbox geometry: {exc}") from exc

    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise MapboxAPIError(f"Unexpected geometry type from Mapbox: {geom.geom_type}")
    if geom.is_empty:
        raise MapboxAPIError("Mapbox returned an empty polygon")

    return geom
