"""Per-chunk exports share the main composites' grid (plan, December step 5 and 6)."""

import pytest

from rstrends.batches import chunk_subset_years, multi_year_bands, subset_bands
from rstrends.config import load_config
from rstrends.harmonize import oli_coefficient_table, roy_variant
from rstrends.sampling import chunk_bounds, grid_offset

EXPORT_UL = (-285075.0, 1702455.0)  # main export origin (gee.export_region), measured on B4


@pytest.fixture
def cfg():
    return load_config()


def test_main_export_origin_is_on_the_nlcd_grid(cfg):
    t = cfg["grid"]["crs_transform"]
    assert grid_offset(*EXPORT_UL, t) == (71017, 53745)


@pytest.mark.parametrize(
    "row_off,col_off,w,h", [(0, 8192, 512, 512), (2048, 8192, 512, 512), (2560, 13312, 282, 512)]
)
def test_chunk_pixels_line_up_with_the_main_export(cfg, row_off, col_off, w, h):
    t = cfg["grid"]["crs_transform"]
    ulx = EXPORT_UL[0] + col_off * t[0]
    uly = EXPORT_UL[1] + row_off * t[4]
    xmin, ymin, xmax, ymax = chunk_bounds(ulx, uly, w, h, t)
    c0, r0 = grid_offset(*EXPORT_UL, t)
    c, r = grid_offset(xmin, ymax, t)
    assert (c - c0, r - r0) == (col_off, row_off)  # same pixel in main and chunk files
    assert grid_offset(xmax, ymin, t) == (c + w, r + h)


def test_off_grid_region_is_refused(cfg):
    with pytest.raises(ValueError):
        grid_offset(EXPORT_UL[0] + 15, EXPORT_UL[1], cfg["grid"]["crs_transform"])


def test_chunk_subset_years_and_bands(cfg):
    years = chunk_subset_years(cfg, done=(2015, 2016, 2017))
    assert years == [*range(2000, 2015), 2018, 2019]
    bands = multi_year_bands(cfg, years, "subsets")
    assert len(bands) == 84
    assert bands[:4] == [
        "y2000_etm_evi2",
        "y2000_etm_n_spring",
        "y2000_etm_n_summer",
        "y2000_etm_n_fall",
    ]
    assert "y2013_oli_evi2" in bands and "y2012_oli_evi2" not in bands
    assert [b.split("_", 1)[1] for b in bands if b.startswith("y2018_")] == subset_bands(cfg, 2018)
    assert multi_year_bands(cfg, [2000, 2001], "roy") == ["y2000_evi2", "y2001_evi2"]


def test_roy_variant_changes_only_the_etm_to_oli_step(cfg):
    harm = {
        "etm_to_oli": {"red": [1.02, -0.007], "nir": [1.13, -0.022]},
        "tm_to_etm": {"2005": {"red": [1.05, 0.001], "nir": [0.98, 0.004]}},
        "etm_to_oli_mode": "group",
        "etm_to_oli_by_group": {
            "classes": {"woody": [41]},
            "coefficients": {"woody": {"red": [1, 0], "nir": [1, 0]}},
        },
    }
    roy = cfg["harmonization"]["roy2016_rma"]
    v = roy_variant(harm, roy)
    assert v["tm_to_etm"] == harm["tm_to_etm"]
    etm = oli_coefficient_table(v, "ETM", 2005)
    assert etm["classes"] == {}
    assert etm["default"]["red"] == pytest.approx((roy["red"]["slope"], roy["red"]["intercept"]))
    tm = oli_coefficient_table(v, "TM", 2005)
    # TM -> ETM+ with our yearly line, then Roy: s = s1 * s2, i = i1 * s2 + i2
    s1, i1 = harm["tm_to_etm"]["2005"]["nir"]
    s2, i2 = roy["nir"]["slope"], roy["nir"]["intercept"]
    assert tm["default"]["nir"] == pytest.approx((s1 * s2, i1 * s2 + i2))
    assert harm["etm_to_oli_mode"] == "group"  # the original is untouched
