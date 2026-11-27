import numpy as np

from rstrends.content import flag_years, year_content

ND = -32768


def test_year_content_counts_only_inside_and_valid():
    idx = np.array([[1000, 2000], [ND, 9999]], dtype=np.int16)
    counts = np.array([[[1, 2], [0, 5]], [[3, 0], [0, 5]], [[0, 2], [0, 5]]], dtype=np.int16)
    inside = np.array([[True, True], [True, False]])
    r = year_content(idx, counts, inside, ND, 10000, min_clear=4)
    assert r["pixels_inside"] == 3
    assert np.isclose(r["valid_share"], 2 / 3)
    assert np.isclose(r["p50"], 0.15)  # 0.1 and 0.2, the outside 0.9999 is ignored
    assert r["median_clear"] == 4  # totals 4, 4, 0 inside
    assert np.isclose(r["share_min_clear"], 2 / 3)


def test_flag_years_catches_drop_shift_range_and_counts():
    base = {"valid_share": 0.95, "p1": 0.05, "p50": 0.30, "p99": 0.6, "median_clear": 12}
    rows = [dict(base, year=y) for y in (2000, 2001, 2002, 2003)]
    rows.append(dict(base, year=2004, valid_share=0.80, p50=0.40, p99=1.2, median_clear=3))
    flags = flag_years(rows, 0.05, 0.05, (-0.2, 1.0), 4)
    assert len(flags) == 4
    assert all(f.startswith("2004") for f in flags)
    assert flag_years(rows[:4], 0.05, 0.05, (-0.2, 1.0), 4) == []
