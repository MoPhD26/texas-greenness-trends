"""Phase 3, step 4: one-chunk local benchmark (plan Sections 8.3, 8.4, 8.6).

Fetches one 512 x 512 chunk of the real annual stack for every year straight from Earth
Engine (interactive requests, about 3.7 MB per year), applies the pixel-year validity rules,
then times the EVI2 trend suite, the leave-one-year-out check, and parallel throughput.
The full-province projection uses the number of chunks that touch the province.

Run:
  conda run -n rs-trends python src/04_benchmark_chunk.py
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import time
import tracemalloc

import geopandas as gpd
import numpy as np
import pyproj
import shapely

from rstrends.config import data_dir, ee_project, load_config, n_years
from rstrends.indices import from_int16
from rstrends.trend import bh_qvalues, leave_one_year_out, trend_suite
from rstrends.validity import pixel_year_valid

BANDS = ["evi2", "nirv", "kndvi", "n_spring", "n_summer", "n_fall", "n_acq"]


def _run_suite(args):
    y, t, hr_alpha = args
    t0 = time.perf_counter()
    trend_suite(y, t, hr_alpha=hr_alpha)
    return time.perf_counter() - t0


def chunk_origin(x, y, transform, size):
    """Upper-left corner of the chunk-aligned window containing (x, y) on the NLCD grid."""
    a, _, x0, _, e, y0 = transform
    col = math.floor((x - x0) / a)
    row = math.floor((y - y0) / e)
    col -= col % size
    row -= row % size
    return x0 + col * a, y0 + row * e


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lon", type=float, default=-97.15, help="a point inside the chunk")
    ap.add_argument("--lat", type=float, default=31.55)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config()
    root = data_dir(cfg)
    size = cfg["compute"]["chunk_size_px"]
    workers = args.workers or cfg["compute"]["dask_workers"]
    start, end = cfg["period"]["start_year"], cfg["period"]["end_year"]
    years = list(range(start, end + 1))
    bench = root / "interim" / "benchmark"
    bench.mkdir(parents=True, exist_ok=True)
    gpkg = root / "raw" / "boundary" / "province255.gpkg"

    import ee

    from rstrends import gee

    gee.initialize(ee_project())
    wkt, transform = gee.grid(cfg)
    crs = pyproj.CRS.from_wkt(wkt)
    poly = gpd.read_file(gpkg).to_crs(crs).geometry.iloc[0]
    to_grid = pyproj.Transformer.from_crs(4326, crs, always_xy=True)
    px, py = to_grid.transform(args.lon, args.lat)
    if not poly.contains(shapely.Point(px, py)):
        raise SystemExit("the benchmark point is outside the province")
    ux, uy = chunk_origin(px, py, transform, size)

    # ---- fetch the chunk for every year (resumable) ----
    # The benchmark measures run time, which harmonization does not change. Values are fetched
    # without harmonization so the benchmark does not depend on the final coefficients.
    harm = None
    fc = gee.province(gpkg)
    grid = {
        "dimensions": {"width": size, "height": size},
        "affineTransform": {
            "scaleX": transform[0],
            "shearX": 0,
            "translateX": ux,
            "shearY": 0,
            "scaleY": transform[4],
            "translateY": uy,
        },
        "crsWkt": wkt,
    }
    fetch_s = {}
    for year in years:
        path = bench / f"chunk_{year}.npy"
        if path.exists():
            continue
        t0 = time.perf_counter()
        img = gee.annual_composite(cfg, year, fc, harm).select(BANDS).unmask(-32768)
        arr = ee.data.computePixels(
            {"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": grid}
        )
        stack = np.stack([arr[b] for b in BANDS]).astype(np.int16)
        np.save(path, stack)
        fetch_s[year] = round(time.perf_counter() - t0, 1)
        print(f"     fetched {year} in {fetch_s[year]} s")
    data = np.stack([np.load(bench / f"chunk_{y}.npy") for y in years])  # (T, 7, H, W)

    # ---- validity rules and EVI2 series ----
    v = cfg["validity"]
    counts = data[:, 3:6].astype(np.int32)  # (T, 3, H, W)
    _, year_ok = pixel_year_valid(counts, v["min_clear_obs_per_year"], v["min_sub_seasons_covered"])
    evi2 = from_int16(data[:, 0], cfg["indices"]["storage_scale"])
    evi2[~year_ok] = np.nan
    y = evi2.reshape(len(years), -1)
    t = np.array(years, dtype=float)
    in_prov = np.isfinite(y).any(axis=0)
    print(f"     chunk pixels with any valid year: {in_prov.mean():.1%}")
    print(f"     median valid years per pixel: {np.median(np.isfinite(y).sum(0)[in_prov]):.0f}")

    # ---- single-process timings ----
    hr_alpha = cfg["trend"]["hr_acf_alpha"]
    trend_suite(y[:, :1000], t)  # warm-up
    tracemalloc.start()
    t0 = time.perf_counter()
    trend_suite(y, t, hr_alpha=hr_alpha)
    t_suite = time.perf_counter() - t0
    peak_mb = tracemalloc.get_traced_memory()[1] / 1e6
    tracemalloc.stop()
    t0 = time.perf_counter()
    leave_one_year_out(y, t)
    t_loo = time.perf_counter() - t0
    p = np.random.default_rng(0).uniform(size=27_000_000)
    t0 = time.perf_counter()
    bh_qvalues(p)
    t_bh27 = time.perf_counter() - t0

    # ---- parallel throughput: `workers` processes each run the suite on the chunk ----
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers) as pool:
        pool.map(_run_suite, [(y[:, :1000], t, hr_alpha)] * workers)  # warm-up
        t0 = time.perf_counter()
        per = pool.map(_run_suite, [(y, t, hr_alpha)] * (workers * 2))
        wall = time.perf_counter() - t0
    chunks_per_s = workers * 2 / wall

    # ---- projection to the province ----
    xmin, ymin, xmax, ymax = poly.bounds
    gx0, gy0 = chunk_origin(xmin, ymax, transform, size)
    step = size * transform[0]
    n_touch = 0
    prepared = shapely.prepared.prep(poly)
    x = gx0
    while x < xmax:
        yy = gy0
        while yy > ymin:
            if prepared.intersects(shapely.box(x, yy - step, x + step, yy)):
                n_touch += 1
            yy -= step
        x += step
    suite_h = n_touch / chunks_per_s / 3600
    loo_h = suite_h * t_loo / t_suite
    bh_min = t_bh27 * (poly.area / 900 / 27e6) / 60

    result = {
        "chunk_upper_left": [ux, uy],
        "years": n_years(cfg),
        "fetch_seconds_per_year": fetch_s,
        "single_process_suite_s": round(t_suite, 2),
        "single_process_peak_mb": round(peak_mb),
        "single_process_loo_s": round(t_loo, 2),
        "parallel_workers": workers,
        "parallel_suite_s_each": [round(s, 2) for s in per],
        "parallel_chunks_per_s": round(chunks_per_s, 3),
        "bh_27M_s": round(t_bh27, 2),
        "chunks_touching_province": n_touch,
        "projected_suite_hours_per_index": round(suite_h, 2),
        "projected_loo_hours_evi2": round(loo_h, 2),
        "projected_bh_minutes_per_index": round(bh_min, 1),
    }
    (bench / "benchmark_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
