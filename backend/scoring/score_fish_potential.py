"""Score candidates on fish potential (f_score, f_confidence, f_species,
f_inferred_from_ara_id, f_graph_distance).

Three tiers:

  strong     — candidate has at least one ARA survey point snapped to it.
               f_score = min(sum_of_species_weights / MAX_PLAUSIBLE, 1.0)
               f_graph_distance = 0

  plausible  — no direct ARA anchor, but reachable via the connectivity graph
               within 5 hops from an anchored candidate.
               f_score = max(source_strong_score * 0.7^hop_distance, speculative_prior)
               Floored at the type-appropriate speculative prior so plausible
               inference never produces a worse score than no inference at all.

  speculative — no path to any ARA anchor within 5 hops.
               f_score = 0.3 (polygon) or 0.2 (reach_segment / other types)

Species matching: species_values stores lowercase names; fish_species_summary stores
original-case comma-separated values (e.g. "Walleye, Northern Pike"). Tokens are
.strip().lower() before weight lookup.

BFS tiebreak: ARA-anchor seeds are added to the BFS queue in survey_date DESC NULLS
LAST order. When two anchors are equidistant from a candidate, FIFO processing means
the most-recently-surveyed anchor wins.

Memory: the connectivity graph (NetworkX) may consume 500 MB–1.5 GB for 652k nodes
and 1–5M edges. Acceptable for a one-shot pipeline; do not run inside a web worker.

Idempotent: resets all five f_* columns to NULL for active candidates first.
Prerequisites: snap_ara_to_candidates.py and build_connectivity.py must have run.
"""

from __future__ import annotations

import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL

BATCH_SIZE      = 500
MAX_BFS_DEPTH   = 5
DISCOUNT_FACTOR = 0.7

SPECULATIVE_PRIOR: dict[str, float] = {
    "polygon": 0.3,
}
DEFAULT_PRIOR = 0.2  # reach_segment, reach_full, unknown types

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

RESET_SQL = text("""
    UPDATE candidates
    SET f_score = NULL, f_confidence = NULL, f_species = NULL,
        f_inferred_from_ara_id = NULL, f_graph_distance = NULL
    WHERE is_active = TRUE
""")

SPECIES_SQL = text("SELECT species_name, weight FROM species_values")

ARA_SQL = text("""
    SELECT ara_id, snapped_candidate_id, fish_species_summary, survey_date
    FROM ara_points
    WHERE snapped_candidate_id IS NOT NULL
      AND fish_species_summary IS NOT NULL
      AND fish_species_summary <> ''
    ORDER BY survey_date DESC NULLS LAST
""")

EDGES_SQL = text("SELECT from_candidate_id, to_candidate_id FROM candidate_edges")

CANDIDATES_SQL = text("""
    SELECT id, candidate_type FROM candidates WHERE is_active = TRUE ORDER BY id
""")

UPDATE_SQL = text("""
    UPDATE candidates
    SET f_score                = :f_score,
        f_confidence           = :f_confidence,
        f_species              = :f_species,
        f_inferred_from_ara_id = :f_inferred_from_ara_id,
        f_graph_distance       = :f_graph_distance
    WHERE id = :id
""")

LOG_SQL = text("""
    SELECT fmz_zone, f_confidence,
           COUNT(*)                         AS n,
           ROUND(AVG(f_score)::numeric, 3)  AS avg_f,
           ROUND(MAX(f_score)::numeric, 3)  AS max_f
    FROM candidates
    WHERE is_active = TRUE
    GROUP BY fmz_zone, f_confidence
    ORDER BY fmz_zone, f_confidence
""")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Anchor:
    species_set:    set   = field(default_factory=set)  # lowercase tokens
    latest_ara_id:  str   = ""
    raw_score:      float = 0.0   # computed in pass 2
    f_score:        float = 0.0   # computed in pass 2
    f_species:      str   = ""    # computed in pass 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_species_weights(conn) -> dict[str, float]:
    rows = conn.execute(SPECIES_SQL).fetchall()
    return {row.species_name: float(row.weight) for row in rows}


def build_ara_map(
    conn,
    species_weights: dict[str, float],
    max_plausible: float,
) -> tuple[dict[int, Anchor], Counter, dict[str, str]]:
    """Return (ara_map, unknown_counter, species_case_map).

    ara_map: candidate_id → Anchor (zero-score anchors excluded).
    unknown_counter: global Counter of species tokens absent from species_values.
    species_case_map: lowercase token → original-case string from fish_species_summary.
    """
    rows = conn.execute(ARA_SQL).fetchall()
    print(f"  ara_points with snap:            {len(rows):,}")

    raw_map:          dict[int, Anchor] = {}
    unknown_counter:  Counter           = Counter()
    species_case_map: dict[str, str]    = {}

    # Pass 1 — union species across all ARA rows per candidate
    for row in rows:
        cand_id     = row.snapped_candidate_id
        tokens_orig = [s.strip() for s in row.fish_species_summary.split(",") if s.strip()]

        for tok_orig in tokens_orig:
            tok_lower = tok_orig.lower()
            if tok_lower not in species_case_map:
                species_case_map[tok_lower] = tok_orig
            if tok_lower not in species_weights:
                unknown_counter[tok_lower] += 1

        if cand_id not in raw_map:
            raw_map[cand_id] = Anchor(latest_ara_id=row.ara_id)

        for tok_orig in tokens_orig:
            raw_map[cand_id].species_set.add(tok_orig.lower())

    # Pass 2 — compute raw_score from full union; drop zero-score anchors
    ara_map: dict[int, Anchor] = {}
    for cand_id, anchor in raw_map.items():
        anchor.raw_score = sum(
            species_weights[tok]
            for tok in anchor.species_set
            if tok in species_weights
        )
        if anchor.raw_score == 0:
            # All species unrecognised — don't anchor; candidate falls to speculative
            # (zero-score anchor would propagate 0 * 0.7^d to neighbors, worse than prior)
            continue

        anchor.f_score = min(anchor.raw_score / max_plausible, 1.0)

        known   = sorted(
            (tok for tok in anchor.species_set if tok in species_weights),
            key=lambda t: -species_weights[t],
        )
        unknown_in_set = sorted(tok for tok in anchor.species_set if tok not in species_weights)
        anchor.f_species = ", ".join(
            species_case_map.get(t, t) for t in known + unknown_in_set
        )
        ara_map[cand_id] = anchor

    return ara_map, unknown_counter, species_case_map


def build_graph(conn) -> nx.Graph:
    t0   = time.monotonic()
    rows = conn.execute(EDGES_SQL).fetchall()
    G    = nx.Graph()
    G.add_edges_from((row.from_candidate_id, row.to_candidate_id) for row in rows)
    elapsed = time.monotonic() - t0
    print(
        f"  graph:                           "
        f"{G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges  ({elapsed:.0f}s)"
    )
    return G


def multi_source_bfs(
    G: nx.Graph,
    ara_map: dict[int, Anchor],
) -> dict[int, tuple[int, int]]:
    """BFS from all anchored candidates simultaneously.

    Returns {candidate_id: (hop_distance, source_candidate_id)}.
    Seeds are processed in ara_map insertion order (survey_date DESC → most-recent
    survey wins equidistant tiebreaks via FIFO).
    """
    visited: dict[int, tuple[int, int]] = {}
    queue:   deque                       = deque()

    for node in ara_map:
        visited[node] = (0, node)
        queue.append((node, node, 0))

    while queue:
        current, source, depth = queue.popleft()
        if depth >= MAX_BFS_DEPTH:
            continue
        for neighbor in G.neighbors(current):
            if neighbor not in visited:
                visited[neighbor] = (depth + 1, source)
                queue.append((neighbor, source, depth + 1))

    return visited


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def score(engine) -> None:
    with engine.connect() as conn:
        # --- sanity checks ---
        ara_total   = conn.execute(text("SELECT COUNT(*) FROM ara_points")).scalar()
        ara_snapped = conn.execute(
            text("SELECT COUNT(*) FROM ara_points WHERE snapped_candidate_id IS NOT NULL")
        ).scalar()
        edge_count  = conn.execute(text("SELECT COUNT(*) FROM candidate_edges")).scalar()
        spec_count  = conn.execute(text("SELECT COUNT(*) FROM species_values")).scalar()

        if spec_count == 0:
            raise RuntimeError("species_values table is empty — run ingest/species_values.py first")

        print(f"  ara_points total:                {ara_total:,}")
        print(f"  ara_points snapped:              {ara_snapped:,}")
        print(f"  candidate_edges:                 {edge_count:,}")
        if ara_snapped == 0:
            print("  WARNING: no ARA points are snapped — all candidates will be speculative")
        if edge_count == 0:
            print("  WARNING: candidate_edges is empty — BFS will not propagate")

        # --- Phase 1: species weights ---
        print("Loading species weights...")
        species_weights = load_species_weights(conn)
        max_plausible   = sum(sorted(species_weights.values(), reverse=True)[:5])
        print(f"  species:                         {len(species_weights):,}")
        print(f"  MAX_PLAUSIBLE (top-5 sum):       {max_plausible:.1f}")

        # --- Phase 2: ARA anchor map ---
        print("Building ARA anchor map...")
        t0 = time.monotonic()
        ara_map, unknown_counter, species_case_map = build_ara_map(
            conn, species_weights, max_plausible
        )
        print(f"  candidates anchored:             {len(ara_map):,}  ({time.monotonic() - t0:.0f}s)")
        if unknown_counter:
            print("  WARNING — unknown species (not in species_values), by frequency:")
            for tok, cnt in unknown_counter.most_common():
                display = species_case_map.get(tok, tok)
                print(f"    \"{display}\": {cnt}x")

        # --- Phase 3 (scores are already on Anchor objects from build_ara_map) ---

        # --- Phase 4: connectivity graph ---
        print("Building connectivity graph...")
        G = build_graph(conn)

        # --- Phase 5: multi-source BFS ---
        # Ensure isolated anchors (ARA point but no candidate_edges) are in the graph.
        # add_edges_from only adds nodes that appear in edge rows; isolated anchors are missing.
        G.add_nodes_from(ara_map.keys())
        print(f"Running multi-source BFS (depth ≤ {MAX_BFS_DEPTH})...")
        t1 = time.monotonic()
        bfs_visited = multi_source_bfs(G, ara_map)
        print(f"  elapsed:                         {time.monotonic() - t1:.0f}s")
        del G  # release ~500 MB–1.5 GB before loading candidates

        # --- Phase 6: load candidates and assemble records ---
        print("Scoring all active candidates...")
        candidates = conn.execute(CANDIDATES_SQL).fetchall()

    strong_count = plausible_count = speculative_count = 0
    records: list[dict[str, Any]] = []

    for row in candidates:
        cand_id   = row.id
        cand_type = row.candidate_type
        prior     = SPECULATIVE_PRIOR.get(cand_type, DEFAULT_PRIOR)

        if cand_id in ara_map:
            anchor = ara_map[cand_id]
            records.append({
                "id":                    cand_id,
                "f_score":               anchor.f_score,
                "f_confidence":          "strong",
                "f_species":             anchor.f_species or None,
                "f_inferred_from_ara_id": anchor.latest_ara_id,
                "f_graph_distance":      0,
            })
            strong_count += 1

        elif cand_id in bfs_visited:
            dist, source = bfs_visited[cand_id]
            source_anchor = ara_map[source]
            discounted    = source_anchor.f_score * (DISCOUNT_FACTOR ** dist)
            f_score       = max(min(discounted, 1.0), prior)
            records.append({
                "id":                    cand_id,
                "f_score":               f_score,
                "f_confidence":          "plausible",
                "f_species":             source_anchor.f_species or None,
                "f_inferred_from_ara_id": source_anchor.latest_ara_id,
                "f_graph_distance":      dist,
            })
            plausible_count += 1

        else:
            records.append({
                "id":                    cand_id,
                "f_score":               prior,
                "f_confidence":          "speculative",
                "f_species":             None,
                "f_inferred_from_ara_id": None,
                "f_graph_distance":      None,
            })
            speculative_count += 1

    print(
        f"  strong: {strong_count:,}  "
        f"plausible: {plausible_count:,}  "
        f"speculative: {speculative_count:,}"
    )

    # --- Phase 7: reset + batch UPDATE ---
    print("Writing f_score to database...")
    t2 = time.monotonic()
    with engine.begin() as conn:
        conn.execute(RESET_SQL)
        for i in range(0, len(records), BATCH_SIZE):
            conn.execute(UPDATE_SQL, records[i : i + BATCH_SIZE])
    print(f"  elapsed:                         {time.monotonic() - t2:.0f}s")

    with engine.connect() as conn:
        log_rows = conn.execute(LOG_SQL).fetchall()

    if log_rows:
        print(f"\n  {'fmz_zone':<10} {'confidence':<12} {'n':>8} {'avg_f':>7} {'max_f':>7}")
        for row in log_rows:
            print(
                f"  {row.fmz_zone:<10} {(row.f_confidence or 'NULL'):<12} {row.n:>8,}"
                f" {row.avg_f:>7} {row.max_f:>7}"
            )


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    score(engine)
