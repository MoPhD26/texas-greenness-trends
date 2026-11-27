from rstrends.batches import main_batches
from rstrends.config import load_config


def test_batches_match_plan_table():
    b = main_batches(load_config())
    assert b["P"] == [2012]
    assert b["B1"] == list(range(2000, 2005))
    assert b["B5"] == list(range(2020, 2025))
    assert b["B6"] == [2025, 2026]
    assert sorted(y for k, v in b.items() if k != "P" for y in v) == list(range(2000, 2027))


def test_single_leftover_year_joins_previous_block():
    cfg = load_config()
    cfg["period"]["end_year"] = 2025
    cfg["export"]["batch_years"] = 5
    b = main_batches(cfg)
    assert b["B5"] == list(range(2020, 2026))
    assert "B6" not in b


def test_export_bands_by_year():
    from rstrends.batches import export_bands

    cfg = load_config()
    base = ["evi2", "nirv", "kndvi", "n_spring", "n_summer", "n_fall"]
    etm = ["etm_evi2", "etm_n_spring", "etm_n_summer", "etm_n_fall"]
    oli = ["oli_evi2", "oli_n_spring", "oli_n_summer", "oli_n_fall"]
    assert export_bands(cfg, 2005, subsets=True) == base + etm
    assert export_bands(cfg, 2015, subsets=True) == base + etm + oli
    assert export_bands(cfg, 2022, subsets=True) == base
    cfg["export"]["subsets_on_sample"] = True
    assert export_bands(cfg, 2015) == base


def test_subset_bands_and_batches():
    from rstrends.batches import subset_bands, subset_batches

    cfg = load_config()
    assert subset_bands(cfg, 2005) == ["etm_evi2", "etm_n_spring", "etm_n_summer", "etm_n_fall"]
    assert len(subset_bands(cfg, 2015)) == 8 and subset_bands(cfg, 2022) == []
    sb = subset_batches(cfg)
    assert sb == {
        "S1": list(range(2000, 2005)),
        "S2": list(range(2005, 2010)),
        "S3": list(range(2010, 2015)),
        "S4": list(range(2015, 2020)),
    }


def test_remaining_commitments_no_double_count():
    from rstrends.tasklog import remaining_commitments

    c = {"B4": {"hours": 168, "group": "B4"}, "old": 3.0, "B1": {"hours": 154, "group": "B1"}}
    left = remaining_commitments(c, {"B4": 150.0})
    assert left == {"B4": 18.0, "old": 3.0, "B1": 154.0}
    assert remaining_commitments(c, {"B4": 200.0})["B4"] == 0.0
