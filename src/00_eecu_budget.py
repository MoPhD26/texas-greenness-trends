"""Earth Engine EECU budget for the current month: spent, committed, remaining.

Batch task EECU comes from each logged task's operation metadata. Interactive use is not
reported per request, so it is entered by hand from the Cloud console (--interactive).
Committed work (approved, not yet finished) is entered as estimates with --commit.

Run:
  conda run -n rs-trends python src/00_eecu_budget.py
  conda run -n rs-trends python src/00_eecu_budget.py --interactive 2026-11 120.5
  conda run -n rs-trends python src/00_eecu_budget.py --commit "B1 main" 154 --group B1
  conda run -n rs-trends python src/00_eecu_budget.py --uncommit "harmonization rest"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

from rstrends import tasklog
from rstrends.config import data_dir, ee_project, load_config


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--month", help="YYYY-MM (default: current UTC month)")
    ap.add_argument("--interactive", nargs=2, metavar=("MONTH", "HOURS"))
    ap.add_argument("--commit", nargs=2, metavar=("LABEL", "HOURS"))
    ap.add_argument("--group", help="with --commit: task-log group whose EECU counts against it")
    ap.add_argument("--uncommit", metavar="LABEL")
    args = ap.parse_args()

    cfg = load_config()
    root = data_dir(cfg)
    state_path = root / "logs" / "eecu_budget.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    state.setdefault("interactive", {})
    state.setdefault("committed", {})
    if args.interactive:
        state["interactive"][args.interactive[0]] = float(args.interactive[1])
    if args.commit:
        state["committed"][args.commit[0]] = {"hours": float(args.commit[1]), "group": args.group}
    if args.uncommit:
        state["committed"].pop(args.uncommit, None)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    month = args.month or dt.datetime.now(dt.UTC).strftime("%Y-%m")
    from rstrends import gee

    project = ee_project()
    gee.initialize(project)
    batch = running = 0.0
    lines = []
    by_group: dict[str, float] = {}
    for row in tasklog.read(root / "logs" / "ee_tasks.csv"):
        if not row["submitted_utc"].startswith(month):
            continue
        s = gee.operation_summary(project, row["task_id"])
        hrs = tasklog.eecu_hours(s["eecu_seconds"]) or 0.0
        batch += hrs
        by_group[row["group"]] = by_group.get(row["group"], 0.0) + hrs
        if s["state"] in ("PENDING", "RUNNING"):
            running += hrs
        lines.append(f"  {row['description']:<26} {s['state']:<10} {hrs:7.3f}")
    inter = state["interactive"].get(month)
    left = tasklog.remaining_commitments(state["committed"], by_group)
    committed = sum(left.values())
    quota, stop = cfg["budget"]["monthly_quota_eecu_h"], cfg["budget"]["stop_at_eecu_h"]
    reserve = cfg["budget"].get("reserve_eecu_h", 0.0)
    print("\n".join(lines))
    print(f"batch tasks {month}: {batch:.1f} EECU-h ({running:.1f} in tasks still running)")
    print(
        "interactive (Cloud console): "
        + (f"{inter:.1f} EECU-h" if inter is not None else "not entered")
    )
    spent = batch + (inter or 0.0)
    for label, hrs in left.items():
        print(f"  committed (still to come): {label} {hrs:.1f}")
    print(
        f"BUDGET {month}: spent {spent:.1f}, committed {committed:.1f}, "
        f"remaining {quota - spent - committed:.1f} of {quota}, "
        f"usable under the {stop} line after the {reserve:.0f} reserve: "
        f"{stop - reserve - spent - committed:.1f}"
    )
    if spent + committed > stop:
        print("STOP: spent plus committed is past the stop-and-ask line")


if __name__ == "__main__":
    main()
