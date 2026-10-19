#!/usr/bin/env python3
"""Daily refresh: get the latest rows, merge them into data.csv safely.

Runs every morning from GitHub Actions. Design choices that came from
running the real version in production:

1. Incremental, not full. Only the last WINDOW_DAYS days are recomputed and
   merged into the history already in data.csv. A full rebuild took over 30
   minutes; the incremental run takes a few.
2. Completeness guard. If the newest day looks far smaller than the week
   before it, the upstream data is probably still loading. That day is
   dropped and picked up tomorrow, instead of showing a fake collapse.
3. Never erase history with worse data. If a day inside the window comes
   back with far fewer rows than history already has for it, the history
   rows are kept.

Usage:
  python scripts/refresh.py               # refresh up to yesterday
  python scripts/refresh.py --full        # rebuild everything
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_source  # noqa: E402  (swap for a warehouse query in a real setup)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data.csv"
FIELDS = ["date", "market", "stage", "plan", "signups", "active_users", "churned_users", "mrr_usd"]

WINDOW_DAYS = 14
COMPLETENESS_THRESHOLD = 0.5   # newest day must reach 50% of the trailing 7-day average
ROW_RETENTION_THRESHOLD = 0.5  # a refreshed day must keep 50% of its historical rows


def fetch(since: date, until: date) -> list[dict]:
    """Get rows for since..until. In production this runs query.sql on the warehouse."""
    return [r for r in demo_source.rows(until) if r["date"] >= since.isoformat()]


def load_history() -> list[dict]:
    if not DATA.exists():
        return []
    with DATA.open() as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            print("data.csv has an unexpected header, doing a full rebuild.")
            return []
        return list(reader)


def by_day(rows: list[dict]) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for r in rows:
        out[r["date"]].append(r)
    return out


def drop_incomplete_last_day(fresh: dict[str, list[dict]]) -> None:
    days = sorted(fresh)
    if len(days) < 8:
        return
    total = lambda d: sum(int(r["signups"]) for r in fresh[d])  # noqa: E731
    last = days[-1]
    avg = sum(total(d) for d in days[-8:-1]) / 7
    if avg and total(last) < COMPLETENESS_THRESHOLD * avg:
        print(f"{last} looks incomplete ({total(last)} vs avg {avg:.0f}), skipping it today.")
        del fresh[last]


def merge(history: list[dict], fresh: dict[str, list[dict]]) -> list[dict]:
    old = by_day(history)
    for day, new_rows in fresh.items():
        if day in old and len(new_rows) < ROW_RETENTION_THRESHOLD * len(old[day]):
            print(f"{day}: only {len(new_rows)} rows vs {len(old[day])} in history, keeping history.")
            continue
        old[day] = new_rows
    return [r for day in sorted(old) for r in old[day]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--until", help="last day to include, YYYY-MM-DD (default: yesterday)")
    args = ap.parse_args()

    until = date.fromisoformat(args.until) if args.until else date.today() - timedelta(days=1)
    history = [] if args.full else load_history()
    since = demo_source.START if not history else until - timedelta(days=WINDOW_DAYS - 1)

    fresh = by_day(fetch(since, until))
    drop_incomplete_last_day(fresh)
    merged = merge(history, fresh)

    with DATA.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(merged)
    print(f"data.csv: {len(merged)} rows, {merged[0]['date']} to {merged[-1]['date']}.")


if __name__ == "__main__":
    main()
