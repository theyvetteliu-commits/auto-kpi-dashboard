"""Demo data source: makes realistic daily SaaS metrics for a fictional company.

In a real setup this file is replaced by a warehouse query (see query.sql).
Everything here is invented. The numbers are seeded, so every run of the
same date range gives the same rows.

Four markets at different stages, on purpose: a mature one, a growing one,
a scaling one and an early one. That's the hard case for a regional view,
because one total hides how differently each market is moving.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

MARKETS = {
    # name: (stage, signups/day at start, yearly growth, monthly churn, active users at start)
    "Japan": ("Mature", 120, 0.08, 0.018, 42000),
    "Korea": ("Growing", 85, 0.35, 0.024, 18000),
    "India": ("Scaling", 210, 0.70, 0.041, 26000),
    "Southeast Asia": ("Early", 60, 1.10, 0.052, 6500),
}

# plan: (share of new signups, price per active user per month in USD)
PLANS = {
    "Starter": (0.62, 9.0),
    "Pro": (0.29, 29.0),
    "Team": (0.09, 79.0),
}

START = date(2026, 1, 1)


def _events(market: str, d: date) -> float:
    """A few one-off moves so the weekly summary has something real to explain."""
    if market == "India" and date(2026, 9, 1) <= d <= date(2026, 9, 21):
        return 1.35  # paid campaign
    if market == "Southeast Asia" and date(2026, 7, 10) <= d <= date(2026, 7, 24):
        return 0.70  # payment provider outage
    if market == "Korea" and d >= date(2026, 10, 12):
        return 1.24  # new local pricing
    if market == "Southeast Asia" and d >= date(2026, 10, 13):
        return 0.82  # competitor promotion
    return 1.0


def rows(until: date) -> list[dict]:
    """Every row from START to `until`, one per date x market x plan."""
    out = []
    for market, (stage, base, growth, churn_m, active0) in MARKETS.items():
        rng = random.Random(f"atlas-{market}")
        active = {p: active0 * share for p, (share, _) in PLANS.items()}
        d = START
        while d <= until:
            t = (d - START).days / 365
            weekday = 0.72 if d.weekday() >= 5 else 1.0
            trend = base * math.exp(growth * t)
            daily_churn = churn_m / 30
            for plan, (share, price) in PLANS.items():
                noise = rng.uniform(0.85, 1.15)
                signups = round(trend * share * weekday * noise * _events(market, d))
                churned = round(active[plan] * daily_churn * rng.uniform(0.8, 1.2))
                active[plan] = max(0.0, active[plan] + signups * 0.55 - churned)
                out.append({
                    "date": d.isoformat(),
                    "market": market,
                    "stage": stage,
                    "plan": plan,
                    "signups": signups,
                    "active_users": round(active[plan]),
                    "churned_users": churned,
                    "mrr_usd": round(active[plan] * price),
                })
            d += timedelta(days=1)
    return out
