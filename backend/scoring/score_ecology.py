"""Score candidates on ecology (e_score).

e_score = fraction of the 100m donut buffer around each candidate that is
forested or wetland per SOLRIS 3.0 class codes (0–1, global).

Donut buffer: ST_Difference(buffer_100m, candidate_geom) — excludes the water
body's own pixels so large lakes don't dilute their surrounding land ecology.
For reach_segment (LineString) candidates the difference has no effect since a
line has no interior area; the full 100m buffer is used.

Run ingest/landcover.py first and confirm FOREST_CODES / WETLAND_CODES in
config.py match the official SOLRIS legend before scoring.

Idempotent: resets e_score to NULL for all active candidates first.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from rasterstats import zonal_stats
from shapely import wkb as shapely_wkb
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DATABASE_URL,
    FOREST_CODES,
    SOLRIS_CACHE_PATH,
    WETLAND_CODES,
)

BATCH_SIZE = 500

RESET_SQL = text(
    "UPDATE candidates SET e_score = NULL WHERE is_active = TRUE"
)

FETCH_SQL = text("""
    SELECT id, ST_AsBinary(geom) AS wkb
    FROM candidates
    WHERE is_active = TRUE
    ORDER BY id
""")

UPDATE_SQL = text(
    "UPDATE candidates SET e_score = :e_score WHERE id = :id"
)

LOG_SQL = text("""
    SELECT fmz_zone,
           COUNT(*)                           AS total,
           COUNT(e_score)                     AS scored,
           ROUND(AVG(e_score)::numeric, 3)    AS avg_e,
           ROUND(MAX(e_score)::numeric, 3)    AS max_e
    FROM candidates
    WHERE is_active = TRUE
    GROUP BY fmz_zone
    ORDER BY fmz_zone
""")


def score(engine) -> None:
    if not SOLRIS_CACHE_PATH.exists():
        raise FileNotFoundError(
            f"Cached SOLRIS raster not found: {SOLRIS_CACHE_PATH}\n"
            "Run `python -m ingest.landcover` first."
        )

    # Load raster into memory once — eliminates 652k random file seeks.
    # Passing a file path on OneDrive causes per-feature I/O that can take hours;
    # passing a numpy array + affine keeps all pixel access in RAM.
    import rasterio
    print("Loading SOLRIS raster into memory...")
    t_load = time.monotonic()
    with rasterio.open(SOLRIS_CACHE_PATH) as src:
        nodata        = src.nodata
        solris_data   = src.read(1)          # uint8 or uint16 numpy array
        solris_affine = src.transform
    print(f"  SOLRIS cache:                    {SOLRIS_CACHE_PATH.name}")
    print(f"  raster size:                     {solris_data.shape[1]:,} × {solris_data.shape[0]:,} px")
    print(f"  memory:                          {solris_data.nbytes / 1e6:.0f} MB")
    print(f"  nodata value:                    {nodata!r}")
    print(f"  load elapsed:                    {time.monotonic() - t_load:.0f}s")
    print(f"  FOREST_CODES:                    {FOREST_CODES}")
    print(f"  WETLAND_CODES:                   {WETLAND_CODES}")

    print("Fetching active candidates...")
    with engine.connect() as conn:
        rows = conn.execute(FETCH_SQL).fetchall()
    print(f"  candidates:                      {len(rows):,}")

    # Decode WKB → Shapely, build donut buffers (100m ring outside the candidate)
    print("Building donut buffers...")
    t0 = time.monotonic()
    ids       = []
    donuts    = []
    for row in rows:
        geom  = shapely_wkb.loads(bytes(row.wkb))
        donut = geom.buffer(100).difference(geom)
        if donut.is_empty:
            donut = geom.buffer(100)   # fallback: shouldn't happen but be defensive
        ids.append(row.id)
        donuts.append(donut)
    print(f"  elapsed:                         {time.monotonic() - t0:.0f}s")

    # Zonal statistics — categorical pixel counts per donut buffer.
    # numpy array + affine avoids all per-feature file I/O.
    print("Running zonal_stats...")
    t1 = time.monotonic()
    stats = zonal_stats(
        donuts,
        solris_data,
        affine=solris_affine,
        categorical=True,
        nodata=nodata if nodata is not None else 255,
        all_touched=False,
        geojson_out=False,
    )
    print(f"  elapsed:                         {time.monotonic() - t1:.0f}s")

    # Compute e_score per candidate
    target_codes = set(FOREST_CODES) | set(WETLAND_CODES)
    records: list[dict[str, Any]] = []
    skipped = 0

    for candidate_id, s in zip(ids, stats):
        if not s:
            skipped += 1
            records.append({"id": candidate_id, "e_score": None})
            continue
        total  = sum(s.values())
        target = sum(s.get(c, 0) for c in target_codes)
        e_score = float(target) / total if total > 0 else None
        records.append({"id": candidate_id, "e_score": e_score})

    scored = sum(1 for r in records if r["e_score"] is not None)
    print(f"  scored:                          {scored:,}")
    print(f"  skipped (no raster coverage):    {skipped:,}")

    # Reset + batch UPDATE
    print("Writing e_score to database...")
    t2 = time.monotonic()
    with engine.begin() as conn:
        conn.execute(RESET_SQL)
        for i in range(0, len(records), BATCH_SIZE):
            conn.execute(UPDATE_SQL, records[i : i + BATCH_SIZE])
    print(f"  elapsed:                         {time.monotonic() - t2:.0f}s")

    with engine.connect() as conn:
        log_rows = conn.execute(LOG_SQL).fetchall()

    if log_rows:
        print(f"\n  {'fmz_zone':<10} {'total':>8} {'scored':>8} {'avg_e':>7} {'max_e':>7}")
        for row in log_rows:
            print(
                f"  {row.fmz_zone:<10} {row.total:>8,} {row.scored:>8,}"
                f" {row.avg_e:>7} {row.max_e:>7}"
            )


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    score(engine)
