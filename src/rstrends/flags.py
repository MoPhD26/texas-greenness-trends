"""Per-pixel quality flags for the trend analysis (plan Section 5.6).

Class flicker: the harmonization group of a pixel comes from its Annual NLCD class in each
year. A pixel that switches group two or more times is more likely to show classification
flicker than real change, so class summaries are run with and without these pixels.

Clear-count correlation: Spearman correlation between a pixel's annual EVI2 and its annual
clear-observation count. A significant correlation (Benjamini-Hochberg q at or below the
trend tests' level) flags a pixel whose values move with data density, for example from
Landsat 7 scan-line gaps in 2003-2012.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

from rstrends.trend import bh_qvalues


def group_switches(groups) -> np.ndarray:
    """Number of year-to-year changes in each pixel's group. groups: (T, N) integer codes."""
    g = np.asarray(groups)
    if g.ndim != 2:
        raise ValueError("groups must have shape (n_years, n_pixels)")
    return (np.diff(g, axis=0) != 0).sum(axis=0)


def flicker_flag(groups, min_switches: int = 2) -> np.ndarray:
    """True where a pixel switches group at least min_switches times."""
    return group_switches(groups) >= min_switches


def spearman_by_pixel(y, c, min_n: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """Spearman rho and two-sided p per pixel over years where both y and c are finite.

    y, c: (T, N). Ties get average ranks. p uses the t approximation with n - 2 degrees of
    freedom, as scipy.stats.spearmanr does. Pixels with fewer than min_n paired years, or a
    constant series, get NaN.
    """
    y = np.asarray(y, dtype=np.float64)
    c = np.asarray(c, dtype=np.float64)
    if y.shape != c.shape or y.ndim != 2:
        raise ValueError("y and c must both have shape (n_years, n_pixels)")
    ok = np.isfinite(y) & np.isfinite(c)
    rho = np.full(y.shape[1], np.nan)
    pval = np.full(y.shape[1], np.nan)
    keys, inv = np.unique(ok.T, axis=0, return_inverse=True)
    for k, mask in enumerate(keys):
        n = int(mask.sum())
        if n < min_n:
            continue
        idx = np.flatnonzero(inv.ravel() == k)
        ry = stats.rankdata(y[mask][:, idx], axis=0)
        rc = stats.rankdata(c[mask][:, idx], axis=0)
        ry -= ry.mean(axis=0)
        rc -= rc.mean(axis=0)
        den = np.sqrt((ry**2).sum(axis=0) * (rc**2).sum(axis=0))
        with np.errstate(invalid="ignore", divide="ignore"):
            r = np.where(den > 0, (ry * rc).sum(axis=0) / den, np.nan)
            t = r * np.sqrt((n - 2) / np.clip(1 - r**2, 1e-300, None))
        rho[idx] = r
        pval[idx] = np.where(np.isfinite(r), 2 * stats.t.sf(np.abs(t), n - 2), np.nan)
    return rho, pval


def count_correlation_flag(y, c, q_level: float, min_n: int = 10):
    """Spearman flag with Benjamini-Hochberg across pixels. Returns (rho, q, flag)."""
    rho, p = spearman_by_pixel(y, c, min_n)
    q = bh_qvalues(p)
    return rho, q, np.isfinite(q) & (q <= q_level)
