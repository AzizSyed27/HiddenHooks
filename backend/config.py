import os
from pathlib import Path

# Repo root (one level above backend/)
REPO_ROOT = Path(__file__).parent.parent

# Raw data paths
OHN_WATERBODY_DIR = REPO_ROOT / "phase-0-data/ohn/Ontario_Hydro_Network_(OHN)_-_Waterbody"
OHN_WATERCOURSE_DIR = REPO_ROOT / "phase-0-data/ohn/Ontario_Hydro_Network_(OHN)_-_Watercourse"
FMZ_DIR = REPO_ROOT / "data/fmz/Fisheries_Management_Zone"
ONTARIO_BOUNDARY_DIR = REPO_ROOT / "data/ontario_boundary/Province"
GREAT_LAKES_DIR = REPO_ROOT / "data/great_lakes/ne_10m_lakes"

#Keeping testbox and corner coordinates as fallbacks.
# Test region: ~20 km radius around Rouge National Urban Park, Scarborough, ON
# (minx, miny, maxx, maxy) in WGS84/NAD83 lon/lat — keep for fast iteration
# during scoring development; full FMZ pipeline is slow.
TEST_BBOX = (-79.367, 43.720, -78.935, 43.937)

# Corner coordinates preserved from original config (lat, lon order)                                                   
topLeft = '43.851098624890895, -79.36722485549986'                                                                     
topRight = '43.936996398203384, -79.04603501687743'                                                                    
bottomLeft = '43.71967675630277, -79.24353684315543'                                                                   
bottomRight = '43.859370326223996, -78.93481555409967' 

# Bounding boxes derived from actual FMZ polygon vertices in the regions table,
# transformed to WGS84 per-vertex (not as projected rectangles, which skew on re-projection).
# Format: (minx, miny, maxx, maxy) i.e. (min_lon, min_lat, max_lon, max_lat)
FMZ16_BBOX = (-83.1173, 41.9094, -78.9081, 45.2666)
FMZ17_BBOX = (-79.2382, 43.7945, -77.5475, 44.7833)

# Union of FMZ 16 and FMZ 17 extents.
COMBINED_BBOX = (-83.1173, 41.9094, -77.5475, 45.2666)

# Combined bbox expanded by 5 km (in EPSG:3161, then converted to WGS84) so that
# candidates near either FMZ boundary aren't artificially far from any road.
ROADS_BBOX = (-83.1859, 41.7160, -77.4188, 45.3463)

# Tunable: length of each reach_segment child created during Part 3 segmentation.
SEGMENT_LENGTH_M = 200

CACHE_DIR = REPO_ROOT / "cache"
ROADS_CACHE_PATH = CACHE_DIR / "roads_fmz_combined.graphml"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://hiddenhooks:hiddenhooks@localhost:5432/hiddenhooks",
)