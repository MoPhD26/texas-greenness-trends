"""Phase 3, step 3: annual composite exports to Google Drive, in batches (plan Section 8.5).

  --batch P        submit the pilot (one year, export.pilot_year)
  --batch B1 ...   submit main-stack batches. Several may run at once (400 GB of Drive holds
                   all of them). Refused until the pilot is verified.
  --batch S1 ...   submit single-sensor subset batches (ETM+ only, OLI only) on the sampled
                   chunks from src/03_subset_chunks.py. S1-S4 mirror the years of B1-B4.
  --status         show state, run time, and EECU-hours of every submitted task

Each year is one export task, written as int16 plain GeoTIFF tiles (no overviews) on the Annual
NLCD grid, with the pilot's computation plus outline and cloud filtering and the folded
single-sensor subsets (gee.annual_composite_production). Bands (rstrends.batches.export_bands):
evi2, nirv, kndvi (x storage_scale) and sub-season clear counts, plus etm_* bands for
2000-2019 and oli_* bands for 2013-2019 (the single-sensor subsets). The pilot (P) used the
earlier seven-band design. Requires final harmonization coefficients.

Run:
  conda run -n rs-trends python src/03_export.py --batch P
  conda run -n rs-trends python src/03_export.py --status
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from rstrends import tasklog
from rstrends.batches import main_batches, subset_batches
from rstrends.config import data_dir, ee_project, load_config


def load_ledger(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    root = data_dir(cfg)
    log_path = root / "logs" / "ee_tasks.csv"
    ledger_path = root / "logs" / "batches.json"
    ledger = load_ledger(ledger_path)
    batches = main_batches(cfg)
    if cfg["export"].get("subsets_on_sample", False):
        batches.update(subset_batches(cfg))

    import ee

    from rstrends import gee

    project = ee_project()
    gee.initialize(project)

    if args.batch:
        name = args.batch
        if name not in batches:
            raise SystemExit(f"unknown batch {name}. Defined: {', '.join(batches)}")
        if name in ledger:
            raise SystemExit(f"batch {name} was already submitted on {ledger[name]['submitted']}")
        if name != "P" and not ledger.get("P", {}).get("verified"):
            raise SystemExit(f"refusing {name}: the pilot is not verified")
        harm_path = root / "outputs" / "harmonization" / "coefficients.json"
        if not harm_path.exists():
            raise SystemExit(
                "no final harmonization coefficients. Review the draft, then --finalize."
            )
        harm = json.loads(harm_path.read_text(encoding="utf-8"))
        if harm.get("status") != "final":
            raise SystemExit("coefficients.json is not marked final")
        want = cfg["harmonization"].get("final_coefficients", {})
        got = hashlib.sha256(harm_path.read_bytes()).hexdigest()
        if got != want.get("sha256") or harm.get("version") != want.get("version"):
            raise SystemExit(
                f"coefficients.json ({harm.get('version')}, {got[:12]}) does not match the "
                f"config ({want.get('version')}, {str(want.get('sha256'))[:12]})"
            )
        gee.check_land_cover_years(cfg, batches[name])
        gpkg = root / "raw" / "boundary" / "province255.gpkg"
        fc = gee.province(gpkg)
        filt = gee.filter_geometry(gpkg, cfg["export"]["filter_buffer_m"])
        region, _ = gee.export_region(cfg, gpkg)
        is_subset = name.startswith("S")
        if is_subset:
            sample = gee.sample_chunks_fc(cfg, root / "interim" / "subset_chunks.csv")
            region = sample.geometry()
        wkt, transform = gee.grid(cfg)
        folder = f"{cfg['export']['drive_folder_prefix']}{name}"
        ids = []
        for year in batches[name]:
            if is_subset:
                img = gee.annual_subsets(cfg, year, fc, sample, filt, harm)
            else:
                img = gee.annual_composite_production(cfg, year, fc, filt, harm)
            # Write masked pixels as nodata explicitly. The pilot showed that the noData format
            # option alone leaves masked pixels as 0, which is a valid EVI2 value.
            img = img.unmask(cfg["export"]["nodata"], False)
            kind = "subsets" if is_subset else "main"
            desc = f"{name}_{kind}_{year}"
            task = ee.batch.Export.image.toDrive(
                image=img,
                description=desc,
                folder=folder,
                fileNamePrefix=f"{kind}_{year}",
                region=region,
                crs=wkt,
                crsTransform=transform,
                maxPixels=int(1e13),
                fileFormat="GeoTIFF",
                fileDimensions=cfg["export"]["file_dimensions"],
                # Plain GeoTIFF: overviews are never read (files are processed in chunks)
                # and added 35% to the pilot's size.
                formatOptions={"cloudOptimized": False, "noData": cfg["export"]["nodata"]},
            )
            task.start()
            tasklog.append(log_path, name, desc, task.id)
            ids.append(task.id)
            print(f"ok   submitted {desc} ({task.id}) to Drive folder {folder}")
        ledger[name] = {
            "submitted": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "years": batches[name],
            "task_ids": ids,
            "verified": False,
        }
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    if args.status:
        total = 0.0
        for row in tasklog.read(log_path):
            s = gee.operation_summary(project, row["task_id"])
            hrs = tasklog.eecu_hours(s["eecu_seconds"])
            total += hrs or 0.0
            run = ""
            if s["start"] and s["end"]:
                t0 = dt.datetime.fromisoformat(s["start"].replace("Z", "+00:00"))
                t1 = dt.datetime.fromisoformat(s["end"].replace("Z", "+00:00"))
                run = f"{(t1 - t0).total_seconds() / 60:.1f} min"
            eecu = f"{hrs:.3f} EECU-h" if hrs is not None else "EECU n/a"
            err = f"  error: {s['error']}" if s["error"] else ""
            print(f"{row['description']:<28} {s['state']:<10} {run:>10}  {eecu}{err}")
        print(f"total EECU-hours logged: {total:.3f}")


if __name__ == "__main__":
    main()
