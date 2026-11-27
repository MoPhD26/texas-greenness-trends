"""Harmonization and data-quality figures (Phase 3 diagnostics).

Reads only local outputs, so it uses no Earth Engine compute:
  <data>/incoming/H/sample2_*.csv, <data>/outputs/harmonization/*.csv and coefficients.json,
  <data>/interim/harmonization/clusters.csv, <data>/interim/subset_chunks.csv,
  <data>/raw/P/*.tif (the 2012 pilot), and the province boundary.

Writes evi2_offsets_cv.csv and tm_etm_offsets_cv.csv to <data>/outputs/harmonization, and six
PNG figures to docs/figures:
  fig1_etm_oli_scatter.png      pooled 2013-2017 ETM+ against OLI, red and NIR, single fit
  fig2_evi2_offset_by_class.png EVI2 offset by class: none, single fit, group fits (fits scored
                                out of sample, cross-validation by box)
  fig3_tm_etm_by_year.png       TM to ETM+ slopes, and EVI2 offsets by year before and after the
                                transform (after: out of sample)
  fig4_false_trend_ratio.png    false trend from the leftover offset (out of sample) over
                                detectable trend
  fig5_sample_design.png        harmonization boxes and subset chunk sample
  fig6_clear_counts_2012.png    2012 clear observations (Landsat 7 SLC-off only), with zoom

Run:
  conda run -n rs-trends python src/05_figures_harmonization.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.features import geometry_mask  # noqa: E402
from rasterio.windows import Window  # noqa: E402

from rstrends import indices  # noqa: E402
from rstrends.config import data_dir, load_config  # noqa: E402
from rstrends.harmonize import fit_linear  # noqa: E402
from rstrends.sampling import cluster_folds  # noqa: E402

# Reference categorical slots 1-4 (dataviz skill palette), used in fixed order.
BLUE, ORANGE, AQUA, YELLOW = "#257de0", "#f47230", "#00b894", "#f2a600"
INK, INK2, GRID = "#191919", "#666666", "#e6e6e6"
CLASS_NAMES = {
    21: "Developed, open",
    22: "Developed, low",
    23: "Developed, medium",
    24: "Developed, high",
    31: "Barren",
    41: "Deciduous forest",
    42: "Evergreen forest",
    43: "Mixed forest",
    52: "Shrub",
    71: "Grassland",
    81: "Pasture and hay",
    82: "Cropland",
    90: "Woody wetlands",
    95: "Emergent wetlands",
}
DPI = 200

plt.rcParams.update(
    {
        "font.size": 9,
        "axes.edgecolor": INK2,
        "axes.labelcolor": INK,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "legend.frameon": False,
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
    }
)


def boot_mean_ci(values, clusters, n=2000, seed=2026):
    rng = np.random.default_rng(seed)
    u, inv = np.unique(clusters, return_inverse=True)
    sums, cnts = np.bincount(inv, values), np.bincount(inv)
    b = np.empty(n)
    for i in range(n):
        k = rng.integers(0, u.size, u.size)
        b[i] = sums[k].sum() / cnts[k].sum()
    return np.percentile(b, [2.5, 97.5])


def oos_offsets(d, x, y, k, seed, groups=None):
    """Out-of-sample EVI2 offset per point (y sensor minus transformed x sensor).

    Points are split into k folds by harmonization box. Each fold is predicted from RMA fits on
    the other folds, so a point never helps fit the line it is scored on. With groups, each land
    cover group gets its own fit, and points outside every group use the pooled fit, as in
    production.
    """
    fold = cluster_folds(d.cid.to_numpy(), k, seed)
    target = np.asarray(indices.evi2(d[f"{y}_red"], d[f"{y}_nir"]))
    out = np.full(len(d), np.nan)
    member = np.full(len(d), -1)
    if groups:
        for gi, classes in enumerate(groups.values()):
            member[d.lc.isin(classes).to_numpy()] = gi
    for f in range(k):
        test = fold == f
        for gi in np.unique(member):
            fit_rows = ~test & ((member == gi) if gi >= 0 else np.ones(len(d), bool))
            rows = test & (member == gi)
            if not rows.any():
                continue
            tr = d[fit_rows]
            fr = fit_linear(tr[f"{x}_red"], tr[f"{y}_red"], "rma")
            fn = fit_linear(tr[f"{x}_nir"], tr[f"{y}_nir"], "rma")
            te = d[rows]
            pred = indices.evi2(fr.apply(te[f"{x}_red"]), fn.apply(te[f"{x}_nir"]))
            out[rows] = target[rows] - np.asarray(pred)
    return out


def load_etm_oli(cfg, root):
    h = cfg["harmonization"]
    y0, y1 = h["etm_to_oli_fit_years"]
    d = pd.read_csv(sorted((root / "incoming/H").rglob(f"sample2_etm_oli_{y0}_{y1}*.csv"))[0])
    nmin = h["min_clear_obs_per_sensor"]
    meds = ["etm_red", "etm_nir", "oli_red", "oli_nir"]
    d = d[(d.etm_n >= nmin) & (d.oli_n >= nmin) & (d[meds] != -9).all(axis=1)]
    return d.reset_index(drop=True)


def class_cv_table(cfg, root):
    """Per-class EVI2 offsets: none, and single and group fits out of sample, with 95% CIs."""
    h = cfg["harmonization"]
    d = load_etm_oli(cfg, root)
    groups = {g: list(c) for g, c in h["class_groups"].items()}
    k, seed = h["cv_folds"], h["seed"]
    none = indices.evi2(d.oli_red, d.oli_nir) - indices.evi2(d.etm_red, d.etm_nir)
    offs = {
        "none": np.asarray(none),
        "single": oos_offsets(d, "etm", "oli", k, seed),
        "group": oos_offsets(d, "etm", "oli", k, seed, groups),
    }
    rows = []
    cid = d.cid.to_numpy()
    for lc in sorted(d.lc.unique()):
        m = (d.lc == lc).to_numpy()
        r = {"lc": int(lc), "n": int(m.sum()), "boxes": int(np.unique(cid[m]).size)}
        for name, v in offs.items():
            lo, hi = boot_mean_ci(v[m], cid[m], n=h["n_boot"], seed=seed)
            r.update({name: v[m].mean(), f"{name}_lo": lo, f"{name}_hi": hi})
        rows.append(r)
    t = pd.DataFrame(rows)
    # False trend from the out-of-sample offsets, with the same step-to-slope factor and
    # detectable trends as src/02b_class_offsets.py
    c = pd.read_csv(root / "outputs/harmonization/class_offset_check.csv")
    k_sen = (c.false_trend_single / c.offset_single).median()
    c["mdt"] = np.where(c.mdt_source == "chunk", c.mdt_chunk, c.mdt_sample)
    t = t.merge(c[["lc", "mdt", "ratio_single", "ratio_group"]], on="lc", how="left")
    t["ratio_single_cv"] = (k_sen * t.single).abs() / t.mdt
    t["ratio_group_cv"] = (k_sen * t.group).abs() / t.mdt
    t.attrs["n_points"] = len(d)
    return t


def fig1(cfg, root, out, harm):
    h = cfg["harmonization"]
    y0, y1 = h["etm_to_oli_fit_years"]
    d = load_etm_oli(cfg, root)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.7))
    for ax, band, lim in ((axes[0], "red", (0, 0.25)), (axes[1], "nir", (0.1, 0.45))):
        ax.hexbin(
            d[f"etm_{band}"],
            d[f"oli_{band}"],
            gridsize=60,
            extent=(*lim, *lim),
            cmap="Blues",
            mincnt=1,
            bins="log",
            linewidths=0,
        )
        x = np.linspace(*lim, 50)
        ax.plot(x, x, color=INK2, lw=1, ls=(0, (2, 2)), label="1:1")
        s, i = harm["etm_to_oli"][band]
        ax.plot(
            x, i + s * x, color=ORANGE, lw=2, label=f"This study, single RMA ({s:.3f}, {i:+.4f})"
        )
        r = h["roy2016_rma"][band]
        ax.plot(
            x,
            r["intercept"] + r["slope"] * x,
            color=AQUA,
            lw=2,
            ls="--",
            label=f"Roy et al. 2016, RMA ({r['slope']:.3f}, {r['intercept']:+.4f})",
        )
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_aspect("equal")
        name = "Red" if band == "red" else "NIR"
        ax.set_title(f"{name} surface reflectance", loc="left", color=INK, fontsize=10)
        ax.set_xlabel("Landsat 7 ETM+ median")
        ax.set_ylabel("Landsat 8 OLI median")
        ax.legend(loc="upper left", fontsize=7)
    fig.suptitle(
        f"ETM+ against OLI, per-point medians {y0}-{y1} (n = {len(d):,} points)",
        x=0.01,
        ha="left",
        fontsize=10,
        color=INK,
    )
    fig.text(
        0.01,
        0.01,
        "The orange line is the pooled single fit, shown for comparison with Roy et al. 2016. "
        "The final transform uses one fit per land cover group.",
        fontsize=7,
        color=INK2,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out / "fig1_etm_oli_scatter.png", dpi=DPI)
    plt.close(fig)


def fig2(cfg, root, out):
    t = class_cv_table(cfg, root).sort_values("lc", ascending=False)
    t.to_csv(root / "outputs/harmonization/evi2_offsets_cv.csv", index=False)
    yy = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(6.4, 4.9))
    ax.axvline(0, color=INK2, lw=1)
    series = (
        ("none", 0.25, "s", INK2, "No transform"),
        ("single", 0.0, "o", BLUE, "Single fit"),
        ("group", -0.25, "D", ORANGE, "Group fits, final"),
    )
    for name, dy, mk, color, label in series:
        ax.errorbar(
            t[name],
            yy + dy,
            xerr=[t[name] - t[f"{name}_lo"], t[f"{name}_hi"] - t[name]],
            fmt=mk,
            ms=4.5,
            color=color,
            lw=1.2,
            label=label,
            zorder=3,
        )
    ax.set_yticks(yy, [CLASS_NAMES[c] for c in t.lc])
    ax.set_xlabel("Mean EVI2 offset, OLI minus ETM+ (fits scored out of sample)")
    ax.set_title(
        "EVI2 offset left by the ETM+ to OLI transform, by land cover class",
        loc="left",
        fontsize=10,
        color=INK,
    )
    ax.legend(loc="upper center", bbox_to_anchor=(0.4, -0.12), ncol=3, fontsize=7.5)
    ax.grid(axis="y", visible=False)
    k = cfg["harmonization"]["cv_folds"]
    fig.text(
        0.01,
        0.01,
        f"Each box is scored with fits from the other folds ({k}-fold cross-validation by box). "
        f"Bars: 95% cluster bootstrap intervals. n = {t.attrs['n_points']:,} points.",
        fontsize=6.5,
        color=INK2,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "fig2_evi2_offset_by_class.png", dpi=DPI)
    plt.close(fig)
    return t


def fig3(cfg, root, out):
    f = pd.read_csv(root / "outputs/harmonization/fit_table.csv")
    f = f[(f["transform"] == "tm_to_etm") & (f.method == "rma")].copy()
    f["year"] = f.years.astype(int)
    h = cfg["harmonization"]
    nmin = h["min_clear_obs_per_sensor_tm"]
    rows = []
    for path in sorted((root / "incoming/H").rglob("sample2_tm_etm_*.csv")):
        d = pd.read_csv(path)
        meds = ["tm_red", "tm_nir", "etm_red", "etm_nir"]
        d = d[(d.tm_n >= nmin) & (d.etm_n >= nmin) & (d[meds] != -9).all(axis=1)]
        off = np.asarray(indices.evi2(d.etm_red, d.etm_nir) - indices.evi2(d.tm_red, d.tm_nir))
        d = d.reset_index(drop=True)
        cid = d.cid.to_numpy()
        lo, hi = boot_mean_ci(off, cid, n=h["n_boot"], seed=h["seed"])
        cv = oos_offsets(d, "tm", "etm", h["cv_folds"], h["seed"])
        clo, chi = boot_mean_ci(cv, cid, n=h["n_boot"], seed=h["seed"])
        rows.append(
            {
                "year": int(d.job.iloc[0][-4:]),
                "off": off.mean(),
                "lo": lo,
                "hi": hi,
                "cv": cv.mean(),
                "cv_lo": clo,
                "cv_hi": chi,
            }
        )
    off = pd.DataFrame(rows).sort_values("year")
    off.to_csv(root / "outputs/harmonization/tm_etm_offsets_cv.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    ax = axes[0]
    ax.axhline(1, color=INK2, lw=1)
    for band, color, mk, dx in (("red", BLUE, "o", -0.12), ("nir", ORANGE, "D", 0.12)):
        g = f[f.band == band].sort_values("year")
        ax.errorbar(
            g.year + dx,
            g.slope,
            yerr=[g.slope - g.slope_lo, g.slope_hi - g.slope],
            fmt=mk,
            ms=4.5,
            color=color,
            lw=1.2,
            label="Red" if band == "red" else "NIR",
        )
    ax.set_title("TM to ETM+ RMA slope by year (95% CI)", loc="left", fontsize=10, color=INK)
    ax.set_xlabel("Year")
    ax.set_ylabel("Slope")
    ax = axes[1]
    ax.axhline(0, color=INK2, lw=1)
    ax.errorbar(
        off.year - 0.12,
        off.off,
        yerr=[off.off - off.lo, off.hi - off.off],
        fmt="s",
        ms=4.5,
        color=INK2,
        lw=1.2,
        label="Before transform",
    )
    ax.errorbar(
        off.year + 0.12,
        off.cv,
        yerr=[off.cv - off.cv_lo, off.cv_hi - off.cv],
        fmt="o",
        ms=4.5,
        color=BLUE,
        lw=1.2,
        label="After yearly RMA, out of sample",
    )
    ax.set_title("EVI2 offset, ETM+ minus TM (95% CI)", loc="left", fontsize=10, color=INK)
    ax.set_xlabel("Year")
    ax.set_ylabel("Mean EVI2 offset")
    ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    axes[0].legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    fig.tight_layout()
    fig.savefig(out / "fig3_tm_etm_by_year.png", dpi=DPI)
    plt.close(fig)


def fig4(cfg, root, out, cv):
    c = pd.read_csv(root / "outputs/harmonization/class_offset_check.csv")
    t = cv.merge(c[["lc", "mdt_source"]], on="lc").sort_values("lc", ascending=False)
    yy = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    ax.barh(yy + 0.2, t.ratio_single_cv, height=0.38, color=BLUE, label="Single fit")
    ax.barh(
        yy - 0.2,
        t.ratio_group_cv,
        height=0.38,
        color=ORANGE,
        hatch="////",
        edgecolor="white",
        linewidth=0,
        label="Group fits, final",
    )
    ax.axvline(1, color=INK, lw=1, ls=(0, (2, 2)))
    ax.text(1.02, len(t) - 0.6, "false trend = detectable trend", fontsize=7.5, color=INK2)
    labels = [
        CLASS_NAMES[c] + (" *" if s == "sample" else "")
        for c, s in zip(t.lc, t.mdt_source, strict=True)
    ]
    ax.set_yticks(yy, labels)
    ax.set_xlabel("False trend from the leftover offset / median detectable trend")
    ax.set_title(
        "Leftover class offsets as a share of the detectable trend, 2000-2026",
        loc="left",
        fontsize=10,
        color=INK,
    )
    ax.legend(loc="lower right", fontsize=7.5)
    ax.grid(axis="y", visible=False)
    k = cfg["harmonization"]["cv_folds"]
    fig.text(
        0.01,
        0.035,
        f"Offsets scored out of sample ({k}-fold cross-validation by box), as in Figure 2.",
        fontsize=7,
        color=INK2,
    )
    fig.text(
        0.01,
        0.01,
        "* detectable trend from Landsat 7 yearly medians at the sample points "
        "(class too rare in the benchmark chunk)",
        fontsize=7,
        color=INK2,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out / "fig4_false_trend_ratio.png", dpi=DPI)
    plt.close(fig)


def fig5(cfg, root, out, crs):
    prov = gpd.read_file(root / "raw/boundary/province255.gpkg").to_crs(crs)
    cl = pd.read_csv(root / "interim/harmonization/clusters.csv")
    ch = pd.read_csv(root / "interim/subset_chunks.csv")
    fig, ax = plt.subplots(figsize=(4.6, 7.4))
    prov.boundary.plot(ax=ax, color=INK2, lw=0.6)
    for r in ch[ch.sampled].itertuples():
        ax.add_patch(
            Rectangle((r.ulx, r.uly - r.h * 30), r.w * 30, r.h * 30, fc=AQUA, ec="none", alpha=0.55)
        )
    side = cfg["harmonization"]["clusters"]["box_px"] * 30
    ax.scatter(cl.ulx + side / 2, cl.uly - side / 2, s=9, marker="s", color=ORANGE, zorder=3)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.scatter(
        [], [], s=20, marker="s", color=ORANGE, label=f"Harmonization boxes ({len(cl)}, 1.92 km)"
    )
    ax.scatter(
        [],
        [],
        s=40,
        marker="s",
        color=AQUA,
        alpha=0.55,
        label=f"Subset chunks ({int(ch.sampled.sum())}, 15.4 km)",
    )
    ax.legend(loc="lower left", fontsize=7.5)
    ax.set_title("Sample design, Province 255", loc="left", fontsize=10, color=INK)
    fig.tight_layout()
    fig.savefig(out / "fig5_sample_design.png", dpi=DPI)
    plt.close(fig)


def fig6(root, out):
    files = sorted(glob.glob(str(root / "raw/P/*.tif")))
    with rasterio.open(files[0]) as s0:
        crs = s0.crs
        t0 = s0.transform
    heights = [rasterio.open(f).height for f in files]
    poly = gpd.read_file(root / "raw/boundary/province255.gpkg").to_crs(crs).geometry.iloc[0]
    k = 8
    parts = []
    for f in files:
        with rasterio.open(f) as src:
            b = [list(src.descriptions).index(n) + 1 for n in ("n_spring", "n_summer", "n_fall")]
            a = (
                src.read(
                    b, out_shape=(3, src.height // k, src.width // k), resampling=Resampling.nearest
                )
                .sum(axis=0)
                .astype(float)
            )
            parts.append(a)
    full = np.vstack(parts)
    tr = rasterio.Affine(t0.a * k, 0, t0.c, 0, t0.e * k, t0.f)
    inside = ~geometry_mask([poly], full.shape, tr)
    full[~inside] = np.nan
    # zoom: a 600 x 600 pixel window (18 km) at full resolution near the province center
    cx, cy = poly.centroid.x, poly.centroid.y
    col = int((cx - t0.c) / t0.a) - 300
    row = int((t0.f - cy) / -t0.e) - 300
    fi = 0
    while row >= heights[fi]:
        row -= heights[fi]
        fi += 1
    with rasterio.open(files[fi]) as src:
        b = [list(src.descriptions).index(n) + 1 for n in ("n_spring", "n_summer", "n_fall")]
        z = src.read(b, window=Window(col, row, 600, 600)).sum(axis=0).astype(float)
    vmax = 16
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 5.6), gridspec_kw={"width_ratios": [1, 1.25]})
    ext = (tr.c, tr.c + tr.a * full.shape[1], tr.f + tr.e * full.shape[0], tr.f)
    im = axes[0].imshow(full, cmap="Blues", vmin=0, vmax=vmax, extent=ext, interpolation="nearest")
    zx = t0.c + col * t0.a
    zy = t0.f + (sum(heights[:fi]) + row) * t0.e
    axes[0].add_patch(
        Rectangle((zx, zy - 600 * 30), 600 * 30, 600 * 30, fc="none", ec=ORANGE, lw=1.5)
    )
    axes[0].set_axis_off()
    axes[0].set_title("Province (every 8th pixel)", loc="left", fontsize=9, color=INK)
    axes[1].imshow(z, cmap="Blues", vmin=0, vmax=vmax, interpolation="nearest")
    axes[1].set_axis_off()
    axes[1].set_title("Zoom, 18 x 18 km at 30 m (orange box)", loc="left", fontsize=9, color=INK)
    cb = fig.colorbar(im, ax=axes, orientation="horizontal", fraction=0.04, pad=0.03)
    cb.set_label("Clear observations, March-October 2012")
    fig.suptitle(
        "2012 clear observations: Landsat 7 SLC-off was the only sensor",
        x=0.01,
        ha="left",
        fontsize=10,
        color=INK,
    )
    fig.savefig(out / "fig6_clear_counts_2012.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    cfg = load_config()
    root = data_dir(cfg)
    out = Path(__file__).resolve().parents[1] / "docs" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    harm = json.loads((root / "outputs/harmonization/coefficients.json").read_text())
    with rasterio.open(sorted(glob.glob(str(root / "raw/P/*.tif")))[0]) as s:
        crs = s.crs
    fig1(cfg, root, out, harm)
    t = fig2(cfg, root, out)
    fig3(cfg, root, out)
    fig4(cfg, root, out, t)
    fig5(cfg, root, out, crs)
    fig6(root, out)
    cols = ["lc", "n", "boxes", "none", "single", "group", "ratio_group", "ratio_group_cv"]
    print(t[cols].round(4).to_string(index=False))
    print(f"ok   wrote 6 figures to {out}")


if __name__ == "__main__":
    main()
