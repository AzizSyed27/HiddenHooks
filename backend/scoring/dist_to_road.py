"""Compute dist_to_road_meters for all polygon and reach_full candidates.

Idempotent by design: reruns overwrite existing values with a full recompute.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL

UPDATE_SQL = text("""
    UPDATE candidates c
    SET dist_to_road_meters = (
        SELECT ST_Distance(c.geom, r.geom)
        FROM roads r
        ORDER BY r.geom <-> c.geom
        LIMIT 1
    )
    WHERE c.candidate_type IN ('polygon', 'reach_full')
""")

STATS_SQL = text("""
    SELECT
        count(*)                                                         AS scored,
        round(min(dist_to_road_meters)::numeric, 1)                     AS min_m,
        round(max(dist_to_road_meters)::numeric, 1)                     AS max_m,
        round(
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY dist_to_road_meters
            )::numeric, 1
        )                                                                AS median_m
    FROM candidates
    WHERE candidate_type IN ('polygon', 'reach_full')
      AND dist_to_road_meters IS NOT NULL
""")


def score(engine) -> None:
    with engine.connect() as conn:
        road_count = conn.execute(text("SELECT count(*) FROM roads")).scalar()

    if road_count == 0:
        raise RuntimeError("roads table is empty — run ingest/roads.py first")

    print("Scoring candidates by distance to nearest road...")
    t0 = time.perf_counter()

    with engine.begin() as conn:
        conn.execute(UPDATE_SQL)

    elapsed = time.perf_counter() - t0

    with engine.connect() as conn:
        row = conn.execute(STATS_SQL).mappings().one()

    print(f"  scored candidates:       {row['scored']:,}")
    print(f"  min / median / max (m):  {row['min_m']} / {row['median_m']} / {row['max_m']}")
    print(f"  elapsed:                 {elapsed:.2f} s")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    score(engine)
