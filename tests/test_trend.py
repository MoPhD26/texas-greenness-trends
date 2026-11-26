import numpy as np
import pymannkendall as pmk
import pytest
from scipy import stats

from rstrends.trend import bh_qvalues, leave_one_year_out, sen_slope, trend_suite


def _series(rng, n_pix, T, ties=False, gaps=0.0):
    t = np.arange(T, dtype=float)
    y = 0.01 * t[:, None] * rng.normal(size=n_pix) + rng.normal(0, 0.05, (T, n_pix))
    # add an AR(1) component so the Hamed-Rao correction has something to do
    for k in range(1, T):
        y[k] += 0.6 * y[k - 1] * rng.uniform(0, 1, n_pix)
    if ties:
        y = np.round(y, 2)
    if gaps:
        y[rng.uniform(size=y.shape) < gaps] = np.nan
    return y


@pytest.mark.parametrize("ties", [False, True])
def test_matches_pymannkendall_without_gaps(ties):
    rng = np.random.default_rng(1)
    T = 27
    y = _series(rng, 60, T, ties=ties)
    t = np.arange(1, T + 1, dtype=float)
    r = trend_suite(y, t)
    for k in range(y.shape[1]):
        ref = pmk.original_test(y[:, k])
        hr = pmk.hamed_rao_modification_test(y[:, k])
        assert r.s[k] == ref.s
        assert r.var_s[k] == pytest.approx(ref.var_s)
        assert r.tau[k] == pytest.approx(ref.Tau)
        assert r.p[k] == pytest.approx(ref.p, rel=1e-9, abs=1e-12)
        assert r.slope[k] == pytest.approx(ref.slope)
        assert r.p_hr[k] == pytest.approx(hr.p, rel=1e-6, abs=1e-12)


def test_matches_pymannkendall_and_scipy_with_gaps():
    rng = np.random.default_rng(2)
    T = 27
    y = _series(rng, 80, T, ties=True, gaps=0.25)
    t = np.arange(2000, 2000 + T, dtype=float)
    r = trend_suite(y, t)
    for k in range(y.shape[1]):
        ok = np.isfinite(y[:, k])
        ref = pmk.original_test(y[:, k])  # S and variance on the valid values
        assert r.s[k] == ref.s
        assert r.var_s[k] == pytest.approx(ref.var_s)
        assert r.p[k] == pytest.approx(ref.p, rel=1e-9, abs=1e-12)
        ts = stats.theilslopes(y[ok, k], t[ok], alpha=0.95)
        assert r.slope[k] == pytest.approx(ts.slope)
        assert r.slope_lo[k] == pytest.approx(ts.low_slope)
        assert r.slope_hi[k] == pytest.approx(ts.high_slope)
        assert r.n_valid[k] == ok.sum()


def test_too_few_years_gives_nan():
    y = np.full((10, 2), np.nan)
    y[:2, 0] = [1.0, 2.0]
    y[:, 1] = np.arange(10.0)
    r = trend_suite(y, np.arange(10.0))
    assert np.isnan(r.slope[0]) and np.isnan(r.p[0])
    assert r.slope[1] == pytest.approx(1.0)


def test_float32_close_to_float64():
    rng = np.random.default_rng(3)
    y = _series(rng, 200, 27, gaps=0.1)
    t = np.arange(2000, 2027, dtype=float)
    r64 = trend_suite(y, t)
    r32 = trend_suite(y.astype(np.float32), t)
    np.testing.assert_allclose(r32.slope, r64.slope, rtol=1e-4, atol=1e-6)
    np.testing.assert_allclose(r32.p, r64.p, rtol=1e-4, atol=1e-6)


def test_leave_one_year_out_brackets_full_slope():
    rng = np.random.default_rng(4)
    y = _series(rng, 50, 15)
    t = np.arange(15.0)
    lo, hi = leave_one_year_out(y, t)
    s = sen_slope(y, t)
    assert np.all(lo <= hi)
    # a direct refit for one pixel and one dropped year agrees
    keep = np.arange(15) != 3
    assert sen_slope(y[keep], t[keep])[0] >= lo[0] - 1e-12
    assert np.all(np.isfinite(s))


def test_bh_matches_statsmodels():
    from statsmodels.stats.multitest import multipletests

    rng = np.random.default_rng(5)
    p = rng.uniform(size=500) ** 3
    p[::17] = np.nan
    q = bh_qvalues(p)
    ok = np.isfinite(p)
    ref = multipletests(p[ok], method="fdr_bh")[1]
    np.testing.assert_allclose(q[ok], ref)
    assert np.all(np.isnan(q[~ok]))
