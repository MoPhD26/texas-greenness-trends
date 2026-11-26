"""Phase 3, step 2: harmonization sample and coefficient fits (plan Section 3).

Steps (each resumes where it stopped):
  --points   draw random candidate points inside the province, read their stable Annual NLCD
             class, and select an area-proportional stratified sample with a per-class floor
  --sample   for every fit year, sample both sensors' March-October median red and NIR and
             their clear-observation counts at the points (interactive requests)
  --submit   the same sample as Earth Engine batch table exports to Google Drive (folder
             rs_trends_H), one task per year. Batch tasks report EECU-hours. Download the CSVs
             to <data>/incoming/H before --fit.
  --fit      fit ETM+ to OLI (pooled 2013-2017, plus each year alone for comparison) and TM to
             ETM+ (one fit per year 2000-2011). RMA primary, OLS for comparison, cluster-bootstrap
             confidence intervals, n, r, R2, RMSE, and scatter diagnostics. Writes a draft only.
  --finalize promote the reviewed draft to coefficients.json, which the exports read

Run:
  conda run -n rs-trends python src/02_harmonization.py --points --sample --fit
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from rstrends import indices, tasklog
from rstrends.config import data_dir, ee_project, load_config
from rstrends.harmonize import allocate, fit_linear, fit_stats

CANDIDATE_FACTOR = 6  # candidates drawn per final point, so rare classes reach their floor
BATCH = 2500  # points per interactive Earth Engine request


def fit_pairs(df, src, tgt, method, n_boot, seed):
    out = {}
    for band in ("red", "nir"):
        f = fit_linear(
            df[f"{src}_{band}"],
            df[f"{tgt}_{band}"],
            method,
            groups=df["pid"],
            n_boot=n_boot,
            seed=seed,
        )
        out[band] = f
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--points", action="store_true")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--fit", action="store_true", help="fit and write draft coefficients")
    ap.add_argument("--finalize", action="store_true", help="promote the reviewed draft")
    ap.add_argument("--submit", action="store_true", help="batch table exports to Drive")
    ap.add_argument("--years", type=int, nargs="*", help="limit --sample to these years")
    ap.add_argument("--workers", type=int, default=6, help="parallel interactive requests")
    args = ap.parse_args()

    cfg = load_config()
    h = cfg["harmonization"]
    root = data_dir(cfg)
    work = root / "interim" / "harmonization"
    work.mkdir(parents=True, exist_ok=True)
    out_dir = root / "outputs" / "harmonization"
    out_dir.mkdir(parents=True, exist_ok=True)
    gpkg = root / "raw" / "boundary" / "province255.gpkg"
    points_csv = work / "points.csv"

    etm_years = list(range(h["etm_to_oli_fit_years"][0], h["etm_to_oli_fit_years"][1] + 1))
    tm_years = [
        y
        for y in range(cfg["period"]["start_year"], cfg["period"]["end_year"] + 1)
        if y < 2012  # TM imaging ended November 2011
    ]

    if args.points or args.sample or args.submit:
        import ee

        from rstrends import gee

        gee.initialize(ee_project())
        _, transform = gee.grid(cfg)
        proj = ee.Image(cfg["grid"]["reference_image"]).projection()

        def sample_df(image, pts: pd.DataFrame, props) -> pd.DataFrame:
            feats = [
                ee.Feature(ee.Geometry.Point([r.lon, r.lat]), {p: getattr(r, p) for p in props})
                for r in pts.itertuples()
            ]
            fc = image.sampleRegions(
                collection=ee.FeatureCollection(feats),
                properties=list(props),
                scale=30,
                projection=proj,
                tileScale=4,
                geometries=False,
            )
            return ee.data.computeFeatures({"expression": fc, "fileFormat": "PANDAS_DATAFRAME"})

        def run_batches(image, pts, props, label, parts_dir=None):
            """Sample in chunks of BATCH points, in parallel.

            With parts_dir, each chunk is saved as soon as it arrives and chunks already on
            disk are skipped, so a failure only repeats the failed chunks. Returns None if
            any chunk failed.
            """
            parts = [pts.iloc[i : i + BATCH] for i in range(0, len(pts), BATCH)]
            if parts_dir is not None:
                parts_dir.mkdir(parents=True, exist_ok=True)

            def part_path(k):
                return None if parts_dir is None else parts_dir / f"part_{k:02d}.csv"

            todo = [
                k for k in range(len(parts)) if part_path(k) is None or not part_path(k).exists()
            ]
            out, failed, t0 = {}, [], time.perf_counter()

            def one(k):
                for attempt in range(1, 4):
                    try:
                        return sample_df(image, parts[k], props)
                    except Exception as exc:  # network or Earth Engine error: retry this chunk
                        print(
                            f"     {label}: chunk {k} attempt {attempt} failed: {exc}", flush=True
                        )
                        time.sleep(5 * attempt)
                raise RuntimeError(f"chunk {k} failed 3 times")

            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(one, k): k for k in todo}
                for fut in as_completed(futs):
                    k = futs[fut]
                    try:
                        df = fut.result()
                    except RuntimeError:
                        failed.append(k)
                        continue
                    if parts_dir is not None:
                        df.to_csv(part_path(k), index=False)
                    out[k] = df
            el = time.perf_counter() - t0
            print(
                f"     {label}: {len(todo)} of {len(parts)} chunks requested, {el:.0f} s, "
                f"failed {failed}",
                flush=True,
            )
            if failed:
                return None
            if parts_dir is not None:
                return pd.concat(
                    [pd.read_csv(part_path(k)) for k in range(len(parts))], ignore_index=True
                )
            return pd.concat(out.values(), ignore_index=True)

    if args.points and not points_csv.exists():
        y0, y1 = h["stable_years"]
        stable = gee.stable_landcover(cfg, y0, y1)
        poly = gpd.read_file(gpkg).to_crs(5070)
        geom = poly.geometry.iloc[0]
        shapely.prepare(geom)
        rng = np.random.default_rng(h["seed"])
        n_cand = h["sample_pixels"] * CANDIDATE_FACTOR
        xmin, ymin, xmax, ymax = geom.bounds
        pts = []
        while sum(len(p) for p in pts) < n_cand:
            xy = rng.uniform([xmin, ymin], [xmax, ymax], size=(n_cand, 2))
            inside = shapely.contains_xy(geom, xy[:, 0], xy[:, 1])
            pts.append(xy[inside])
        xy = np.concatenate(pts)[:n_cand]
        ll = gpd.GeoSeries(gpd.points_from_xy(xy[:, 0], xy[:, 1]), crs=5070).to_crs(4326)
        cand = pd.DataFrame({"cid": np.arange(n_cand), "lon": ll.x, "lat": ll.y})
        print(f"     {n_cand} candidate points inside the province")
        got = run_batches(stable, cand, ["cid"], "stable class at candidates")
        cand = cand.merge(got[["cid", "lc"]], on="cid", how="inner")
        cand["lc"] = cand["lc"].astype(int)
        counts = cand["lc"].value_counts().sort_index()
        alloc = allocate(counts, h["sample_pixels"], h["min_points_per_class"])
        chosen = pd.concat(
            [
                cand[cand.lc == c].sample(n=int(n), random_state=h["seed"])
                for c, n in alloc.items()
                if n > 0
            ]
        )
        chosen = chosen.sort_values("cid").reset_index(drop=True)
        chosen.insert(0, "pid", np.arange(len(chosen)))
        chosen[["pid", "lon", "lat", "lc"]].to_csv(points_csv, index=False)
        summary = pd.DataFrame(
            {
                "candidates_stable": counts,
                "share": (counts / counts.sum()).round(4),
                "sampled": alloc,
            }
        )
        summary.to_csv(out_dir / "sample_allocation.csv")
        print(f"ok   {len(chosen)} points, {len(cand)} of {n_cand} candidates were stable")
        print(summary.to_string())

    jobs = [(y, "LE07", "LC08", "etm", "oli") for y in etm_years]
    jobs += [(y, "LT05", "LE07", "tm", "etm") for y in tm_years]
    if args.years:
        jobs = [j for j in jobs if j[0] in args.years]

    if args.submit:
        pts = pd.read_csv(points_csv)
        fc_region = gee.province(gpkg).geometry().bounds()
        fc_pts = ee.FeatureCollection(
            [
                ee.Feature(ee.Geometry.Point([r.lon, r.lat]), {"pid": int(r.pid), "lc": int(r.lc)})
                for r in pts.itertuples()
            ]
        )
        submitted = {r["description"] for r in tasklog.read(root / "logs" / "ee_tasks.csv", "H")}
        for year, ka, kb, pa, pb in jobs:
            desc = f"H_sample_{pa}_{pb}_{year}"
            if desc in submitted:
                print(f"skip {desc}: already submitted")
                continue
            win = gee.common_window(cfg, ka, kb, year)
            img = gee.sensor_medians(cfg, ka, year, fc_region, pa, win).addBands(
                gee.sensor_medians(cfg, kb, year, fc_region, pb, win)
            )
            table = img.sampleRegions(
                collection=fc_pts,
                properties=["pid", "lc"],
                scale=30,
                projection=proj,
                tileScale=4,
                geometries=False,
            ).map(lambda f, y=year: f.set("year", y))
            cols = ["pid", "lc", "year"] + [
                f"{q}_{b}" for q in (pa, pb) for b in ("red", "nir", "n")
            ]
            task = ee.batch.Export.table.toDrive(
                collection=table,
                description=desc,
                folder=f"{cfg['export']['drive_folder_prefix']}H",
                fileNamePrefix=f"sample_{pa}_{pb}_{year}",
                fileFormat="CSV",
                selectors=cols,
            )
            task.start()
            tasklog.append(root / "logs" / "ee_tasks.csv", "H", desc, task.id)
            print(f"ok   submitted {desc} ({task.id})")

    if args.sample:
        pts = pd.read_csv(points_csv)
        fc_region = gee.province(gpkg).geometry().bounds()
        for year, ka, kb, pa, pb in jobs:
            path = work / f"sample_{pa}_{pb}_{year}.csv"
            if path.exists():
                continue
            win = gee.common_window(cfg, ka, kb, year)
            img = gee.sensor_medians(cfg, ka, year, fc_region, pa, win).addBands(
                gee.sensor_medians(cfg, kb, year, fc_region, pb, win)
            )
            parts_dir = work / "parts" / f"{pa}_{pb}_{year}"
            df = run_batches(img, pts, ["pid", "lc"], f"{pa}->{pb} {year} {win}", parts_dir)
            if df is None:
                print(f"FAIL {pa}->{pb} {year}: rerun to retry only the failed chunks")
                continue
            df["year"] = year
            df["window_start"], df["window_end"] = win
            df.drop(columns=[c for c in ("geo",) if c in df], inplace=True)
            df.to_csv(path, index=False)
            print(f"ok   {path.name}: {len(df)} rows", flush=True)

    def find_sample(name: str):
        """Batch CSV downloaded from Drive (incoming/H) if present, else the interactive copy."""
        for folder in (root / "incoming" / "H", work):
            hits = sorted(folder.rglob(name)) if folder.exists() else []
            if hits:
                return hits[0]
        return None

    def read_sample(name: str) -> pd.DataFrame:
        return pd.read_csv(find_sample(name))

    if args.fit:
        nmin = h["min_clear_obs_per_sensor"]
        nb, seed = h["n_boot"], h["seed"]
        missing = [
            n
            for n in [f"sample_etm_oli_{y}.csv" for y in etm_years]
            + [f"sample_tm_etm_{y}.csv" for y in tm_years]
            if find_sample(n) is None
        ]
        if missing:
            raise SystemExit(f"samples missing, fit not run: {missing}")
        rows, diag = [], []
        draft = {"etm_to_oli": {}, "tm_to_etm": {}}

        def usable(df, a, b):
            need = [f"{q}_{k}" for q in (a, b) for k in ("red", "nir", "n")]
            return df[(df[f"{a}_n"] >= nmin) & (df[f"{b}_n"] >= nmin)].dropna(subset=need)

        def fit_row(name, label, df, src, tgt, boot=True):
            out, fits = {}, {}
            ev_src = indices.evi2(df[f"{src}_red"], df[f"{src}_nir"])
            ev_tgt = indices.evi2(df[f"{tgt}_red"], df[f"{tgt}_nir"])
            for band in ("red", "nir"):
                x, y = df[f"{src}_{band}"], df[f"{tgt}_{band}"]
                g = df["pid"]
                k = nb if boot else 0
                rma = fit_linear(x, y, "rma", groups=g, n_boot=k, seed=seed)
                ols = fit_linear(x, y, "ols", groups=g, n_boot=k, seed=seed)
                st_r, st_o = fit_stats(x, y, rma), fit_stats(x, y, ols)
                fits[band] = rma
                rows.append(
                    {
                        "transform": name,
                        "years": label,
                        "band": band,
                        "n": st_r["n"],
                        "n_points": df["pid"].nunique(),
                        "r": st_r["r"],
                        "r2": st_r["r2"],
                        "ols_slope": ols.slope,
                        "ols_intercept": ols.intercept,
                        "rmse_ols": st_o["rmse"],
                        "rma_slope": rma.slope,
                        "rma_slope_lo": rma.slope_ci[0] if rma.slope_ci else np.nan,
                        "rma_slope_hi": rma.slope_ci[1] if rma.slope_ci else np.nan,
                        "rma_intercept": rma.intercept,
                        "rma_intercept_lo": rma.intercept_ci[0] if rma.intercept_ci else np.nan,
                        "rma_intercept_hi": rma.intercept_ci[1] if rma.intercept_ci else np.nan,
                        "rmse_rma": st_r["rmse"],
                        "evi2_offset_before": float(np.mean(ev_tgt - ev_src)),
                    }
                )
                out[band] = [rma.slope, rma.intercept]
            ev_adj = indices.evi2(
                fits["red"].apply(df[f"{src}_red"]), fits["nir"].apply(df[f"{src}_nir"])
            )
            for r in rows[-2:]:
                r["evi2_offset_after"] = float(np.mean(ev_tgt - ev_adj))
            return out

        def diagnostics(df, src, tgt, label):
            """Correlation by clear-count bin and by land cover class, to explain scatter."""
            m = np.minimum(df[f"{src}_n"], df[f"{tgt}_n"])
            bins = pd.cut(m, [nmin - 1, 5, 9, 14, 1000], labels=["4-5", "6-9", "10-14", "15+"])
            groups = [("min_clear_obs", k, g) for k, g in df.groupby(bins, observed=True)]
            groups += [("nlcd_class", k, g) for k, g in df.groupby("lc")]
            for band in ("red", "nir"):
                for kind, key, grp in groups:
                    if len(grp) < 30:
                        continue
                    x, y = grp[f"{src}_{band}"], grp[f"{tgt}_{band}"]
                    diag.append(
                        {
                            "fit": label,
                            "band": band,
                            "group_type": kind,
                            "group": key,
                            "n": len(grp),
                            "r": float(np.corrcoef(x, y)[0, 1]),
                            "rma_slope": fit_linear(x, y, "rma").slope,
                            "ols_slope": fit_linear(x, y, "ols").slope,
                            "median_abs_diff": float(np.median(np.abs(y - x))),
                        }
                    )

        etm_all = []
        for y in etm_years:
            df = usable(read_sample(f"sample_etm_oli_{y}.csv"), "etm", "oli")
            fit_row("etm_to_oli", str(y), df, "etm", "oli", boot=False)
            etm_all.append(df)
        etm = pd.concat(etm_all, ignore_index=True)
        label = f"{etm_years[0]}-{etm_years[-1]} pooled"
        draft["etm_to_oli"] = fit_row("etm_to_oli", label, etm, "etm", "oli")
        diagnostics(etm, "etm", "oli", f"etm_to_oli {label}")
        for y in tm_years:
            tm = usable(read_sample(f"sample_tm_etm_{y}.csv"), "tm", "etm")
            draft["tm_to_etm"][str(y)] = fit_row("tm_to_etm", str(y), tm, "tm", "etm")
            diagnostics(tm, "tm", "etm", f"tm_to_etm {y}")
        table = pd.DataFrame(rows)
        table.to_csv(out_dir / "fit_table.csv", index=False)
        pd.DataFrame(diag).to_csv(out_dir / "fit_diagnostics.csv", index=False)
        draft["method"] = "rma"
        draft["status"] = "draft, not reviewed"
        draft["note"] = f"point-years with >= {nmin} clear obs per sensor, common date window"
        out_path = out_dir / "coefficients_draft.json"
        out_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")
        pd.set_option("display.width", 250)
        cols = [
            "transform",
            "years",
            "band",
            "n",
            "r",
            "r2",
            "ols_slope",
            "rma_slope",
            "rma_intercept",
            "rmse_ols",
            "rmse_rma",
            "evi2_offset_before",
            "evi2_offset_after",
        ]
        print(table[cols].round(4).to_string(index=False))
        print(f"ok   wrote {out_path} (draft, exports will not use it)")

    if args.finalize:
        draft = json.loads((out_dir / "coefficients_draft.json").read_text(encoding="utf-8"))
        draft["status"] = "final"
        draft["finalized_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (out_dir / "coefficients.json").write_text(json.dumps(draft, indent=2), encoding="utf-8")
        print(f"ok   finalized {out_dir / 'coefficients.json'}")


if __name__ == "__main__":
    main()
