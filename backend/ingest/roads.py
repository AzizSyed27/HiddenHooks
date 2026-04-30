"""Download OSM road network for the test bbox, project to EPSG:3161, store in roads table."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import osmnx as ox
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CACHE_DIR, DATABASE_URL, ROADS_CACHE_PATH, TEST_BBOX

NETWORK_TYPE = "drive"

INSERT_SQL = text("""
    INSERT INTO roads (osm_id, name, highway, geom)
    VALUES (
        :osm_id, :name, :highway,
        ST_GeomFromWKB(decode(:geom, 'hex'), 3161)
    )
""")


def download_or_load(
    bbox: tuple[float, float, float, float],
    cache_path: Path,
    network_type: str,
) -> Any:
    if cache_path.exists():
        print(f"  loading graph from cache: {cache_path}")
        return ox.io.load_graphml(filepath=cache_path)

    print("  downloading road network from OSM...")
    G = ox.graph_from_bbox(bbox=bbox, network_type=network_type)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ox.io.save_graphml(G, filepath=cache_path)
    print(f"  cached to {cache_path}")
    return G


def ingest(engine) -> None:
    print("Loading road network...")
    G = download_or_load(TEST_BBOX, ROADS_CACHE_PATH, NETWORK_TYPE)

    G_proj = ox.project_graph(G, to_crs="EPSG:3161")
    edges = ox.graph_to_gdfs(G_proj, nodes=False, edges=True)
    print(f"  edges after projection:          {len(edges):,}")

    rows: list[dict[str, Any]] = [
        {
            "osm_id": str(row.osmid),
            "name": row.name if isinstance(row.name, str) and row.name.strip() else None,
            "highway": str(row.highway) if hasattr(row, "highway") else None,
            "geom": row.geometry.wkb_hex,
        }
        for row in edges.itertuples(index=False)
    ]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM roads"))
        for i in range(0, len(rows), 500):
            conn.execute(INSERT_SQL, rows[i : i + 500])

    print(f"  inserted:                        {len(rows):,}")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    ingest(engine)
