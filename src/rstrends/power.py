"""Minimum detectable trend (plan Section 5, power).

Weatherhead et al. (1998, Journal of Geophysical Research 103(D14), 17149-17161,
https://doi.org/10.1029/98JD00995) give the number of years needed to detect a linear trend
of size w with probability 0.90 at the 5% level, for annual data with residual standard
deviation sigma and lag-1 autocorrelation phi:

    n = [ (3.3 * sigma / |w|) * sqrt((1 + phi) / (1 - phi)) ] ** (2 / 3)

Solved for w, the minimum detectable trend for a record of n years is

    w = 3.3 * sigma * sqrt((1 + phi) / (1 - phi)) / n ** 1.5
"""

from __future__ import annotations

import numpy as np

PHI_LIMIT = 0.9  # keep the autocorrelation factor finite for short, noisy series


def mdt_weatherhead(sigma, phi, n):
    """Minimum detectable trend per year (90% detection probability, 5% level)."""
    sigma = np.asarray(sigma, dtype=np.float64)
    phi = np.clip(np.asarray(phi, dtype=np.float64), -PHI_LIMIT, PHI_LIMIT)
    n = np.asarray(n, dtype=np.float64)
    return 3.3 * sigma * np.sqrt((1 + phi) / (1 - phi)) / n**1.5


def residual_sigma_phi(y, t, step_at=None):
    """Residual standard deviation and lag-1 autocorrelation per series.

    y: (T, N) array with NaN for missing years. t: (T,) years. Each series is fitted by OLS
    with an intercept and a linear trend, plus a step at `step_at` if given (the step absorbs
    a known level shift, for example a sensor change in data that were not harmonized).
    The autocorrelation uses consecutive years where both residuals exist. In short series it
    is biased low (roughly -k/n for k fitted terms), which makes the detectable trend slightly
    smaller, the cautious direction when it is compared with a possible false trend.
    """
    y = np.asarray(y, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64)
    cols = [np.ones_like(t), t - t.mean()]
    if step_at is not None:
        cols.append((t >= step_at).astype(np.float64))
    X = np.stack(cols, axis=1)
    T, N = y.shape
    sigma = np.full(N, np.nan)
    phi = np.full(N, np.nan)
    ok = np.isfinite(y)
    # group series by their missing-year pattern so each pattern is one least squares solve
    keys, inv = np.unique(ok.T, axis=0, return_inverse=True)
    for k, mask in enumerate(keys):
        idx = np.flatnonzero(inv.ravel() == k)
        if mask.sum() < X.shape[1] + 3:
            continue
        Xm = X[mask]
        coef, *_ = np.linalg.lstsq(Xm, y[mask][:, idx], rcond=None)
        r = np.full((T, idx.size), np.nan)
        r[mask] = y[mask][:, idx] - Xm @ coef
        dof = mask.sum() - X.shape[1]
        sigma[idx] = np.sqrt(np.nansum(r**2, axis=0) / dof)
        a, b = r[:-1], r[1:]
        both = np.isfinite(a) & np.isfinite(b)
        num = np.where(both, a * b, 0).sum(axis=0)
        den = np.where(np.isfinite(r), r**2, 0).sum(axis=0)
        phi[idx] = num / den
    return sigma, phi
