"""Build the candidate_edges connectivity graph.

Run after segment_reaches.py. Idempotent: deletes all existing edges and rebuilds.
Estimated runtime: ~10-15 min for FMZ 16+17 (652k active candidates).

--limit N caps the outer loop to the first N active candidates (by ID). The inner join
still searches the full candidates table via the GiST index, so --limit is a smoke-test
affordance — not a proportionally faster run. Use it to confirm the query executes and
produces plausible output before committing to a full build.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, SNAP_TOLERANCE_M

BUILD_SQL = text("""
    INSERT INTO candidate_edges (from_candidate_id, to_candidate_id, edge_type, distance_m)
    SELECT
        a.id,
        b.id,
        CASE WHEN d.dist = 0 THEN 'touches'::text ELSE 'snapped'::text END,
        d.dist
    FROM candidates a
    JOIN candidates b ON a.id < b.id
        AND ST_DWithin(a.geom, b.geom, :snap_m)
    JOIN LATERAL (SELECT ST_Distance(a.geom, b.geom) AS dist) d ON TRUE
    WHERE a.is_active = TRUE
      AND b.is_active = TRUE
      AND NOT (a.candidate_type = 'polygon' AND b.candidate_type = 'polygon' AND d.dist > 0)
""")

BUILD_LIMITED_SQL = text("""
    INSERT INTO candidate_edges (from_candidate_id, to_candidate_id, edge_type, distance_m)
    SELECT
        a.id,
        b.id,
        CASE WHEN d.dist = 0 THEN 'touches'::text ELSE 'snapped'::text END,
        d.dist
    FROM candidates a
    JOIN candidates b ON a.id < b.id
        AND ST_DWithin(a.geom, b.geom, :snap_m)
    JOIN LATERAL (SELECT ST_Distance(a.geom, b.geom) AS dist) d ON TRUE
    WHERE a.is_active = TRUE
      AND b.is_active = TRUE
      AND a.id <= :max_id
      AND NOT (a.candidate_type = 'polygon' AND b.candidate_type = 'polygon' AND d.dist > 0)
""")


def ingest(engine, limit: int | None = None) -> None:
    with engine.connect() as conn:
        type_rows = conn.execute(text("""
            SELECT candidate_type, COUNT(*) AS n
            FROM candidates
            WHERE is_active = TRUE
            GROUP BY candidate_type
            ORDER BY candidate_type
        """)).fetchall()

    total = sum(r.n for r in type_rows)
    print(f"  active candidates:               {total:,}")
    for row in type_rows:
        print(f"    {row.candidate_type}: {row.n:,}")

    print("  clearing existing edges...")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM candidate_edges"))

    params: dict = {"snap_m": SNAP_TOLERANCE_M}

    if limit is not None:
        with engine.connect() as conn:
            max_id = conn.execute(text(
                "SELECT id FROM candidates WHERE is_active = TRUE ORDER BY id LIMIT 1 OFFSET :offset"
            ), {"offset": limit - 1}).scalar()
        if max_id is None:
            print(f"  WARNING: fewer than {limit:,} active candidates; running full build.")
            sql = BUILD_SQL
        else:
            params["max_id"] = max_id
            sql = BUILD_LIMITED_SQL
            print(f"  limit: {limit:,} outer candidates (id <= {max_id})")
    else:
        sql = BUILD_SQL

    print(f"  building connectivity graph (snap tolerance: {SNAP_TOLERANCE_M}m)...")
    t0 = time.monotonic()
    with engine.begin() as conn:
        conn.execute(sql, params)
    elapsed = time.monotonic() - t0

    with engine.connect() as conn:
        edge_rows = conn.execute(text("""
            SELECT edge_type, COUNT(*) AS n
            FROM candidate_edges
            GROUP BY edge_type
            ORDER BY edge_type
        """)).fetchall()

    total_edges = sum(r.n for r in edge_rows)
    print(f"  elapsed:                         {elapsed:.0f}s")
    print(f"  edges inserted:                  {total_edges:,}")
    for row in edge_rows:
        print(f"    {row.edge_type}: {row.n:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build candidate_edges connectivity graph.")
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help=(
            "Smoke-test affordance: cap the outer loop to the first N active candidates "
            "by ID. The inner join still searches the full table via the GiST index, so "
            "this is not a proportionally faster run — use it to verify execution and "
            "output shape before committing to a full build (~10-15 min)."
        ),
    )
    args = parser.parse_args()
    engine = create_engine(DATABASE_URL)
    ingest(engine, limit=args.limit)
