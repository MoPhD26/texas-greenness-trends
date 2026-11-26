"""Phase 3, step 2: harmonization sample and coefficient fits (plan Section 3).

Steps (each resumes where it stopped):
  --points   draw random candidate points inside the province, read their stable Annual NLCD
             class, and select an area-proportional stratified sample with a per-class floor
  --sample   for every fit year, sample both sensors' March-October median red and NIR and
             their clear-observation counts at the points (interactive requests)
  --submit   the same sample as Earth Engine batch table exports to Google Drive (folder
             rs_trends_H), one task per year. Batch tasks report EECU-hours. Download the CSVs
             to <data>/incoming/H before --fit.
  --fit      fit ETM+ to OLI (pooled 2013-2017) and TM to ETM+ (one fit per year 2000-2011),
             RMA primary and OLS for comparison, with cluster-bootstrap confidence intervals

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
from rstrends.harmonize import allocate, fit_linear

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
    ap.add_argument("--fit", action="store_true")
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

        def run_batches(image, pts, props, label):
            parts = [pts.iloc[i : i + BATCH] for i in range(0, len(pts), BATCH)]
            out, t0 = [], time.perf_counter()
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(sample_df, image, p, props): k for k, p in enumerate(parts)}
                for done, fut in enumerate(as_completed(futs), start=1):
                    out.append(fut.result())
                    if done % 10 == 0:
                        el = time.perf_counter() - t0
                        print(f"     {label}: {done}/{len(parts)} ({el:.0f} s)", flush=True)
            print(f"     {label}: {len(parts)} requests in {time.perf_counter() - t0:.0f} s")
            return pd.concat(out, ignore_index=True)

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
            df = run_batches(img, pts, ["pid", "lc"], f"{pa}->{pb} {year}")
            df["year"] = year
            df.to_csv(path, index=False)

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
        # Fit with the years available. Missing years make the result provisional.
        all_etm, all_tm = etm_years, tm_years
        etm_years = [y for y in all_etm if find_sample(f"sample_etm_oli_{y}.csv")]
        tm_years = [y for y in all_tm if find_sample(f"sample_tm_etm_{y}.csv")]
        if not etm_years:
            raise SystemExit("no ETM+ to OLI samples yet")
        provisional = etm_years != all_etm or tm_years != all_tm
        nmin = h["min_clear_obs_per_sensor"]
        nb, seed = h["n_boot"], h["seed"]
        rows, coeffs = [], {"etm_to_oli": {}, "tm_to_etm": {}}

        def usable(df, a, b):
            need = [f"{q}_{k}" for q in (a, b) for k in ("red", "nir", "n")]
            return df[(df[f"{a}_n"] >= nmin) & (df[f"{b}_n"] >= nmin)].dropna(subset=need)

        def record(name, year, df, src, tgt, fits_rma, fits_ols):
            ev_src = indices.evi2(df[f"{src}_red"], df[f"{src}_nir"])
            ev_tgt = indices.evi2(df[f"{tgt}_red"], df[f"{tgt}_nir"])
            ev_adj = indices.evi2(
                fits_rma["red"].apply(df[f"{src}_red"]), fits_rma["nir"].apply(df[f"{src}_nir"])
            )
            for band in ("red", "nir"):
                for method, f in (("rma", fits_rma[band]), ("ols", fits_ols[band])):
                    rows.append(
                        {
                            "transform": name,
                            "year": year,
                            "band": band,
                            "method": method,
                            "slope": f.slope,
                            "slope_lo": f.slope_ci[0],
                            "slope_hi": f.slope_ci[1],
                            "intercept": f.intercept,
                            "intercept_lo": f.intercept_ci[0],
                            "intercept_hi": f.intercept_ci[1],
                            "r": f.r,
                            "n_pairs": f.n,
                            "n_points": df["pid"].nunique(),
                            "evi2_offset_before": float(np.mean(ev_tgt - ev_src)),
                            "evi2_offset_after": float(np.mean(ev_tgt - ev_adj)),
                        }
                    )

        etm = pd.concat(
            [read_sample(f"sample_etm_oli_{y}.csv") for y in etm_years], ignore_index=True
        )
        etm = usable(etm, "etm", "oli")
        rma = fit_pairs(etm, "etm", "oli", "rma", nb, seed)
        ols = fit_pairs(etm, "etm", "oli", "ols", nb, seed)
        record("etm_to_oli", f"{etm_years[0]}-{etm_years[-1]}", etm, "etm", "oli", rma, ols)
        coeffs["etm_to_oli"] = {b: [rma[b].slope, rma[b].intercept] for b in ("red", "nir")}
        for y in tm_years:
            tm = usable(read_sample(f"sample_tm_etm_{y}.csv"), "tm", "etm")
            rma = fit_pairs(tm, "tm", "etm", "rma", nb, seed)
            ols = fit_pairs(tm, "tm", "etm", "ols", nb, seed)
            record("tm_to_etm", str(y), tm, "tm", "etm", rma, ols)
            coeffs["tm_to_etm"][str(y)] = {b: [rma[b].slope, rma[b].intercept] for b in rma}
        table = pd.DataFrame(rows)
        table.to_csv(out_dir / "coefficients_table.csv", index=False)
        coeffs["method"] = "rma"
        coeffs["etm_to_oli_years"] = etm_years
        coeffs["provisional"] = provisional
        if provisional:
            print(f"NOTE provisional fit: ETM+ years {etm_years}, TM years {tm_years}")
        coeffs["note"] = f"fitted on point-years with >= {nmin} clear obs per sensor"
        (out_dir / "coefficients.json").write_text(json.dumps(coeffs, indent=2), encoding="utf-8")
        pd.set_option("display.width", 200)
        print(table.round(4).to_string(index=False))
        print(f"ok   wrote {out_dir / 'coefficients.json'}")


if __name__ == "__main__":
    main()
