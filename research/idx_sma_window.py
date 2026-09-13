#!/usr/bin/env python3
"""IDX — the moving-average window (2026-09-13). The operator asks whether 100 days beats 200. A sweep of the window for
the two overlays the book now offers, everything else as in research/idx_trend_overlay.py.

PRE-REGISTERED. Windows 50, 100, 150, 200, 250 trading days. Arms per window: the index regime filter on the 2008-2026
basket, on the IHSG itself, and on the 2021-2026 strict book (four calendars), and the entry gate on the strict book.
Counted as 4 arms x 4 new windows = 16 trials; cumulative 84 + 16 = 100.

READING RULE (declared before the run): 200 stays unless another window beats it in BOTH parts on BOTH counts, that is
a shallower worst drawdown AND a higher total return over 2008-2026 on the basket, and a higher total in at least three
of four calendars on the strict book with no deeper worst drawdown. Smoothness across neighbouring windows is the point:
one good window between two poor ones is noise, not a finding.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_sma_window.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

WINDOWS = (50, 100, 150, 200, 250)
N_TRIALS = 100
OUT = os.path.join(VQ.OUTDIR, "sma_window_results.json")
TO.N_TRIALS = N_TRIALS


def main():
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "windows": list(WINDOWS), "part_a": {}, "part_b": {}}
    eps = ("2008", "2013", "2015", "2018", "2020", "2022", "2025")

    # ---- Part A: the 2008-2026 basket and the IHSG
    close, vol, jk = TO.load_yahoo()
    end = close.index[-1]
    annual = []
    for y in range(2008, end.year + 1):
        pos = close.index.searchsorted(pd.Timestamp(f"{y}-05-02"))
        if pos < len(close.index):
            annual.append(close.index[pos])
    lists = TO.baskets(close, vol, annual)
    checks = sorted(set(TO.month_starts(close.index, annual[0], end)) | set(annual))
    jk_close = pd.DataFrame({"JKSE": jk}).reindex(close.index).ffill()
    jk_vol = pd.DataFrame({"JKSE": 1.0}, index=close.index)
    print(f"=== PART A 2008-2026: index regime filter by window (basket of {TO.BASKET_N}; IHSG)   cash {100 * TO.CASH_RATE:.0f} %/yr")
    print(f"{'arm':16s} {'total%':>8} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} | episode drawdowns %")
    base = VQ.simulate(TO.build_plan("none", lists, TO.Signals(close, jk, checks)), close, vol, {}, TO.EMPTY_DIV, annual[0], end, True,
                       mode="drift", cap=1 / TO.BASKET_N, cash_rate=TO.CASH_RATE)
    v = TO.read(base, annual)
    results["part_a"]["basket/none"] = v
    print(TO.line("basket/none", v, eps))
    for w in WINDOWS:
        TO.SMA = w
        sig = TO.Signals(close, jk, checks)
        nav = VQ.simulate(TO.build_plan("index", lists, sig), close, vol, {}, TO.EMPTY_DIV, annual[0], end, True, mode="drift",
                          cap=1 / TO.BASKET_N, cash_rate=TO.CASH_RATE)
        v = TO.read(nav, annual)
        results["part_a"][f"basket/index{w}"] = v
        print(TO.line(f"basket/index{w}", v, eps))
        nav = VQ.simulate(TO.build_plan("index", {annual[0]: {"JKSE"}}, TO.Signals(jk_close, jk, checks)), jk_close, jk_vol, {}, TO.EMPTY_DIV,
                          annual[0], end, False, mode="drift", cash_rate=TO.CASH_RATE)
        v = TO.read(nav, annual)
        results["part_a"][f"JKSE/index{w}"] = v
        print(TO.line(f"JKSE/index{w}", v, eps))
        sys.stdout.flush()

    # ---- Part B: the strict book, four calendars, rows built once per date
    conn = VQ.connect()
    close, vol, delisted, div, ix = VQ.load(conn)
    end = close.index[-1]
    jkb = ix["COMPOSITE"].dropna()
    eps_b = ("2022", "2025")
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        rows_at = {D: cand.build(conn, D.date())["all_rows"] for D in rebals}
        lists = {D: {r["code"] for r in ST.pick("strict", rows_at[D]) if r["selected"]} for D in rebals}
        checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))

        def slot(d, lists=lists):
            return 1 / max(1, len(lists[max(a for a in lists if a <= d)]))

        table = {}
        print(f"\n=== PART B month {month}: strict book, by window")
        print(f"{'arm':16s} {'total%':>8} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} | episode drawdowns %")
        TO.SMA = 200
        nav = VQ.simulate(TO.build_plan("none", lists, TO.Signals(close, jkb, checks)), close, vol, delisted, div, rebals[0], end, True,
                          mode="drift", cap=slot, cash_rate=TO.CASH_RATE)
        table["none"] = TO.read(nav, rebals)
        print(TO.line("none", table["none"], eps_b))
        for w in WINDOWS:
            TO.SMA = w
            sig = TO.Signals(close, jkb, checks)
            for kind in ("index", "entry_only"):
                nav = VQ.simulate(TO.build_plan(kind, lists, sig), close, vol, delisted, div, rebals[0], end, True, mode="drift", cap=slot,
                                  cash_rate=TO.CASH_RATE)
                table[f"{kind}{w}"] = TO.read(nav, rebals)
                print(TO.line(f"{kind}{w}", table[f"{kind}{w}"], eps_b))
            sys.stdout.flush()
        results["part_b"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}

    # ---- the reading rule, mechanically
    print("\n--- reading rule: 200 stays unless a window beats it on every count")
    a = results["part_a"]
    for w in WINDOWS:
        if w == 200:
            continue
        a_ok = a[f"basket/index{w}"]["mdd_pct"] < a["basket/index200"]["mdd_pct"] and a[f"basket/index{w}"]["total_pct"] > a["basket/index200"]["total_pct"]
        wins = sum(results["part_b"][m]["table"][f"index{w}"]["total_pct"] > results["part_b"][m]["table"]["index200"]["total_pct"] for m in results["part_b"])
        dd_ok = max(results["part_b"][m]["table"][f"index{w}"]["mdd_pct"] for m in results["part_b"]) <= \
            max(results["part_b"][m]["table"]["index200"]["mdd_pct"] for m in results["part_b"])
        g_wins = sum(results["part_b"][m]["table"][f"entry_only{w}"]["total_pct"] > results["part_b"][m]["table"]["entry_only200"]["total_pct"]
                     for m in results["part_b"])
        print(f"    window {w:3d}: index filter part A {'better' if a_ok else 'not better'} than 200; strict book ahead in {wins}/4, drawdown ok {dd_ok}; "
              f"entry gate ahead in {g_wins}/4 -> {'BEATS 200' if a_ok and wins >= 3 and dd_ok else 'keep 200'}")
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
