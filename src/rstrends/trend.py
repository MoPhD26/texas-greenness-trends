"""Vectorized per-pixel trend tests (plan Sections 5.3 and 8.3).

Input layout: y has shape (T, N), T years by N pixels, float, NaN for missing years.
t has shape (T,), strictly increasing (years).

Theil-Sen slope: median of all pairwise slopes over valid year pairs (Sen 1968,
https://doi.org/10.1080/01621459.1968.10480934). Slope confidence interval uses the rank
rule in scipy.stats.theilslopes, so results can be checked against scipy.
Mann-Kendall S and its variance with tie correction (Kendall 1975), as in pyMannKendall.
Hamed and Rao (1998) variance correction for autocorrelation
(https://doi.org/10.1016/S0022-1694(97)00125-X), following pyMannKendall's
hamed_rao_modification_test. One deliberate difference: we detrend with the actual years,
so a missing year keeps its true spacing. Without missing years the two are identical.
Benjamini-Hochberg false discovery rate (https://doi.org/10.1111/j.2517-6161.1995.tb02031.x).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.special import ndtr, ndtri


@lru_cache(maxsize=8)
def pair_indices(T: int) -> tuple[np.ndarray, np.ndarray]:
    """Index arrays (i, j) for all pairs i < j, ordered row by row."""
    i, j = np.triu_indices(T, k=1)
    return i, j


@lru_cache(maxsize=8)
def _incidence(T: int) -> tuple[np.ndarray, np.ndarray]:
    """Pair incidence matrices of shape (T, P).

    unsigned: 1 where year k belongs to pair p. signed: +1 if k is the later year, -1 if earlier.
    """
    i, j = pair_indices(T)
    P = i.size
    unsigned = np.zeros((T, P), dtype=np.float32)
    signed = np.zeros((T, P), dtype=np.float32)
    cols = np.arange(P)
    unsigned[i, cols] = 1
    unsigned[j, cols] = 1
    signed[i, cols] = -1
    signed[j, cols] = 1
    return unsigned, signed


def _check(y, t):
    y = np.asarray(y)
    t = np.asarray(t, dtype=np.float64)
    if y.ndim != 2 or y.shape[0] != t.size:
        raise ValueError("y must have shape (T, N) with T == len(t)")
    if np.any(np.diff(t) <= 0):
        raise ValueError("t must be strictly increasing")
    return y, t


def pairwise_slopes(y, t) -> np.ndarray:
    """All pairwise slopes, shape (P, N). NaN where either year is missing."""
    y, t = _check(y, t)
    i, j = pair_indices(t.size)
    dt = (t[j] - t[i]).astype(y.dtype)[:, None]
    return (y[j] - y[i]) / dt


def _sorted_median(sorted_vals: np.ndarray, count: np.ndarray) -> np.ndarray:
    """Median of the first `count` values of each column of a column-sorted array."""
    out = np.full(count.shape, np.nan, dtype=sorted_vals.dtype)
    has = count > 0
    lo = np.clip((count - 1) // 2, 0, None)
    hi = np.clip(count // 2, 0, None)
    a = np.take_along_axis(sorted_vals, lo[None, :], 0)[0]
    b = np.take_along_axis(sorted_vals, hi[None, :], 0)[0]
    out[has] = 0.5 * (a[has] + b[has])
    return out


@dataclass
class TrendResult:
    slope: np.ndarray
    slope_lo: np.ndarray
    slope_hi: np.ndarray
    s: np.ndarray
    var_s: np.ndarray
    tau: np.ndarray
    p: np.ndarray
    p_hr: np.ndarray
    n_valid: np.ndarray


def mk_z(s: np.ndarray, var_s: np.ndarray) -> np.ndarray:
    """Continuity-corrected Mann-Kendall Z."""
    s = np.asarray(s, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        sd = np.sqrt(np.where(var_s > 0, var_s, np.nan))
        z = np.where(s > 0, (s - 1) / sd, np.where(s < 0, (s + 1) / sd, 0.0))
    return np.where(np.isfinite(sd), z, np.nan)


def p_two_sided(z: np.ndarray) -> np.ndarray:
    return 2 * ndtr(-np.abs(z))


def trend_suite(y, t, ci: float = 0.95, hr_alpha: float = 0.05, min_n: int = 3) -> TrendResult:
    """Theil-Sen slope with confidence interval, Mann-Kendall test, and Hamed-Rao test.

    Pixels with fewer than min_n valid years get NaN outputs.
    """
    y, t = _check(y, t)
    work = np.float64 if y.dtype == np.float64 else np.float32
    y = y.astype(work, copy=False)
    T, _ = y.shape
    valid = np.isfinite(y)
    m = valid.sum(axis=0)
    unsigned, signed = _incidence(T)
    i, j = pair_indices(T)

    # Mann-Kendall S and tie-corrected variance
    diff = y[j] - y[i]  # (P, N), NaN if either missing
    sgn = np.sign(np.nan_to_num(diff, nan=0.0)).astype(np.float32)
    s = sgn.sum(axis=0, dtype=np.float64)
    eq = (diff == 0).astype(np.float32)
    c = 1.0 + unsigned @ eq  # tie group size for each year's value
    c = np.where(valid, c, 1.0)
    tie_term = ((c - 1) * (2 * c + 5)).sum(axis=0, dtype=np.float64)
    mf = m.astype(np.float64)
    var_s = (mf * (mf - 1) * (2 * mf + 5) - tie_term) / 18.0
    del eq, c

    # Theil-Sen slope from sorted pairwise slopes (NaN sort last)
    dt = (t[j] - t[i]).astype(work)[:, None]
    slopes = diff / dt
    del diff
    npairs = np.isfinite(slopes).sum(axis=0)
    slopes.sort(axis=0)
    slope = _sorted_median(slopes, npairs)

    # Slope confidence interval, same rank rule as scipy.stats.theilslopes
    z_ci = ndtri((1 - ci) / 2)  # negative
    sigma = np.sqrt(np.clip(var_s, 0, None))  # Sen (1968) eq. 2.6, ties in y removed
    ru = np.minimum(np.round((npairs - z_ci * sigma) / 2).astype(np.int64), npairs - 1)
    rl = np.maximum(np.round((npairs + z_ci * sigma) / 2).astype(np.int64) - 1, 0)
    ru = np.clip(ru, 0, None)
    slope_lo = np.take_along_axis(slopes, rl[None, :], 0)[0]
    slope_hi = np.take_along_axis(slopes, ru[None, :], 0)[0]
    del slopes

    # Hamed-Rao: ranks of the detrended series among valid years
    # Time counted from 1 at the first year (as pyMannKendall does), which also keeps float32
    # products small. Ranks are unchanged by this shift.
    tt = (t - t[0] + 1).astype(work)
    detr = y - tt[:, None] * slope[None, :]
    dd = np.sign(np.nan_to_num(detr[j] - detr[i], nan=0.0)).astype(np.float32)
    ranks = (mf[None, :] + 1) / 2 + (signed @ dd) / 2  # average ranks with ties
    del dd, detr
    ranks = np.where(valid, ranks, np.nan)
    order = np.argsort(~valid, axis=0, kind="stable")  # valid years first, in time order
    rc = np.take_along_axis(ranks, order, 0)
    centered = np.nan_to_num(rc - (mf[None, :] + 1) / 2, nan=0.0)
    acov0 = (centered * centered).sum(axis=0)
    bound = ndtri(1 - hr_alpha / 2) / np.sqrt(np.where(m > 0, mf, np.nan))
    sni = np.zeros_like(mf)
    with np.errstate(invalid="ignore", divide="ignore"):
        for k in range(1, T):
            acf = (centered[:-k] * centered[k:]).sum(axis=0) / acov0
            w = (mf - k) * (mf - k - 1) * (mf - k - 2)
            sig = np.abs(acf) > bound
            sni += np.where(sig & (k < m), w * acf, 0.0)
        n_ns = 1 + 2 / (mf * (mf - 1) * (mf - 2)) * sni
    var_hr = var_s * n_ns

    with np.errstate(invalid="ignore", divide="ignore"):
        tau = s / (0.5 * mf * (mf - 1))
    p = p_two_sided(mk_z(s, var_s))
    p_hr = p_two_sided(mk_z(s, var_hr))

    bad = m < min_n
    out = TrendResult(slope, slope_lo, slope_hi, s, var_s, tau, p, p_hr, m)
    for name in ("slope", "slope_lo", "slope_hi", "s", "var_s", "tau", "p", "p_hr"):
        arr = np.asarray(getattr(out, name), dtype=np.float64 if work == np.float64 else np.float32)
        arr = arr.copy()
        arr[bad] = np.nan
        setattr(out, name, arr)
    return out


def sen_slope(y, t) -> np.ndarray:
    """Theil-Sen slope only (used by the leave-one-year-out check)."""
    slopes = pairwise_slopes(y, t)
    n = np.isfinite(slopes).sum(axis=0)
    slopes.sort(axis=0)
    return _sorted_median(slopes, n)


def leave_one_year_out(y, t) -> tuple[np.ndarray, np.ndarray]:
    """Minimum and maximum Theil-Sen slope over all leave-one-year-out refits."""
    y, t = _check(y, t)
    lo = np.full(y.shape[1], np.inf, dtype=np.float64)
    hi = np.full(y.shape[1], -np.inf, dtype=np.float64)
    keep = np.ones(t.size, dtype=bool)
    for k in range(t.size):
        keep[:] = True
        keep[k] = False
        s = sen_slope(y[keep], t[keep])
        lo = np.fmin(lo, s)
        hi = np.fmax(hi, s)
    lo[~np.isfinite(lo)] = np.nan
    hi[~np.isfinite(hi)] = np.nan
    return lo, hi


def bh_qvalues(p) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (q-values). NaN p-values stay NaN, not counted."""
    p = np.asarray(p, dtype=np.float64)
    flat = p.ravel()
    ok = np.flatnonzero(np.isfinite(flat))
    q = np.full(flat.shape, np.nan)
    if ok.size == 0:
        return q.reshape(p.shape)
    pv = flat[ok]
    order = np.argsort(pv, kind="stable")
    ranked = pv[order] * ok.size / np.arange(1, ok.size + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(pv)
    out[order] = np.minimum(ranked, 1.0)
    q[ok] = out
    return q.reshape(p.shape)
