"""Phase 3: cost test for exporting the single-sensor subsets as small rectangles.

S4 2015 cost 28.8 EECU-hours instead of the area-scaled 8. Its export region was the whole
province bounding box, and masking to the sampled chunks did not stop Earth Engine computing the
masked pixels. This test exports the 2015 subset bands for

  one  a single 512 x 512 chunk, its own rectangle as the region
  four a 2 x 2 block of adjacent chunks (the single chunk is its upper left), one rectangle

so per-task overhead and per-area cost can be separated:
  cost = overhead + rate x chunks.

All four chunks lie fully inside the province, so the province mask does not change the area.

Run:
  conda run -n rs-trends python src/03_subset_region_test.py --submit
  conda run -n rs-trends python src/03_subset_region_test.py --status
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

from rstrends import tasklog
from rstrends.config import data_dir, ee_project, load_config

YEAR = 2015  # ETM+ and OLI both fly, the same year as the S4 2015 measurement
GROUP = "T2"


def pick_block(chunks: pd.DataFrame, size: int = 512) -> list[str]:
    """First 2 x 2 block of chunks fully inside the province, preferring sampled corners."""
    full = chunks[(chunks.inside >= 1.0) & (chunks.w == size) & (chunks.h == size)]
    have = set(zip(full.row_off, full.col_off, strict=True))
    for r in full.sort_values(["sampled", "key"], ascending=[False, True]).itertuples():
        block = [(r.row_off + dr, r.col_off + dc) for dr in (0, size) for dc in (0, size)]
        if all(b in have for b in block):
            return [f"r{ro:06d}_c{co:06d}" for ro, co in block]
    raise SystemExit("no 2 x 2 block of full chunks found")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--status", action="store_true")
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
        if tasklog.read(log_path, GROUP):
            raise SystemExit("region test already submitted. Use --status.")
        chunks_csv = root / "interim" / "subset_chunks.csv"
        block = pick_block(pd.read_csv(chunks_csv))
        harm = json.loads(
            (root / "outputs" / "harmonization" / "coefficients.json").read_text(encoding="utf-8")
        )
        fc = gee.province(gpkg)
        filt = gee.filter_geometry(gpkg, cfg["export"]["filter_buffer_m"])
        wkt, transform = gee.grid(cfg)
        tests = {"one": block[:1], "four": block}
        meta = {"year": YEAR, "tests": tests}
        (root / "logs" / "subset_region_test.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        for name, keys in tests.items():
            sample = gee.sample_chunks_fc(cfg, chunks_csv, keys=keys)
            img = gee.annual_subsets(cfg, YEAR, fc, sample, filt, harm)
            img = img.unmask(cfg["export"]["nodata"], False)
            desc = f"T2_subsets_{name}_{YEAR}"
            task = ee.batch.Export.image.toDrive(
                image=img,
                description=desc,
                folder=f"{cfg['export']['drive_folder_prefix']}T",
                fileNamePrefix=desc,
                region=sample.geometry().bounds(1, ee.Projection(wkt)),
                crs=wkt,
                crsTransform=transform,
                maxPixels=int(1e9),
                fileFormat="GeoTIFF",
                formatOptions={"cloudOptimized": False, "noData": cfg["export"]["nodata"]},
            )
            task.start()
            tasklog.append(log_path, GROUP, desc, task.id)
            print(f"ok   submitted {desc} ({task.id}), chunks {', '.join(keys)}")

    if args.status:
        for row in tasklog.read(log_path, GROUP):
            s = gee.operation_summary(project, row["task_id"])
            hrs = tasklog.eecu_hours(s["eecu_seconds"])
            eecu = f"{hrs:.3f} EECU-h" if hrs is not None else "n/a"
            print(f"{row['description']:<24} {s['state']:<10} {eecu}")


if __name__ == "__main__":
    main()
