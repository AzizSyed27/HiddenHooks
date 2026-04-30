"""Ingest OHN Watercourse linestrings into the candidates table as reach_full rows."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, OHN_WATERCOURSE_DIR, TEST_BBOX

UPSERT_SQL = text("""
    INSERT INTO candidates
        (ohn_id, source_dataset, candidate_type, name, geom, length_m)
    VALUES
        (:ohn_id, 'watercourse', 'reach_full', :name,
         ST_GeomFromWKB(decode(:geom, 'hex'), 3161), :length_m)
    ON CONFLICT (ohn_id, source_dataset)
        WHERE candidate_type = 'reach_full'
    DO UPDATE SET
        name     = EXCLUDED.name,
        geom     = EXCLUDED.geom,
        length_m = EXCLUDED.length_m
""")

BATCH_SIZE = 500


def load_watercourses(path: Path, bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    shp = next(path.glob("*.shp"))

    # Count source features without loading geometry
    source_count = len(gpd.read_file(shp, engine="pyogrio", ignore_geometry=True))
    print(f"  source features (province-wide): {source_count:,}")

    gdf = gpd.read_file(shp, bbox=bbox, engine="pyogrio")
    print(f"  post-bbox filter:                {len(gdf):,}")

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    print(f"  post-validity filter:            {len(gdf):,}")

    gdf = gdf.to_crs(3161)

    gdf = gdf.rename(columns={"OGF_ID": "ohn_id", "OFFICIAL_N": "name"})
    gdf["name"] = gdf["name"].where(
        gdf["name"].notna() & (gdf["name"].str.strip() != ""), other=None
    )
    gdf["length_m"] = gdf.geometry.length

    return gdf[["ohn_id", "name", "geometry", "length_m"]]


def ingest(engine) -> None:
    print("Loading watercourses...")
    gdf = load_watercourses(OHN_WATERCOURSE_DIR, TEST_BBOX)

    rows: list[dict[str, Any]] = [
        {
            "ohn_id": str(row.ohn_id),
            "name": row.name,
            "geom": row.geometry.wkb_hex,
            "length_m": float(row.length_m),
        }
        for row in gdf.itertuples(index=False)
    ]

    inserted = 0
    with engine.begin() as conn:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            conn.execute(UPSERT_SQL, batch)
            inserted += len(batch)

    print(f"  inserted/updated:                {inserted:,}")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    ingest(engine)
