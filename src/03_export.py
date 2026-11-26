"""Phase 3, step 3: annual composite exports to Google Drive, in batches (plan Section 8.5).

  --batch P        submit the pilot (one year, export.pilot_year)
  --batch B1 ...   submit a main-stack batch. Refused while an earlier batch is not verified.
  --status         show state, run time, and EECU-hours of every submitted task

Each year is one export task, written as int16 Cloud Optimized GeoTIFF tiles on the Annual
NLCD grid. Bands: evi2, nirv, kndvi (x storage_scale), n_spring, n_summer, n_fall, n_acq.

Run:
  conda run -n rs-trends python src/03_export.py --batch P
  conda run -n rs-trends python src/03_export.py --status
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from rstrends import tasklog
from rstrends.batches import main_batches
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
        if name != "P":
            pending = [b for b, v in ledger.items() if not v.get("verified")]
            if pending or "P" not in ledger:
                raise SystemExit(
                    f"refusing {name}: pilot not run or batches not yet verified: {pending}"
                )
        harm_path = root / "outputs" / "harmonization" / "coefficients.json"
        harm = json.loads(harm_path.read_text(encoding="utf-8"))
        fc = gee.province(root / "raw" / "boundary" / "province255.gpkg")
        wkt, transform = gee.grid(cfg)
        folder = f"{cfg['export']['drive_folder_prefix']}{name}"
        ids = []
        for year in batches[name]:
            img = gee.annual_composite(cfg, year, fc, harm)
            desc = f"{name}_main_{year}"
            task = ee.batch.Export.image.toDrive(
                image=img,
                description=desc,
                folder=folder,
                fileNamePrefix=f"main_{year}",
                region=fc.geometry().bounds(),
                crs=wkt,
                crsTransform=transform,
                maxPixels=int(1e13),
                fileFormat="GeoTIFF",
                fileDimensions=cfg["export"]["file_dimensions"],
                formatOptions={"cloudOptimized": True, "noData": cfg["export"]["nodata"]},
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
