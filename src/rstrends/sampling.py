"""Clustered sample design for the harmonization sample (pure, no Earth Engine).

Points are grouped in small square boxes aligned to the analysis grid. Earth Engine reads
Landsat data in tiles, so points that share a box share the tiles read, which makes the
sample far cheaper than the same number of scattered points. The boxes are a simple random
sample of grid-aligned positions fully inside the province, with no two boxes overlapping.
"""

from __future__ import annotations

import numpy as np
import shapely


def pick_boxes(poly, transform, n: int, box_px: int, seed: int, max_draws: int = 1_000_000):
    """Upper-left corners of n grid-aligned, non-overlapping boxes of box_px pixels inside poly.

    poly and transform must be in the grid's coordinate system. transform is the affine
    [a, 0, x0, 0, e, y0] list of the grid (a > 0, e < 0).
    """
    a, _, x0, _, e, y0 = transform
    side = box_px * a
    shapely.prepare(poly)
    xmin, ymin, xmax, ymax = poly.bounds
    rng = np.random.default_rng(seed)
    corners: dict[tuple[int, int], tuple[int, int]] = {}  # lattice cell -> (col, row)
    chosen: list[tuple[float, float]] = []
    draws = 0
    while len(chosen) < n:
        if draws >= max_draws:
            raise RuntimeError(f"placed only {len(chosen)} of {n} boxes")
        draws += 1
        col = int(np.floor((rng.uniform(xmin, xmax - side) - x0) / a))
        row = int(np.floor((y0 - rng.uniform(ymin + side, ymax)) / -e))
        cell = (col // box_px, row // box_px)
        # a box overlaps another only if their corners are under box_px apart on both axes,
        # which can only happen for boxes in the same or a neighboring lattice cell
        clash = any(
            abs(c - col) < box_px and abs(r - row) < box_px
            for k in ((cell[0] + i, cell[1] + j) for i in (-1, 0, 1) for j in (-1, 0, 1))
            if (cr := corners.get(k)) is not None
            for c, r in [cr]
        )
        if clash or cell in corners:
            continue
        ulx, uly = x0 + col * a, y0 + row * e
        if not poly.contains(shapely.box(ulx, uly - side, ulx + side, uly)):
            continue
        corners[cell] = (col, row)
        chosen.append((ulx, uly))
    return chosen


def snap_bounds(bounds, transform) -> tuple[float, float, int, int]:
    """Grid-aligned upper-left corner, width, and height covering (xmin, ymin, xmax, ymax)."""
    a, _, x0, _, e, y0 = transform
    xmin, ymin, xmax, ymax = bounds
    c0 = int(np.floor((xmin - x0) / a))
    c1 = int(np.ceil((xmax - x0) / a))
    r0 = int(np.floor((y0 - ymax) / -e))
    r1 = int(np.ceil((y0 - ymin) / -e))
    return x0 + c0 * a, y0 + r0 * e, c1 - c0, r1 - r0


def stratified_chunk_sample(strata, fraction: float, min_per_stratum: int, seed: int) -> list:
    """Random sample of chunk keys, proportional within each stratum, with a floor per stratum.

    strata: pandas Series, index = chunk key, value = stratum label.
    """
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    rng = np.random.default_rng(seed)
    chosen = []
    for label in sorted(strata.unique(), key=str):
        keys = sorted(strata.index[strata == label])
        n = min(len(keys), max(min_per_stratum, int(round(fraction * len(keys)))))
        chosen += rng.choice(keys, size=n, replace=False).tolist()
    return sorted(chosen)


def cluster_folds(clusters, k: int, seed: int) -> np.ndarray:
    """Fold number (0 to k-1) for each point, with every cluster kept whole in one fold.

    Clusters are shuffled and dealt to folds in turn, so fold sizes differ by at most one
    cluster. Used for cross-validation by harmonization box.
    """
    clusters = np.asarray(clusters)
    u, inv = np.unique(clusters, return_inverse=True)
    order = np.random.default_rng(seed).permutation(u.size)
    fold_of = np.empty(u.size, dtype=int)
    fold_of[order] = np.arange(u.size) % k
    return fold_of[inv]


def grid_offset(x: float, y: float, transform) -> tuple[int, int]:
    """(col, row) of the pixel whose upper-left corner is (x, y) on the grid of transform.

    transform is a GDAL-style list [a, 0, x0, 0, e, y0]. Raises if (x, y) is not a pixel corner,
    so an export region that would shift the grid is caught before submission.
    """
    a, _, x0, _, e, y0 = transform
    col, row = (x - x0) / a, (y - y0) / e
    if abs(col - round(col)) > 1e-9 or abs(row - round(row)) > 1e-9:
        raise ValueError(f"({x}, {y}) is not a pixel corner of the grid")
    return int(round(col)), int(round(row))


def chunk_bounds(ulx: float, uly: float, w: int, h: int, transform) -> tuple[float, ...]:
    """(xmin, ymin, xmax, ymax) of a chunk, checked to sit on pixel corners of the grid."""
    a, e = transform[0], transform[4]
    grid_offset(ulx, uly, transform)
    return ulx, uly + h * e, ulx + w * a, uly
