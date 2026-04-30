import os
from pathlib import Path

# Repo root (one level above backend/)
REPO_ROOT = Path(__file__).parent.parent

# Raw data paths
OHN_WATERBODY_DIR = REPO_ROOT / "phase-0-data/ohn/Ontario_Hydro_Network_(OHN)_-_Waterbody"
OHN_WATERCOURSE_DIR = REPO_ROOT / "phase-0-data/ohn/Ontario_Hydro_Network_(OHN)_-_Watercourse"

# Test region: ~20 km radius around Rouge National Urban Park, Scarborough, ON
# (minx, miny, maxx, maxy) in WGS84/NAD83 lon/lat
TEST_BBOX = (-79.367, 43.720, -78.935, 43.937)

# Corner coordinates preserved from original config (lat, lon order)
topLeft = '43.851098624890895, -79.36722485549986'
topRight = '43.936996398203384, -79.04603501687743'
bottomLeft = '43.71967675630277, -79.24353684315543'
bottomRight = '43.859370326223996, -78.93481555409967'

CACHE_DIR = REPO_ROOT / "cache"
ROADS_CACHE_PATH = CACHE_DIR / "roads_bbox.graphml"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://hiddenhooks:hiddenhooks@localhost:5432/hiddenhooks",
)