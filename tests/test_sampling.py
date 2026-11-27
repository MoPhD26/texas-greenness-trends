import itertools

import shapely

from rstrends.sampling import pick_boxes

T = [30, 0, -1000, 0, -30, 1000]


def test_boxes_inside_aligned_and_disjoint():
    poly = shapely.Polygon([(0, 0), (30000, 0), (30000, 20000), (0, 25000)])
    boxes = pick_boxes(poly, T, n=40, box_px=20, seed=1)
    assert len(boxes) == 40
    side = 20 * 30
    geoms = [shapely.box(x, y - side, x + side, y) for x, y in boxes]
    for (x, y), g in zip(boxes, geoms, strict=True):
        assert (x - T[2]) % 30 == 0 and (T[5] - y) % 30 == 0
        assert poly.contains(g)
    for g1, g2 in itertools.combinations(geoms, 2):
        assert g1.intersection(g2).area == 0


def test_boxes_reproducible():
    poly = shapely.box(0, 0, 20000, 20000)
    assert pick_boxes(poly, T, 10, 16, seed=3) == pick_boxes(poly, T, 10, 16, seed=3)
    assert pick_boxes(poly, T, 10, 16, seed=3) != pick_boxes(poly, T, 10, 16, seed=4)


def test_snap_bounds_matches_grid():
    from rstrends.sampling import snap_bounds

    t = [30, 0, -2415585, 0, -30, 3314805]
    ulx, uly, w, h = snap_bounds((-306700.0, 300000.0, 137700.0, 1706590.0), t)
    assert (ulx - t[2]) % 30 == 0 and (t[5] - uly) % 30 == 0
    assert ulx <= -306700 and uly >= 1706590
    assert ulx + 30 * w >= 137700 and uly - 30 * h <= 300000
    assert ulx > -306700 - 30 and uly < 1706590 + 30


def test_stratified_chunk_sample_floor_and_reproducible():
    import pandas as pd

    from rstrends.sampling import stratified_chunk_sample

    strata = pd.Series(["a"] * 100 + ["b"] * 30 + ["c"] * 4, index=[f"k{i}" for i in range(134)])
    s = stratified_chunk_sample(strata, 0.2, 5, seed=1)
    got = strata[s].value_counts()
    assert got["a"] == 20 and got["b"] == 6 and got["c"] == 4
    assert s == stratified_chunk_sample(strata, 0.2, 5, seed=1)
