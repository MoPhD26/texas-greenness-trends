"""Phase 3: one-tile Earth Engine cost test of the export design variants.

Exports the same tile and year four ways and records EECU-hours per variant:
  A  current pilot design: 3 indices, 3 sub-season counts, acquisition count, five passes,
     scenes filtered by the province bounding box
  B  outline filter (buffered province polygon), scenes over the cloud limit skipped,
     single map over the scenes, 3 indices and 3 counts
  C  B with EVI2 only
  D  C plus the single-sensor subset bands folded in (the revision 4 production design)
  E  revision 6 production design: A's computation (3 indices, one pass per count) with the
     outline filter, the cloud skip, the folded subset bands, and the final group harmonization

The tile straddles the province edge, so the outline filter's effect is included.

Run:
  conda run -n rs-trends python src/03_cost_test.py --submit
  conda run -n rs-trends python src/03_cost_test.py --status
"""

from __future__ import annotations

import argparse
import json
import math

import geopandas as gpd
import pyproj
import shapely

from rstrends import tasklog
from rstrends.config import data_dir, ee_project, load_config

YEAR = 2015  # Landsat 7 and 8 both fly, so both subsets apply
TILE_PX = 3072
TARGET_FRACTION = 0.5  # share of the tile inside the province


def pick_tile(poly, transform, size_px):
    """Chunk-aligned tile whose province share is closest to TARGET_FRACTION."""
    a, _, x0, _, e, y0 = transform
    step = size_px * a
    xmin, ymin, xmax, ymax = poly.bounds
    c0 = math.floor((xmin - x0) / step)
    r0 = math.floor((y0 - ymax) / step)
    best = None
    cx, cy = poly.centroid.x, poly.centroid.y
    for c in range(c0, c0 + int((xmax - xmin) / step) + 2):
        for r in range(r0, r0 + int((ymax - ymin) / step) + 2):
            ulx, uly = x0 + c * step, y0 - r * step
            box = shapely.box(ulx, uly - step, ulx + step, uly)
            frac = poly.intersection(box).area / box.area
            score = abs(frac - TARGET_FRACTION) + box.centroid.distance(shapely.Point(cx, cy)) / 1e7
            if best is None or score < best[0]:
                best = (score, ulx, uly, frac)
    return best[1], best[2], best[3]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument(
        "--rerun",
        metavar="TAG",
        help="submit the same four variants again with this tag in their names (for a clean rerun)",
    )
    ap.add_argument("--variants", default="ABCD", help="variants to submit, for example E")
    args = ap.parse_args()

    cfg = load_config()
    root = data_dir(cfg)
    log_path = root / "logs" / "ee_tasks.csv"
    gpkg = root / "raw" / "boundary" / "province255.gpkg"

    import ee

    from rstrends import gee

    project = ee_project()
    gee.initialize(project)

    if args.submit:
        tag = f"_{args.rerun}" if args.rerun else ""
        live = [
            r["description"]
            for r in tasklog.read(log_path, "T")
            if r["description"].endswith(f"_{YEAR}{tag}")
            and gee.operation_summary(project, r["task_id"])["state"] not in ("FAILED", "CANCELLED")
        ]
        if live:
            raise SystemExit(f"cost test already submitted and not failed: {live}. Use --status.")
        wkt, transform = gee.grid(cfg)
        crs = pyproj.CRS.from_wkt(wkt)
        poly = gpd.read_file(gpkg).to_crs(crs).geometry.iloc[0]
        ulx, uly, frac = pick_tile(poly, transform, TILE_PX)
        step = TILE_PX * transform[0]
        region = ee.Geometry.Rectangle(
            [ulx, uly - step, ulx + step, uly], ee.Projection(wkt), False
        )
        harm = json.loads(
            # Cost does not depend on coefficient values, so the provisional set is fine here.
            (
                root
                / "outputs"
                / "harmonization"
                / "coefficients_provisional_2013_mismatched_window.json"
            ).read_text(encoding="utf-8")
        )
        fc = gee.province(gpkg)
        filt = gee.filter_geometry(gpkg, cfg["export"]["filter_buffer_m"])
        three = ["evi2", "nirv", "kndvi"]
        final = json.loads(
            (root / "outputs" / "harmonization" / "coefficients.json").read_text(encoding="utf-8")
        )
        builders = {
            "A": lambda: gee.annual_composite(cfg, YEAR, fc, harm),
            "B": lambda: gee.annual_composite_single_pass(
                cfg, YEAR, fc, filt, harm, indices=three, subsets=False
            ),
            "C": lambda: gee.annual_composite_single_pass(
                cfg, YEAR, fc, filt, harm, indices=["evi2"], subsets=False
            ),
            "D": lambda: gee.annual_composite_single_pass(cfg, YEAR, fc, filt, harm),
            "E": lambda: gee.annual_composite_production(cfg, YEAR, fc, filt, final),
        }
        variants = {k: builders[k]() for k in args.variants}
        meta = {"year": YEAR, "tile_px": TILE_PX, "upper_left": [ulx, uly], "fraction": frac}
        (root / "logs" / "cost_test.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"     tile {TILE_PX} px at {ulx:.0f}, {uly:.0f}, {frac:.0%} inside the province")
        for name, img in variants.items():
            desc = f"T_cost_{name}_{YEAR}{tag}"
            task = ee.batch.Export.image.toDrive(
                image=img,
                description=desc,
                folder=f"{cfg['export']['drive_folder_prefix']}T",
                fileNamePrefix=f"cost_{name}_{YEAR}{tag}",
                region=region,
                crs=wkt,
                crsTransform=transform,
                maxPixels=int(1e10),
                fileFormat="GeoTIFF",
                formatOptions={"cloudOptimized": True, "noData": cfg["export"]["nodata"]},
            )
            task.start()
            tasklog.append(log_path, "T", desc, task.id)
            print(f"ok   submitted {desc} ({task.id})")

    if args.status:
        for row in tasklog.read(log_path, "T"):
            s = gee.operation_summary(project, row["task_id"])
            hrs = tasklog.eecu_hours(s["eecu_seconds"])
            eecu = f"{hrs:.3f} EECU-h" if hrs is not None else "n/a"
            print(f"{row['description']:<18} {s['state']:<10} {eecu}")


if __name__ == "__main__":
    main()
