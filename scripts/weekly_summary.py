#!/usr/bin/env python3
"""Write the "What changed this week" summary that sits at the top of the dashboard.

Step 1 (always): work out the facts in code. Week-over-week change in
signups, MRR and churn for every market, and which moves are big enough
to matter. The numbers never come from the AI.

Step 2 (if ANTHROPIC_API_KEY is set): ask Claude to turn those facts into
a short plain-English read for a regional leader. It only gets the facts
table, so it can't invent numbers. Without a key, a rules-based summary is
written instead, so the dashboard never shows an empty box.

Output: summary.json at the repo root.
"""
from __future__ import annotations

import csv
import json
import os
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data.csv"
OUT = ROOT / "summary.json"
MODEL = os.environ.get("SUMMARY_MODEL", "claude-sonnet-5-5")
NOTABLE = 0.08  # a move of 8%+ week over week is worth calling out


def load():
    with DATA.open() as f:
        return list(csv.DictReader(f))


def week_stats(rows, end: date):
    """Totals per market for the 7 days ending `end`."""
    start = end - timedelta(days=6)
    s = defaultdict(lambda: {"signups": 0, "churned": 0, "mrr": 0, "active": 0})
    for r in rows:
        d = date.fromisoformat(r["date"])
        if start <= d <= end:
            m = s[r["market"]]
            m["signups"] += int(r["signups"])
            m["churned"] += int(r["churned_users"])
            if d == end:  # MRR and active users are point-in-time, take the last day
                m["mrr"] += int(r["mrr_usd"])
                m["active"] += int(r["active_users"])
    return s


def pct(a, b):
    return (a - b) / b if b else 0.0


def facts(rows):
    end = max(date.fromisoformat(r["date"]) for r in rows)
    this, last = week_stats(rows, end), week_stats(rows, end - timedelta(days=7))
    stage = {r["market"]: r["stage"] for r in rows}
    out = []
    for m in sorted(this):
        t, l = this[m], last[m]
        churn_t = t["churned"] / t["active"] if t["active"] else 0
        churn_l = l["churned"] / l["active"] if l["active"] else 0
        out.append({
            "market": m,
            "stage": stage[m],
            "signups": t["signups"],
            "signups_wow": round(pct(t["signups"], l["signups"]), 3),
            "mrr": t["mrr"],
            "mrr_wow": round(pct(t["mrr"], l["mrr"]), 3),
            "weekly_churn_rate": round(churn_t, 4),
            "churn_change_pts": round((churn_t - churn_l) * 100, 2),
        })
    return end, out


def rules_summary(f):
    total_mrr = sum(x["mrr"] for x in f)
    biggest = max(f, key=lambda x: abs(x["signups_wow"]))
    bullets = []
    for x in sorted(f, key=lambda x: -abs(x["signups_wow"])):
        if abs(x["signups_wow"]) >= NOTABLE or abs(x["mrr_wow"]) >= NOTABLE / 2:
            way = "up" if x["signups_wow"] > 0 else "down"
            bullets.append(
                f"{x['market']}: signups {way} {abs(x['signups_wow']):.0%} week over week, "
                f"MRR {x['mrr_wow']:+.1%}."
            )
    if not bullets:
        bullets.append("No market moved more than 8% this week. A steady week.")
    if abs(biggest["signups_wow"]) < NOTABLE:
        headline = f"A steady week. MRR is ${total_mrr:,.0f} and no market moved more than 8%."
    else:
        headline = (f"MRR is ${total_mrr:,.0f}. The biggest mover is {biggest['market']} "
                    f"({biggest['signups_wow']:+.0%} signups).")
    return {
        "headline": headline,
        "bullets": bullets[:4],
        "watch": "Check whether the biggest move is a one-off (campaign, outage, pricing) before planning around it.",
    }


def ai_summary(f, end):
    prompt = (
        "You write the weekly business read for a regional leader of a software company. "
        "Use ONLY the numbers in this JSON. Do not invent causes; if a cause isn't in the data, "
        "say what to check. Plain English, short sentences.\n\n"
        f"Week ending {end}:\n{json.dumps(f, indent=1)}\n\n"
        'Reply with JSON only: {"headline": one sentence, "bullets": up to 4 short strings, '
        '"watch": one sentence on what to look into next}'
    )
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": MODEL, "max_tokens": 600,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = json.load(resp)["content"][0]["text"]
    text = text[text.find("{"): text.rfind("}") + 1]
    return json.loads(text)


def main():
    end, f = facts(load())
    source = "rules"
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            s, source = ai_summary(f, end), "ai"
        except Exception as e:  # never break the refresh because the summary failed
            print(f"AI summary failed ({e}), using the rules-based one.")
            s = rules_summary(f)
    else:
        s = rules_summary(f)
    s.update({
        "week_ending": end.isoformat(),
        "source": source,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "facts": f,
    })
    OUT.write_text(json.dumps(s, indent=2))
    print(f"summary.json written ({source}).")


if __name__ == "__main__":
    main()
