"""Pixel-year and pixel validity rules (plan Section 5.1).

Rules, applied in order:
1. clear count: a pixel-year needs at least `min_clear` clear observations in the season
2. seasonal coverage: a pixel-year needs clear observations in at least `min_sub_seasons`
   of the sub-seasons
3. valid years: a pixel needs at least `min_valid_years` valid pixel-years
4. endpoint coverage: a pixel needs at least `min_per_endpoint` valid years in each of the
   first and last `window` years of the record

Array layout: sub-season clear counts have shape (n_years, n_sub_seasons, *spatial).
Pixel-year masks have shape (n_years, *spatial). Pixel masks have shape (*spatial).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ValidityResult:
    """Masks after each rule. True means the pixel-year or pixel passed."""

    pass_clear: np.ndarray  # (n_years, *spatial) after rule 1
    pass_seasonal: np.ndarray  # (n_years, *spatial) after rules 1 and 2, the final pixel-year mask
    pass_valid_years: np.ndarray  # (*spatial) after rule 3
    pass_endpoint: np.ndarray  # (*spatial) after rules 3 and 4, the final pixel mask


def pixel_year_valid(
    subseason_counts: np.ndarray, min_clear: int, min_sub_seasons: int
) -> tuple[np.ndarray, np.ndarray]:
    """Apply rules 1 and 2. Returns (pass_clear, pass_seasonal)."""
    counts = np.asarray(subseason_counts)
    if counts.ndim < 2:
        raise ValueError("subseason_counts must have shape (n_years, n_sub_seasons, ...)")
    total = counts.sum(axis=1)
    covered = (counts > 0).sum(axis=1)
    pass_clear = total >= min_clear
    pass_seasonal = pass_clear & (covered >= min_sub_seasons)
    return pass_clear, pass_seasonal


def pixel_valid(
    year_valid: np.ndarray, min_valid_years: int, window: int, min_per_endpoint: int
) -> tuple[np.ndarray, np.ndarray]:
    """Apply rules 3 and 4 to a pixel-year mask. Returns (pass_valid_years, pass_endpoint)."""
    yv = np.asarray(year_valid, dtype=bool)
    n = yv.shape[0]
    if 2 * window > n:
        raise ValueError("endpoint windows overlap: 2 * window exceeds the number of years")
    pass_years = yv.sum(axis=0) >= min_valid_years
    first_ok = yv[:window].sum(axis=0) >= min_per_endpoint
    last_ok = yv[n - window :].sum(axis=0) >= min_per_endpoint
    return pass_years, pass_years & first_ok & last_ok


def apply_validity_rules(
    subseason_counts: np.ndarray,
    min_clear: int,
    min_sub_seasons: int,
    min_valid_years: int,
    window: int,
    min_per_endpoint: int,
) -> ValidityResult:
    """Apply all four rules in order and return the mask after each one."""
    pass_clear, pass_seasonal = pixel_year_valid(subseason_counts, min_clear, min_sub_seasons)
    pass_years, pass_end = pixel_valid(pass_seasonal, min_valid_years, window, min_per_endpoint)
    return ValidityResult(pass_clear, pass_seasonal, pass_years, pass_end)


def removal_counts(result: ValidityResult, in_area: np.ndarray | None = None) -> dict:
    """Count what each rule removes, among pixels inside the study area.

    Returns per-year arrays for the pixel-year rules and scalars for the pixel rules.
    Each rule counts only units that survived the previous rules, so the counts add up.
    """
    spatial = result.pass_endpoint.shape
    area = np.ones(spatial, dtype=bool) if in_area is None else np.asarray(in_area, dtype=bool)
    removed_clear = (~result.pass_clear & area).reshape(result.pass_clear.shape[0], -1).sum(axis=1)
    removed_seasonal = (
        (result.pass_clear & ~result.pass_seasonal & area)
        .reshape(result.pass_clear.shape[0], -1)
        .sum(axis=1)
    )
    return {
        "pixel_years_removed_clear_count": removed_clear,
        "pixel_years_removed_seasonal_coverage": removed_seasonal,
        "pixels_removed_valid_years": int((~result.pass_valid_years & area).sum()),
        "pixels_removed_endpoint_coverage": int(
            (result.pass_valid_years & ~result.pass_endpoint & area).sum()
        ),
        "pixels_in_area": int(area.sum()),
        "pixels_passing": int((result.pass_endpoint & area).sum()),
    }
