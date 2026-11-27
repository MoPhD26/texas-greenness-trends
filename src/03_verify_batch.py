"""Phase 3: verify a downloaded export batch (plan Section 8.5, step 4).

Unzips everything in <data>/incoming/<batch>, opens every GeoTIFF, and checks CRS, 30 m
pixels, alignment to the Annual NLCD grid, band count, data type, and nodata. Writes a
SHA-256 for every file to <data>/manifest.csv, reports sizes and compression, moves the
files to <data>/raw/<batch>, and marks the batch verified. Nothing is deleted.

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

import pyproj
import rasterio

from rstrends.batches import export_bands, subset_bands
from rstrends.config import data_dir, ee_project, load_config

MAX_ZERO_SHARE = 0.01  # band 1 (EVI2 x 10000) is exactly 0 in far fewer pixels than this
PILOT_BANDS = 7  # the pilot used the earlier design: 3 indices, 3 counts, acquisitions


def expected_bands(cfg: dict, batch: str, filename: str) -> int:
    """Band count for one file, from the year in its name (main_YYYY...)."""
    if batch == "P":
        return PILOT_BANDS
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", required=True)
    args = ap.parse_args()

    cfg = load_config()
    root = data_dir(cfg)
    inc = root / "incoming" / args.batch
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

    print(f"files: {len(tifs)}, on disk {total_bytes / 1e9:.2f} GB, grid {total_px / 1e6:.0f} M px")
    print(f"uncompressed bbox {raw_bytes / 1e9:.2f} GB, ratio {total_bytes / raw_bytes:.3f}")
    nd_share, zero_share = nd_share / b1_px, zero_share / b1_px
    print(f"band 1: nodata {nd_share:.1%} of pixels, exactly 0 {zero_share:.2%}")
    if nd_share == 0:
        problems.append("band 1 has no nodata pixels, so masked pixels were not written as nodata")
    if zero_share > MAX_ZERO_SHARE:
        problems.append(f"band 1 is exactly 0 in {zero_share:.1%} of pixels (masked written as 0?)")
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
    dest = root / "raw" / args.batch
    dest.mkdir(parents=True, exist_ok=True)
    for path in tifs:
        shutil.move(str(path), dest / path.name)
    ledger_path = root / "logs" / "batches.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}
    ledger.setdefault(args.batch, {})["verified"] = True
    ledger[args.batch]["bytes"] = total_bytes
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"PASS  moved {len(tifs)} files to {dest}")


if __name__ == "__main__":
    main()
