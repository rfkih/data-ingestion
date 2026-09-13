#!/usr/bin/env python3
"""IDX — earnings acceleration (2026-09-13). The doubler sleeve found one thing that is not a lottery ticket: names whose
TTM earnings run-rate is well above the last audited year (the quarterly statements say profit is rising before the
audit does) doubled 33-47 % of the time with a POSITIVE median 12-month return, and a twenty-name basket of them beat
the strict composite on return in every calendar offset, at the price of 52-61 % drawdowns and a thin, wild pool.
This test asks whether the signal survives without the doubler profile: acceleration alone, acceleration inside the
quality gates, and acceleration as a filter on the deployed list.

PRE-REGISTERED MENU (4 trials; cumulative 117 + 4 = 121; plus the control below, 122).
CONTROL added after the first run showed value_accel ahead: before 2024 no quarterly reports exist, so accel is 0 for
everyone and value_accel is simply the strict list refreshed quarterly. `strict_q` (the strict list refreshed quarterly,
no filter) separates the refresh from the filter; the filter is credited only if value_accel beats strict_q in at least
two of three offsets over 2024-05 onward, the window in which it removes anything. Quarterly rebalance, three offsets, equal weight, real costs,
2022-07 to the end, the monthly panel of research/idx_multibagger.py (point-in-time; accel = ep_ttm / ep - 1).
    accel_all     every liquid name with accel >= 0.3 and a positive audited profit, equal weight, no cap
    accel_loose   the same within the light quality gate (profit > 0, ROE >= 5 %)
    accel_strict  the same within the strict gate (ROE >= 10 %, two profitable years, CFO > 0, D/E <= 1.5)
    value_accel   the deployed strict composite list, refreshed quarterly, minus names whose accel < 0 (the cheap list
                  with the decelerating names removed); names never fewer than 8
    references: strict (annual May), ew (the pool), each measured from the same start as the arms.

READING RULE (declared before the run): an arm becomes a catalog candidate only if its CAGR beats the strict composite in
at least two of three offsets AND its worst-offset max drawdown is at most 30 %. Otherwise recorded as tested.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_accel.py
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
import idx_multibagger as MB  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

N_TRIALS = 121
OUT = os.path.join(VQ.OUTDIR, "accel_results.json")
START = pd.Timestamp("2022-07-01")
ACCEL = 0.3
ARMS = ("accel_all", "accel_loose", "accel_strict", "value_accel", "strict_q")
FILTER_FROM = pd.Timestamp("2024-05-01")


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    end = close.index[-1]
    panel = pd.read_parquet(MB.PANEL)
    months = sorted(panel["date"].unique())
    rows_cache: dict = {}

    def strict_list(D):
        if D not in rows_cache:
            rows_cache[D] = {r["code"] for r in ST.pick("strict", cand.build(conn, D.date())["all_rows"]) if r["selected"]}
        return rows_cache[D]

    may = [d for d in VQ.rebalance_dates(close.index, 5) if d >= pd.Timestamp("2022-05-01")]
    strict_annual = {D: strict_list(D) for D in may}
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "offsets": {}}
    for off in (0, 1, 2):
        dates = [d for d in months if d >= START and (d.month - 1) % 3 == (6 + off) % 3]
        print(f"\n=== offset {off}: {len(dates)} quarterly rebalances {dates[0].date()} … {dates[-1].date()}   (DSR at N_trials = {N_TRIALS})")
        print(f"{'arm':13s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | names | picked names' 12m: mean / median / P(<-50%)")
        table = {}
        picks: dict[str, list] = {a: [] for a in ARMS}
        plans: dict[str, dict] = {a: {} for a in ARMS}
        for D in dates:
            g = panel[panel["date"] == D]
            acc = g[(g["accel"] >= ACCEL) & (g["ep"] > 0)]
            plans["accel_all"][D] = set(acc["code"])
            plans["accel_loose"][D] = set(acc[acc["gate_loose"]]["code"])
            plans["accel_strict"][D] = set(acc[acc["gate_strict"]]["code"])
            sl = strict_list(D)
            keep = {c for c in sl if not (g[g["code"] == c]["accel"] < 0).any()}
            plans["value_accel"][D] = keep if len(keep) >= 8 else sl
            plans["strict_q"][D] = set(sl)
            for a in ARMS:
                sub = g[g["code"].isin(plans[a][D])]
                picks[a].extend(float(v) for v in sub["fwd12"].dropna())
        for a in ARMS:
            plan = plans[a]
            start = next((D for D in dates if plan[D]), None)
            if start is None:
                continue
            nav = VQ.simulate(plan, close, vol, delisted, div, start, end, True)
            st = VQ.stats(nav, [d for d in dates if d >= start])
            r = list(st.pop("_r"))
            st["dsr"] = round(ES.deflated_sharpe(r, N_TRIALS), 3)
            st["from"] = str(start.date())
            st["n"] = round(float(np.mean([len(plan[D]) for D in dates if D >= start])), 1)
            f12 = pd.Series(picks[a])
            st["picked_mean12"], st["picked_median12"], st["picked_p50loss"] = float(f12.mean()), float(f12.median()), float((f12 < -0.5).mean())
            table[a] = st
            print(f"{a:13s} {st['total_pct']:7.1f} {st['cagr_pct']:6.1f} {st['sharpe']:6.2f} {st['mdd_pct']:5.0f} {st['dsr']:5.2f} | {st['n']:5.1f} | "
                  f"{100 * st['picked_mean12']:+.0f}% / {100 * st['picked_median12']:+.0f}% / {100 * st['picked_p50loss']:.0f}%   from {st['from']}")
            sys.stdout.flush()
        # references from the same start as the arms (the earliest start among them)
        start0 = min(pd.Timestamp(table[a]["from"]) for a in table)
        for label, plan in (("strict", strict_annual), ("ew", {D: set(panel[panel["date"] == D]["code"]) for D in dates})):
            nav = VQ.simulate(plan, close, vol, delisted, div, start0, end, True)
            st = VQ.stats(nav, [d for d in dates if d >= start0])
            st.pop("_r")
            st["from"] = str(start0.date())
            table[label] = st
            print(f"{label + ' (ref)':13s} {st['total_pct']:7.1f} {st['cagr_pct']:6.1f} {st['sharpe']:6.2f} {st['mdd_pct']:5.0f}        from {st['from']}")
        # the filter's own window: both quarterly arms from the first rebalance at/after 2024-05
        sub_dates = [d for d in dates if d >= FILTER_FROM]
        sub = {}
        for a in ("value_accel", "strict_q"):
            nav = VQ.simulate({d: plans[a][d] for d in sub_dates}, close, vol, delisted, div, sub_dates[0], end, True)
            st = VQ.stats(nav, sub_dates)
            st.pop("_r")
            sub[a] = st
            removed = [len(plans["strict_q"][d]) - len(plans["value_accel"][d]) for d in sub_dates]
        print(f"{'2024-05+ only':13s} value_accel {sub['value_accel']['total_pct']:+.1f}% (mDD {sub['value_accel']['mdd_pct']:.0f}%)  vs  "
              f"strict_q {sub['strict_q']['total_pct']:+.1f}% (mDD {sub['strict_q']['mdd_pct']:.0f}%);  names removed by the filter per quarter: {removed}")
        table["sub_2024"] = sub
        results["offsets"][str(off)] = {"rebalances": [str(d.date()) for d in dates], "table": table}
    print("\n--- reading rule: CAGR > strict in >= 2/3 offsets AND worst mDD <= 30 %")
    verdict = {}
    filt = sum(results["offsets"][o]["table"]["sub_2024"]["value_accel"]["total_pct"] > results["offsets"][o]["table"]["sub_2024"]["strict_q"]["total_pct"]
               for o in results["offsets"])
    print(f"    filter credited (value_accel > strict_q over 2024-05+): {filt}/3")
    results["filter_credited"] = int(filt)
    for a in ARMS:
        offs = [o for o in results["offsets"] if a in results["offsets"][o]["table"]]
        w = sum(results["offsets"][o]["table"][a]["cagr_pct"] > results["offsets"][o]["table"]["strict"]["cagr_pct"] for o in offs)
        dd = max(results["offsets"][o]["table"][a]["mdd_pct"] for o in offs) if offs else float("nan")
        ok = len(offs) == 3 and w >= 2 and dd <= 30
        verdict[a] = {"beats_strict": int(w), "worst_mdd": dd, "adopt": bool(ok)}
        print(f"    {a:13s} beats strict {w}/3, worst mDD {dd:.0f}% -> {'CATALOG CANDIDATE' if ok else 'tested'}")
    results["verdict"] = verdict
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
