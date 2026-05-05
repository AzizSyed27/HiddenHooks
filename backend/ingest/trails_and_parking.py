"""Download OSM trails and parking for FMZ 16+17 + 5km buffer, ingest into trails and parking tables.

Idempotent: DELETE + INSERT on each run (same pattern as roads.py).
Cache: pickle files in CACHE_DIR — delete to force re-download from OSM.

Trails:  highway IN (path, footway, cycleway, track) — LineStrings only;
         MultiLineStrings are exploded to individual LineStrings before insert.
Parking: amenity=parking — Points (nodes) and Polygons (ways/lots) stored as-is;
         geometry(Geometry) column accepts both types, PostGIS KNN works on either.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    CACHE_DIR,
    DATABASE_URL,
    PARKING_CACHE_PATH,
    ROADS_BBOX,
    TRAILS_CACHE_PATH,
)

TRAIL_TAGS   = {"highway": ["path", "footway", "cycleway", "track"]}
PARKING_TAGS = {"amenity": "parking"}

BATCH_SIZE = 500

TRAIL_INSERT = text("""
    INSERT INTO trails (osm_id, highway, geom)
    VALUES (:osm_id, :highway, ST_GeomFromWKB(decode(:geom, 'hex'), 3161))
""")

PARKING_INSERT = text("""
    INSERT INTO parking (osm_id, geom)
    VALUES (:osm_id, ST_GeomFromWKB(decode(:geom, 'hex'), 3161))
""")


def download_or_load(cache_path: Path, bbox, tags: dict, label: str) -> gpd.GeoDataFrame:
    if cache_path.exists():
        print(f"  loading {label} from cache: {cache_path}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    print(f"  downloading {label} from OSM...")
    gdf = ox.features_from_bbox(bbox=bbox, tags=tags)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(gdf, f)
    print(f"  cached to {cache_path}")
    return gdf


def _scalar_str(val) -> str | None:
    """Flatten OSMnx tag values to a single string, handling lists and NaN."""
    if val is None:
        return None
    if isinstance(val, list):
        val = val[0] if val else None
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return s or None


def ingest_trails(engine, raw_gdf: gpd.GeoDataFrame) -> None:
    print("Ingesting trails...")
    gdf = raw_gdf[
        raw_gdf.geometry.notna()
        & raw_gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
    ].copy()
    print(f"  raw linestring features:         {len(gdf):,}")

    gdf = gdf.to_crs(3161)
    gdf = gdf.explode(index_parts=False)
    gdf = gdf[gdf.geometry.geom_type == "LineString"].copy()
    print(f"  after explode/filter:            {len(gdf):,}")

    # Use positional level access — MultiIndex level names vary across OSMnx versions
    osm_ids   = gdf.index.get_level_values(1).astype(str)
    hw_series = gdf["highway"].apply(_scalar_str) if "highway" in gdf.columns else pd.Series([None] * len(gdf), index=gdf.index)

    rows: list[dict[str, Any]] = [
        {
            "osm_id":  osm_id,
            "highway": hw,
            "geom":    geom.wkb_hex,
        }
        for osm_id, hw, geom in zip(osm_ids, hw_series, gdf.geometry)
    ]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM trails"))
        for i in range(0, len(rows), BATCH_SIZE):
            conn.execute(TRAIL_INSERT, rows[i : i + BATCH_SIZE])

    print(f"  inserted:                        {len(rows):,}")


def ingest_parking(engine, raw_gdf: gpd.GeoDataFrame) -> None:
    print("Ingesting parking...")
    gdf = raw_gdf[raw_gdf.geometry.notna() & ~raw_gdf.geometry.is_empty].copy()
    print(f"  raw features:                    {len(gdf):,}")

    gdf = gdf.to_crs(3161)

    osm_ids = gdf.index.get_level_values(1).astype(str)

    rows: list[dict[str, Any]] = [
        {
            "osm_id": osm_id,
            "geom":   geom.wkb_hex,
        }
        for osm_id, geom in zip(osm_ids, gdf.geometry)
    ]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM parking"))
        for i in range(0, len(rows), BATCH_SIZE):
            conn.execute(PARKING_INSERT, rows[i : i + BATCH_SIZE])

    print(f"  inserted:                        {len(rows):,}")


def ingest(engine) -> None:
    trails_gdf  = download_or_load(TRAILS_CACHE_PATH,  ROADS_BBOX, TRAIL_TAGS,   "trails")
    ingest_trails(engine, trails_gdf)

    parking_gdf = download_or_load(PARKING_CACHE_PATH, ROADS_BBOX, PARKING_TAGS, "parking")
    ingest_parking(engine, parking_gdf)


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    ingest(engine)
