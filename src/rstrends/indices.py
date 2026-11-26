"""Vegetation indices from red and NIR surface reflectance (plan Section 4).

EVI2: Jiang et al. (2008), https://doi.org/10.1016/j.rse.2008.06.006
NIRv: Badgley et al. (2017), https://doi.org/10.1126/sciadv.1602244
kNDVI: Camps-Valls et al. (2021), https://doi.org/10.1126/sciadv.abc7447, using the
       recommended kernel width sigma = 0.5 * (NIR + red), which reduces kNDVI to tanh(NDVI^2).
"""

from __future__ import annotations

import numpy as np

INT16_NODATA = -32768


def ndvi(red, nir):
    red, nir = np.asarray(red, dtype=np.float64), np.asarray(nir, dtype=np.float64)
    return (nir - red) / (nir + red)


def evi2(red, nir):
    red, nir = np.asarray(red, dtype=np.float64), np.asarray(nir, dtype=np.float64)
    return 2.5 * (nir - red) / (nir + 2.4 * red + 1.0)


def nirv(red, nir):
    return ndvi(red, nir) * np.asarray(nir, dtype=np.float64)


def kndvi(red, nir):
    return np.tanh(ndvi(red, nir) ** 2)


def to_int16(values, scale: int) -> np.ndarray:
    """Store an index as int16 = round(value * scale), with NaN mapped to the nodata value."""
    v = np.asarray(values, dtype=np.float64) * scale
    out = np.full(v.shape, INT16_NODATA, dtype=np.int16)
    ok = np.isfinite(v)
    if np.any(np.abs(v[ok]) > 32767):
        raise ValueError("scaled index exceeds the int16 range")
    out[ok] = np.round(v[ok]).astype(np.int16)
    return out


def from_int16(stored, scale: int) -> np.ndarray:
    """Inverse of to_int16, with nodata mapped back to NaN."""
    s = np.asarray(stored)
    out = s.astype(np.float32) / scale
    out[s == INT16_NODATA] = np.nan
    return out
