"""
Thin synchronous client for the Mapbox Isochrones and Directions APIs.

Public surface:
    get_drive_isochrone(lat, lon, minutes) -> Polygon | MultiPolygon
    get_drive_directions(start_lat, start_lon, end_lat, end_lon) -> dict
    MapboxAPIError                          (base; HTTP errors, bad shape)
    MapboxTimeoutError(MapboxAPIError)      (request timeout specifically)

Caller responsibility:
    - Catch MapboxTimeoutError and MapboxAPIError separately if needed;
      MapboxTimeoutError is a subclass of MapboxAPIError so a single
      `except MapboxAPIError` catches both.
    - Returned geometries are in EPSG:4326. Reproject as needed before
      using against the EPSG:3161 candidates table.

Hygiene:
    - The API key is never included in exception messages.
    - No URL containing the token is ever stringified into an error.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Final

import requests
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (  # noqa: E402  (sys.path-insert pattern matches other backend modules)
    MAPBOX_API_KEY,
    MAPBOX_DIRECTIONS_URL,
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


def get_drive_directions(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> dict[str, Any]:
    """Return the Mapbox driving route between two WGS84 points.

    Args:
        start_lat, start_lon: Origin in EPSG:4326 (decimal degrees).
        end_lat, end_lon: Destination in EPSG:4326.

    Returns:
        {
            "duration_minutes": float,
            "distance_km":      float,
            "geometry":         dict,  # GeoJSON LineString in EPSG:4326
        }

    Raises:
        MapboxTimeoutError: Request did not complete within MAPBOX_HTTP_TIMEOUT_SECONDS.
        MapboxAPIError: Misconfiguration (no API key), HTTP non-200, malformed
                        JSON, non-Ok routing code, missing/empty `routes`, or
                        missing/non-LineString `geometry`.
    """
    if not MAPBOX_API_KEY:
        raise MapboxAPIError("MAPBOX_API_KEY environment variable is not set")

    url = f"{MAPBOX_DIRECTIONS_URL}/{start_lon},{start_lat};{end_lon},{end_lat}"
    params = {
        "geometries": "geojson",
        "overview": "full",
        "access_token": MAPBOX_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=MAPBOX_HTTP_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout as exc:
        raise MapboxTimeoutError(
            f"Mapbox directions request timed out after {MAPBOX_HTTP_TIMEOUT_SECONDS}s"
        ) from exc
    except requests.exceptions.RequestException as exc:
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

    code = payload.get("code")
    if code != "Ok":
        raise MapboxAPIError(f"Mapbox routing code: {code}")

    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise MapboxAPIError("Mapbox response missing 'routes'")

    route = routes[0]
    geometry = route.get("geometry")
    if not geometry or geometry.get("type") != "LineString":
        raise MapboxAPIError("Mapbox response missing or non-LineString route geometry")

    duration_s = route.get("duration")
    distance_m = route.get("distance")
    if duration_s is None or distance_m is None:
        raise MapboxAPIError("Mapbox response missing route duration or distance")

    return {
        "duration_minutes": float(duration_s) / 60.0,
        "distance_km": float(distance_m) / 1000.0,
        "geometry": geometry,
    }
