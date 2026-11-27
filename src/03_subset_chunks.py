"""Phase 3: stratified random sample of 512 x 512 chunks for the single-sensor subset checks.

The export grid is the province bounding box snapped to the Annual NLCD grid (the same grid
the exports write). Chunks that touch the province are classed by their dominant Annual NLCD
class inside the province (read at 300 m with one small interactive request). Classes covering
at least subset_sample.major_class_share of the province are strata of their own, the rest
share one stratum. Each stratum is sampled at subset_sample.fraction with a floor of
subset_sample.min_per_stratum chunks.

Writes <data>/interim/subset_chunks.csv (all chunks with class shares and a sampled flag) and
prints how well the sample represents each class.

Run:
  conda run -n rs-trends python src/03_subset_chunks.py
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import shapely

from rstrends.chunks import chunk_windows
from rstrends.config import data_dir, ee_project, load_config
from rstrends.sampling import snap_bounds, stratified_chunk_sample

READ_SCALE_M = 300  # class composition is read at 300 m, ample for chunk-level shares


def main() -> None:
    cfg = load_config()
    root = data_dir(cfg)
    ss = cfg["subset_sample"]
    out_csv = root / "interim" / "subset_chunks.csv"
    import ee

    from rstrends import gee

    gee.initialize(ee_project())
    wkt, transform = gee.grid(cfg)
    gpkg = root / "raw" / "boundary" / "province255.gpkg"
    poly = gpd.read_file(gpkg).to_crs(pyproj.CRS.from_wkt(wkt)).geometry.iloc[0]
    shapely.prepare(poly)
    ulx, uly, width, height = snap_bounds(poly.bounds, transform)
    print(f"     export grid: upper left {ulx:.0f}, {uly:.0f}, {width} x {height} px")
    size = cfg["compute"]["chunk_size_px"]
    rows = []
    for w in chunk_windows(height, width, size):
        x0, y0 = ulx + w.col_off * 30, uly - w.row_off * 30
        box = shapely.box(x0, y0 - w.height * 30, x0 + w.width * 30, y0)
        inside = poly.intersection(box).area / box.area if poly.intersects(box) else 0.0
        if inside > 0:
            rows.append(
                {
                    "key": w.key,
                    "row_off": w.row_off,
                    "col_off": w.col_off,
                    "ulx": x0,
                    "uly": y0,
                    "w": w.width,
                    "h": w.height,
                    "inside": inside,
                }
            )
    chunks = pd.DataFrame(rows)
    print(f"     {len(chunks)} chunks touch the province")

    proj = ee.Projection(wkt)
    feats = [
        ee.Feature(
            ee.Geometry.Rectangle([r.ulx, r.uly - r.h * 30, r.ulx + r.w * 30, r.uly], proj, False),
            {"key": r.key},
        )
        for r in chunks.itertuples()
    ]
    lc = gee.land_cover_year(cfg, ss["land_cover_year"]).updateMask(
        gee.province_mask(gee.province(gpkg))
    )
    got = lc.reduceRegions(
        collection=ee.FeatureCollection(feats),
        reducer=ee.Reducer.frequencyHistogram(),
        scale=READ_SCALE_M,
        crs=proj,
    ).getInfo()["features"]
    hist = {
        f["properties"]["key"]: {
            int(float(k)): v for k, v in (f["properties"].get("histogram") or {}).items()
        }
        for f in got
    }
    comp = pd.DataFrame.from_dict(hist, orient="index").fillna(0.0)
    comp = comp.reindex(chunks.key).fillna(0.0)
    comp = comp[[c for c in sorted(comp.columns) if c not in (0,)]]
    area = comp.sum(axis=0)
    share = area / area.sum()
    majors = sorted(share.index[share >= ss["major_class_share"]])
    dominant = comp.idxmax(axis=1).where(comp.sum(axis=1) > 0, other=-1)
    strata = dominant.map(lambda c: str(int(c)) if c in majors else "other")
    pick = stratified_chunk_sample(strata, ss["fraction"], ss["min_per_stratum"], ss["seed"])
    chunks = chunks.set_index("key")
    chunks["stratum"] = strata
    chunks["sampled"] = chunks.index.isin(pick)
    for c in comp.columns:
        chunks[f"lc_{c}"] = comp[c] / comp.sum(axis=1).replace(0, np.nan)
    chunks.to_csv(out_csv)

    samp_area = comp.loc[pick].sum(axis=0)
    rep = pd.DataFrame(
        {
            "province_share": share.round(4),
            "sample_share": (samp_area / samp_area.sum()).round(4),
            "major": [c in majors for c in share.index],
            "chunks_dominant": strata.value_counts()
            .reindex([str(c) for c in share.index])
            .fillna(0)
            .astype(int)
            .values,
            "sampled_dominant": strata[pick]
            .value_counts()
            .reindex([str(c) for c in share.index])
            .fillna(0)
            .astype(int)
            .values,
        }
    )
    print(rep.to_string())
    frac_px = (chunks.loc[pick, "inside"] * chunks.loc[pick, "w"] * chunks.loc[pick, "h"]).sum() / (
        chunks["inside"] * chunks["w"] * chunks["h"]
    ).sum()
    summary = {
        "chunks": len(chunks),
        "sampled": len(pick),
        "share_of_province_pixels": frac_px,
        "majors": [int(c) for c in majors],
        "export_grid": [ulx, uly, width, height],
    }
    (root / "interim" / "subset_chunks.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
