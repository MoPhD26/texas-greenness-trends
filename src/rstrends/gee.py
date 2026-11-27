"""Earth Engine computation graphs: masking, harmonization, composites, samples, tasks.

This is the only module in the package that talks to Earth Engine. Tests do not import it.
QA bit positions and thresholds come from rstrends.qa and the config, so the server-side
masks follow the same tested logic as the NumPy versions.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import ee

from rstrends import qa
from rstrends.harmonize import oli_coefficient_table

INDEX_BANDS = ["evi2", "nirv", "kndvi"]


def initialize(project: str) -> None:
    ee.Initialize(project=project)


def asset_id(project: str, rel: str) -> str:
    return f"projects/{project}/assets/{rel}"


def ensure_folder(project: str, rel_folder: str) -> None:
    path = asset_id(project, rel_folder)
    try:
        ee.data.getAsset(path)
    except ee.EEException:
        ee.data.createAsset({"type": "FOLDER"}, path)


def asset_exists(path: str) -> bool:
    try:
        ee.data.getAsset(path)
        return True
    except ee.EEException:
        return False


# ---------- grid and study area ----------


def grid(cfg: dict) -> tuple[str, list[float]]:
    """CRS WKT and transform of the Annual NLCD grid, checked against the config."""
    img = ee.Image(cfg["grid"]["reference_image"])
    info = img.select(0).getInfo()["bands"][0]
    transform = [float(v) for v in info["crs_transform"]]
    expected = [float(v) for v in cfg["grid"]["crs_transform"]]
    if transform != expected:
        raise RuntimeError(f"NLCD grid transform {transform} differs from config {expected}")
    return img.projection().wkt().getInfo(), transform


def province(gpkg_path) -> ee.FeatureCollection:
    """Province polygon from the local GeoPackage written by 01_boundary.py.

    Sent as client-side geometry (about 0.4 MB). Source edges are straight lines in
    geographic coordinates, so geodesic=False. NAD83 to WGS84 differs by about 1 m here,
    far below the 1:3,500,000 presentation scale of the source map.
    """
    import geopandas as gpd

    g = gpd.read_file(gpkg_path).to_crs(4326).geometry.iloc[0]
    geom = ee.Geometry(g.__geo_interface__, "EPSG:4326", False)
    return ee.FeatureCollection([ee.Feature(geom, {"code": "255"})])


def province_mask(fc: ee.FeatureCollection) -> ee.Image:
    """1 inside the province, masked outside."""
    return ee.Image().byte().paint(fc, 1)


# ---------- per-observation preparation ----------


def prep(img: ee.Image, family: str, cfg: dict) -> ee.Image:
    """Scale red and NIR to reflectance and mask unusable observations.

    Returns bands red, nir (masked where not clear) and acq (1 wherever the scene has data,
    used for the total acquisition count).
    """
    b = qa.SENSOR_BANDS[family]
    qap = img.select("QA_PIXEL")
    clear = qap.bitwiseAnd(qa.bits_to_mask(qa.qa_pixel_mask_bits(family))).eq(0)
    unsat = img.select("QA_RADSAT").bitwiseAnd(qa.bits_to_mask(b["radsat_bits"])).eq(0)
    red = img.select(b["red"]).multiply(qa.SR_SCALE).add(qa.SR_OFFSET)
    nir = img.select(b["nir"]).multiply(qa.SR_SCALE).add(qa.SR_OFFSET)
    ok = clear.And(unsat).And(red.gte(0)).And(red.lte(1)).And(nir.gte(0)).And(nir.lte(1))
    if family == "OLI":
        if cfg["qa"]["drop_high_aerosol"]:
            level = img.select("SR_QA_AEROSOL").rightShift(qa.AEROSOL_LEVEL_SHIFT).bitwiseAnd(3)
            ok = ok.And(level.neq(qa.AEROSOL_LEVEL_HIGH))
    else:
        op = img.select("SR_ATMOS_OPACITY").unmask(-1)
        ok = ok.And(op.multiply(qa.OPACITY_SCALE).lte(cfg["qa"]["max_atmos_opacity"]).Or(op.lt(0)))
    acq = qap.bitwiseAnd(1 << qa.QA_FILL).eq(0).rename("acq")
    refl = red.rename("red").addBands(nir.rename("nir")).updateMask(ok)
    return ee.Image(refl.addBands(acq).copyProperties(img, ["system:time_start"]))


def add_indices(img: ee.Image) -> ee.Image:
    red, nir = img.select("red"), img.select("nir")
    ndvi = nir.subtract(red).divide(nir.add(red))
    evi2 = nir.subtract(red).multiply(2.5).divide(nir.add(red.multiply(2.4)).add(1))
    nirv = ndvi.multiply(nir)
    kndvi = ndvi.pow(2).tanh()
    return (
        img.addBands(evi2.rename("evi2"))
        .addBands(nirv.rename("nirv"))
        .addBands(kndvi.rename("kndvi"))
    )


def apply_linear(img: ee.Image, coeffs: dict[str, tuple[float, float]]) -> ee.Image:
    """Apply per-band (slope, intercept) to red and NIR, keeping other bands."""
    red = img.select("red").multiply(coeffs["red"][0]).add(coeffs["red"][1])
    nir = img.select("nir").multiply(coeffs["nir"][0]).add(coeffs["nir"][1])
    return img.addBands(red.rename("red"), overwrite=True).addBands(
        nir.rename("nir"), overwrite=True
    )


def land_cover_year(cfg: dict, year: int) -> ee.Image:
    """Annual NLCD class for one year (the latest available year if later)."""
    ic = ee.ImageCollection(cfg["land_cover_collection"])
    ic = ic.filter(ee.Filter.lte("year", year)).sort("year", False)
    return ee.Image(ic.first()).select([0]).rename("lc")


def to_oli_coefficients(harm: dict | None, family: str, year: int, cfg: dict | None = None):
    """Per-band (slope, intercept) taking a family's reflectance to OLI-equivalent.

    harm layout: {"etm_to_oli": {"red": [s, i], "nir": [s, i]},
                  "tm_to_etm": {"2000": {"red": [s, i], "nir": [s, i]}, ...},
                  optional "etm_to_oli_mode": "group" with "etm_to_oli_by_group"}
    Single mode returns numbers. Group mode returns per-pixel images, chosen by the pixel's
    Annual NLCD class in that year (needs cfg).
    """
    if harm is None or family == "OLI":
        return None
    table = oli_coefficient_table(harm, family, year)
    if not table["classes"]:
        return table["default"]
    if cfg is None:
        raise ValueError("group coefficients need cfg for the land cover collection")
    lc = land_cover_year(cfg, year)
    classes = sorted(table["classes"])
    out = {}
    for b in ("red", "nir"):
        pair = []
        for k in (0, 1):
            vals = [float(table["classes"][c][b][k]) for c in classes]
            img = lc.remap(classes, vals, float(table["default"][b][k])).rename(f"{b}_{k}")
            pair.append(img.toFloat())
        out[b] = tuple(pair)
    return out


# ---------- collections ----------


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def sensor_window(cfg: dict, key: str, year: int) -> tuple[str, str] | None:
    """Date window [start, end) for one sensor in one year's season, or None if it has no data."""
    s = cfg["sensors"][key]
    season_start = _date(f"{year}-{cfg['season']['start_month_day']}")
    season_end = _date(f"{year}-{cfg['season']['end_month_day']}") + dt.timedelta(days=1)
    start = max(season_start, _date(s["start"]))
    end = min(season_end, _date(s["end"]) + dt.timedelta(days=1))
    if s["family"] == "ETM":
        end = min(end, _date(cfg["sensors"]["landsat7_cutoff"]))
    if start >= end:
        return None
    return start.isoformat(), end.isoformat()


def sensor_keys(cfg: dict) -> list[str]:
    return [k for k, v in cfg["sensors"].items() if isinstance(v, dict)]


def sensor_collection(cfg: dict, key: str, year: int, region: ee.Geometry, window=None):
    """Prepared (masked, scaled, not harmonized) collection for one sensor and year."""
    win = window or sensor_window(cfg, key, year)
    if win is None:
        return None
    s = cfg["sensors"][key]
    fam = s["family"]
    return (
        ee.ImageCollection(s["collection"])
        .filterBounds(region)
        .filterDate(win[0], win[1])
        .map(lambda im: prep(im, fam, cfg))
    )


def year_observations(cfg: dict, year: int, region: ee.Geometry, harm: dict | None):
    """All harmonized observations for one year's season with indices added."""
    parts = []
    for key in sensor_keys(cfg):
        col = sensor_collection(cfg, key, year, region)
        if col is None:
            continue
        coeffs = to_oli_coefficients(harm, cfg["sensors"][key]["family"], year, cfg)
        if coeffs is not None:
            col = col.map(lambda im, c=coeffs: apply_linear(im, c))
        parts.append(col)
    if not parts:
        raise ValueError(f"no sensors cover the {year} season")
    merged = parts[0]
    for p in parts[1:]:
        merged = merged.merge(p)
    return merged.map(add_indices)


def annual_composite(cfg: dict, year: int, fc: ee.FeatureCollection, harm: dict | None):
    """Main stack for one year as int16: evi2, nirv, kndvi (x scale), sub-season counts, n_acq."""
    region = fc.geometry().bounds()
    obs = year_observations(cfg, year, region, harm)
    scale = cfg["indices"]["storage_scale"]
    med = obs.select(INDEX_BANDS).median().multiply(scale).round().toInt16()
    counts = []
    for name, (a, b) in cfg["season"]["sub_seasons"].items():
        end = _date(f"{year}-{b}") + dt.timedelta(days=1)
        n = obs.filterDate(f"{year}-{a}", end.isoformat()).select("evi2").count()
        counts.append(n.unmask(0).toInt16().rename(f"n_{name}"))
    n_acq = obs.select("acq").sum().unmask(0).toInt16().rename("n_acq")
    out = med.rename(INDEX_BANDS).addBands(counts).addBands(n_acq)
    return out.updateMask(province_mask(fc)).set("year", year)


def filter_geometry(gpkg_path, buffer_m: float) -> ee.Geometry:
    """Province outline buffered and simplified by buffer_m, for filtering scenes.

    Filtering by the full 10,583-vertex polygon exceeds Earth Engine memory limits. The
    buffer keeps every scene that touches the province.
    """
    import geopandas as gpd

    g = gpd.read_file(gpkg_path).to_crs(5070).geometry.iloc[0]
    g = g.buffer(buffer_m).simplify(buffer_m)
    g = gpd.GeoSeries([g], crs=5070).to_crs(4326).iloc[0]
    return ee.Geometry(g.__geo_interface__, "EPSG:4326", False)


def _subseason_index(img: ee.Image, cfg: dict, year: int) -> ee.Number:
    """0-based index of the sub-season that holds the image date, -1 if none."""
    t = ee.Number(img.get("system:time_start"))
    idx = ee.Number(-1)
    for k, (a, b) in enumerate(cfg["season"]["sub_seasons"].values()):
        start = ee.Date(f"{year}-{a}").millis()
        end = ee.Date((_date(f"{year}-{b}") + dt.timedelta(days=1)).isoformat()).millis()
        idx = ee.Number(ee.Algorithms.If(t.gte(start).And(t.lt(end)), k, idx))
    return idx


def annual_composite_single_pass(
    cfg: dict,
    year: int,
    fc: ee.FeatureCollection,
    filt: ee.Geometry,
    harm: dict | None,
    indices: list[str] | None = None,
    subsets: bool = True,
    max_cloud: float | None = None,
    return_observations: bool = False,
) -> ee.Image:
    """One year's main export, computed in a single pass over the scenes.

    Every observation carries its index bands and one 0/1 indicator per sub-season (masked
    where the observation is not clear), built in one map over the scenes. The median of the
    index bands and the sum of the indicators replace the old five separate passes
    (median, three sub-season counts, acquisition count). Single-sensor subset bands are
    masked on observations from other sensors.
    Band order matches rstrends.batches.export_bands.
    """
    from rstrends.batches import export_bands

    indices = list(indices or cfg["export"]["main_indices"])
    seasons = list(cfg["season"]["sub_seasons"])
    active = {
        name: sub
        for name, sub in cfg["export"]["subsets"].items()
        if subsets and sub["years"][0] <= year <= sub["years"][1]
    }
    if max_cloud is None:
        max_cloud = cfg["qa"]["max_scene_cloud_cover_land"]
    med_names = indices + [f"{n}_evi2" for n in active]
    cnt_names = [f"n_{s}" for s in seasons] + [f"{n}_n_{s}" for n in active for s in seasons]

    parts = []
    for key in sensor_keys(cfg):
        win = sensor_window(cfg, key, year)
        if win is None:
            continue
        fam = cfg["sensors"][key]["family"]
        col = ee.ImageCollection(cfg["sensors"][key]["collection"]).filterBounds(filt)
        col = col.filterDate(win[0], win[1])
        if max_cloud is not None:
            col = col.filter(ee.Filter.lte("CLOUD_COVER_LAND", max_cloud))
        coeffs = to_oli_coefficients(harm, fam, year, cfg)

        def build(im, fam=fam, coeffs=coeffs):
            o = prep(im, fam, cfg)
            if coeffs is not None:
                o = apply_linear(o, coeffs)
            o = add_indices(o)
            valid = o.select("evi2").mask()
            k = _subseason_index(im, cfg, year)
            ind = ee.Image.cat(
                [ee.Image.constant(0).add(ee.Number(k).eq(i)).toByte() for i in range(len(seasons))]
            ).updateMask(valid)
            empty = ee.Image.constant(0).updateMask(ee.Image.constant(0))
            bands = [o.select(indices).toFloat()]
            for name, sub in active.items():
                if sub["family"] == fam:
                    bands.append(o.select("evi2").toFloat().rename(f"{name}_evi2"))
                else:
                    bands.append(empty.toFloat().rename(f"{name}_evi2"))
            bands.append(ind.rename([f"n_{s}" for s in seasons]))
            for name, sub in active.items():
                names = [f"{name}_n_{s}" for s in seasons]
                bands.append(
                    ind.rename(names)
                    if sub["family"] == fam
                    else ee.Image.cat([empty.toByte()] * len(seasons)).rename(names)
                )
            return ee.Image.cat(bands).select(med_names + cnt_names)

        parts.append(col.map(build))
    if not parts:
        raise ValueError(f"no sensors cover the {year} season")
    obs = parts[0]
    for p in parts[1:]:
        obs = obs.merge(p)
    if return_observations:
        return obs

    # Per-band reducers. A multi-input reducer would drop every observation where any band
    # is masked, and subset bands are masked on the other sensor's scenes.
    scale = cfg["indices"]["storage_scale"]
    med = obs.select(med_names).median().rename(med_names).multiply(scale).round().toInt16()
    cnt = obs.select(cnt_names).sum().rename(cnt_names).unmask(0).toInt16()
    out = med.addBands(cnt).select(
        export_bands(cfg, year)
        if indices == list(cfg["export"]["main_indices"]) and subsets
        else med_names + cnt_names
    )
    return out.updateMask(province_mask(fc)).set("year", year)


# ---------- harmonization sample ----------


def stable_landcover(cfg: dict, y0: int, y1: int) -> ee.Image:
    """Annual NLCD class where the class is unchanged in every year y0..y1, else masked."""
    ic = ee.ImageCollection(cfg["land_cover_collection"]).filter(
        ee.Filter.rangeContains("year", y0, y1)
    )
    n = ic.size().getInfo()
    if n != y1 - y0 + 1:
        raise RuntimeError(f"expected {y1 - y0 + 1} Annual NLCD years, found {n}")
    stack = ic.select([0])
    stable = stack.min().eq(stack.max())
    lc = stack.min().rename("lc")
    keep = stable
    for c in cfg["harmonization"]["exclude_classes"]:
        keep = keep.And(lc.neq(c))
    return lc.updateMask(keep)


def common_window(cfg: dict, key_a: str, key_b: str, year: int) -> tuple[str, str]:
    """Overlap of two sensors' windows in one season, so both medians cover the same dates."""
    wa, wb = sensor_window(cfg, key_a, year), sensor_window(cfg, key_b, year)
    if wa is None or wb is None:
        raise ValueError(f"{key_a} and {key_b} do not overlap in {year}")
    start, end = max(wa[0], wb[0]), min(wa[1], wb[1])
    if start >= end:
        raise ValueError(f"{key_a} and {key_b} do not overlap in {year}")
    return start, end


def sensor_medians(cfg: dict, key: str, year: int, region: ee.Geometry, prefix: str, window=None):
    col = sensor_collection(cfg, key, year, region, window)
    if col is None:
        raise ValueError(f"{key} has no data in the {year} season")
    med = col.select(["red", "nir"]).median().rename([f"{prefix}_red", f"{prefix}_nir"])
    n = col.select("red").count().rename(f"{prefix}_n")
    return med.addBands(n)


def boxes_fc(boxes, box_px: int, wkt: str, res: float = 30.0) -> ee.FeatureCollection:
    """Cluster boxes (upper-left corners in the grid CRS) as planar rectangles with a cid."""
    proj = ee.Projection(wkt)
    side = box_px * res
    return ee.FeatureCollection(
        [
            ee.Feature(ee.Geometry.Rectangle([x, y - side, x + side, y], proj, False), {"cid": i})
            for i, (x, y) in enumerate(boxes)
        ]
    )


def sensor_stats(cfg: dict, key: str, windows, region, prefix: str) -> ee.Image:
    """Median, standard deviation, and clear count of red and NIR over several date windows.

    windows: list of (year, (start, end)). Observations from all windows are pooled, so a
    multi-year window list gives one median per pixel across those years. Each statistic is
    reduced band by band. Masked medians become -9 and counts 0, so sampling never drops a
    point because one sensor had no clear view.
    """
    cols = [sensor_collection(cfg, key, y, region, w) for y, w in windows]
    cols = [c for c in cols if c is not None]
    if not cols:
        raise ValueError(f"{key} has no data in {windows}")
    col = cols[0]
    for c in cols[1:]:
        col = col.merge(c)
    col = col.select(["red", "nir"])
    med = col.median().rename([f"{prefix}_red", f"{prefix}_nir"])
    sd = col.reduce(ee.Reducer.stdDev()).rename([f"{prefix}_red_sd", f"{prefix}_nir_sd"])
    n = col.select("nir").count().rename(f"{prefix}_n")
    return med.addBands(sd).unmask(-9).addBands(n.unmask(0).toInt16())


# ---------- tasks ----------


def operation_summary(project: str, task_id: str) -> dict[str, Any]:
    """State, timing, and EECU use of one batch task."""
    op = ee.data.getOperation(f"projects/{project}/operations/{task_id}")
    md = op.get("metadata", {})
    return {
        "task_id": task_id,
        "description": md.get("description"),
        "state": md.get("state"),
        "create": md.get("createTime"),
        "start": md.get("startTime"),
        "end": md.get("endTime"),
        "eecu_seconds": md.get("batchEecuUsageSeconds"),
        "progress": md.get("progress"),
        "destination": md.get("destinationUris"),
        "error": op.get("error", {}).get("message"),
    }
