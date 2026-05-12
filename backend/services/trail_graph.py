"""
In-memory trail routing graph, built once at uvicorn startup.

Source: the `trails` table, filtered to OSM `highway IN ('path', 'track')`.
Hiking-relevant classes only — `footway` and `cycleway` (sidewalks, bike paths)
are excluded; they're already credited via the Phase 2 accessibility score.

Vertex deduplication uses a 5m × 5m spatial hash (cell size = SNAP_TOLERANCE_M
from config, same value as the Phase 2 water-connectivity snap). For each
LineString vertex we look up its home cell **and the 8 surrounding cells** — a
9-cell neighbourhood — so two vertices within 5m always resolve to the same
node, regardless of how floor() boundaries fall.

Edge attributes:
    length: Euclidean distance in EPSG:3161 metres between canonical node positions.
    class:  the OSM `highway` value of the LineString that contributed the edge.
            If the same node pair is offered by multiple LineStrings, the shorter
            candidate wins and its class is kept.

`find_nearest_trail_node` uses a `scipy.spatial.cKDTree` built once after graph
construction — O(log N) per query so the Part 5 walk-time endpoint stays cheap.

Memory cost: at ~80k edges, NetworkX overhead lands in the 150–300 MB range.
Acceptable for the personal-use process. The graph is rebuilt from scratch on
every uvicorn startup; there is no on-disk cache.
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point
from sqlalchemy import text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SNAP_TOLERANCE_M  # noqa: E402

# Module-level state. Populated by build_trail_graph.
_graph: nx.Graph | None = None
_kdtree: cKDTree | None = None
_node_ids: list[int] | None = None

_CELL_SIZE_M: float = SNAP_TOLERANCE_M
_NEAREST_NODE_MAX_DIST_M: float = 5000.0

_TOTAL_COUNT_SQL = text("SELECT COUNT(*) FROM trails")
_FILTERED_COUNT_SQL = text(
    "SELECT COUNT(*) FROM trails WHERE highway IN ('path', 'track')"
)
_TRAILS_GEOM_SQL = "SELECT id, highway, geom FROM trails WHERE highway IN ('path', 'track')"


def build_trail_graph(engine: Engine) -> None:
    """Build the trail routing graph and stash it at module level.

    Raises:
        RuntimeError: if the trails table has zero rows matching the filter
                      (data not ingested — run ingest.trails_and_parking first).
    """
    global _graph, _kdtree, _node_ids

    print("Building trail graph...")
    t0 = time.perf_counter()

    with engine.connect() as conn:
        total_rows = conn.execute(_TOTAL_COUNT_SQL).scalar() or 0
        filtered_rows = conn.execute(_FILTERED_COUNT_SQL).scalar() or 0

    if filtered_rows == 0:
        raise RuntimeError(
            "trails table has zero rows with highway IN ('path', 'track'). "
            "Run `python -m ingest.trails_and_parking` from backend/ before starting the API."
        )

    gdf = gpd.read_postgis(_TRAILS_GEOM_SQL, engine, geom_col="geom")

    G: nx.Graph = nx.Graph()
    buckets: dict[tuple[int, int], list[tuple[int, float, float]]] = {}
    next_id = 0
    tol_sq = SNAP_TOLERANCE_M * SNAP_TOLERANCE_M

    def find_or_create_node(x: float, y: float) -> int:
        nonlocal next_id
        cx = int(math.floor(x / _CELL_SIZE_M))
        cy = int(math.floor(y / _CELL_SIZE_M))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for nid, vx, vy in buckets.get((cx + dx, cy + dy), ()):
                    if (x - vx) * (x - vx) + (y - vy) * (y - vy) <= tol_sq:
                        return nid
        nid = next_id
        next_id += 1
        buckets.setdefault((cx, cy), []).append((nid, x, y))
        G.add_node(nid, pos=(x, y))
        return nid

    for line, hwy in zip(gdf.geometry, gdf.highway):
        prev_nid: int | None = None
        for x, y in line.coords:
            nid = find_or_create_node(float(x), float(y))
            if prev_nid is not None and prev_nid != nid:
                px, py = G.nodes[prev_nid]["pos"]
                nx_pos, ny_pos = G.nodes[nid]["pos"]
                length = math.hypot(nx_pos - px, ny_pos - py)
                if G.has_edge(prev_nid, nid):
                    if length < G[prev_nid][nid]["length"]:
                        G[prev_nid][nid]["length"] = length
                        G[prev_nid][nid]["class"] = hwy
                else:
                    G.add_edge(prev_nid, nid, length=length, **{"class": hwy})
            prev_nid = nid

    elapsed = time.perf_counter() - t0

    node_ids = list(G.nodes)
    coords = np.array([G.nodes[n]["pos"] for n in node_ids], dtype=float)
    _graph = G
    _kdtree = cKDTree(coords)
    _node_ids = node_ids

    components = list(nx.connected_components(G))
    largest = max(components, key=len) if components else set()
    largest_edges = G.subgraph(largest).number_of_edges() if largest else 0
    isolated = sum(1 for _ in nx.isolates(G))

    print(f"  trails table:                    {total_rows:,} rows")
    print(f"  filtered (path + track):         {filtered_rows:,} rows")
    print(f"  building graph...                ({elapsed:.0f}s)")
    print(f"  nodes:                           {G.number_of_nodes():,}")
    print(f"  edges:                           {G.number_of_edges():,}")
    print(f"  components:                      {len(components):,}")
    print(f"  largest component:               {len(largest):,} nodes / {largest_edges:,} edges")
    print(f"  isolated nodes:                  {isolated:,}")


def get_trail_graph() -> nx.Graph:
    """Return the trail graph built by build_trail_graph. Raises if not yet built."""
    if _graph is None:
        raise RuntimeError(
            "Trail graph has not been built. Call build_trail_graph(engine) first."
        )
    return _graph


def find_nearest_trail_node(point_3161: Point) -> int | None:
    """Return the node ID of the trail-graph node nearest to point_3161, or None
    if no node lies within 5 km of the input.

    The argument must be a Shapely Point in EPSG:3161 (the same CRS the graph
    lives in). Backed by a cKDTree built once during build_trail_graph.
    """
    if _kdtree is None or _node_ids is None:
        raise RuntimeError(
            "Trail graph has not been built. Call build_trail_graph(engine) first."
        )
    dist, idx = _kdtree.query(
        (point_3161.x, point_3161.y),
        distance_upper_bound=_NEAREST_NODE_MAX_DIST_M,
    )
    if math.isinf(dist):
        return None
    return _node_ids[idx]
