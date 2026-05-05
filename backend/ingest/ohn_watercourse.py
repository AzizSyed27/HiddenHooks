"""Ingest OHN Watercourse linestrings into the candidates table (Phase 2: FMZ 16 + 17)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely import wkb as shapely_wkb
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import COMBINED_BBOX, DATABASE_URL, OHN_WATERCOURSE_DIR

UPSERT_SQL = text("""
    INSERT INTO candidates
        (ohn_id, source_dataset, candidate_type, name, fmz_zone, geom, length_m)
    VALUES
        (:ohn_id, 'watercourse', 'reach_full', :name, :fmz_zone,
         ST_SimplifyPreserveTopology(ST_GeomFromWKB(decode(:geom, 'hex'), 3161), 1.0),
         :length_m)
    ON CONFLICT (ohn_id, source_dataset)
        WHERE candidate_type = 'reach_full'
    DO UPDATE SET
        name     = EXCLUDED.name,
        fmz_zone = EXCLUDED.fmz_zone,
        geom     = EXCLUDED.geom,
        length_m = EXCLUDED.length_m
""")

BATCH_SIZE = 500


def load_region_geometries(engine) -> dict[str, Any]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT name, ST_AsBinary(geom) AS wkb FROM regions"
        )).fetchall()
    return {row.name: shapely_wkb.loads(bytes(row.wkb)) for row in rows}


def load_watercourses(
    path: Path,
    bbox: tuple[float, float, float, float],
    regions: dict[str, Any],
) -> gpd.GeoDataFrame:
    shp = next(path.glob("*.shp"))

    source_count = len(gpd.read_file(shp, engine="pyogrio", ignore_geometry=True))
    print(f"  source features (province-wide): {source_count:,}")

    gdf = gpd.read_file(shp, bbox=bbox, engine="pyogrio")
    print(f"  post-bbox filter:                {len(gdf):,}")

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    print(f"  post-validity filter:            {len(gdf):,}")

    gdf = gdf.to_crs(3161)

    centroids = gdf.geometry.centroid
    gdf["fmz_zone"] = None
    gdf.loc[centroids.within(regions["FMZ 16"]), "fmz_zone"] = "FMZ16"
    gdf.loc[centroids.within(regions["FMZ 17"]), "fmz_zone"] = "FMZ17"
    gdf = gdf[gdf["fmz_zone"].notna()].copy()
    fmz16_n = (gdf["fmz_zone"] == "FMZ16").sum()
    fmz17_n = (gdf["fmz_zone"] == "FMZ17").sum()
    print(f"  post-FMZ centroid filter:        {len(gdf):,}  (FMZ16: {fmz16_n:,}, FMZ17: {fmz17_n:,})")

    gdf = gdf[~gdf.geometry.centroid.within(regions["Great Lakes"])].copy()
    print(f"  post-lakes exclusion:            {len(gdf):,}")

    gdf = gdf.rename(columns={"OGF_ID": "ohn_id", "OFFICIAL_N": "name"})
    gdf["name"] = gdf["name"].where(
        gdf["name"].notna()
        & (gdf["name"].str.strip() != "")
        & (gdf["name"].str.strip().str.upper() != "NAN"),
        other=None,
    )
    gdf["length_m"] = gdf.geometry.length

    return gdf[["ohn_id", "name", "fmz_zone", "geometry", "length_m"]]


def ingest(engine) -> None:
    print("Loading region geometries from DB...")
    regions = load_region_geometries(engine)

    print("Loading watercourses...")
    gdf = load_watercourses(OHN_WATERCOURSE_DIR, COMBINED_BBOX, regions)

    rows: list[dict[str, Any]] = [
        {
            "ohn_id":   str(row.ohn_id),
            "name":     row.name,
            "fmz_zone": row.fmz_zone,
            "geom":     row.geometry.wkb_hex,
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
