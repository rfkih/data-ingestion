#!/usr/bin/env python3
"""IDX — "no falling knives", the whole rule (2026-09-13). The operator's principle: do not buy what is still falling, do
not hold through a market fall. The entry gate (buy a listed name only above its 200-day average) and the index regime
filter (cash while the IHSG is under its 200-day average) were each tested alone in IDX_TREND_OVERLAY; this is the two
together, as the paper book runs them, plus a stricter entry (above the 200-day average AND up from the 252-day low by
at least 20 %, the doubler study's "already turned" signal).

PRE-REGISTERED MENU (2 trials; cumulative 124 + 2 = 126). Strict composite, 2021-2026, four calendars, monthly checks,
drift mode with a one-slot cap, cash 4 %/yr; reference arms recomputed (none, entry_only, index).
    regime_entry   cash while the IHSG is under its MA200; when it is above, buy listed names only when they are above
                   their own MA200 (at the rebalance, or at the monthly check they cross); never sell a held name on trend
    regime_turned  as regime_entry, but a name must also be at least 20 % above its 252-day low to be bought
READING RULE (declared before the run): read against `index` (the regime filter alone): a combined rule is preferred only
if its worst-calendar drawdown is shallower than index's AND its total return is within 10 % (relative) of index's in at
least three calendars. Otherwise the filter alone remains the recommended crash rule and the entry gate stays optional.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_no_knife.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

N_TRIALS = 126
TO.N_TRIALS = N_TRIALS
OUT = os.path.join(VQ.OUTDIR, "no_knife_results.json")
UP_FROM_LOW = 0.20


def build_combined(kind: str, lists: dict, sig: TO.Signals, close) -> dict:
    annual = sorted(lists)
    dates = sorted(set(sig.checks) | set(annual))
    lo252 = close.rolling(252, min_periods=120).min().reindex(dates, method="ffill")
    px = close.reindex(dates, method="ffill")

    def current(m):
        return lists[max(a for a in annual if a <= m)]

    plan = {}
    for m in dates:
        L = current(m)
        if not sig.regime(m):
            plan[m] = set()
            continue

        def rule(held, m=m, L=L):
            entrants = sig.above_sma(m, L - held)
            if kind == "regime_turned":
                entrants = {c for c in entrants if not np.isnan(lo252.loc[m].get(c, np.nan)) and px.loc[m][c] >= (1 + UP_FROM_LOW) * lo252.loc[m][c]}
            return (held & L) | entrants
        plan[m] = rule
    return plan


def main():
    conn = VQ.connect()
    close, vol, delisted, div, ix = VQ.load(conn)
    end = close.index[-1]
    jk = ix["COMPOSITE"].dropna()
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "months": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        lists = {D: {r["code"] for r in ST.pick("strict", cand.build(conn, D.date())["all_rows"]) if r["selected"]} for D in rebals}
        checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))
        sig = TO.Signals(close, jk, checks)

        def slot(d, lists=lists):
            return 1 / max(1, len(lists[max(a for a in lists if a <= d)]))

        table = {}
        print(f"\n=== month {month}: strict composite {[str(r.date()) for r in rebals]}   (DSR at N_trials = {N_TRIALS})")
        print(f"{'arm':14s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | 2022 / 2025 episode dd")
        for kind in ("none", "entry_only", "index", "regime_entry", "regime_turned"):
            plan = TO.build_plan(kind, lists, sig) if kind in ("none", "entry_only", "index") else build_combined(kind, lists, sig, close)
            nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="drift", cap=slot, cash_rate=TO.CASH_RATE)
            v = TO.read(nav, rebals)
            table[kind] = v
            e = v["episodes"]
            print(f"{kind:14s} {v['total_pct']:7.1f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v['dsr']:5.2f} | {e['2022']} / {e['2025']}")
            sys.stdout.flush()
        results["months"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}
    print("\n--- reading rule vs the regime filter alone: shallower worst drawdown AND within 10 % of its return in >= 3 calendars")
    verdict = {}
    idx_dd = max(results["months"][m]["table"]["index"]["mdd_pct"] for m in results["months"])
    for kind in ("regime_entry", "regime_turned"):
        dd = max(results["months"][m]["table"][kind]["mdd_pct"] for m in results["months"])
        near = sum(results["months"][m]["table"][kind]["total_pct"] >= 0.9 * results["months"][m]["table"]["index"]["total_pct"] for m in results["months"])
        ok = dd < idx_dd and near >= 3
        verdict[kind] = {"worst_mdd": dd, "index_worst_mdd": idx_dd, "within_10pct": int(near), "prefer": bool(ok)}
        print(f"    {kind:14s} worst mDD {dd:.0f}% vs index {idx_dd:.0f}%; within 10 % of index in {near}/4 -> {'PREFERRED over the filter alone' if ok else 'filter alone stays'}")
    results["verdict"] = verdict
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
