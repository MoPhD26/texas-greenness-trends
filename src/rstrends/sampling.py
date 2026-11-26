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
