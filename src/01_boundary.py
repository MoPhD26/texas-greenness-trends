"""Phase 3, step 1: study area boundary (Bailey's Province 255) and its Earth Engine asset.

Source: USDA Forest Service ECOMAP Ecological Provinces, 2007 release. Province 255 exists
only in this release. Citation: Cleland, D.T., Freeouf, J.A., Keys, J.E., Nowacki, G.J.,
Carpenter, C.A., McNab, W.H. 2007. Ecological Subregions: Sections and Subsections for the
conterminous United States. Gen. Tech. Report WO-76D. Washington, DC: USDA Forest Service.
https://doi.org/10.2737/WO-GTR-76D

Run:
  conda run -n rs-trends python src/01_boundary.py

The saved GeoPackage is sent to Earth Engine as client-side geometry by later scripts
(about 0.4 MB), so no Earth Engine asset is needed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import urllib.request
import zipfile

import geopandas as gpd

from rstrends.config import data_dir, load_config


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()

    cfg = load_config()
    sa = cfg["study_area"]
    root = data_dir(cfg)
    incoming = root / "incoming" / "boundary"
    incoming.mkdir(parents=True, exist_ok=True)
    zpath = incoming / sa["source_url"].rsplit("/", 1)[-1]
    if not zpath.exists():
        print(f"downloading {sa['source_url']}")
        urllib.request.urlretrieve(sa["source_url"], zpath)
    digest = sha256(zpath)
    if digest != sa["source_sha256"]:
        raise SystemExit(f"checksum mismatch for {zpath.name}: {digest}")
    print(f"ok   source checksum {digest[:12]}...")

    with zipfile.ZipFile(zpath) as z:
        shp = next(n for n in z.namelist() if n.lower().endswith(".shp"))
    provinces = gpd.read_file(f"zip://{zpath}!{shp}")
    sel = provinces[provinces[sa["code_field"]] == sa["bailey_province_code"]]
    if sel.empty:
        raise SystemExit(f"province {sa['bailey_province_code']} not found")
    name = sel.iloc[0]["MAP_UNIT_N"]
    geom = sel.dissolve()
    area_km2 = geom.to_crs(5070).area.iloc[0] / 1e6
    print(f"ok   {name}: {len(sel)} feature(s), {area_km2:,.0f} km2, CRS {provinces.crs}")

    out_dir = root / "raw" / "boundary"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = geom[[sa["code_field"], "MAP_UNIT_N", "geometry"]]
    out.to_file(out_dir / "province255.gpkg", driver="GPKG")
    meta = {
        "source_url": sa["source_url"],
        "source_sha256": digest,
        "accessed_utc": dt.datetime.now(dt.UTC).date().isoformat(),
        "citation": "Cleland et al. 2007, GTR WO-76D, https://doi.org/10.2737/WO-GTR-76D",
        "area_km2_conus_albers": round(area_km2, 1),
        "source_crs": str(provinces.crs),
    }
    (out_dir / "province255.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"ok   wrote {out_dir / 'province255.gpkg'}")


if __name__ == "__main__":
    main()
