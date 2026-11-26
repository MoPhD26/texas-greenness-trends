"""Chunk grids and a done-marker ledger so long local jobs can resume after a crash.

A job splits the raster into fixed windows. After a window's results are safely written,
the job records a marker file for it. On restart, windows with markers are skipped.
Markers are written atomically (temporary file, then rename), so a crash mid-write never
leaves a false "done".
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Window:
    """A rectangular block of the raster grid, in pixel offsets."""

    row_off: int
    col_off: int
    height: int
    width: int

    @property
    def key(self) -> str:
        return f"r{self.row_off:06d}_c{self.col_off:06d}"


def chunk_windows(height: int, width: int, size: int) -> list[Window]:
    """Tile a height x width grid into windows of at most size x size, row by row."""
    if height <= 0 or width <= 0 or size <= 0:
        raise ValueError("height, width, and size must be positive")
    return [
        Window(r, c, min(size, height - r), min(size, width - c))
        for r in range(0, height, size)
        for c in range(0, width, size)
    ]


class ChunkLedger:
    """Records which windows of a job are finished, one marker file per window."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _marker(self, key: str) -> Path:
        return self.directory / f"{key}.done"

    def is_done(self, key: str) -> bool:
        return self._marker(key).exists()

    def mark_done(self, key: str, info: dict | None = None) -> None:
        """Atomically write the marker for one window."""
        final = self._marker(key)
        tmp = final.with_suffix(".tmp")
        payload = {"key": key, "finished_unix": time.time(), **(info or {})}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, final)

    def done_keys(self) -> set[str]:
        return {p.stem for p in self.directory.glob("*.done")}


def run_resumable(
    windows: Iterable[Window],
    process: Callable[[Window], dict | None],
    ledger: ChunkLedger,
) -> dict[str, int]:
    """Run `process` on every window not yet marked done.

    `process` must write its own results before returning. Its return value, if any,
    is stored in the marker. An exception stops the run, and the failed window stays
    unmarked so it is retried next time.
    """
    ran = skipped = 0
    for w in windows:
        if ledger.is_done(w.key):
            skipped += 1
            continue
        start = time.perf_counter()
        info = process(w) or {}
        ledger.mark_done(w.key, {"seconds": round(time.perf_counter() - start, 3), **info})
        ran += 1
    return {"ran": ran, "skipped": skipped}
