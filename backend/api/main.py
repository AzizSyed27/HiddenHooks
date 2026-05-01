from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL

from api.models import CandidateFeature, CandidateProperties, FeatureCollection

SQL = text("""
    SELECT
        id,
        name,
        candidate_type::text,
        source_dataset::text,
        dist_to_road_meters,
        area_m2,
        length_m,
        ST_AsGeoJSON(ST_Transform(geom, 4326))::json AS geometry_geojson,
        RANK() OVER (ORDER BY dist_to_road_meters DESC NULLS LAST) AS rank
    FROM candidates
    ORDER BY dist_to_road_meters DESC NULLS LAST
""")

PROP_KEYS = (
    "id", "name", "candidate_type", "source_dataset",
    "dist_to_road_meters", "area_m2", "length_m", "rank",
)

app = FastAPI(title="HiddenHooks API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

engine = create_engine(DATABASE_URL)


@app.get("/candidates", response_model=FeatureCollection)
def get_candidates() -> FeatureCollection:
    with engine.connect() as conn:
        rows = conn.execute(SQL).mappings().all()

    features = [
        CandidateFeature(
            geometry=row["geometry_geojson"],
            properties=CandidateProperties(**{k: row[k] for k in PROP_KEYS}),
        )
        for row in rows
    ]
    return FeatureCollection(features=features)
