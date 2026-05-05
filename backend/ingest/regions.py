"""Ingest FMZ 16, FMZ 17, Ontario land mask, and Great Lakes into the regions table."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, FMZ_DIR, GREAT_LAKES_DIR, ONTARIO_BOUNDARY_DIR

UPSERT_SQL = text("""
    INSERT INTO regions (name, region_type, geom)
    VALUES (:name, :region_type,
            ST_Multi(ST_GeomFromWKB(decode(:geom, 'hex'), 3161)))
    ON CONFLICT (name, region_type)
    DO UPDATE SET geom = EXCLUDED.geom
""")


def load_fmz(fmz_dir: Path, zone_numbers: list[int]) -> list[dict[str, Any]]:
    shp = next(fmz_dir.glob("*.shp"))
    gdf = gpd.read_file(shp, engine="pyogrio")
    print(f"  FMZ source features (all zones): {len(gdf):,}")

    gdf = gdf[gdf["FISHERIES_"].isin(zone_numbers)].copy()
    print(f"  post-filter (zones {zone_numbers}):       {len(gdf):,}")

    gdf = gdf.to_crs(3161)

    return [
        {
            "name": f"FMZ {int(row['FISHERIES_'])}",
            "region_type": "fmz",
            "geom": row.geometry.wkb_hex,
        }
        for _, row in gdf.iterrows()
    ]


def load_ontario_boundary(boundary_dir: Path) -> list[dict[str, Any]]:
    shp = next(boundary_dir.glob("*.shp"))
    gdf = gpd.read_file(shp, engine="pyogrio")
    print(f"  Ontario boundary features: {len(gdf):,}")

    gdf = gdf.to_crs(3161)

    return [
        {
            "name": "Ontario Land",
            "region_type": "land_mask",
            "geom": row.geometry.wkb_hex,
        }
        for _, row in gdf.iterrows()
    ]


def load_great_lakes(lakes_dir: Path) -> list[dict[str, Any]]:
    shp = next(lakes_dir.glob("*.shp"))
    gdf = gpd.read_file(shp, engine="pyogrio")
    print(f"  Natural Earth lake features (all):   {len(gdf):,}")

    gdf = gdf[gdf["name_alt"] == "Great Lakes"].copy()
    print(f"  post-filter (Great Lakes bodies):    {len(gdf):,}")

    gdf = gdf.to_crs(3161)

    # Union all Great Lakes bodies into one MultiPolygon so the ingest
    # scripts can do a single centroid.within() check.
    union_geom = unary_union(gdf.geometry)
    if union_geom.geom_type == "Polygon":
        union_geom = MultiPolygon([union_geom])

    return [
        {
            "name": "Great Lakes",
            "region_type": "lakes_mask",
            "geom": union_geom.wkb_hex,
        }
    ]


def ingest(engine) -> None:
    print("Loading FMZ polygons...")
    records = load_fmz(FMZ_DIR, [16, 17])

    print("Loading Ontario boundary...")
    records += load_ontario_boundary(ONTARIO_BOUNDARY_DIR)

    print("Loading Great Lakes...")
    records += load_great_lakes(GREAT_LAKES_DIR)

    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)

    print(f"  inserted/updated: {len(records)} regions")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    ingest(engine)
