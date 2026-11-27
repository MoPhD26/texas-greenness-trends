import numpy as np
import pytest

from rstrends import harmonize, indices, qa


def test_qa_pixel_clear_flags():
    clear = 1 << 6  # "clear" bit only
    cloud = clear | (1 << 3)
    cirrus = 1 << 2
    water = 1 << 7
    arr = np.array([clear, cloud, cirrus, water, 1 << 1, 1 << 4, 1 << 5, 1])
    np.testing.assert_array_equal(
        qa.qa_pixel_clear(arr, "OLI"), [True, False, False, False, False, False, False, False]
    )
    # cirrus bit is unused on ETM+ and must not mask
    np.testing.assert_array_equal(qa.qa_pixel_clear(arr, "ETM")[:3], [True, False, True])


def test_unknown_family_rejected():
    with pytest.raises(ValueError):
        qa.qa_pixel_mask_bits("MSS")


def test_radsat_bits_per_family():
    red_sat_tm = 1 << 2
    red_sat_oli = 1 << 3
    assert not qa.radsat_ok(np.array([red_sat_tm]), "TM")[0]
    assert qa.radsat_ok(np.array([red_sat_tm]), "OLI")[0]
    assert not qa.radsat_ok(np.array([red_sat_oli]), "OLI")[0]
    assert not qa.radsat_ok(np.array([1 << 4]), "OLI")[0]  # OLI NIR is band 5


def test_aerosol_and_opacity():
    vals = np.array([0b00 << 6, 0b01 << 6, 0b10 << 6, 0b11 << 6 | 0b10])
    np.testing.assert_array_equal(qa.aerosol_ok(vals), [True, True, True, False])
    np.testing.assert_array_equal(
        qa.opacity_ok(np.array([50, 300, 301, -9999]), 0.3), [True, True, False, True]
    )


def test_scale_and_range():
    assert qa.scale_sr(np.array([7273]))[0] == pytest.approx(0.0000275 * 7273 - 0.2)
    np.testing.assert_array_equal(
        qa.reflectance_in_range(np.array([0.1, -0.01, 0.5]), np.array([0.2, 0.3, 1.2])),
        [True, False, False],
    )


def test_indices_known_values():
    red, nir = 0.05, 0.45
    assert indices.ndvi(red, nir) == pytest.approx(0.8)
    assert indices.evi2(red, nir) == pytest.approx(2.5 * 0.4 / (0.45 + 0.12 + 1))
    assert indices.nirv(red, nir) == pytest.approx(0.8 * 0.45)
    assert indices.kndvi(red, nir) == pytest.approx(np.tanh(0.64))


def test_int16_round_trip():
    v = np.array([0.1234, -0.5, np.nan])
    s = indices.to_int16(v, 10000)
    np.testing.assert_array_equal(s, [1234, -5000, indices.INT16_NODATA])
    back = indices.from_int16(s, 10000)
    assert back[0] == pytest.approx(0.1234) and np.isnan(back[2])
    with pytest.raises(ValueError):
        indices.to_int16(np.array([4.0]), 10000)


def test_rma_recovers_symmetric_line_and_ols_attenuates():
    rng = np.random.default_rng(0)
    truth = rng.uniform(0.05, 0.5, 20000)
    x = truth + rng.normal(0, 0.03, truth.size)
    y = 0.01 + 0.95 * truth + rng.normal(0, 0.03 * 0.95, truth.size)
    rma = harmonize.fit_linear(x, y, "rma")
    ols = harmonize.fit_linear(x, y, "ols")
    assert rma.slope == pytest.approx(0.95, abs=0.01)
    assert ols.slope < rma.slope  # errors in x pull OLS toward zero
    # RMA is symmetric: fitting x on y gives the inverse line
    inv = harmonize.fit_linear(y, x, "rma")
    assert inv.slope == pytest.approx(1 / rma.slope)


def test_cluster_bootstrap_ci_contains_estimate():
    rng = np.random.default_rng(1)
    pts = np.repeat(np.arange(300), 5)
    x = rng.uniform(0, 1, pts.size)
    y = 2 * x + 0.1 + rng.normal(0, 0.05, pts.size)
    f = harmonize.fit_linear(x, y, "rma", groups=pts, n_boot=200, seed=2)
    assert f.slope_ci[0] < f.slope < f.slope_ci[1]
    assert f.intercept_ci[0] < f.intercept < f.intercept_ci[1]
    assert f.n == pts.size


def test_compose_chain():
    first, second = (0.9, 0.02), (1.1, -0.01)
    s, i = harmonize.compose(first, second)
    x = 0.3
    assert s * x + i == pytest.approx(1.1 * (0.9 * x + 0.02) - 0.01)


def test_allocate_proportional_with_floor():
    import pandas as pd

    counts = pd.Series({41: 50000, 71: 40000, 81: 9000, 95: 600, 31: 100})
    alloc = harmonize.allocate(counts, total=10000, floor=500)
    assert alloc[31] == 100  # capped by availability
    assert alloc[95] == 500  # raised to the floor
    assert alloc[41] > alloc[71] > alloc[81] >= 500
    assert abs(alloc.sum() - 10000) <= 150


def test_fit_stats_perfect_and_noisy():
    x = np.linspace(0.05, 0.5, 200)
    f = harmonize.fit_linear(x, 0.01 + 0.9 * x, "rma")
    st = harmonize.fit_stats(x, 0.01 + 0.9 * x, f)
    assert st["r2"] == pytest.approx(1.0) and st["rmse"] == pytest.approx(0, abs=1e-12)
    rng = np.random.default_rng(3)
    y = 0.01 + 0.9 * x + rng.normal(0, 0.02, x.size)
    ols = harmonize.fit_linear(x, y, "ols")
    rma = harmonize.fit_linear(x, y, "rma")
    s_ols, s_rma = harmonize.fit_stats(x, y, ols), harmonize.fit_stats(x, y, rma)
    assert s_ols["rmse"] <= s_rma["rmse"]  # OLS minimizes squared error in y
    assert s_ols["bias"] == pytest.approx(0, abs=1e-12)
    assert s_ols["n"] == 200


def test_deming_special_cases_and_recovery():
    rng = np.random.default_rng(5)
    t = rng.uniform(0, 1, 20000)
    x = t + rng.normal(0, 0.05, t.size)
    y = 0.1 + 1.2 * t + rng.normal(0, 0.1, t.size)
    lam_true = 0.1**2 / 0.05**2
    dem = harmonize.fit_linear(x, y, "deming", lam=lam_true)
    assert dem.slope == pytest.approx(1.2, abs=0.02)
    assert dem.intercept == pytest.approx(0.1, abs=0.02)
    # RMA is Deming with lam = var(y) / var(x), OLS is the large-lam limit
    rma = harmonize.fit_linear(x, y, "rma")
    lam_rma = y.var() / x.var()
    assert harmonize.fit_linear(x, y, "deming", lam=lam_rma).slope == pytest.approx(rma.slope)
    ols = harmonize.fit_linear(x, y, "ols")
    assert harmonize.fit_linear(x, y, "deming", lam=1e9).slope == pytest.approx(ols.slope, 1e-6)
    with pytest.raises(ValueError):
        harmonize.fit_linear(x, y, "deming")


def test_median_error_variance_and_lambda():
    v = harmonize.median_error_variance([0.02, 0.04], [10, 0])
    assert v[0] == pytest.approx(np.pi / 2 * 0.0004 / 10)
    assert np.isnan(v[1])
    assert harmonize.deming_lambda([1.0, 3.0], [4.0, np.nan]) == pytest.approx(2.0)


def test_smooth_in_time_reproduces_cubic_and_respects_weights():
    years = np.arange(2000, 2012)
    truth = 1.0 + 0.01 * (years - 2005) - 0.002 * (years - 2005) ** 2
    se = np.full(years.size, 0.01)
    assert harmonize.smooth_in_time(years, truth, se) == pytest.approx(truth)
    noisy = truth.copy()
    noisy[4] += 0.2
    se_out = se.copy()
    se_out[4] = 10.0  # a very uncertain year barely moves the curve
    sm = harmonize.smooth_in_time(years, noisy, se_out)
    assert np.max(np.abs(np.delete(sm - truth, 4))) < 0.002


def test_oli_coefficient_table_single_and_group():
    harm = {
        "etm_to_oli": {"red": [1.0, 0.0], "nir": [1.1, -0.02]},
        "tm_to_etm": {"2005": {"red": [1.02, -0.003], "nir": [0.99, 0.001]}},
        "etm_to_oli_by_group": {
            "classes": {"woody": [41, 43], "herb": [71]},
            "coefficients": {
                "woody": {"red": [1.05, -0.01], "nir": [1.2, -0.05]},
                "herb": {"red": [0.98, 0.002], "nir": [1.05, -0.01]},
            },
        },
    }
    t = harmonize.oli_coefficient_table(harm, "ETM", 2005)
    assert t["default"]["nir"] == (1.1, -0.02) and t["classes"] == {}
    harm["etm_to_oli_mode"] = "group"
    t = harmonize.oli_coefficient_table(harm, "TM", 2005)
    assert set(t["classes"]) == {41, 43, 71}
    s, i = t["classes"][43]["nir"]
    assert (s, i) == pytest.approx(harmonize.compose((0.99, 0.001), (1.2, -0.05)))
    assert t["default"]["red"] == pytest.approx(harmonize.compose((1.02, -0.003), (1.0, 0.0)))
    with pytest.raises(ValueError):
        harmonize.oli_coefficient_table(harm, "OLI", 2005)
