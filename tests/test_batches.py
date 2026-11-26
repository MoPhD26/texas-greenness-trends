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
