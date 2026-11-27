import numpy as np
import pytest

from rstrends.power import mdt_weatherhead, residual_sigma_phi


def test_mdt_formula_and_inverse():
    # n from Weatherhead eq: n = (3.3 sigma / w * sqrt((1+phi)/(1-phi))) ** (2/3)
    sigma, phi, w = 0.03, 0.3, 0.001
    n = (3.3 * sigma / w * np.sqrt((1 + phi) / (1 - phi))) ** (2 / 3)
    assert mdt_weatherhead(sigma, phi, n) == pytest.approx(w)
    assert mdt_weatherhead(0.03, 0.0, 27) == pytest.approx(3.3 * 0.03 / 27**1.5)
    assert mdt_weatherhead(0.03, 0.5, 27) > mdt_weatherhead(0.03, 0.0, 27)


def test_residual_sigma_phi_recovers_noise_and_ignores_step():
    rng = np.random.default_rng(2)
    t = np.arange(2000, 2027)
    N = 4000
    e = rng.normal(0, 0.02, (t.size, N))
    y = 0.3 + 0.002 * (t - 2000)[:, None] + 0.05 * (t >= 2013)[:, None] + e
    y[3, :100] = np.nan  # one missing-year pattern
    s, p = residual_sigma_phi(y, t, step_at=2013)
    assert np.median(s) == pytest.approx(0.02, rel=0.05)
    # residual autocorrelation is biased low in short series (about -k/n for k regressors)
    assert -0.2 < np.median(p) < 0.0
    s_nostep, _ = residual_sigma_phi(y, t)
    assert np.median(s_nostep) > 1.1 * np.median(s)  # an unmodelled step inflates residuals
