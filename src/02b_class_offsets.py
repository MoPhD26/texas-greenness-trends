"""Phase 3, step 2b: are the class offsets left by the ETM+ to OLI transform a problem?

(a) For each land cover class, the false trend that its residual EVI2 offset would create over
    2000-2026 (a step at 2013), compared with the class's median minimum detectable trend.
    Detectable trends come from the one-chunk benchmark (27 years of real composites) with
    Weatherhead et al. (1998), and, for every class, a quick estimate from the Landsat 7
    yearly medians at the harmonization points (2000-2011).
(b) Sensitivity: ETM+ to OLI fitted separately for class groups (harmonization.class_groups).
    Offsets per class after the single fit and after the group fits, with cluster-bootstrap
    intervals (boxes resampled).

Reads the pooled 2013-2017 sample from <data>/incoming/H. Fetches the Annual NLCD class of the
benchmark chunk once (one small interactive request) and caches it.

Run:
  conda run -n rs-trends python src/02b_class_offsets.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from rstrends import indices
from rstrends.config import data_dir, ee_project, load_config
from rstrends.harmonize import fit_linear
from rstrends.power import mdt_weatherhead, residual_sigma_phi
from rstrends.trend import sen_slope

STEP_YEAR = 2013  # Landsat 8 enters the record
MIN_CLASS_PX = 200  # chunk pixels needed to report a chunk-based detectable trend
TEST_STEP = 0.01  # EVI2 step used to measure how a step turns into a Theil-Sen slope


def load_pooled(cfg, root) -> pd.DataFrame:
    h = cfg["harmonization"]
    y0, y1 = h["etm_to_oli_fit_years"]
    f = sorted((root / "incoming" / "H").rglob(f"sample2_etm_oli_{y0}_{y1}*.csv"))[0]
    df = pd.read_csv(f)
    nmin = h["min_clear_obs_per_sensor"]
    meds = [f"{p}_{b}" for p in ("etm", "oli") for b in ("red", "nir")]
    df = df[(df.etm_n >= nmin) & (df.oli_n >= nmin) & (df[meds] != -9).all(axis=1)]
    return df.reset_index(drop=True)


def class_offsets(df, groups: dict[str, list[int]] | None, idx=None) -> dict[int, float]:
    """Mean EVI2 offset (OLI minus transformed ETM+) per class, single fit or group fits."""
    d = df if idx is None else df.iloc[idx]
    parts = {"all": d} if groups is None else {g: d[d.lc.isin(c)] for g, c in groups.items()}
    out = {}
    for part in parts.values():
        if len(part) < 10:
            continue
        fr = fit_linear(part.etm_red, part.oli_red, "rma")
        fn = fit_linear(part.etm_nir, part.oli_nir, "rma")
        off = indices.evi2(part.oli_red, part.oli_nir) - indices.evi2(
            fr.apply(part.etm_red), fn.apply(part.etm_nir)
        )
        for lc, v in (
            pd.Series(np.asarray(off), index=part.lc.values).groupby(level=0).mean().items()
        ):
            out[int(lc)] = float(v)
    return out


def bootstrap_offsets(df, groups, n_boot, seed):
    clusters = df.cid.unique()
    rows = {c: np.flatnonzero(df.cid.values == c) for c in clusters}
    rng = np.random.default_rng(seed)
    draws = {"single": [], "group": []}
    for _ in range(n_boot):
        pick = rng.choice(clusters, clusters.size, replace=True)
        idx = np.concatenate([rows[c] for c in pick])
        draws["single"].append(class_offsets(df, None, idx))
        draws["group"].append(class_offsets(df, groups, idx))
    return {k: pd.DataFrame(v) for k, v in draws.items()}


def chunk_series(root, cfg):
    bench = root / "interim" / "benchmark"
    meta = json.loads((bench / "benchmark_result.json").read_text(encoding="utf-8"))
    years = list(range(cfg["period"]["start_year"], cfg["period"]["end_year"] + 1))
    stack = np.stack([np.load(bench / f"chunk_{y}.npy")[0] for y in years]).astype(np.float64)
    nodata = cfg["export"]["nodata"]
    evi2 = np.where(stack == nodata, np.nan, stack / cfg["indices"]["storage_scale"])
    return np.array(years), evi2.reshape(len(years), -1), meta["chunk_upper_left"], evi2.shape[1]


def chunk_landcover(root, cfg, ul, size) -> np.ndarray:
    path = root / "interim" / "benchmark" / "chunk_stable_lc.npy"
    if path.exists():
        return np.load(path)
    import ee

    from rstrends import gee

    gee.initialize(ee_project())
    wkt, transform = gee.grid(cfg)
    y0, y1 = cfg["harmonization"]["stable_years"]
    img = gee.stable_landcover(cfg, y0, y1).unmask(0)
    grid = {
        "dimensions": {"width": size, "height": size},
        "affineTransform": {
            "scaleX": transform[0],
            "shearX": 0,
            "translateX": ul[0],
            "shearY": 0,
            "scaleY": transform[4],
            "translateY": ul[1],
        },
        "crsWkt": wkt,
    }
    arr = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": grid})
    lc = np.asarray(arr["lc"]).astype(np.int16)
    np.save(path, lc)
    return lc


def sample_mdt(root, cfg) -> pd.DataFrame:
    """Quick detectable-trend estimate per point from Landsat 7 yearly medians, 2000-2011."""
    n_full = cfg["period"]["end_year"] - cfg["period"]["start_year"] + 1
    nmin = cfg["validity"]["min_clear_obs_per_year"]
    frames = []
    for y in range(cfg["period"]["start_year"], 2012):
        f = sorted((root / "incoming" / "H").rglob(f"sample2_tm_etm_{y}*.csv"))[0]
        d = pd.read_csv(f, usecols=["x", "y", "lc", "etm_red", "etm_nir", "etm_n"])
        ok = (d.etm_n >= nmin) & (d.etm_red != -9) & (d.etm_nir != -9)
        d["evi2"] = np.where(ok, indices.evi2(d.etm_red, d.etm_nir), np.nan)
        d["year"] = y
        frames.append(d[["x", "y", "lc", "year", "evi2"]])
    long = pd.concat(frames)
    wide = long.pivot(index=["x", "y", "lc"], columns="year", values="evi2")
    yrs = np.array(wide.columns, dtype=float)
    vals = wide.to_numpy().T
    keep = np.isfinite(vals).sum(axis=0) >= 8
    s, p = residual_sigma_phi(vals[:, keep], yrs)
    lc = wide.index.get_level_values("lc").to_numpy()[keep]
    return pd.DataFrame({"lc": lc, "mdt": mdt_weatherhead(s, p, n_full)})


def main() -> None:
    cfg = load_config()
    h = cfg["harmonization"]
    root = data_dir(cfg)
    out_dir = root / "outputs" / "harmonization"
    groups = {g: list(c) for g, c in h["class_groups"].items()}

    df = load_pooled(cfg, root)
    single = class_offsets(df, None)
    group = class_offsets(df, groups)
    boots = bootstrap_offsets(df, groups, h["n_boot"], h["seed"])

    # step -> Theil-Sen slope, measured on the real chunk series
    years, evi2, ul, size = chunk_series(root, cfg)
    valid = np.isfinite(evi2).sum(axis=0) >= cfg["validity"]["min_valid_years"]
    y = evi2[:, valid]
    step = (years >= STEP_YEAR).astype(float)[:, None]
    k_sen = float(np.nanmedian(sen_slope(y + TEST_STEP * step, years) - sen_slope(y, years)))
    k_sen /= TEST_STEP
    tc = years - years.mean()
    k_ols = float((tc * (years >= STEP_YEAR)).sum() / (tc**2).sum())

    lc = chunk_landcover(root, cfg, ul, size).ravel()[valid]
    s, p = residual_sigma_phi(y, years, step_at=STEP_YEAR)
    mdt_px = mdt_weatherhead(s, p, years.size)
    chunk = pd.DataFrame({"lc": lc, "mdt": mdt_px, "sigma": s, "phi": p})
    chunk = chunk[chunk.lc > 0]
    samp = sample_mdt(root, cfg)

    rows = []
    for c in sorted(single):
        cg = chunk[chunk.lc == c]
        ci_s = boots["single"][c].quantile([0.025, 0.975]).to_numpy()
        ci_g = boots["group"][c].quantile([0.025, 0.975]).to_numpy()
        mdt_chunk = float(cg.mdt.median()) if len(cg) >= MIN_CLASS_PX else np.nan
        mdt_samp = float(samp[samp.lc == c].mdt.median())
        mdt_use = mdt_chunk if np.isfinite(mdt_chunk) else mdt_samp
        rows.append(
            {
                "lc": c,
                "group": next(g for g, cl in groups.items() if c in cl),
                "n_points": int((df.lc == c).sum()),
                "offset_single": single[c],
                "single_lo": ci_s[0],
                "single_hi": ci_s[1],
                "offset_group": group[c],
                "group_lo": ci_g[0],
                "group_hi": ci_g[1],
                "chunk_px": len(cg),
                "chunk_sigma": float(cg.sigma.median()) if len(cg) else np.nan,
                "chunk_phi": float(cg.phi.median()) if len(cg) else np.nan,
                "mdt_chunk": mdt_chunk,
                "mdt_sample": mdt_samp,
                "mdt_source": "chunk" if np.isfinite(mdt_chunk) else "sample",
                "false_trend_single": k_sen * single[c],
                "false_trend_group": k_sen * group[c],
                "ratio_single": abs(k_sen * single[c]) / mdt_use,
                "ratio_group": abs(k_sen * group[c]) / mdt_use,
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(out_dir / "class_offset_check.csv", index=False)
    summary = {
        "step_to_sen_slope_per_year": k_sen,
        "step_to_ols_slope_per_year": k_ols,
        "chunk_valid_px": int(valid.sum()),
        "chunk_classes": {int(c): int(n) for c, n in chunk.lc.value_counts().items()},
        "chunk_mdt_median_all": float(np.nanmedian(mdt_px)),
        "sample_mdt_median_all": float(samp.mdt.median()),
    }
    Path(out_dir / "class_offset_check.json").write_text(json.dumps(summary, indent=2))
    pd.set_option("display.width", 250)
    print(json.dumps(summary, indent=2))
    print(table.round(5).to_string(index=False))


if __name__ == "__main__":
    main()
