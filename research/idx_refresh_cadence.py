#!/usr/bin/env python3
"""IDX — refresh cadence of the strict composite (2026-09-13). The acceleration control (research/idx_accel.py) showed
that the deployed list refreshed QUARTERLY beat the annual May rebalance in two of three offsets over 2022-07 to 2026-09,
and that the earnings-acceleration filter itself added nothing. That control was not pre-registered. This is the
pre-registered confirmation over the full window, with all cadences on the same footing.

PRE-REGISTERED MENU (2 trials; cumulative 122 + 2 = 124). The strict composite (the deployed rule, `strategies.pick`),
equal weight, reset at every rebalance, real costs, dividends net of tax, 2021-05 to the end.
    annual      one rebalance a year; four calendars (May, Feb, Aug, Nov)              -> the deployed rule (reference)
    semiannual  two a year; two offsets (May/Nov, Feb/Aug)
    quarterly   four a year; three offsets (May/Aug/Nov/Feb, Jun/Sep/Dec/Mar, Jul/Oct/Jan/Apr)
Each cadence is summarised by the mean and the worst of its offsets.

READING RULE (declared before the run): a faster cadence replaces annual only if its mean CAGR across offsets exceeds the
annual mean by at least 2 points AND its worst-offset drawdown is no more than 5 points deeper than annual's worst. If
quarterly and semiannual both pass, the slower one is preferred (fewer trades). Otherwise annual stays.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_refresh_cadence.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import equity_screen as ES  # noqa: E402
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

N_TRIALS = 124
OUT = os.path.join(VQ.OUTDIR, "refresh_cadence_results.json")
START = pd.Timestamp("2021-05-01")
CADENCES = {
    "annual": [(5,), (2,), (8,), (11,)],
    "semiannual": [(5, 11), (2, 8)],
    "quarterly": [(5, 8, 11, 2), (6, 9, 12, 3), (7, 10, 1, 4)],
}


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    end = close.index[-1]
    months = TO.month_starts(close.index, START, end)
    cache: dict = {}

    def strict_list(D):
        if D not in cache:
            cache[D] = {r["code"] for r in ST.pick("strict", cand.build(conn, D.date())["all_rows"]) if r["selected"]}
        return cache[D]

    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "cadences": {}}
    print(f"strict composite, {START.date()} -> {end.date()}   (DSR at N_trials = {N_TRIALS})")
    print(f"{'cadence / offset':28s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | rebalances | trades/yr")
    for name, offsets in CADENCES.items():
        rows = []
        for months_of in offsets:
            dates = [d for d in months if d.month in months_of]
            # the first date of an offset is its first calendar month at/after START
            plan = {D: strict_list(D) for D in dates}
            nav = VQ.simulate(plan, close, vol, delisted, div, dates[0], end, True)
            st = VQ.stats(nav, dates)
            r = list(st.pop("_r"))
            st["dsr"] = round(ES.deflated_sharpe(r, N_TRIALS), 3)
            st["offset"] = "/".join(pd.Timestamp(2000, m, 1).strftime("%b") for m in months_of)
            # turnover: names changed per rebalance, summed per year
            changes = [len(plan[dates[i]] ^ plan[dates[i - 1]]) for i in range(1, len(dates))]
            yrs = (dates[-1] - dates[0]).days / 365.25
            st["trades_per_year"] = round(sum(changes) / yrs, 1) if yrs else None
            rows.append(st)
            print(f"{name + ' ' + st['offset']:28s} {st['total_pct']:7.1f} {st['cagr_pct']:6.1f} {st['sharpe']:6.2f} {st['mdd_pct']:5.0f} {st['dsr']:5.2f} | {len(dates):3d}        | {st['trades_per_year']}")
            sys.stdout.flush()
        summary = {"mean_cagr": float(np.mean([x["cagr_pct"] for x in rows])), "min_cagr": float(min(x["cagr_pct"] for x in rows)),
                   "worst_mdd": float(max(x["mdd_pct"] for x in rows)), "mean_sharpe": float(np.mean([x["sharpe"] for x in rows])),
                   "trades_per_year": float(np.mean([x["trades_per_year"] for x in rows]))}
        results["cadences"][name] = {"offsets": rows, "summary": summary}
        print(f"  -> {name}: mean CAGR {summary['mean_cagr']:.1f}%  (worst offset {summary['min_cagr']:.1f}%), mean Sharpe {summary['mean_sharpe']:.2f}, worst mDD {summary['worst_mdd']:.0f}%, "
              f"~{summary['trades_per_year']:.0f} name changes a year\n")
    a = results["cadences"]["annual"]["summary"]
    print("--- reading rule: mean CAGR >= annual + 2 pts AND worst mDD <= annual worst + 5 pts; slower wins a tie")
    choice = "annual"
    for name in ("semiannual", "quarterly"):
        s = results["cadences"][name]["summary"]
        ok = s["mean_cagr"] >= a["mean_cagr"] + 2 and s["worst_mdd"] <= a["worst_mdd"] + 5
        print(f"    {name:10s} mean CAGR {s['mean_cagr']:.1f}% vs annual {a['mean_cagr']:.1f}%; worst mDD {s['worst_mdd']:.0f}% vs {a['worst_mdd']:.0f}% -> {'passes' if ok else 'no'}")
        if ok and choice == "annual":
            choice = name
    print(f"    cadence for the catalog: {choice}")
    results["choice"] = choice
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
