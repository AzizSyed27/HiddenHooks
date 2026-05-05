"""Split reach_full candidates into 200m reach_segment children.

LIFECYCLE WARNING: After Part 4 builds the candidate_edges connectivity graph,
re-running this script will cascade-delete all edges (candidate_edges rows have
FKs into candidates; deleting reach_segments cascades through parent_candidate_id).
Re-run build_connectivity.py immediately after re-segmenting.
"""

from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path
from typing import Any

from shapely import wkb as shapely_wkb
from shapely.ops import substring
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, SEGMENT_LENGTH_M

LOAD_SQL = text("""
    SELECT id, ohn_id, name, fmz_zone,
           ST_AsBinary(geom) AS geom_wkb,
           length_m
    FROM candidates
    WHERE candidate_type = 'reach_full'
""")

INSERT_SQL = text("""
    INSERT INTO candidates
        (ohn_id, source_dataset, candidate_type, parent_candidate_id,
         name, fmz_zone, geom, length_m)
    VALUES
        (:ohn_id, 'watercourse', 'reach_segment', :parent_id,
         :name, :fmz_zone,
         ST_GeomFromWKB(decode(:geom, 'hex'), 3161),
         :length_m)
""")

RESET_ACTIVE_SQL = text("""
    UPDATE candidates SET is_active = TRUE
    WHERE candidate_type = 'reach_full'
""")

DEACTIVATE_SEGMENTED_SQL = text("""
    UPDATE candidates SET is_active = FALSE
    WHERE candidate_type = 'reach_full'
      AND EXISTS (
          SELECT 1 FROM candidates c2
          WHERE c2.parent_candidate_id = candidates.id
      )
""")

BATCH_SIZE = 500


def warn_if_edges_exist(conn) -> None:
    try:
        n = conn.execute(text("SELECT COUNT(*) FROM candidate_edges")).scalar()
        if n > 0:
            print(f"  WARNING: {n:,} edges in candidate_edges will be cascade-deleted.")
            print("           Re-run build_connectivity.py after this script.")
    except Exception:
        pass  # Table does not exist yet (Part 4 not done) — skip silently


def segment_line(line, parent: dict[str, Any]) -> list[dict[str, Any]]:
    """Return segment records for a single LineString part of a parent reach."""
    total = line.length
    n_segs = math.ceil(total / SEGMENT_LENGTH_M)
    segments = []
    for i in range(n_segs):
        start = i * SEGMENT_LENGTH_M
        end = min((i + 1) * SEGMENT_LENGTH_M, total)
        seg = substring(line, start, end)
        segments.append({
            "ohn_id":    parent["ohn_id"],
            "parent_id": parent["id"],
            "name":      parent["name"],
            "fmz_zone":  parent["fmz_zone"],
            "geom":      seg.wkb_hex,
            "length_m":  seg.length,
        })
    return segments


def segmentize(parents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Segmentize all reach_full parents. Returns (all_segments, skipped_part_count)."""
    all_segments: list[dict[str, Any]] = []
    skipped = 0

    for parent in parents:
        geom = parent["geom"]
        if geom.geom_type == "LineString":
            parts = [geom]
        else:  # MultiLineString
            parts = list(geom.geoms)

        parent_segs = []
        for part in parts:
            if part.length < 1.0:
                skipped += 1
                continue
            parent_segs.extend(segment_line(part, parent))

        all_segments.extend(parent_segs)

    return all_segments, skipped


def ingest(engine) -> None:
    # Step 1: check for downstream edges before deleting
    with engine.connect() as conn:
        warn_if_edges_exist(conn)

    # Step 2: clear existing reach_segments and load parents
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM candidates WHERE parent_candidate_id IS NOT NULL"))

        rows = conn.execute(LOAD_SQL).fetchall()

    parents = [
        {
            "id":       row.id,
            "ohn_id":   row.ohn_id,
            "name":     row.name,
            "fmz_zone": row.fmz_zone,
            "geom":     shapely_wkb.loads(bytes(row.geom_wkb)),
            "length_m": row.length_m,
        }
        for row in rows
    ]

    fmz16_parents = sum(1 for p in parents if p["fmz_zone"] == "FMZ16")
    fmz17_parents = sum(1 for p in parents if p["fmz_zone"] == "FMZ17")
    print(f"  reach_full rows loaded:          {len(parents):,}")
    print(f"    FMZ16: {fmz16_parents:,}, FMZ17: {fmz17_parents:,}")

    # Step 3: segmentize
    all_segments, skipped = segmentize(parents)

    segs_fmz16 = sum(1 for s in all_segments if s["fmz_zone"] == "FMZ16")
    segs_fmz17 = sum(1 for s in all_segments if s["fmz_zone"] == "FMZ17")
    print(f"  total segments produced:         {len(all_segments):,}")
    print(f"    FMZ16: {segs_fmz16:,}, FMZ17: {segs_fmz17:,}")

    # Segments-per-parent distribution
    segs_by_parent: dict[int, int] = {}
    for s in all_segments:
        segs_by_parent[s["parent_id"]] = segs_by_parent.get(s["parent_id"], 0) + 1
    if segs_by_parent:
        counts = list(segs_by_parent.values())
        print(f"  segments per parent — min: {min(counts)}, max: {max(counts)}, mean: {statistics.mean(counts):.1f}")

    print(f"  skipped <1m parts:               {skipped:,}")

    # Step 4: reset is_active, batch insert, then deactivate segmented parents
    inserted = 0
    deactivated = 0
    with engine.begin() as conn:
        conn.execute(RESET_ACTIVE_SQL)
        for i in range(0, len(all_segments), BATCH_SIZE):
            batch = all_segments[i : i + BATCH_SIZE]
            conn.execute(INSERT_SQL, batch)
            inserted += len(batch)
        result = conn.execute(DEACTIVATE_SEGMENTED_SQL)
        deactivated = result.rowcount

    print(f"  inserted:                        {inserted:,}")
    print(f"  deactivated reach_full rows:     {deactivated:,}")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    ingest(engine)
