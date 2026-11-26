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
    base = ["evi2", "n_spring", "n_summer", "n_fall"]
    etm = ["etm_evi2", "etm_n_spring", "etm_n_summer", "etm_n_fall"]
    oli = ["oli_evi2", "oli_n_spring", "oli_n_summer", "oli_n_fall"]
    assert export_bands(cfg, 2005) == base + etm
    assert export_bands(cfg, 2015) == base + etm + oli
    assert export_bands(cfg, 2022) == base


def test_sample_chunks_reproducible():
    from rstrends.batches import sample_chunks

    keys = [f"k{i}" for i in range(1318)]
    a = sample_chunks(keys, 0.10, 1)
    assert a == sample_chunks(list(reversed(keys)), 0.10, 1)
    assert len(a) == 132 and len(set(a)) == 132
