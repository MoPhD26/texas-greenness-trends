"""Landsat Collection 2 Level-2 QA decoding and reflectance scaling (plan Section 5.1).

Bit positions come from the USGS Collection 2 QA band page
(https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands)
and the Earth Engine catalog pages for LANDSAT/LE07/C02/T1_L2 and LANDSAT/LC08/C02/T1_L2.
The same constants drive the Earth Engine masking code, so the tested logic here and
the server-side logic cannot drift apart.
"""

from __future__ import annotations

import numpy as np

# Surface reflectance scaling, identical for all Collection 2 Level-2 sensors (USGS)
SR_SCALE = 0.0000275
SR_OFFSET = -0.2

# QA_PIXEL bits
QA_FILL = 0
QA_DILATED_CLOUD = 1
QA_CIRRUS = 2  # OLI only. Unused on TM and ETM+.
QA_CLOUD = 3
QA_CLOUD_SHADOW = 4
QA_SNOW = 5
QA_WATER = 7

# SR_QA_AEROSOL (OLI): bits 6-7 hold the aerosol level, 3 = high
AEROSOL_LEVEL_SHIFT = 6
AEROSOL_LEVEL_HIGH = 3

# SR_ATMOS_OPACITY (TM, ETM+) scale factor
OPACITY_SCALE = 0.001

# Per family: surface reflectance band names for red and NIR, and their QA_RADSAT bits.
# QA_RADSAT bit (k - 1) flags saturation in band k.
SENSOR_BANDS = {
    "TM": {"red": "SR_B3", "nir": "SR_B4", "radsat_bits": (2, 3)},
    "ETM": {"red": "SR_B3", "nir": "SR_B4", "radsat_bits": (2, 3)},
    "OLI": {"red": "SR_B4", "nir": "SR_B5", "radsat_bits": (3, 4)},
}


def qa_pixel_mask_bits(family: str) -> tuple[int, ...]:
    """QA_PIXEL bits that must all be 0 for an observation to count as clear."""
    bits = [QA_FILL, QA_DILATED_CLOUD, QA_CLOUD, QA_CLOUD_SHADOW, QA_SNOW, QA_WATER]
    if family == "OLI":
        bits.append(QA_CIRRUS)
    elif family not in ("TM", "ETM"):
        raise ValueError(f"unknown sensor family {family!r}")
    return tuple(sorted(bits))


def bits_to_mask(bits: tuple[int, ...]) -> int:
    """Integer with the given bit positions set."""
    m = 0
    for b in bits:
        m |= 1 << b
    return m


def qa_pixel_clear(qa_pixel: np.ndarray, family: str) -> np.ndarray:
    """True where none of the flagged QA_PIXEL bits are set."""
    return (np.asarray(qa_pixel).astype(np.int64) & bits_to_mask(qa_pixel_mask_bits(family))) == 0


def radsat_ok(qa_radsat: np.ndarray, family: str) -> np.ndarray:
    """True where neither red nor NIR is saturated."""
    m = bits_to_mask(SENSOR_BANDS[family]["radsat_bits"])
    return (np.asarray(qa_radsat).astype(np.int64) & m) == 0


def aerosol_ok(sr_qa_aerosol: np.ndarray) -> np.ndarray:
    """True where the OLI aerosol level is not high."""
    level = (np.asarray(sr_qa_aerosol).astype(np.int64) >> AEROSOL_LEVEL_SHIFT) & 0b11
    return level != AEROSOL_LEVEL_HIGH


def opacity_ok(sr_atmos_opacity: np.ndarray, max_opacity: float) -> np.ndarray:
    """True where TM or ETM+ scaled atmospheric opacity is at or below the threshold.

    Opacity fill (no value) is not treated as hazy here. QA_PIXEL fill handles missing data.
    """
    raw = np.asarray(sr_atmos_opacity)
    return (raw * OPACITY_SCALE <= max_opacity) | (raw < 0)


def scale_sr(dn: np.ndarray) -> np.ndarray:
    """Convert Collection 2 surface reflectance digital numbers to reflectance."""
    return np.asarray(dn, dtype=np.float64) * SR_SCALE + SR_OFFSET


def reflectance_in_range(*bands: np.ndarray) -> np.ndarray:
    """True where every band lies in the physical range 0 to 1."""
    ok = np.ones(np.shape(bands[0]), dtype=bool)
    for b in bands:
        b = np.asarray(b)
        ok &= (b >= 0) & (b <= 1)
    return ok
