from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL

app = FastAPI(title="HiddenHooks API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
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


class HealthResponse(BaseModel):
    status: str


class RegionInfo(BaseModel):
    fmz_zone: str
    candidate_count: int


class RegionsResponse(BaseModel):
    regions: list[RegionInfo]


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

# {fmz_filter} is filled at call time with either "" or "AND fmz_zone = :fmz".
# The placeholder is hardcoded in Python — never from user input — so str.format() is safe.
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
) -> CandidateFeatureCollection:
    weight_sum = w_h + w_a + w_f + w_e
    if weight_sum <= 0:
        raise HTTPException(status_code=422, detail="At least one weight must be > 0")
    w_h, w_a, w_f, w_e = w_h / weight_sum, w_a / weight_sum, w_f / weight_sum, w_e / weight_sum

    fmz_filter = "AND fmz_zone = :fmz" if fmz else ""
    sql = text(_CANDIDATES_SQL_TEMPLATE.format(fmz_filter=fmz_filter))

    params: dict[str, Any] = {
        "w_h": w_h, "w_a": w_a, "w_f": w_f, "w_e": w_e,
        "limit": limit,
    }
    if fmz:
        params["fmz"] = fmz

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

    return CandidateFeatureCollection(features=features, total_count=total_count)
