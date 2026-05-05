"""Snap ARA survey points to their nearest active candidate within ARA_SNAP_TOLERANCE_M.

Idempotent: resets all snap fields first, then re-snaps. Handles the case where a
point previously had a snap but now has no candidate within tolerance (stale snap
would otherwise survive a re-run). Run after both ara_points.py and
segment_reaches.py are complete.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ARA_SNAP_TOLERANCE_M, DATABASE_URL

RESET_SQL = text(
    "UPDATE ara_points SET snapped_candidate_id = NULL, snap_distance_m = NULL"
)

SNAP_SQL = text("""
    UPDATE ara_points
    SET snapped_candidate_id = nearest.id,
        snap_distance_m      = nearest.dist
    FROM ara_points src
    JOIN LATERAL (
        SELECT c.id, ST_Distance(src.geom, c.geom) AS dist
        FROM candidates c
        WHERE c.candidate_type IN ('polygon', 'reach_segment')
          AND ST_DWithin(src.geom, c.geom, :snap_m)
        ORDER BY src.geom <-> c.geom
        LIMIT 1
    ) nearest ON TRUE
    WHERE ara_points.ara_id = src.ara_id
""")

LOG_SQL = text("""
    SELECT fmz_zone,
           COUNT(*)                                    AS total,
           COUNT(snapped_candidate_id)                 AS snapped,
           COUNT(*) - COUNT(snapped_candidate_id)      AS unsnapped
    FROM ara_points
    GROUP BY fmz_zone
    ORDER BY fmz_zone
""")


def snap(engine) -> None:
    print(f"  snapping ARA points to candidates (tolerance: {ARA_SNAP_TOLERANCE_M}m)...")
    t0 = time.monotonic()

    with engine.begin() as conn:
        reset_result = conn.execute(RESET_SQL)
        reset_count  = reset_result.rowcount
        snap_result  = conn.execute(SNAP_SQL, {"snap_m": ARA_SNAP_TOLERANCE_M})
        snapped      = snap_result.rowcount

    elapsed = time.monotonic() - t0

    print(f"  reset:                           {reset_count:,} rows cleared")
    print(f"  elapsed:                         {elapsed:.0f}s")
    print(f"  snapped:                         {snapped:,}  (of {reset_count:,} total)")
    print(f"  unsnapped:                       {reset_count - snapped:,}")

    with engine.connect() as conn:
        rows = conn.execute(LOG_SQL).fetchall()

    if rows:
        print(f"\n  {'fmz_zone':<10} {'total':>8} {'snapped':>8} {'unsnapped':>10}")
        for row in rows:
            print(f"  {row.fmz_zone:<10} {row.total:>8,} {row.snapped:>8,} {row.unsnapped:>10,}")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    snap(engine)
