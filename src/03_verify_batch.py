"""Phase 3: verify a downloaded export batch (plan Section 8.5, step 4).

Unzips everything in <data>/incoming/<batch>, opens every GeoTIFF, and checks CRS, 30 m
pixels, alignment to the Annual NLCD grid, band count, data type, and nodata. Writes a
SHA-256 for every file to <data>/manifest.csv, reports sizes and compression, moves the
files to <data>/raw/<batch>, and marks the batch verified. Nothing is deleted.

Also checks that every year of the batch is present, that band names match the expected order,
and that each year's tiles together cover the export grid (gee.export_region).

Content checks (every batch but the pilot): per year and product, the share of pixels inside
the province (and the sampled chunks, for subsets) that hold a value, EVI2 percentiles, and the
median clear count, from every 8th pixel. Years out of line with the other verified years of the
same product are flagged. They are reported, not failed.

  --keep          check and record only, leave the files in incoming (nothing is moved)
  --content-only  run only the content checks, on files already verified

Run:
  conda run -n rs-trends python src/03_verify_batch.py --batch P
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import rasterio
import shapely
from rasterio.enums import Resampling
from rasterio.features import geometry_mask

from rstrends.batches import (
    SUB_SEASON_PREFIX,
    chunk_product_years,
    export_bands,
    multi_year_bands,
    subset_bands,
)
from rstrends.config import data_dir, ee_project, load_config
from rstrends.content import flag_years, year_content

MAX_ZERO_SHARE = 0.01  # band 1 (EVI2 x 10000) is exactly 0 in far fewer pixels than this
PILOT_BANDS = 7  # the pilot used the earlier design: 3 indices, 3 counts, acquisitions


def expected_bands(cfg: dict, batch: str, filename: str) -> int:
    """Band count for one file, from the year in its name (main_YYYY...)."""
    if batch == "P":
        return PILOT_BANDS
    c = re.search(r"(subsets|roy)_r\d{6}_c\d{6}", filename)
    if c:  # per-chunk export, years as bands (src/03_chunk_export.py)
        return len(multi_year_bands(cfg, chunk_product_years(cfg, c.group(1)), c.group(1)))
    m = re.search(r"(main|subsets)_(\d{4})", filename)
    if not m:
        raise SystemExit(f"cannot read the year from {filename}")
    year = int(m.group(2))
    return len(subset_bands(cfg, year) if m.group(1) == "subsets" else export_bands(cfg, year))


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def area_mask(shapes, shape, transform) -> np.ndarray:
    """True inside any of the shapes (planar, in the file CRS)."""
    return ~geometry_mask(shapes, out_shape=shape, transform=transform)


def content_check(cfg: dict, root, batch: str, tifs: list) -> list[str]:
    """Per year and product: valid share inside the area, EVI2 percentiles, clear counts.

    Reads every decimate-th pixel. The area is the province outline, intersected with the
    sampled chunks for subset files. Writes <data>/logs/content_<batch>.csv and returns flags
    for years out of line with the other verified years of the same product.
    """
    v = cfg["verify"]
    k = v["decimate"]
    nodata = cfg["export"]["nodata"]
    scale = cfg["indices"]["storage_scale"]
    seasons = list(cfg["season"]["sub_seasons"])
    with rasterio.open(tifs[0]) as s0:
        crs = s0.crs
    prov = gpd.read_file(root / "raw" / "boundary" / "province255.gpkg").to_crs(crs)
    prov_shapes = list(prov.geometry)
    chunk_shapes = None
    by_year: dict[tuple[str, int], list] = {}
    for path in tifs:
        m = re.search(r"(main|subsets)_(\d{4})", path.name)
        if m:
            by_year.setdefault((m.group(1), int(m.group(2))), []).append(path)
    rows = []
    if not by_year:
        print("content checks: per-chunk files are checked in the Phase 4 chunk reader")
        return []
    for (kind, year), paths in sorted(by_year.items()):
        if kind == "main":
            products = {"main": ("evi2", [f"{SUB_SEASON_PREFIX}{s}" for s in seasons])}
        else:
            products = {
                name: (f"{name}_evi2", [f"{name}_{SUB_SEASON_PREFIX}{s}" for s in seasons])
                for name in cfg["export"]["subsets"]
                if f"{name}_evi2" in subset_bands(cfg, year)
            }
            if chunk_shapes is None:
                c = pd.read_csv(root / "interim" / "subset_chunks.csv")
                c = c[c.sampled]
                chunk_shapes = [
                    shapely.box(r.ulx, r.uly - r.h * 30, r.ulx + r.w * 30, r.uly)
                    for r in c.itertuples()
                ]
        for product, (ib, cbs) in products.items():
            idx_parts, cnt_parts, in_parts = [], [], []
            for path in paths:
                with rasterio.open(path) as src:
                    names = list(src.descriptions)
                    shp = (max(1, src.height // k), max(1, src.width // k))
                    bands = [names.index(ib) + 1] + [names.index(b) + 1 for b in cbs]
                    arr = src.read(
                        bands, out_shape=(len(bands), *shp), resampling=Resampling.nearest
                    )
                    t = src.transform * rasterio.Affine.scale(
                        src.width / shp[1], src.height / shp[0]
                    )
                    inside = area_mask(prov_shapes, shp, t)
                    if kind == "subsets":
                        inside &= area_mask(chunk_shapes, shp, t)
                idx_parts.append(arr[0].ravel())
                cnt_parts.append(arr[1:].reshape(len(cbs), -1))
                in_parts.append(inside.ravel())
            r = year_content(
                np.concatenate(idx_parts),
                np.concatenate(cnt_parts, axis=1),
                np.concatenate(in_parts),
                nodata,
                scale,
                cfg["validity"]["min_clear_obs_per_year"],
            )
            rows.append({"batch": batch, "product": product, "year": year, **r})
    table = pd.DataFrame(rows)
    out = root / "logs" / f"content_{batch}.csv"
    table.to_csv(out, index=False)
    # Reference: this batch plus every earlier content table, per product
    ref = pd.concat(
        [pd.read_csv(p) for p in sorted((root / "logs").glob("content_*.csv")) if p != out]
        + [table]
    )
    flags = []
    for product, g in table.groupby("product"):
        hist = ref[ref["product"] == product].drop_duplicates(["product", "year"], keep="last")
        f = flag_years(
            hist.to_dict("records"),
            v["max_valid_share_drop"],
            v["max_median_evi2_shift"],
            tuple(v["evi2_range"]),
            cfg["validity"]["min_clear_obs_per_year"],
        )
        years = {str(y) for y in g.year}
        flags += [f"{product} {x}" for x in f if x.split(":")[0] in years]
    show = ["product", "year", "valid_share", "p1", "p5", "p50", "p95", "p99"]
    show += ["median_clear", "share_min_clear"]
    print(table[show].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"content table written to {out}")
    return flags


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--keep", action="store_true", help="leave the files in incoming")
    ap.add_argument(
        "--content-only",
        action="store_true",
        help="run only the content checks on files already verified (no checksums, no move)",
    )
    args = ap.parse_args()

    cfg = load_config()
    root = data_dir(cfg)
    inc = root / "incoming" / args.batch
    if args.content_only:
        where = [inc, root / "raw" / args.batch]
        tifs = next((sorted(d.rglob("*.tif")) for d in where if list(d.rglob("*.tif"))), [])
        if not tifs:
            raise SystemExit(f"no GeoTIFFs for {args.batch} in incoming or raw")
        flags = content_check(cfg, root, args.batch, tifs)
        print("content flags:" if flags else "content flags: none")
        for f in flags:
            print(f"  {f}")
        return
    if not inc.exists():
        raise SystemExit(f"{inc} does not exist. Download the Drive folder there first.")
    for z in inc.glob("*.zip"):
        with zipfile.ZipFile(z) as zf:
            zf.extractall(inc)
    tifs = sorted(inc.rglob("*.tif"))
    if not tifs:
        raise SystemExit(f"no GeoTIFFs found in {inc}")

    from rstrends import gee

    gee.initialize(ee_project())
    wkt, transform = gee.grid(cfg)
    nlcd_crs = pyproj.CRS.from_wkt(wkt)
    a, _, x0, _, e, y0 = transform
    nodata = cfg["export"]["nodata"]
    ledger_path = root / "logs" / "batches.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}
    years_expected = set(ledger.get(args.batch, {}).get("years", []))
    _, (gx, gy, gw, gh) = gee.export_region(cfg, root / "raw" / "boundary" / "province255.gpkg")
    extent: dict[int, list[float]] = {}
    band_names: dict[str, tuple] = {}

    problems, rows, total_bytes, total_px, raw_bytes = [], [], 0, 0, 0
    nd_share = zero_share = b1_px = 0.0
    for path in tifs:
        with rasterio.open(path) as src:
            t = src.transform
            if not pyproj.CRS.from_wkt(src.crs.to_wkt()).equals(nlcd_crs, ignore_axis_order=True):
                problems.append(f"{path.name}: CRS differs from Annual NLCD")
            if (t.a, t.e) != (a, e) or t.b or t.d:
                problems.append(f"{path.name}: pixel size {t.a},{t.e} is not 30 m north-up")
            if (t.c - x0) % a or (t.f - y0) % abs(e):
                problems.append(f"{path.name}: origin not aligned to the NLCD grid")
            nb = expected_bands(cfg, args.batch, path.name)
            if src.count != nb:
                problems.append(f"{path.name}: {src.count} bands, expected {nb}")
            raw_bytes += src.width * src.height * nb * 2
            if set(src.dtypes) != {"int16"}:
                problems.append(f"{path.name}: data types {set(src.dtypes)}")
            if src.nodata != nodata:
                problems.append(f"{path.name}: nodata {src.nodata}, expected {nodata}")
            total_px += src.width * src.height
            m = re.search(r"(main|subsets)_(\d{4})", path.name)
            if m and args.batch != "P":
                yr = int(m.group(2))
                want = (subset_bands if m.group(1) == "subsets" else export_bands)(cfg, yr)
                if tuple(src.descriptions) != tuple(want):
                    problems.append(f"{path.name}: band names {src.descriptions}, expected {want}")
                band_names[m.group(1)] = tuple(src.descriptions)
                b = src.bounds
                e0 = extent.setdefault(yr, [b.left, b.bottom, b.right, b.top])
                extent[yr] = [
                    min(e0[0], b.left),
                    min(e0[1], b.bottom),
                    max(e0[2], b.right),
                    max(e0[3], b.top),
                ]
            # Masked pixels must be nodata, not 0. Every file's bounding box reaches outside
            # the province, and an EVI2 of exactly 0 is rare, so read band 1 at 1/16 scale.
            b1 = src.read(1, out_shape=(max(1, src.height // 16), max(1, src.width // 16)))
            nd_share += float((b1 == nodata).sum())
            zero_share += float((b1 == 0).sum())
            b1_px += b1.size
        size = path.stat().st_size
        total_bytes += size
        rows.append(
            {
                "batch": args.batch,
                "file": path.name,
                "bytes": size,
                "sha256": sha256(path),
                "verified_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            }
        )

    if extent:
        print(f"years present: {sorted(extent)}")
        missing = years_expected - set(extent)
        if missing:
            problems.append(f"years missing: {sorted(missing)}")
        for name, bands in band_names.items():
            print(f"{name} bands: {', '.join(bands)}")
        if args.batch.startswith("B"):
            want_ext = [gx, gy - gh * abs(e), gx + gw * a, gy]
            for yr, ext in sorted(extent.items()):
                if any(abs(u - v) > 1e-6 for u, v in zip(ext, want_ext, strict=True)):
                    problems.append(f"{yr}: tiles cover {ext}, export grid is {want_ext}")
            print(f"extent per year matches the export grid {gw} x {gh} px at ({gx}, {gy})")
    print(f"crs: {nlcd_crs.name}, nodata {nodata}")
    print(f"files: {len(tifs)}, on disk {total_bytes / 1e9:.2f} GB, grid {total_px / 1e6:.0f} M px")
    print(f"uncompressed bbox {raw_bytes / 1e9:.2f} GB, ratio {total_bytes / raw_bytes:.3f}")
    nd_share, zero_share = nd_share / b1_px, zero_share / b1_px
    print(f"band 1: nodata {nd_share:.1%} of pixels, exactly 0 {zero_share:.2%}")
    if nd_share == 0:
        problems.append("band 1 has no nodata pixels, so masked pixels were not written as nodata")
    if zero_share > MAX_ZERO_SHARE:
        problems.append(f"band 1 is exactly 0 in {zero_share:.1%} of pixels (masked written as 0?)")
    if args.batch != "P":
        flags = content_check(cfg, root, args.batch, tifs)
        print("content flags:" if flags else "content flags: none")
        for f in flags:
            print(f"  {f}")
    if problems:
        print("FAIL")
        for p in problems:
            print(f"  {p}")
        raise SystemExit(1)

    manifest = root / "manifest.csv"
    new = not manifest.exists()
    with open(manifest, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        if new:
            w.writeheader()
        w.writerows(rows)
    dest = inc if args.keep else root / "raw" / args.batch
    if not args.keep:
        dest.mkdir(parents=True, exist_ok=True)
        for path in tifs:
            shutil.move(str(path), dest / path.name)
    ledger.setdefault(args.batch, {})["verified"] = True
    ledger[args.batch]["bytes"] = total_bytes
    ledger[args.batch]["location"] = str(dest)
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"PASS  {len(tifs)} files " + (f"left in {dest}" if args.keep else f"moved to {dest}"))


if __name__ == "__main__":
    main()
