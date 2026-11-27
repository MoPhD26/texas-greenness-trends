"""A small CSV log of submitted Earth Engine tasks, for later status and EECU lookups."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

FIELDS = ["submitted_utc", "group", "description", "task_id"]


def append(path: str | Path, group: str, description: str, task_id: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(
            {
                "submitted_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "group": group,
                "description": description,
                "task_id": task_id,
            }
        )


def read(path: str | Path, group: str | None = None) -> list[dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if group is None or r["group"] == group]


def eecu_hours(seconds: float | None) -> float | None:
    return None if seconds is None else seconds / 3600.0


def remaining_commitments(committed: dict, actual_by_group: dict[str, float]) -> dict[str, float]:
    """Committed EECU-hours still to come, per label.

    committed: label -> hours (an estimate not tied to tasks) or {"hours": h, "group": g}.
    When an entry names a task-log group, the EECU those tasks already used is counted as
    spent, so only the rest of the estimate stays committed (never below zero). This keeps
    a running batch from being counted twice, once as spent and once as committed.
    """
    out = {}
    for label, item in committed.items():
        if isinstance(item, dict):
            used = actual_by_group.get(item.get("group"), 0.0) if item.get("group") else 0.0
            out[label] = max(0.0, float(item["hours"]) - used)
        else:
            out[label] = float(item)
    return out
