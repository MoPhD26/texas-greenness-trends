"""Phase 3, step 2: harmonization sample and coefficient fits (plan Section 3, revision 5).

Sample design: about 10,000 stable Annual NLCD pixels in 200 small grid-aligned boxes (clusters)
spread at random over the province. Clustering lets points share the Landsat tiles Earth Engine
reads, which cuts the cost far below that of scattered points.

Steps:
  --clusters  pick the boxes (local), then read the stable class counts inside them (one small
              interactive request on Annual NLCD only) and allocate points to classes
  --submit    batch table exports to Google Drive (folder rs_trends_H). Jobs:
                etm_oli_2013_2017  one median per point and sensor across all 2013-2017 dates
                                   that both Landsat 7 and Landsat 8 cover
                tm_etm_YYYY        one median per point and sensor in year YYYY (2000-2011),
                                   over the dates both Landsat 5 and Landsat 7 cover
              Choose jobs with --jobs. Download the CSVs to <data>/incoming/H before --fit.
  --status    state and EECU-hours of the submitted sample tasks
  --fit       RMA (primary), Deming with an estimated error ratio (check), and OLS (for the
              Roy et al. 2016 comparison). Cluster-bootstrap confidence intervals. Fit statistics
              and the EVI2 offset each transform removes, overall and by land cover class.
              Writes a draft only.
  --finalize  promote the reviewed draft to coefficients.json, which the exports read

Run:
  conda run -n rs-trends python src/02_harmonization.py --clusters
  conda run -n rs-trends python src/02_harmonization.py --submit --jobs tm_etm_2006
  conda run -n rs-trends python src/02_harmonization.py --status
  conda run -n rs-trends python src/02_harmonization.py --fit
"""

from __future__ import annotations

import argparse
import json
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj

from rstrends import indices, tasklog
from rstrends.config import data_dir, ee_project, load_config
from rstrends.harmonize import (
    LinearFit,
    allocate,
    deming_lambda,
    fit_linear,
    fit_stats,
    median_error_variance,
)
from rstrends.sampling import pick_boxes

GROUP = "H2"  # task log group for the clustered batch sample
MISSING = -9  # sensor_stats writes masked medians as this value


def job_list(cfg: dict) -> dict[str, list[tuple[str, str, str, str, list[int]]]]:
    """Job name -> (sensor key a, key b, prefix a, prefix b, years)."""
    h = cfg["harmonization"]
    y0, y1 = h["etm_to_oli_fit_years"]
    jobs = {f"etm_oli_{y0}_{y1}": ("LE07", "LC08", "etm", "oli", list(range(y0, y1 + 1)))}
    for y in range(cfg["period"]["start_year"], 2012):  # TM imaging ended November 2011
        jobs[f"tm_etm_{y}"] = ("LT05", "LE07", "tm", "etm", [y])
    return jobs


def stat_columns(pa: str, pb: str) -> list[str]:
    return [f"{p}_{s}" for p in (pa, pb) for s in ("red", "nir", "red_sd", "nir_sd", "n")]


def evi2_offset(df, src, tgt, red_fit=None, nir_fit=None) -> np.ndarray:
    """Target EVI2 minus source EVI2, with the source optionally transformed first."""
    red, nir = df[f"{src}_red"], df[f"{src}_nir"]
    if red_fit is not None:
        red, nir = red_fit.apply(red), nir_fit.apply(nir)
    return indices.evi2(df[f"{tgt}_red"], df[f"{tgt}_nir"]) - indices.evi2(red, nir)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clusters", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--jobs", nargs="*", help="job names for --submit (default: all)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--fit", action="store_true", help="fit and write draft coefficients")
    ap.add_argument("--finalize", action="store_true", help="promote the reviewed draft")
    args = ap.parse_args()

    cfg = load_config()
    h = cfg["harmonization"]
    root = data_dir(cfg)
    work = root / "interim" / "harmonization"
    work.mkdir(parents=True, exist_ok=True)
    out_dir = root / "outputs" / "harmonization"
    out_dir.mkdir(parents=True, exist_ok=True)
    gpkg = root / "raw" / "boundary" / "province255.gpkg"
    log_path = root / "logs" / "ee_tasks.csv"
    clusters_csv = work / "clusters.csv"
    alloc_json = work / "cluster_allocation.json"
    jobs = job_list(cfg)
    box_px = h["clusters"]["box_px"]

    if args.clusters or args.submit or args.status:
        import ee

        from rstrends import gee

        project = ee_project()
        gee.initialize(project)
        wkt, transform = gee.grid(cfg)
        proj = ee.Image(cfg["grid"]["reference_image"]).projection()

    if args.clusters:
        if not clusters_csv.exists():
            poly = gpd.read_file(gpkg).to_crs(pyproj.CRS.from_wkt(wkt)).geometry.iloc[0]
            boxes = pick_boxes(poly, transform, h["clusters"]["n"], box_px, h["seed"])
            pd.DataFrame(boxes, columns=["ulx", "uly"]).rename_axis("cid").to_csv(clusters_csv)
            print(f"ok   {len(boxes)} boxes of {box_px} x {box_px} px -> {clusters_csv}")
        if not alloc_json.exists():
            cl = pd.read_csv(clusters_csv)
            boxes = gee.boxes_fc(list(zip(cl.ulx, cl.uly, strict=True)), box_px, wkt)
            y0, y1 = h["stable_years"]
            hist = (
                gee.stable_landcover(cfg, y0, y1)
                .reduceRegion(
                    reducer=ee.Reducer.frequencyHistogram(),
                    geometry=boxes.geometry(),
                    crs=proj,
                    maxPixels=int(1e8),
                )
                .get("lc")
                .getInfo()
            )
            counts = pd.Series({int(float(k)): int(v) for k, v in hist.items()}).sort_index()
            alloc = allocate(counts, h["sample_pixels"], h["min_points_per_class"])
            summary = pd.DataFrame(
                {
                    "stable_px_in_boxes": counts,
                    "share": (counts / counts.sum()).round(4),
                    "points": alloc,
                }
            )
            summary.to_csv(out_dir / "sample_allocation_clustered.csv")
            alloc_json.write_text(
                json.dumps(
                    {
                        "classValues": [int(c) for c in alloc.index],
                        "classPoints": [int(n) for n in alloc.values],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(summary.to_string())
            print(f"ok   {int(alloc.sum())} points allocated -> {alloc_json}")

    if args.submit:
        if not alloc_json.exists():
            raise SystemExit("run --clusters first")
        cl = pd.read_csv(clusters_csv)
        alloc = json.loads(alloc_json.read_text(encoding="utf-8"))
        boxes = gee.boxes_fc(list(zip(cl.ulx, cl.uly, strict=True)), box_px, wkt)
        region = boxes.geometry()
        y0, y1 = h["stable_years"]
        base = (
            gee.stable_landcover(cfg, y0, y1)
            .addBands(ee.Image().int().paint(boxes, "cid").rename("cid"))
            .addBands(ee.Image.pixelCoordinates(proj).rename(["x", "y"]))
        )
        live = {
            r["description"]
            for r in tasklog.read(log_path, GROUP)
            if gee.operation_summary(project, r["task_id"])["state"] not in ("FAILED", "CANCELLED")
        }
        for name in args.jobs or list(jobs):
            if name not in jobs:
                raise SystemExit(f"unknown job {name}. Jobs: {list(jobs)}")
            ka, kb, pa, pb, years = jobs[name]
            desc = f"H2_{name}"
            if desc in live:
                print(f"skip {desc}: already submitted and not failed")
                continue
            windows = [(y, gee.common_window(cfg, ka, kb, y)) for y in years]
            stack = base.addBands(gee.sensor_stats(cfg, ka, windows, region, pa)).addBands(
                gee.sensor_stats(cfg, kb, windows, region, pb)
            )
            table = stack.stratifiedSample(
                numPoints=0,
                classBand="lc",
                region=region,
                scale=30,
                projection=proj,
                seed=h["seed"],
                classValues=alloc["classValues"],
                classPoints=alloc["classPoints"],
                tileScale=4,
                geometries=False,
            ).map(lambda f, n=name: f.set("job", n))
            task = ee.batch.Export.table.toDrive(
                collection=table,
                description=desc,
                folder=f"{cfg['export']['drive_folder_prefix']}H",
                fileNamePrefix=f"sample2_{name}",
                fileFormat="CSV",
                selectors=["job", "x", "y", "cid", "lc"] + stat_columns(pa, pb),
            )
            task.start()
            tasklog.append(log_path, GROUP, desc, task.id)
            print(f"ok   submitted {desc} ({task.id}), windows {windows}")

    if args.status:
        for row in tasklog.read(log_path, GROUP):
            s = gee.operation_summary(project, row["task_id"])
            hrs = tasklog.eecu_hours(s["eecu_seconds"])
            eecu = f"{hrs:.3f} EECU-h" if hrs is not None else "n/a"
            print(f"{row['description']:<26} {s['state']:<10} {eecu}")

    if args.fit:
        fit(cfg, root, out_dir, jobs)

    if args.finalize:
        draft = json.loads((out_dir / "coefficients_draft.json").read_text(encoding="utf-8"))
        draft["status"] = "final"
        draft["finalized_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (out_dir / "coefficients.json").write_text(json.dumps(draft, indent=2), encoding="utf-8")
        print(f"ok   finalized {out_dir / 'coefficients.json'}")


def fit(cfg: dict, root, out_dir, jobs) -> None:
    h = cfg["harmonization"]
    nmin, nb, seed = h["min_clear_obs_per_sensor"], h["n_boot"], h["seed"]
    inc = root / "incoming" / "H"
    files = {n: sorted(inc.rglob(f"sample2_{n}*.csv")) if inc.exists() else [] for n in jobs}
    missing = [n for n, f in files.items() if not f]
    if missing:
        raise SystemExit(f"samples missing in {inc}, fit not run: {missing}")
    roy = {m: h[f"roy2016_{m}"] for m in ("rma", "ols")}

    fit_rows, class_rows, offset_rows = [], [], []
    draft: dict = {"etm_to_oli": {}, "tm_to_etm": {}}

    for name, (_, _, src, tgt, years) in jobs.items():
        df = pd.read_csv(files[name][0])
        n_all = len(df)
        need = stat_columns(src, tgt)
        df = df.dropna(subset=need)
        df = df[(df[f"{src}_n"] >= nmin) & (df[f"{tgt}_n"] >= nmin)]
        df = df[(df[[f"{p}_{b}" for p in (src, tgt) for b in ("red", "nir")]] != MISSING).all(1)]
        label = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])
        transform = f"{src}_to_{tgt}"
        print(f"     {name}: {len(df)} of {n_all} points have >= {nmin} clear obs per sensor")

        fits: dict[str, dict[str, LinearFit]] = {"rma": {}, "deming": {}, "ols": {}}
        for band in ("red", "nir"):
            x, y = df[f"{src}_{band}"], df[f"{tgt}_{band}"]
            ev_x = median_error_variance(df[f"{src}_{band}_sd"], df[f"{src}_n"])
            ev_y = median_error_variance(df[f"{tgt}_{band}_sd"], df[f"{tgt}_n"])
            lam = deming_lambda(ev_x, ev_y)
            for method in fits:
                f = fit_linear(
                    x,
                    y,
                    method,
                    groups=df["cid"],
                    n_boot=0 if method == "ols" else nb,
                    seed=seed,
                    lam=lam if method == "deming" else None,
                )
                fits[method][band] = f
                st = fit_stats(x, y, f)
                fit_rows.append(
                    {
                        "transform": transform,
                        "years": label,
                        "band": band,
                        "method": method,
                        "n": st["n"],
                        "n_clusters": df["cid"].nunique(),
                        "slope": f.slope,
                        "intercept": f.intercept,
                        "slope_lo": f.slope_ci[0] if f.slope_ci else np.nan,
                        "slope_hi": f.slope_ci[1] if f.slope_ci else np.nan,
                        "intercept_lo": f.intercept_ci[0] if f.intercept_ci else np.nan,
                        "intercept_hi": f.intercept_ci[1] if f.intercept_ci else np.nan,
                        "r": st["r"],
                        "r2": st["r2"],
                        "rmse": st["rmse"],
                        "bias": st["bias"],
                        "lam": lam if method == "deming" else np.nan,
                    }
                )
                for lc, g in df.groupby("lc"):
                    if len(g) < 30:
                        continue
                    sg = fit_stats(g[f"{src}_{band}"], g[f"{tgt}_{band}"], f)
                    class_rows.append(
                        {
                            "transform": transform,
                            "years": label,
                            "band": band,
                            "method": method,
                            "lc": lc,
                            **sg,
                        }
                    )

        variants = {
            name_: (fits[m]["red"], fits[m]["nir"])
            for name_, m in (("rma", "rma"), ("deming", "deming"), ("ols", "ols"))
        }
        if transform == "etm_to_oli":
            for m, c in roy.items():
                variants[f"roy2016_{m}"] = (
                    LinearFit(c["red"]["slope"], c["red"]["intercept"], 0, np.nan),
                    LinearFit(c["nir"]["slope"], c["nir"]["intercept"], 0, np.nan),
                )
        groups = [("all", df)] + [(int(lc), g) for lc, g in df.groupby("lc") if len(g) >= 30]
        for key, g in groups:
            before = evi2_offset(g, src, tgt)
            row = {
                "transform": transform,
                "years": label,
                "group": key,
                "n": len(g),
                "offset_none": float(np.mean(before)),
                "rmsd_none": float(np.sqrt(np.mean(before**2))),
            }
            for v, (fr, fn) in variants.items():
                after = evi2_offset(g, src, tgt, fr, fn)
                row[f"offset_{v}"] = float(np.mean(after))
                row[f"rmsd_{v}"] = float(np.sqrt(np.mean(after**2)))
            offset_rows.append(row)

        coeffs = {
            m: {b: [fits[m][b].slope, fits[m][b].intercept] for b in ("red", "nir")} for m in fits
        }
        if transform == "etm_to_oli":
            draft["etm_to_oli"] = coeffs["rma"]
            draft["etm_to_oli_checks"] = {m: coeffs[m] for m in ("deming", "ols")}
        else:
            draft["tm_to_etm"][label] = coeffs["rma"]
            draft.setdefault("tm_to_etm_checks", {})[label] = {
                m: coeffs[m] for m in ("deming", "ols")
            }

    pd.DataFrame(fit_rows).to_csv(out_dir / "fit_table.csv", index=False)
    pd.DataFrame(class_rows).to_csv(out_dir / "fit_by_class.csv", index=False)
    offsets = pd.DataFrame(offset_rows)
    offsets.to_csv(out_dir / "evi2_offsets.csv", index=False)
    draft["method"] = "rma"
    draft["status"] = "draft, not reviewed"
    draft["note"] = (
        f"clustered sample, points with >= {nmin} clear obs per sensor, common date window. "
        "ETM+ to OLI pooled 2013-2017 per-point medians. TM to ETM+ per year."
    )
    out_path = out_dir / "coefficients_draft.json"
    out_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")
    pd.set_option("display.width", 250)
    cols = [
        "transform",
        "years",
        "band",
        "method",
        "n",
        "n_clusters",
        "slope",
        "slope_lo",
        "slope_hi",
        "intercept",
        "r",
        "r2",
        "rmse",
        "bias",
        "lam",
    ]
    print(pd.DataFrame(fit_rows)[cols].round(4).to_string(index=False))
    print(offsets[offsets.group == "all"].round(4).to_string(index=False))
    print(f"ok   wrote {out_path} (draft, exports will not use it)")


if __name__ == "__main__":
    main()
