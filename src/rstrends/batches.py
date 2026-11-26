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
