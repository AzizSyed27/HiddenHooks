"""Score candidates on hiddenness (h_score).

h_score = PERCENT_RANK of dist_to_road_meters within fmz_zone (0–1),
plus 0.1 for unnamed candidates (name IS NULL or literal 'NaN'), clipped to 1.0.

Note: unnamed candidates near the top of their FMZ percentile distribution
compress to h_score = 1.0 due to the boost + clamp interaction. Acceptable
for v1; revisit in Phase 6 calibration if score distribution is too top-heavy.

Idempotent: resets h_score to NULL for all active candidates first.
Run after dist_to_road.py has populated dist_to_road_meters.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL

RESET_SQL = text(
    "UPDATE candidates SET h_score = NULL WHERE is_active = TRUE"
)

SCORE_SQL = text("""
    UPDATE candidates
    SET h_score = sub.h
    FROM (
        SELECT id,
            PERCENT_RANK() OVER (PARTITION BY fmz_zone ORDER BY dist_to_road_meters) AS h
        FROM candidates
        WHERE is_active = TRUE
          AND dist_to_road_meters IS NOT NULL
    ) sub
    WHERE candidates.id = sub.id
""")

BOOST_SQL = text("""
    UPDATE candidates
    SET h_score = LEAST(h_score + 0.1, 1.0)
    WHERE is_active = TRUE
      AND h_score IS NOT NULL
      AND (name IS NULL OR name = 'NaN')
""")

LOG_SQL = text("""
    SELECT fmz_zone,
           COUNT(*)                         AS total,
           COUNT(h_score)                   AS scored,
           COUNT(*) - COUNT(h_score)        AS skipped,
           ROUND(AVG(h_score)::numeric, 3)  AS avg_h,
           ROUND(MAX(h_score)::numeric, 3)  AS max_h
    FROM candidates
    WHERE is_active = TRUE
    GROUP BY fmz_zone
    ORDER BY fmz_zone
""")


def score(engine) -> None:
    print("scoring hiddenness (h_score)...")
    t0 = time.monotonic()

    with engine.begin() as conn:
        reset_result = conn.execute(RESET_SQL)
        reset_count  = reset_result.rowcount
        score_result = conn.execute(SCORE_SQL)
        scored       = score_result.rowcount
        boost_result = conn.execute(BOOST_SQL)
        boosted      = boost_result.rowcount

    elapsed = time.monotonic() - t0

    print(f"  reset:                           {reset_count:,} active candidates cleared")
    print(f"  scored:                          {scored:,} candidates ranked")
    print(f"  skipped (no road dist):          {reset_count - scored:,}")
    print(f"  boosted (unnamed +0.1):          {boosted:,}")
    print(f"  elapsed:                         {elapsed:.0f}s")

    with engine.connect() as conn:
        rows = conn.execute(LOG_SQL).fetchall()

    if rows:
        print(f"\n  {'fmz_zone':<10} {'total':>8} {'scored':>8} {'skipped':>8} {'avg_h':>7} {'max_h':>7}")
        for row in rows:
            print(
                f"  {row.fmz_zone:<10} {row.total:>8,} {row.scored:>8,}"
                f" {row.skipped:>8,} {row.avg_h:>7} {row.max_h:>7}"
            )


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    score(engine)
