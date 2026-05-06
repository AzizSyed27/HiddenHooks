"""Validate and clip the SOLRIS 3.0 landcover raster for use in ecology scoring.

Does NOT write to the database — the raster stays on disk. This script:
  1. Locates the SOLRIS GeoTIFF in SOLRIS_DIR
  2. Checks CRS and spatial coverage against COMBINED_BBOX
  3. Clips to COMBINED_BBOX + 200 m padding and saves to SOLRIS_CACHE_PATH
  4. Prints the full class-code inventory (pixel counts + %) and nodata value
  5. Prints a verification gate with the SOLRIS legend URL

Always run this before score_ecology.py, and confirm the class codes in config.py
match the official SOLRIS legend before scoring.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pyproj
import rasterio
from rasterio.mask import mask as rio_mask
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    CACHE_DIR,
    COMBINED_BBOX,
    FOREST_CODES,
    SOLRIS_CACHE_PATH,
    SOLRIS_DIR,
    WETLAND_CODES,
)

BBOX_PADDING_M = 200  # extra metres beyond COMBINED_BBOX so 100m buffers near the edge are covered


def find_tif(directory: Path) -> Path:
    tifs = list(directory.glob("*.tif")) + list(directory.glob("*.tiff"))
    if not tifs:
        raise FileNotFoundError(
            f"No .tif / .tiff found in {directory}.\n"
            "Download SOLRIS 3.0 from Ontario GeoHub and place it in that directory."
        )
    return tifs[0]


def combined_bbox_in_crs(target_crs) -> tuple[float, float, float, float]:
    """Return COMBINED_BBOX (WGS84) reprojected to target_crs as (minx, miny, maxx, maxy)."""
    transformer = pyproj.Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    minx, miny = transformer.transform(COMBINED_BBOX[0], COMBINED_BBOX[1])
    maxx, maxy = transformer.transform(COMBINED_BBOX[2], COMBINED_BBOX[3])
    return minx, miny, maxx, maxy


def class_inventory(tif_path: Path, nodata) -> Counter:
    counts: Counter = Counter()
    with rasterio.open(tif_path) as src:
        for _, window in src.block_windows(1):
            data = src.read(1, window=window).flatten()
            unique, ucounts = np.unique(data, return_counts=True)
            for v, c in zip(unique.tolist(), ucounts.tolist()):
                counts[v] += c
    if nodata is not None:
        counts.pop(int(nodata), None)
    return counts


def validate_and_clip() -> None:
    tif_path = find_tif(SOLRIS_DIR)
    print(f"Validating SOLRIS raster: {tif_path.name}")

    with rasterio.open(tif_path) as src:
        crs    = src.crs
        nodata = src.nodata
        res    = src.res          # (pixel_width, pixel_height) in CRS units
        bounds = src.bounds

    print(f"  CRS:      {crs}")
    print(f"  nodata:   {nodata!r}  ← confirm this matches rasterstats nodata= before scoring")
    print(f"  res:      {res[0]:.1f} × {res[1]:.1f} m")
    print(f"  bounds:   ({bounds.left:.0f}, {bounds.bottom:.0f}, {bounds.right:.0f}, {bounds.top:.0f})")

    # Reproject COMBINED_BBOX into raster CRS for coverage check
    minx, miny, maxx, maxy = combined_bbox_in_crs(crs)
    covers = (
        bounds.left  <= minx and bounds.bottom <= miny
        and bounds.right >= maxx and bounds.top   >= maxy
    )
    print(f"  covers COMBINED_BBOX: {'YES' if covers else 'WARNING — raster does not fully cover COMBINED_BBOX'}")

    # Clip to COMBINED_BBOX + padding
    if SOLRIS_CACHE_PATH.exists():
        print(f"\nCached raster already exists: {SOLRIS_CACHE_PATH}")
        print("  Delete it to force re-clip.")
    else:
        clip_geom = box(
            minx - BBOX_PADDING_M, miny - BBOX_PADDING_M,
            maxx + BBOX_PADDING_M, maxy + BBOX_PADDING_M,
        )
        print(f"\nClipping to COMBINED_BBOX + {BBOX_PADDING_M}m padding → {SOLRIS_CACHE_PATH.name} ...")
        t0 = time.monotonic()
        with rasterio.open(tif_path) as src:
            out_image, out_transform = rio_mask(
                src, [clip_geom.__geo_interface__], crop=True
            )
            out_meta = src.meta.copy()

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        out_meta.update({
            "driver":    "GTiff",
            "height":    out_image.shape[1],
            "width":     out_image.shape[2],
            "transform": out_transform,
        })
        with rasterio.open(SOLRIS_CACHE_PATH, "w", **out_meta) as dst:
            dst.write(out_image)

        elapsed = time.monotonic() - t0
        print(f"  elapsed: {elapsed:.0f}s")
        print(f"  size:    {out_image.shape[2]} × {out_image.shape[1]} pixels")

    # Class inventory
    print("\nClass inventory (clipped raster, nodata excluded):")
    counts = class_inventory(SOLRIS_CACHE_PATH, nodata)
    total  = sum(counts.values())

    print(f"  {'value':>6}  {'count':>12}  {'pct':>6}")
    for v, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        pct = 100 * c / total if total else 0
        print(f"  {v:>6}  {c:>12,}  {pct:>5.1f}%")

    target_codes = set(FOREST_CODES) | set(WETLAND_CODES)
    target_px    = sum(counts.get(c, 0) for c in target_codes)
    forest_px    = sum(counts.get(c, 0) for c in FOREST_CODES)
    wetland_px   = sum(counts.get(c, 0) for c in WETLAND_CODES)

    print(f"\nConfigured FOREST_CODES  {FOREST_CODES}  →  {forest_px:,} px  ({100 * forest_px / total:.1f}%)")
    print(f"Configured WETLAND_CODES {WETLAND_CODES}  →  {wetland_px:,} px  ({100 * wetland_px / total:.1f}%)")
    print(f"Combined forest+wetland  →  {target_px:,} px  ({100 * target_px / total:.1f}%)")

    # Verification gate
    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  VERIFICATION GATE — do this before running score_ecology.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Cross-reference the class inventory above with the official SOLRIS 3.0 legend:
       https://geohub.lio.gov.on.ca/maps/mnrf::solris-3-0/about
     → Click "Download" or "Attribute Table" to get the full class-code legend PDF.

  2. Confirm FOREST_CODES and WETLAND_CODES in backend/config.py match the legend.
     Correct them if the codes above don't line up with forested/wetland classes.

  3. Confirm the nodata value shown above matches the nodata= kwarg in score_ecology.py.
     (Default assumption: nodata=0. Update if the raster uses a different sentinel.)

  4. Once verified, run: python -m scoring.score_ecology
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")


if __name__ == "__main__":
    validate_and_clip()
