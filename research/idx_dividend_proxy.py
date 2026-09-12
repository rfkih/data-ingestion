#!/usr/bin/env python3
"""Dividend-yield proxy for the IDX screen report (task 1.2, interim).

Primary dividend data (IDX cash-dividend announcements) arrives with the announcement job in
phase 1b; until then, Yahoo's dividend events (v8 chart API, events=div) give a per-year cash
dividend per share for the names under review. Yield_y = sum(dividends in y) / mean close in y
(split-only close). Output: research-scratch/idx-screen/dividends_yahoo.json

    python research/idx_dividend_proxy.py BBCA,BBRI,...   (codes without .JK)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research-scratch", "idx-screen", "dividends_yahoo.json")


def fetch(code):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(code + ".JK")
           + "?interval=1d&range=10y&events=div")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)["chart"]["result"][0]
    ts = d["timestamp"]; closes = d["indicators"]["quote"][0]["close"]
    divs = (d.get("events") or {}).get("dividends") or {}
    by_year_close = defaultdict(list)
    for t, c in zip(ts, closes):
        if c:
            by_year_close[datetime.fromtimestamp(t, tz=timezone.utc).year].append(c)
    by_year_div = defaultdict(float)
    for v in divs.values():
        by_year_div[datetime.fromtimestamp(v["date"], tz=timezone.utc).year] += float(v["amount"])
    years = sorted(y for y in by_year_close if y in by_year_div)
    yields = {y: by_year_div[y] / (sum(by_year_close[y]) / len(by_year_close[y])) for y in years}
    full = [yields[y] for y in years if y < datetime.now(timezone.utc).year]
    return {"years": {str(y): round(yields[y] * 100, 2) for y in years},
            "avg_yield_pct": round(100 * sum(full) / len(full), 2) if full else 0.0,
            "n_div_events": len(divs)}


def main(codes):
    out = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for c in codes:
        c = c.strip().upper()
        if not c or c in out:
            continue
        try:
            out[c] = fetch(c)
            print("%-6s avg yield %.2f%% events=%d" % (c, out[c]["avg_yield_pct"], out[c]["n_div_events"]))
        except Exception as e:  # noqa: BLE001
            out[c] = {"error": str(e)[:100]}
            print("%-6s ERR %s" % (c, str(e)[:80]))
        time.sleep(1.5)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1].split(",") if len(sys.argv) > 1 else [])
