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


def export_bands(cfg: dict, year: int, subsets: bool | None = None) -> list[str]:
    """Band names of one year's main export, in order.

    Main index bands and sub-season clear counts. The single-sensor subset bands follow only
    when subsets is True, or when subsets is None and the config does not put them on the
    chunk sample (export.subsets_on_sample).
    """
    if subsets is None:
        subsets = not cfg["export"].get("subsets_on_sample", False)
    seasons = list(cfg["season"]["sub_seasons"])
    bands = list(cfg["export"]["main_indices"]) + [f"{SUB_SEASON_PREFIX}{s}" for s in seasons]
    return bands + (subset_bands(cfg, year) if subsets else [])


def subset_bands(cfg: dict, year: int) -> list[str]:
    """For each single-sensor subset that covers the year: its EVI2 and sub-season counts."""
    seasons = list(cfg["season"]["sub_seasons"])
    bands = []
    for name, sub in cfg["export"]["subsets"].items():
        y0, y1 = sub["years"]
        if y0 <= year <= y1:
            bands += [f"{name}_evi2"] + [f"{name}_{SUB_SEASON_PREFIX}{s}" for s in seasons]
    return bands


def subset_batches(cfg: dict) -> dict[str, list[int]]:
    """Subset batches S1.. mirror the main batches B1.., limited to years a subset covers."""
    years = set()
    for sub in cfg["export"]["subsets"].values():
        years |= set(range(sub["years"][0], sub["years"][1] + 1))
    out = {}
    for name, yrs in main_batches(cfg).items():
        if name.startswith("B"):
            keep = [y for y in yrs if y in years]
            if keep:
                out["S" + name[1:]] = keep
    return out
