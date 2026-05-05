"""Score candidates on accessibility (a_score).

Populates a_dist_to_trail_m and a_dist_to_parking_m via PostGIS KNN, then:

    a_score = 1 - clip(min(dist_to_trail, dist_to_parking) / ACCESSIBILITY_DECAY_M, 0, 1)

    At 0 m from trail or parking: a_score = 1.0
    At >= ACCESSIBILITY_DECAY_M (2000 m): a_score = 0.0
    Linear in between.

Global formula — same decay threshold in both FMZs.

All four statements (reset, trail KNN, parking KNN, score formula) run in one transaction.
Partial state cannot be committed if a step fails mid-run.

Runtime: ~9 min per KNN pass on 652k active candidates (0.80 ms/row, timed 2026-05-05);
expect ~18-20 min total. Idempotent: resets all three columns to NULL first.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ACCESSIBILITY_DECAY_M, DATABASE_URL

RESET_SQL = text("""
    UPDATE candidates
    SET a_dist_to_trail_m = NULL, a_dist_to_parking_m = NULL, a_score = NULL
    WHERE is_active = TRUE
""")

TRAIL_KNN_SQL = text("""
    UPDATE candidates c
    SET a_dist_to_trail_m = (
        SELECT ST_Distance(c.geom, t.geom)
        FROM trails t
        ORDER BY t.geom <-> c.geom
        LIMIT 1
    )
    WHERE c.is_active = TRUE
""")

PARKING_KNN_SQL = text("""
    UPDATE candidates c
    SET a_dist_to_parking_m = (
        SELECT ST_Distance(c.geom, p.geom)
        FROM parking p
        ORDER BY p.geom <-> c.geom
        LIMIT 1
    )
    WHERE c.is_active = TRUE
""")

SCORE_SQL = text("""
    UPDATE candidates
    SET a_score = 1.0 - LEAST(
        GREATEST(
            LEAST(a_dist_to_trail_m, a_dist_to_parking_m) / :decay_m,
            0.0
        ),
        1.0
    )
    WHERE is_active = TRUE
      AND a_dist_to_trail_m  IS NOT NULL
      AND a_dist_to_parking_m IS NOT NULL
""")

LOG_SQL = text("""
    SELECT fmz_zone,
           COUNT(*)                           AS total,
           COUNT(a_score)                     AS scored,
           ROUND(MIN(a_score)::numeric, 3)    AS min_a,
           ROUND(AVG(a_score)::numeric, 3)    AS avg_a,
           ROUND(MAX(a_score)::numeric, 3)    AS max_a
    FROM candidates
    WHERE is_active = TRUE
    GROUP BY fmz_zone
    ORDER BY fmz_zone
""")


def score(engine) -> None:
    with engine.connect() as conn:
        trail_count   = conn.execute(text("SELECT COUNT(*) FROM trails")).scalar()
        parking_count = conn.execute(text("SELECT COUNT(*) FROM parking")).scalar()

    print(f"  trails table:                    {trail_count:,} rows")
    print(f"  parking table:                   {parking_count:,} rows")

    if trail_count == 0:
        raise RuntimeError("trails table is empty — run ingest/trails_and_parking.py first")
    if parking_count == 0:
        raise RuntimeError("parking table is empty — run ingest/trails_and_parking.py first")

    print("scoring accessibility (a_score)...")
    t0 = time.monotonic()

    with engine.begin() as conn:
        reset_result = conn.execute(RESET_SQL)
        print(f"  reset:                           {reset_result.rowcount:,} active candidates cleared")

        t1 = time.monotonic()
        trail_result = conn.execute(TRAIL_KNN_SQL)
        t2 = time.monotonic()
        print(f"  trail KNN:                       {trail_result.rowcount:,} rows  ({t2 - t1:.0f}s)")

        parking_result = conn.execute(PARKING_KNN_SQL)
        t3 = time.monotonic()
        print(f"  parking KNN:                     {parking_result.rowcount:,} rows  ({t3 - t2:.0f}s)")

        score_result = conn.execute(SCORE_SQL, {"decay_m": ACCESSIBILITY_DECAY_M})
        print(f"  scored:                          {score_result.rowcount:,} candidates")

    elapsed = time.monotonic() - t0
    print(f"  elapsed total:                   {elapsed:.0f}s")

    with engine.connect() as conn:
        rows = conn.execute(LOG_SQL).fetchall()

    if rows:
        print(f"\n  {'fmz_zone':<10} {'total':>8} {'scored':>8} {'min_a':>7} {'avg_a':>7} {'max_a':>7}")
        for row in rows:
            print(
                f"  {row.fmz_zone:<10} {row.total:>8,} {row.scored:>8,}"
                f" {row.min_a:>7} {row.avg_a:>7} {row.max_a:>7}"
            )


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    score(engine)
