import numpy as np
import pytest
from scipy import stats

from rstrends.flags import (
    count_correlation_flag,
    flicker_flag,
    group_switches,
    spearman_by_pixel,
)


def test_group_switches_and_flicker():
    g = np.array([[2, 2, 2, 1], [2, 3, 1, 1], [2, 3, 2, 1], [2, 3, 1, 1]])
    assert group_switches(g).tolist() == [0, 1, 3, 0]
    assert flicker_flag(g).tolist() == [False, False, True, False]


def test_spearman_matches_scipy_with_ties_and_gaps():
    rng = np.random.default_rng(4)
    T, N = 27, 300
    c = rng.integers(2, 12, (T, N)).astype(float)  # integer counts, many ties
    y = 0.02 * c + rng.normal(0, 0.05, (T, N))
    y[5, :50] = np.nan
    c[9, 100:120] = np.nan
    rho, p = spearman_by_pixel(y, c)
    for j in (0, 60, 110, 299):
        ok = np.isfinite(y[:, j]) & np.isfinite(c[:, j])
        r_ref, p_ref = stats.spearmanr(y[ok, j], c[ok, j])
        assert rho[j] == pytest.approx(r_ref, abs=1e-12)
        assert p[j] == pytest.approx(p_ref, rel=1e-9)


def test_count_flag_uses_bh_and_min_n():
    rng = np.random.default_rng(5)
    T = 27
    c = rng.integers(2, 12, (T, 200)).astype(float)
    y = rng.normal(0, 1, (T, 200))
    y[:, :20] = c[:, :20] + rng.normal(0, 0.1, (T, 20))  # strongly tied to counts
    y[:20, 199] = np.nan  # too few paired years
    rho, q, flag = count_correlation_flag(y, c, q_level=0.10)
    assert flag[:20].all()
    assert flag[20:].mean() < 0.05
    assert np.isnan(q[199]) and not flag[199]
