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


def chunk_subset_years(cfg: dict, done: tuple[int, ...] = ()) -> list[int]:
    """Years the per-chunk subset export covers: every subset year not already exported."""
    years = set()
    for sub in cfg["export"]["subsets"].values():
        years |= set(range(sub["years"][0], sub["years"][1] + 1))
    return sorted(years - set(done))


def multi_year_bands(cfg: dict, years, product: str) -> list[str]:
    """Band names of a per-chunk export with years as bands, in order.

    product "subsets": the year's subset bands (rstrends.batches.subset_bands).
    product "roy": EVI2 only (clear counts equal the main export's, same observations).
    Each name is prefixed with y<year>_, for example y2013_oli_evi2.
    """
    out = []
    for y in years:
        names = subset_bands(cfg, y) if product == "subsets" else ["evi2"]
        out += [f"y{y}_{b}" for b in names]
    return out


DONE_SUBSET_YEARS = (2015, 2016, 2017)  # S4, exported on the province-wide region (November)


def chunk_product_years(cfg: dict, product: str) -> list[int]:
    """Years in a per-chunk export file (src/03_chunk_export.py).

    subsets: every subset year not already exported. roy: every year a transform applies
    (2000-2019). Later years are OLI only and are not transformed.
    """
    if product == "subsets":
        return chunk_subset_years(cfg, done=DONE_SUBSET_YEARS)
    y0 = min(s["years"][0] for s in cfg["export"]["subsets"].values())
    y1 = max(s["years"][1] for s in cfg["export"]["subsets"].values())
    return list(range(y0, y1 + 1))
