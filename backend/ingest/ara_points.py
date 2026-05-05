"""Ingest ARA Survey Point shapefile into the ara_points table.

Snap fields (snapped_candidate_id, snap_distance_m) are left NULL here —
populated by a separate snap step after all candidates are loaded.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely import wkb as shapely_wkb
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ARA_DIR, COMBINED_BBOX, DATABASE_URL

UPSERT_SQL = text("""
    INSERT INTO ara_points (ara_id, geom, survey_date, fish_species_summary, fmz_zone)
    VALUES (
        :ara_id,
        ST_GeomFromWKB(decode(:geom, 'hex'), 3161),
        :survey_date,
        :fish_species_summary,
        :fmz_zone
    )
    ON CONFLICT (ara_id) DO UPDATE SET
        geom                 = EXCLUDED.geom,
        survey_date          = EXCLUDED.survey_date,
        fish_species_summary = EXCLUDED.fish_species_summary,
        fmz_zone             = EXCLUDED.fmz_zone
""")

BATCH_SIZE = 500


def load_region_geometries(engine) -> dict[str, Any]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT name, ST_AsBinary(geom) AS wkb FROM regions"
        )).fetchall()
    return {row.name: shapely_wkb.loads(bytes(row.wkb)) for row in rows}


def load_ara_points(
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

    # Points use .within() directly — no .centroid step needed
    gdf["fmz_zone"] = None
    gdf.loc[gdf.geometry.within(regions["FMZ 16"]), "fmz_zone"] = "FMZ16"
    gdf.loc[gdf.geometry.within(regions["FMZ 17"]), "fmz_zone"] = "FMZ17"
    gdf = gdf[gdf["fmz_zone"].notna()].copy()
    fmz16_n = (gdf["fmz_zone"] == "FMZ16").sum()
    fmz17_n = (gdf["fmz_zone"] == "FMZ17").sum()
    print(f"  post-FMZ filter:                 {len(gdf):,}  (FMZ16: {fmz16_n:,}, FMZ17: {fmz17_n:,})")

    # pyogrio may expose full column names from XML metadata or truncated DBF names
    species_col = "FISH_SPECIES_SUMMARY" if "FISH_SPECIES_SUMMARY" in gdf.columns else "FISH_SPECI"
    date_col    = "SURVEY_DATE"          if "SURVEY_DATE"          in gdf.columns else "SURVEY_DAT"

    gdf["fish_species_summary"] = gdf[species_col].where(
        gdf[species_col].notna()
        & (gdf[species_col].str.strip() != "")
        & (gdf[species_col].str.strip().str.upper() != "NAN"),
        other=None,
    )

    dates = pd.to_datetime(gdf[date_col], errors="coerce").dt.date
    gdf["survey_date"] = dates.where(dates.notna(), other=None)

    return gdf[["OGF_ID", "fish_species_summary", "survey_date", "fmz_zone", "geometry"]]


def ingest(engine) -> None:
    print("Loading region geometries from DB...")
    regions = load_region_geometries(engine)

    print("Loading ARA survey points...")
    gdf = load_ara_points(ARA_DIR, COMBINED_BBOX, regions)

    rows: list[dict[str, Any]] = [
        {
            "ara_id":               str(row.OGF_ID),
            "geom":                 row.geometry.wkb_hex,
            "survey_date":          row.survey_date,
            "fish_species_summary": row.fish_species_summary,
            "fmz_zone":             row.fmz_zone,
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
