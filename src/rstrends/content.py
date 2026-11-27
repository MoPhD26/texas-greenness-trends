"""Content checks for exported composites (pure functions, no file access).

For one year and one index: the share of pixels inside the area of interest that hold a value,
EVI2 percentiles after removing the storage scale, and the median clear count. Years that look
out of line with the others are flagged.
"""

from __future__ import annotations

import numpy as np

PERCENTILES = (1, 5, 50, 95, 99)


def year_content(
    index_raw: np.ndarray,
    counts_raw: np.ndarray,
    inside: np.ndarray,
    nodata: int,
    scale: float,
    min_clear: int,
) -> dict[str, float]:
    """Content statistics for one year.

    index_raw: stored index values (index x scale), shape (*spatial)
    counts_raw: sub-season clear counts, shape (n_sub_seasons, *spatial)
    inside: True where the pixel is in the area of interest
    """
    idx = np.asarray(index_raw)
    counts = np.asarray(counts_raw)
    inside = np.asarray(inside, dtype=bool)
    n_in = int(inside.sum())
    valid = inside & (idx != nodata)
    out: dict[str, float] = {
        "pixels_inside": n_in,
        "valid_share": float(valid.sum() / n_in) if n_in else np.nan,
    }
    vals = idx[valid].astype(float) / scale
    pct = np.percentile(vals, PERCENTILES) if vals.size else [np.nan] * len(PERCENTILES)
    out.update({f"p{p}": float(v) for p, v in zip(PERCENTILES, pct, strict=True)})
    c_ok = inside & (counts != nodata).all(axis=0)
    total = np.where(counts == nodata, 0, counts).sum(axis=0)
    out["median_clear"] = float(np.median(total[c_ok])) if c_ok.any() else np.nan
    out["share_min_clear"] = float((total[c_ok] >= min_clear).sum() / n_in) if n_in else np.nan
    return out


def flag_years(
    rows: list[dict],
    max_valid_drop: float,
    max_median_shift: float,
    value_range: tuple[float, float],
    min_median_clear: float,
) -> list[str]:
    """Plain-language flags for years that look out of line.

    rows: dicts with "year" and the year_content keys. The reference is the median over all
    rows given, so pass earlier verified years too when there are few in the batch.
    """
    if not rows:
        return []
    ref_valid = float(np.nanmedian([r["valid_share"] for r in rows]))
    ref_p50 = float(np.nanmedian([r["p50"] for r in rows]))
    lo, hi = value_range
    flags = []
    for r in rows:
        y = r["year"]
        if r["valid_share"] < ref_valid - max_valid_drop:
            flags.append(
                f"{y}: valid share {r['valid_share']:.1%} is more than {max_valid_drop:.0%} "
                f"below the median {ref_valid:.1%}"
            )
        if abs(r["p50"] - ref_p50) > max_median_shift:
            flags.append(
                f"{y}: median {r['p50']:.3f} differs from {ref_p50:.3f} by more than "
                f"{max_median_shift}"
            )
        if r["p1"] < lo or r["p99"] > hi:
            flags.append(
                f"{y}: 1st-99th percentile {r['p1']:.3f} to {r['p99']:.3f} outside {lo} to {hi}"
            )
        if r["median_clear"] < min_median_clear:
            flags.append(
                f"{y}: median clear count {r['median_clear']:.0f} below {min_median_clear}"
            )
    return flags
