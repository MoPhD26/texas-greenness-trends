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
