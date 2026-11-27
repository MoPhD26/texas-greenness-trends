"""Export batch definitions (plan Section 8.5)."""

from __future__ import annotations


def main_batches(cfg: dict) -> dict[str, list[int]]:
    """Batch name to years. P is the pilot. B1.. cover the record in batch_years blocks."""
    start, end = cfg["period"]["start_year"], cfg["period"]["end_year"]
    size = cfg["export"]["batch_years"]
    out = {"P": [cfg["export"]["pilot_year"]]}
    years = list(range(start, end + 1))
    blocks = [years[i : i + size] for i in range(0, len(years), size)]
    # a short final block joins the one before it only if it would be a single year
    if len(blocks) > 1 and len(blocks[-1]) == 1:
        blocks[-2] += blocks.pop()
    for k, b in enumerate(blocks, start=1):
        out[f"B{k}"] = b
    return out


SUB_SEASON_PREFIX = "n_"


def export_bands(cfg: dict, year: int) -> list[str]:
    """Band names of one year's main export, in order.

    Main index bands and sub-season clear counts, then for each single-sensor subset that
    covers the year, its EVI2 and its own sub-season counts.
    """
    seasons = list(cfg["season"]["sub_seasons"])
    bands = list(cfg["export"]["main_indices"]) + [f"{SUB_SEASON_PREFIX}{s}" for s in seasons]
    for name, sub in cfg["export"]["subsets"].items():
        y0, y1 = sub["years"]
        if y0 <= year <= y1:
            bands += [f"{name}_evi2"] + [f"{name}_{SUB_SEASON_PREFIX}{s}" for s in seasons]
    return bands
