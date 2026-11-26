"""Cross-sensor harmonization fits (plan Section 3).

Linear transforms map a source sensor's reflectance to a target sensor's:
    target = intercept + slope * source

Reduced major axis (RMA) regression is primary because both sensors carry measurement
error, and ordinary least squares (OLS) would bias the slope toward zero. Roy et al. (2016)
report both. OLS is also fitted here so our numbers can be compared with Roy's OLS set.

Confidence intervals use a cluster bootstrap: whole sample points are resampled, so
repeated years at the same point are not treated as independent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    n: int
    r: float
    slope_ci: tuple[float, float] | None = None
    intercept_ci: tuple[float, float] | None = None

    def apply(self, x):
        return self.intercept + self.slope * np.asarray(x, dtype=np.float64)


def _clean(x, y):
    x, y = np.asarray(x, dtype=np.float64).ravel(), np.asarray(y, dtype=np.float64).ravel()
    if x.shape != y.shape:
        raise ValueError("x and y must have the same length")
    ok = np.isfinite(x) & np.isfinite(y)
    return x[ok], y[ok]


def _rma(x, y):
    sx, sy = x.std(ddof=1), y.std(ddof=1)
    r = np.corrcoef(x, y)[0, 1]
    slope = np.sign(r) * sy / sx
    return slope, y.mean() - slope * x.mean(), r


def _ols(x, y):
    xm, ym = x.mean(), y.mean()
    slope = np.sum((x - xm) * (y - ym)) / np.sum((x - xm) ** 2)
    return slope, ym - slope * xm, np.corrcoef(x, y)[0, 1]


_METHODS = {"rma": _rma, "ols": _ols}


def fit_linear(
    x,
    y,
    method: str = "rma",
    groups=None,
    n_boot: int = 0,
    ci: float = 0.95,
    seed: int = 0,
) -> LinearFit:
    """Fit target y against source x.

    groups: optional cluster label per observation (for example a point ID). The bootstrap
    resamples clusters. Without groups, each observation is its own cluster.
    """
    if method not in _METHODS:
        raise ValueError(f"method must be one of {sorted(_METHODS)}")
    xr = np.asarray(x, dtype=np.float64).ravel()
    yr = np.asarray(y, dtype=np.float64).ravel()
    g = np.arange(xr.size) if groups is None else np.asarray(groups).ravel()
    ok = np.isfinite(xr) & np.isfinite(yr)
    xr, yr, g = xr[ok], yr[ok], g[ok]
    if xr.size < 3:
        raise ValueError("need at least 3 valid pairs")
    fn = _METHODS[method]
    slope, intercept, r = fn(xr, yr)
    slope_ci = intercept_ci = None
    if n_boot > 0:
        rng = np.random.default_rng(seed)
        uniq, inv = np.unique(g, return_inverse=True)
        order = np.argsort(inv, kind="stable")
        starts = np.searchsorted(inv[order], np.arange(uniq.size))
        ends = np.append(starts[1:], inv.size)
        boots = np.empty((n_boot, 2))
        for b in range(n_boot):
            pick = rng.integers(0, uniq.size, uniq.size)
            idx = np.concatenate([order[starts[k] : ends[k]] for k in pick])
            s, i, _ = fn(xr[idx], yr[idx])
            boots[b] = s, i
        lo, hi = (1 - ci) / 2 * 100, (1 + ci) / 2 * 100
        slope_ci = tuple(np.percentile(boots[:, 0], [lo, hi]))
        intercept_ci = tuple(np.percentile(boots[:, 1], [lo, hi]))
    return LinearFit(float(slope), float(intercept), int(xr.size), float(r), slope_ci, intercept_ci)


def compose(first: tuple[float, float], second: tuple[float, float]) -> tuple[float, float]:
    """Chain two transforms given as (slope, intercept): apply `first`, then `second`.

    Used for TM -> ETM+ -> OLI.
    """
    s1, i1 = first
    s2, i2 = second
    return s2 * s1, s2 * i1 + i2


def allocate(class_counts: pd.Series, total: int, floor: int) -> pd.Series:
    """Area-proportional allocation with a minimum per class, capped by availability."""
    share = class_counts / class_counts.sum()
    alloc = np.maximum((share * total).round().astype(int), floor)
    alloc = np.minimum(alloc, class_counts)
    # scale the classes above the floor so the total stays close to the target
    over = alloc > floor
    excess = alloc.sum() - total
    if excess > 0 and over.any():
        alloc[over] = np.maximum(
            floor, (alloc[over] - excess * alloc[over] / alloc[over].sum()).round().astype(int)
        )
    return alloc.astype(int)


def fit_stats(x, y, fit: LinearFit) -> dict[str, float]:
    """Agreement of target y with the transformed source x.

    r and R2 (= r squared, the share of target variance explained by a linear relation) do not
    depend on the method. RMSE and bias are of y minus the transformed x, so they show how
    well each method's line reproduces the target.
    """
    x, y = _clean(x, y)
    resid = y - fit.apply(x)
    r = float(np.corrcoef(x, y)[0, 1])
    return {
        "n": int(x.size),
        "r": r,
        "r2": r * r,
        "rmse": float(np.sqrt(np.mean(resid**2))),
        "bias": float(np.mean(resid)),
    }
