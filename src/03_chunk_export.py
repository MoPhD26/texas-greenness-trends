"""Phase 3, December steps 1, 5 and 6: per-chunk exports with years as bands.

One Earth Engine task per sampled chunk (option A, approved 2026-11-27). The export region is the
chunk's own rectangle, so only the chunk's pixels are computed (the S4 lesson: masking a
province-wide region to the chunks did not cut cost). Every task uses the main composites'
CRS and crsTransform, and each chunk's corners are checked to be pixel corners of that grid, so
chunk pixels line up with the main export.

Products:
  subsets  ETM+ only and OLI only EVI2 and sub-season counts, for every subset year not already
           exported (S4 2015-2017 is). 2000-2014 and 2018-2019, 84 bands.
  roy      EVI2 over all sensors for 2000-2019 with the Roy et al. (2016) RMA line for the ETM+
           to OLI step. The study's yearly TM to ETM+ lines are kept, so the comparison isolates
           the ETM+ to OLI step (rstrends.harmonize.roy_variant). 20 bands.

Band names are y<year>_<band> (rstrends.batches.multi_year_bands).

  --dry-run   build every task's image and settings locally and check them. Nothing is sent to
              Earth Engine and no EECU is used (the images are never evaluated).
  --test      submit the one-chunk test (December step 1) for the product
  --submit    submit all 253 tasks for the product. Refused until that product's test finished.
  --status    EECU and state of the product's tasks

Run:
  conda run -n rs-trends python src/03_chunk_export.py --product roy --dry-run
  conda run -n rs-trends python src/03_chunk_export.py --product roy --test
"""

from __future__ import annotations

import argparse
import hashlib
import json

import pandas as pd

from rstrends import tasklog
from rstrends.batches import chunk_product_years, multi_year_bands
from rstrends.config import data_dir, ee_project, load_config
from rstrends.harmonize import roy_variant
from rstrends.sampling import chunk_bounds

TEST_CHUNK = "r002048_c008192"  # fully inside the province, the chunk of the November cost test
GROUPS = {"subsets": "CS", "roy": "CR"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--product", choices=sorted(GROUPS), required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--test", action="store_true")
    mode.add_argument("--submit", action="store_true")
    mode.add_argument("--status", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    root = data_dir(cfg)
    log_path = root / "logs" / "ee_tasks.csv"
    group = GROUPS[args.product]
    years = chunk_product_years(cfg, args.product)
    bands = multi_year_bands(cfg, years, args.product)
    t = [float(v) for v in cfg["grid"]["crs_transform"]]

    chunks = pd.read_csv(root / "interim" / "subset_chunks.csv")
    chunks = chunks[chunks.sampled].reset_index(drop=True)
    for r in chunks.itertuples():  # refuse before anything is built if a corner is off the grid
        chunk_bounds(r.ulx, r.uly, r.w, r.h, t)
    if args.test or args.dry_run:
        run = chunks[chunks.key == TEST_CHUNK] if args.test else chunks
    else:
        run = chunks

    harm_path = root / "outputs" / "harmonization" / "coefficients.json"
    harm = json.loads(harm_path.read_text(encoding="utf-8"))
    want = cfg["harmonization"]["final_coefficients"]
    got = hashlib.sha256(harm_path.read_bytes()).hexdigest()
    if got != want["sha256"] or harm.get("version") != want["version"]:
        raise SystemExit("coefficients.json does not match the config's final version")
    if args.product == "roy":
        harm = roy_variant(harm, cfg["harmonization"]["roy2016_rma"])

    import ee

    from rstrends import gee

    if args.status:
        gee.initialize(ee_project())
        total, n_done = 0.0, 0
        for row in tasklog.read(log_path, group):
            s = gee.operation_summary(ee_project(), row["task_id"])
            hrs = tasklog.eecu_hours(s["eecu_seconds"]) or 0.0
            total += hrs
            n_done += s["state"] == "SUCCEEDED"
            print(f"{row['description']:<34} {s['state']:<10} {hrs:.4f} EECU-h")
        print(f"{group}: {n_done} succeeded, {total:.3f} EECU-hours")
        return

    gee.initialize(ee_project())  # local session only. --dry-run never evaluates anything
    if args.submit:
        tests = [r for r in tasklog.read(log_path, group) if "_test_" in r["description"]]
        ok = [
            r
            for r in tests
            if gee.operation_summary(ee_project(), r["task_id"])["state"] == "SUCCEEDED"
        ]
        if not ok:
            raise SystemExit(f"refusing: the one-chunk {args.product} test has not succeeded")
        if any("_test_" not in r["description"] for r in tasklog.read(log_path, group)):
            raise SystemExit(f"{group} tasks were already submitted. Use --status.")
    elif args.test and tasklog.read(log_path, group):
        raise SystemExit(f"{group} test already submitted. Use --status.")

    gpkg = root / "raw" / "boundary" / "province255.gpkg"
    fc = gee.province(gpkg)
    if args.dry_run:
        wkt = ee.Image(cfg["grid"]["reference_image"]).projection()  # not evaluated
    else:
        # The same CRS WKT and transform check the main exports use (src/03_export.py)
        wkt, t_ee = gee.grid(cfg)
        if t_ee != t:
            raise SystemExit(f"grid transform {t_ee} differs from the config {t}")
    folder = f"{cfg['export']['drive_folder_prefix']}{group}"
    kind = "test" if args.test else "chunk"
    for r in run.itertuples():
        region = gee.chunk_rectangle(cfg, r.ulx, r.uly, r.w, r.h)
        img = gee.chunk_multi_year(cfg, args.product, years, fc, region, harm)
        img = img.unmask(cfg["export"]["nodata"], False)
        desc = f"{group}_{kind}_{r.key}"
        params = dict(
            image=img,
            description=desc,
            folder=folder,
            fileNamePrefix=f"{args.product}_{r.key}",
            region=region,
            crs=wkt,
            crsTransform=t,
            maxPixels=int(1e9),
            fileFormat="GeoTIFF",
            formatOptions={"cloudOptimized": False, "noData": cfg["export"]["nodata"]},
        )
        if args.dry_run:
            continue
        task = ee.batch.Export.image.toDrive(**params)
        task.start()
        tasklog.append(log_path, group, desc, task.id)
        print(f"ok   submitted {desc} ({task.id}) to Drive folder {folder}")

    if args.dry_run:
        print(f"dry run, {args.product}: {len(run)} chunk tasks built, none sent")
        print(f"years: {years[0]}-{years[-1]} ({len(years)}), bands per file: {len(bands)}")
        print(f"first bands: {', '.join(bands[:5])}, last: {bands[-1]}")
        print(f"crsTransform {t}, every chunk corner on the grid, Drive folder {folder}")
        if args.product == "roy":
            print(
                f"ETM+ to OLI: {harm['etm_to_oli']} ({harm['etm_to_oli_mode']}), "
                f"TM to ETM+: the study's yearly fits ({len(harm['tm_to_etm'])} years)"
            )


if __name__ == "__main__":
    main()
