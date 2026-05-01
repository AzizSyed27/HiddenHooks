from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI
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


class CandidateProperties(BaseModel):
    id: int
    name: str | None
    candidate_type: str
    source_dataset: str
    dist_to_road_meters: float | None
    area_m2: float | None
    length_m: float | None
    rank: int


class CandidateFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: CandidateProperties


class CandidateFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[CandidateFeature]


CANDIDATES_SQL = text("""
    SELECT
        id,
        name,
        candidate_type::text                                            AS candidate_type,
        source_dataset::text                                            AS source_dataset,
        dist_to_road_meters,
        area_m2,
        length_m,
        ROW_NUMBER() OVER (
            ORDER BY dist_to_road_meters DESC NULLS LAST
        )                                                               AS rank,
        ST_AsGeoJSON(ST_Transform(geom, 4326))                         AS geometry_json
    FROM candidates
    WHERE geom IS NOT NULL
    ORDER BY dist_to_road_meters DESC NULLS LAST
""")


@app.get("/candidates", response_model=CandidateFeatureCollection)
def get_candidates() -> CandidateFeatureCollection:
    with engine.connect() as conn:
        rows = conn.execute(CANDIDATES_SQL).mappings().all()
    features = [
        CandidateFeature(
            geometry=json.loads(row["geometry_json"]),
            properties=CandidateProperties(
                id=row["id"],
                name=row["name"],
                candidate_type=row["candidate_type"],
                source_dataset=row["source_dataset"],
                dist_to_road_meters=row["dist_to_road_meters"],
                area_m2=row["area_m2"],
                length_m=row["length_m"],
                rank=row["rank"],
            ),
        )
        for row in rows
    ]
    return CandidateFeatureCollection(features=features)
