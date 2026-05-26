from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import MultiPolygon, Polygon, mapping
from sqlalchemy import bindparam, create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY, DATABASE_URL, MAPBOX_API_KEY
from services.conditions import get_all_conditions
from services.mapbox import (
    MapboxAPIError,
    MapboxTimeoutError,
    get_drive_directions,
    get_drive_isochrone,
)
from services.orchestrator import (
    OrchestrationError,
    run_rerank_orchestration,
    run_trip_plan_orchestration,
)
from services.topn import select_top_n
from services.weather import WeatherAPIError, WeatherTimeoutError, get_weather_context

_log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MAPBOX_API_KEY:
        raise RuntimeError(
            "MAPBOX_API_KEY is missing from environment. "
            "Set it in backend/.env before starting the API."
        )
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing from environment. "
            "Set it in backend/.env before starting the API."
        )
    yield


app = FastAPI(title="HiddenHooks API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
engine = create_engine(DATABASE_URL)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CandidateProperties(BaseModel):
    id: int
    name: str | None
    candidate_type: str
    source_dataset: str
    fmz_zone: str
    dist_to_road_meters: float | None
    area_m2: float | None
    length_m: float | None
    h_score: float | None
    a_score: float | None
    f_score: float | None
    e_score: float | None
    f_confidence: str | None
    f_species: str | None
    a_dist_to_trail_m: float | None
    a_dist_to_parking_m: float | None
    composite: float
    rank: int
    fmz_total: int  # total active candidates in this FMZ, regardless of response limit


class CandidateFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: CandidateProperties


class CandidateFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[CandidateFeature]
    total_count: int  # total matching active candidates pre-LIMIT; compare with len(features) to detect truncation
    isochrone_polygon: dict[str, Any] | None = None  # GeoJSON Polygon/MultiPolygon in EPSG:4326; null when drive_time_min not set


class HealthResponse(BaseModel):
    status: str


class RegionInfo(BaseModel):
    fmz_zone: str
    candidate_count: int


class RegionsResponse(BaseModel):
    regions: list[RegionInfo]


class DriveTimeResponse(BaseModel):
    drive_time_min: float | None
    drive_distance_km: float | None
    route_geometry: dict[str, Any] | None  # GeoJSON LineString, EPSG:4326
    parking_lat: float | None
    parking_lon: float | None
    error: str | None


class RerankRequest(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=200)
    near_lat: float = Field(ge=41.0, le=50.0)
    near_lon: float = Field(ge=-85.0, le=-74.0)
    top_n_mode: Literal["composite", "f_score"] = "composite"
    top_n: int = Field(default=30, ge=5, le=50)

    @field_validator("candidate_ids")
    @classmethod
    def must_be_unique(cls, v: list[int]) -> list[int]:
        if len(v) != len(set(v)):
            raise ValueError("candidate_ids must contain unique values")
        return v


class RerankedCandidate(BaseModel):
    candidate_id: int
    rank: int
    composite_call: float
    one_line_why: str
    specialist_agreement: Literal["high", "medium", "low"]


class RerankResponse(BaseModel):
    request_id: str
    ranked_candidates: list[RerankedCandidate]
    weighting: dict[str, Any]
    current_conditions: str         # handler-derived label: "Spring, Saturday, Dawn"
    synthesis_note: str | None
    specialist_metadata: dict[str, Any] | None = None


class TripPlanRequest(BaseModel):
    candidate_id: int
    near_lat: float = Field(ge=41.0, le=50.0)
    near_lon: float = Field(ge=-85.0, le=-74.0)


class TripPlanResponse(BaseModel):
    request_id: str
    candidate_id: int
    overall_call: Literal["go now", "good window coming", "wait", "skip"]
    best_window: str
    expected_species: list[dict[str, Any]]
    conditions_summary: str         # coordinator-generated 2-3 sentence synthesis
    things_to_watch: list[str]
    key_risks: list[str]
    confidence: Literal["high", "medium", "low"]
    specialist_metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

# {fmz_filter} and {isochrone_filter} are filled at call time. Both placeholders are
# hardcoded in Python — never from user input — so str.format() is safe.
_CANDIDATES_SQL_TEMPLATE = """
WITH scored AS (
    SELECT
        id,
        name,
        candidate_type::text                                                  AS candidate_type,
        source_dataset::text                                                  AS source_dataset,
        fmz_zone,
        dist_to_road_meters,
        area_m2,
        length_m,
        h_score,
        a_score,
        f_score,
        e_score,
        f_confidence,
        f_species,
        a_dist_to_trail_m,
        a_dist_to_parking_m,
        COALESCE(:w_h * h_score, 0)
          + COALESCE(:w_a * a_score, 0)
          + COALESCE(:w_f * f_score, 0)
          + COALESCE(:w_e * e_score, 0)                                       AS composite,
        ST_AsGeoJSON(ST_Transform(geom, 4326))                                AS geometry_json
    FROM candidates
    WHERE is_active = TRUE
      AND geom IS NOT NULL
      {fmz_filter}
      {isochrone_filter}
),
total AS (
    SELECT COUNT(*) AS n FROM scored
),
ranked AS (
    SELECT *,
        RANK() OVER (PARTITION BY fmz_zone ORDER BY composite DESC NULLS LAST) AS rank,
        COUNT(*) OVER (PARTITION BY fmz_zone)                                  AS fmz_total
    FROM scored
)
SELECT r.*, t.n AS total_available
FROM ranked r, total t
ORDER BY composite DESC NULLS LAST, id
LIMIT :limit
"""

_REGIONS_SQL = text("""
    SELECT fmz_zone, COUNT(*) AS candidate_count
    FROM candidates
    WHERE is_active = TRUE
    GROUP BY fmz_zone
    ORDER BY fmz_zone
""")

# Existence + nearest-parking in one LATERAL JOIN round-trip.
# Three observable outcomes from the same row set:
#   - 0 rows: candidate missing or inactive -> 404
#   - 1 row, parking_id IS NULL: parking table empty for this candidate -> graceful no-parking
#   - 1 row, parking_id non-null: happy path, call Mapbox
_NEAREST_PARKING_SQL = text("""
    SELECT
        p.id                                          AS parking_id,
        ST_Y(ST_Transform(ST_Centroid(p.geom), 4326)) AS parking_lat,
        ST_X(ST_Transform(ST_Centroid(p.geom), 4326)) AS parking_lon
    FROM candidates c
    LEFT JOIN LATERAL (
        SELECT id, geom
        FROM parking
        ORDER BY parking.geom <-> c.geom
        LIMIT 1
    ) p ON true
    WHERE c.id = :candidate_id AND c.is_active = TRUE
""")


# Columns the agent layer needs. id aliased to candidate_id so agent output
# keys match input keys. f_tier is derived from f_confidence — not a DB column.
# Omits source_dataset, dist_to_road_meters, area_m2, length_m,
# a_dist_to_trail_m, a_dist_to_parking_m — not referenced by any agent prompt.
_AGENT_CANDIDATES_SELECT = """
    SELECT
        id                              AS candidate_id,
        name,
        candidate_type::text            AS candidate_type,
        fmz_zone,
        h_score,
        a_score,
        f_score,
        e_score,
        f_species,
        f_confidence,
        CASE f_confidence
            WHEN 'strong'      THEN 1
            WHEN 'plausible'   THEN 2
            WHEN 'speculative' THEN 3
            ELSE NULL
        END                             AS f_tier
    FROM candidates
"""

_FETCH_CANDIDATES_BY_IDS_SQL = text(
    f"{_AGENT_CANDIDATES_SELECT} WHERE id IN :ids AND is_active = TRUE"
).bindparams(bindparam("ids", expanding=True))

_FETCH_CANDIDATE_SQL = text(
    f"{_AGENT_CANDIDATES_SELECT} WHERE id = :candidate_id AND is_active = TRUE"
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/regions", response_model=RegionsResponse)
def get_regions() -> RegionsResponse:
    with engine.connect() as conn:
        rows = conn.execute(_REGIONS_SQL).mappings().all()
    return RegionsResponse(
        regions=[
            RegionInfo(fmz_zone=row["fmz_zone"], candidate_count=row["candidate_count"])
            for row in rows
        ]
    )


@app.get("/candidates", response_model=CandidateFeatureCollection)
def get_candidates(
    w_h: float = Query(default=0.25, ge=0.0),
    w_a: float = Query(default=0.25, ge=0.0),
    w_f: float = Query(default=0.25, ge=0.0),
    w_e: float = Query(default=0.25, ge=0.0),
    fmz: str | None = Query(default=None, pattern="^FMZ1[67]$"),
    limit: int = Query(default=2000, ge=1, le=10000),
    near_lat: float | None = Query(default=None, ge=41.0, le=50.0),
    near_lon: float | None = Query(default=None, ge=-85.0, le=-74.0),
    drive_time_min: int | None = Query(default=None, ge=1, le=60),
) -> CandidateFeatureCollection:
    weight_sum = w_h + w_a + w_f + w_e
    if weight_sum <= 0:
        raise HTTPException(status_code=422, detail="At least one weight must be > 0")
    w_h, w_a, w_f, w_e = w_h / weight_sum, w_a / weight_sum, w_f / weight_sum, w_e / weight_sum

    has_loc = (near_lat is not None) or (near_lon is not None)
    if has_loc and (near_lat is None or near_lon is None):
        raise HTTPException(status_code=422, detail="near_lat and near_lon must both be provided together")
    if has_loc and drive_time_min is None:
        raise HTTPException(status_code=422, detail="drive_time_min is required when near_lat/near_lon are set")
    if drive_time_min is not None and not has_loc:
        raise HTTPException(status_code=422, detail="drive_time_min requires near_lat and near_lon")

    isochrone_polygon: Polygon | MultiPolygon | None = None
    isochrone_wkt: str | None = None
    if has_loc and drive_time_min is not None:
        assert near_lat is not None and near_lon is not None  # narrowed by has_loc check above
        try:
            isochrone_polygon = get_drive_isochrone(near_lat, near_lon, drive_time_min)
        except MapboxTimeoutError:
            raise HTTPException(status_code=503, detail="Drive-time service timed out")
        except MapboxAPIError as exc:
            raise HTTPException(status_code=503, detail=f"Drive-time service unavailable: {exc}")
        isochrone_wkt = isochrone_polygon.wkt

    fmz_filter = "AND fmz_zone = :fmz" if fmz else ""
    isochrone_filter = (
        "AND ST_Within(geom, ST_Transform(ST_GeomFromText(:isochrone_wkt, 4326), 3161))"
        if isochrone_wkt is not None else ""
    )
    sql = text(_CANDIDATES_SQL_TEMPLATE.format(
        fmz_filter=fmz_filter,
        isochrone_filter=isochrone_filter,
    ))

    params: dict[str, Any] = {
        "w_h": w_h, "w_a": w_a, "w_f": w_f, "w_e": w_e,
        "limit": limit,
    }
    if fmz:
        params["fmz"] = fmz
    if isochrone_wkt is not None:
        params["isochrone_wkt"] = isochrone_wkt

    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()

    total_count = int(rows[0]["total_available"]) if rows else 0

    features = [
        CandidateFeature(
            geometry=json.loads(row["geometry_json"]),
            properties=CandidateProperties(
                id=row["id"],
                name=row["name"],
                candidate_type=row["candidate_type"],
                source_dataset=row["source_dataset"],
                fmz_zone=row["fmz_zone"],
                dist_to_road_meters=row["dist_to_road_meters"],
                area_m2=row["area_m2"],
                length_m=row["length_m"],
                h_score=row["h_score"],
                a_score=row["a_score"],
                f_score=row["f_score"],
                e_score=row["e_score"],
                f_confidence=row["f_confidence"],
                f_species=row["f_species"],
                a_dist_to_trail_m=row["a_dist_to_trail_m"],
                a_dist_to_parking_m=row["a_dist_to_parking_m"],
                composite=float(row["composite"]),
                rank=int(row["rank"]),
                fmz_total=int(row["fmz_total"]),
            ),
        )
        for row in rows
    ]

    return CandidateFeatureCollection(
        features=features,
        total_count=total_count,
        isochrone_polygon=mapping(isochrone_polygon) if isochrone_polygon is not None else None,
    )


@app.get("/candidates/{candidate_id}/drive-time", response_model=DriveTimeResponse)
def get_candidate_drive_time(
    candidate_id: int,
    from_lat: float = Query(..., ge=41.0, le=50.0),
    from_lon: float = Query(..., ge=-85.0, le=-74.0),
) -> DriveTimeResponse:
    with engine.connect() as conn:
        row = conn.execute(
            _NEAREST_PARKING_SQL, {"candidate_id": candidate_id}
        ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate {candidate_id} not found or not active",
        )

    if row["parking_id"] is None:
        return DriveTimeResponse(
            drive_time_min=None,
            drive_distance_km=None,
            route_geometry=None,
            parking_lat=None,
            parking_lon=None,
            error="No parking found near candidate",
        )

    try:
        directions = get_drive_directions(
            start_lat=from_lat,
            start_lon=from_lon,
            end_lat=row["parking_lat"],
            end_lon=row["parking_lon"],
        )
    except MapboxTimeoutError:
        raise HTTPException(status_code=503, detail="Drive-time service timed out")
    except MapboxAPIError as exc:
        raise HTTPException(status_code=503, detail=f"Drive-time service unavailable: {exc}")

    return DriveTimeResponse(
        drive_time_min=directions["duration_minutes"],
        drive_distance_km=directions["distance_km"],
        route_geometry=directions["geometry"],
        parking_lat=row["parking_lat"],
        parking_lon=row["parking_lon"],
        error=None,
    )


# Rate-limiting: not implemented in v1. These endpoints invoke Claude for each
# request (~20-40s wall time, ~$0.05-0.15/call). The UI buttons are opt-in and
# not auto-triggered, so user discipline is the primary guard. Revisit if cost
# monitoring shows unexpected spend.

@app.post("/agents/rerank", response_model=RerankResponse)
def post_agents_rerank(
    req: RerankRequest,
    debug: bool = Query(default=False),
) -> RerankResponse:
    request_id = str(uuid.uuid4())
    t_start = time.perf_counter()

    with engine.connect() as conn:
        rows = conn.execute(
            _FETCH_CANDIDATES_BY_IDS_SQL, {"ids": req.candidate_ids}
        ).mappings().all()

    if len(rows) != len(req.candidate_ids):
        found = {r["candidate_id"] for r in rows}
        missing = [cid for cid in req.candidate_ids if cid not in found]
        raise HTTPException(
            status_code=404,
            detail=f"Candidates not found or inactive: {missing}",
        )

    id_order = {cid: i for i, cid in enumerate(req.candidate_ids)}
    candidates = sorted(
        [dict(r) for r in rows],
        key=lambda c: id_order.get(c["candidate_id"], 9999),
    )

    top_n = select_top_n(candidates, mode=req.top_n_mode, n=req.top_n)

    try:
        weather_ctx = get_weather_context(req.near_lat, req.near_lon)
    except WeatherTimeoutError:
        raise HTTPException(status_code=503, detail="Weather service timed out")
    except WeatherAPIError as exc:
        raise HTTPException(status_code=503, detail=f"Weather service unavailable: {exc}")

    conditions = get_all_conditions()

    try:
        result = run_rerank_orchestration(top_n, weather_ctx, conditions)
    except OrchestrationError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Agent orchestration failed (request_id={request_id}): {exc}",
        )

    elapsed = time.perf_counter() - t_start
    _log.info(
        "rerank request_id=%s candidates=%d top_n=%d time=%.2fs errors=%s",
        request_id, len(candidates), len(top_n), elapsed, result["errors"],
    )

    coord = result["coordinator_output"]
    current_conditions = (
        f"{conditions['season'].title()}, "
        f"{conditions['day_category'].title()}, "
        f"{conditions['time_of_day'].title()}"
    )

    return RerankResponse(
        request_id=request_id,
        ranked_candidates=[RerankedCandidate(**c) for c in coord["ranked_candidates"]],
        weighting=coord["weighting"],
        current_conditions=current_conditions,
        synthesis_note=coord.get("synthesis_note"),
        specialist_metadata=(
            {"round1": result["round1"], "round2": result["round2"],
             "timings": result["timings"], "errors": result["errors"]}
            if debug else None
        ),
    )


@app.post("/agents/trip-plan", response_model=TripPlanResponse)
def post_agents_trip_plan(
    req: TripPlanRequest,
    debug: bool = Query(default=False),
) -> TripPlanResponse:
    request_id = str(uuid.uuid4())
    t_start = time.perf_counter()

    with engine.connect() as conn:
        row = conn.execute(
            _FETCH_CANDIDATE_SQL, {"candidate_id": req.candidate_id}
        ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate {req.candidate_id} not found or inactive",
        )

    candidate = dict(row)

    try:
        weather_ctx = get_weather_context(req.near_lat, req.near_lon)
    except WeatherTimeoutError:
        raise HTTPException(status_code=503, detail="Weather service timed out")
    except WeatherAPIError as exc:
        raise HTTPException(status_code=503, detail=f"Weather service unavailable: {exc}")

    conditions = get_all_conditions()

    try:
        result = run_trip_plan_orchestration(candidate, weather_ctx, conditions)
    except OrchestrationError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Agent orchestration failed (request_id={request_id}): {exc}",
        )

    elapsed = time.perf_counter() - t_start
    _log.info(
        "trip-plan request_id=%s candidate_id=%d time=%.2fs errors=%s",
        request_id, req.candidate_id, elapsed, result["errors"],
    )

    coord = result["coordinator_output"]

    return TripPlanResponse(
        request_id=request_id,
        candidate_id=req.candidate_id,
        overall_call=coord["overall_call"],
        best_window=coord["best_window"],
        expected_species=coord["expected_species"],
        conditions_summary=coord["conditions_summary"],
        things_to_watch=coord["things_to_watch"],
        key_risks=coord["key_risks"],
        confidence=coord["confidence"],
        specialist_metadata=(
            {"round1": result["round1"], "round2": result["round2"],
             "timings": result["timings"], "errors": result["errors"]}
            if debug else None
        ),
    )
