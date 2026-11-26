import numpy as np
import pytest

from rstrends.validity import apply_validity_rules, pixel_valid, pixel_year_valid, removal_counts


def counts(*per_year):
    """Build (n_years, 3, 1) sub-season counts for a single pixel."""
    return np.array(per_year, dtype=np.uint8).reshape(len(per_year), 3, 1)


def test_clear_count_rule():
    c = counts([1, 1, 1], [2, 1, 1], [4, 0, 0])
    pass_clear, _ = pixel_year_valid(c, min_clear=4, min_sub_seasons=2)
    assert pass_clear[:, 0].tolist() == [False, True, True]


def test_seasonal_coverage_rule_rejects_one_sub_season():
    # Year 3 has 4 clear dates, but all in spring, so it fails seasonal coverage.
    c = counts([2, 2, 0], [1, 1, 2], [4, 0, 0])
    pass_clear, pass_seasonal = pixel_year_valid(c, min_clear=4, min_sub_seasons=2)
    assert pass_clear[:, 0].tolist() == [True, True, True]
    assert pass_seasonal[:, 0].tolist() == [True, True, False]


def test_seasonal_rule_never_passes_a_year_that_failed_clear_count():
    c = counts([1, 1, 1])
    _, pass_seasonal = pixel_year_valid(c, min_clear=4, min_sub_seasons=2)
    assert not pass_seasonal.any()


def test_endpoint_rule():
    # 12 years, window 5, need 3 per window and 8 total.
    good = np.array([1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 0], dtype=bool)  # 3 first, 3 last, 8 total
    weak_start = np.array([1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1], dtype=bool)  # 2 first
    yv = np.stack([good, weak_start], axis=1)  # (12, 2)
    pass_years, pass_end = pixel_valid(yv, min_valid_years=8, window=5, min_per_endpoint=3)
    assert pass_years.tolist() == [True, True]
    assert pass_end.tolist() == [True, False]


def test_endpoint_windows_must_not_overlap():
    with pytest.raises(ValueError):
        pixel_valid(np.ones((8, 1), dtype=bool), 4, window=5, min_per_endpoint=3)


def test_removal_counts_add_up():
    rng = np.random.default_rng(0)
    c = rng.integers(0, 4, size=(27, 3, 10, 10))
    res = apply_validity_rules(c, 4, 2, 20, 5, 3)
    rc = removal_counts(res)
    n_pixel_years = 27 * 100
    kept_years = int(res.pass_seasonal.sum())
    removed_years = (
        rc["pixel_years_removed_clear_count"].sum()
        + rc["pixel_years_removed_seasonal_coverage"].sum()
    )
    assert removed_years + kept_years == n_pixel_years
    assert (
        rc["pixels_removed_valid_years"]
        + rc["pixels_removed_endpoint_coverage"]
        + rc["pixels_passing"]
        == rc["pixels_in_area"]
    )


def test_removal_counts_ignore_pixels_outside_area():
    c = np.zeros((10, 3, 2), dtype=np.uint8)  # every pixel-year fails
    res = apply_validity_rules(c, 4, 2, 6, 3, 2)
    rc = removal_counts(res, in_area=np.array([True, False]))
    assert rc["pixel_years_removed_clear_count"].tolist() == [1] * 10
    assert rc["pixels_in_area"] == 1
