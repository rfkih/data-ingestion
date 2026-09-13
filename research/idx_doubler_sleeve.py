#!/usr/bin/env python3
"""IDX — a doubler sleeve? (2026-09-13). The doubler study found the profile of names that reach 2x within a year (small,
volatile, heavily traded, already rising, revenue growing, energy / materials / tech) and that the profile is a lottery
ticket: a good mean, a poor median. The operator asks for research that finds such names. The fair test is therefore a
PORTFOLIO test: a basket of twenty such names, refreshed every quarter, real costs, several calendar offsets.

PRE-REGISTERED MENU (6 trials; cumulative 111 + 6 = 117). Universe: the desk's liquid pool at each rebalance (the monthly
panel of research/idx_multibagger.py). Rebalance on the first trading day of every third month from 2022-07 to the end,
three offsets (Jul/Oct/Jan/Apr, Aug/Nov/Feb/May, Sep/Dec/Mar/Jun) as the robustness check. Twenty names, equal weight,
reset each rebalance, 25 bps + half-tick per side, dividends net of tax, cash 0.
    ew           every name in the pool, equal weight (the like-for-like baseline)
    rules20      score = mean percentile of: small cap, high 60-day volatility, high turnover, high 12-1 momentum, high
                 rise from the 252-day low, high audited revenue growth; top twenty
    rules20_earn rules20 within names whose audited profit AND revenue grew (the earnings-led class)
    rules20_cheap rules20 within the light-gate pool with earnings yield at or above the pool median (cheap and moving)
    rules20_accel rules20 within names whose TTM earnings run-rate is at least 30 % above the audited year (the statements
                 say profit is rising before the audit does)
    rules20_flow rules20 within names with positive 20-day foreign net flow and at least one ownership filing in 30 days
                 (someone is accumulating)
    model20      LightGBM (the doubler study's fixed parameters, v2 features) retrained at every rebalance on rows whose
                 12-month label closed before that date; top twenty by score
    strict       the deployed strict composite, annual May rebalance, same simulator (reference, not a trial)

READ: total, CAGR, Sharpe, max drawdown per offset; the pooled distribution of the picked names' 12-month returns (mean,
median, share below -50 %) for the lottery shape; average names per rebalance and turnover.
READING RULE (declared before the run): an arm earns a paper sleeve only if its CAGR beats `ew` in all three offsets,
beats `strict` in at least two, and its worst-offset max drawdown is at most 35 %. Otherwise it is recorded as tested.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_doubler_sleeve.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import lightgbm as lgb
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

N_TRIALS = 117
OUT = os.path.join(VQ.OUTDIR, "doubler_sleeve_results.json")
N = 20
START = pd.Timestamp("2022-07-01")
ARMS = ("ew", "rules20", "rules20_earn", "rules20_cheap", "rules20_accel", "rules20_flow", "model20")
SIGNALS = (("log_mcap", -1), ("vol60", 1), ("turnover", 1), ("mom", 1), ("up_low252", 1), ("rev_yoy", 1))


def profile_score(g: pd.DataFrame) -> pd.Series:
    parts = []
    for col, sign in SIGNALS:
        r = g[col].rank(pct=True)
        parts.append((r if sign > 0 else 1 - r).fillna(0.5))
    return sum(parts) / len(parts)


def pick(arm: str, g: pd.DataFrame, panel: pd.DataFrame, D: pd.Timestamp) -> list[str]:
    if arm == "ew":
        return list(g["code"])
    if arm == "model20":
        cutoff = D - pd.Timedelta(days=372)
        train = panel[(panel["date"] <= cutoff) & panel["touch12"].notna()]
        if train["touch12"].sum() < 60:
            return []
        Xtr = pd.concat([train[MB.FEATURES].astype(float), train[["sector_cat"]]], axis=1)
        Xte = pd.concat([g[MB.FEATURES].astype(float), g[["sector_cat"]]], axis=1)
        m = lgb.train(MB.PARAMS, lgb.Dataset(Xtr, label=train["touch12"].values.astype(int), categorical_feature=["sector_cat"], free_raw_data=False),
                      num_boost_round=MB.ROUNDS)
        s = pd.Series(m.predict(Xte), index=g.index)
        return list(g.loc[s.sort_values(ascending=False).index[:N], "code"])
    h = g
    if arm == "rules20_earn":
        h = g[(g["np_yoy"] > 0) & (g["rev_yoy"] > 0)]
    elif arm == "rules20_cheap":
        pool = g[g["gate_loose"] & (g["ep"] > 0)]
        h = pool[pool["ep"] >= pool["ep"].median()]
    elif arm == "rules20_accel":
        h = g[g["accel"] >= 0.3]
    elif arm == "rules20_flow":
        h = g[(g["f20"] > 0) & (g["ev_own30"] > 0)]
    if h.empty:
        return []
    sc = profile_score(h)
    return list(h.loc[sc.sort_values(ascending=False).index[:N], "code"])


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    end = close.index[-1]
    if os.path.exists(MB.PANEL):
        panel = pd.read_parquet(MB.PANEL)
    else:
        panel = pd.DataFrame()
    if panel.empty or panel["date"].max() < end - pd.Timedelta(days=40):
        print("building the monthly panel to the end (features for every month, labels where the window closed)…", flush=True)
        panel = MB.build_panel(conn, close, vol)
        panel.to_parquet(MB.PANEL)
    panel["sector_cat"] = panel["sector"].astype("category")
    months = sorted(panel["date"].unique())
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "offsets": {}}
    # the strict reference: May lists from 2022, annual
    may = [d for d in VQ.rebalance_dates(close.index, 5) if d >= pd.Timestamp("2022-05-01")]
    strict_lists = {D: {r["code"] for r in ST.pick("strict", cand.build(conn, D.date())["all_rows"]) if r["selected"]} for D in may}
    picks_log: dict[str, list[dict]] = {a: [] for a in ARMS}
    for off in (0, 1, 2):
        dates = [d for d in months if d >= START and (d.month - 1) % 3 == (6 + off) % 3]
        print(f"\n=== offset {off}: rebalances {[str(d.date()) for d in dates[:3]]} … {str(dates[-1].date())} ({len(dates)} rebalances)  (DSR at N_trials = {N_TRIALS})")
        print(f"{'arm':14s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | names | picked names' 12m: mean / median / P(<-50%)")
        table = {}
        for arm in ARMS:
            plan = {}
            for D in dates:
                g = panel[panel["date"] == D]
                codes = pick(arm, g, panel, D)
                plan[D] = set(codes)
                sub = g[g["code"].isin(codes)]
                picks_log[arm].extend({"date": str(D.date()), "off": off, "code": c, "fwd12": float(v)} for c, v in zip(sub["code"], sub["fwd12"], strict=True))
            start = next((D for D in dates if plan[D]), None)
            if start is None:
                continue
            nav = VQ.simulate(plan, close, vol, delisted, div, start, end, True)
            st = VQ.stats(nav, [d for d in dates if d >= start])
            st["from"] = str(start.date())
            r = list(st.pop("_r"))
            st["dsr"] = round(ES.deflated_sharpe(r, N_TRIALS), 3)
            st["n"] = round(float(np.mean([len(plan[D]) for D in dates if plan[D]])), 1)
            f12 = pd.Series([p["fwd12"] for p in picks_log[arm] if p["off"] == off]).dropna()
            st["picked_mean12"], st["picked_median12"], st["picked_p50loss"] = float(f12.mean()), float(f12.median()), float((f12 < -0.5).mean())
            table[arm] = st
            print(f"{arm:14s} {st['total_pct']:7.1f} {st['cagr_pct']:6.1f} {st['sharpe']:6.2f} {st['mdd_pct']:5.0f} {st['dsr']:5.2f} | {st['n']:5.1f} | "
                  f"{100 * st['picked_mean12']:+.0f}% / {100 * st['picked_median12']:+.0f}% / {100 * st['picked_p50loss']:.0f}%")
            sys.stdout.flush()
        # strict reference over the same window
        nav = VQ.simulate(strict_lists, close, vol, delisted, div, dates[0], end, True)
        st = VQ.stats(nav, dates)
        st.pop("_r")
        table["strict"] = st
        print(f"{'strict (ref)':14s} {st['total_pct']:7.1f} {st['cagr_pct']:6.1f} {st['sharpe']:6.2f} {st['mdd_pct']:5.0f}")
        results["offsets"][str(off)] = {"rebalances": [str(d.date()) for d in dates], "table": table}
    print("\n--- reading rule: beats ew in 3/3 offsets, strict in >= 2/3, worst mDD <= 35 %")
    verdict = {}
    for arm in ARMS[1:]:
        offs = [o for o in results["offsets"] if arm in results["offsets"][o]["table"]]
        ew_w = sum(results["offsets"][o]["table"][arm]["cagr_pct"] > results["offsets"][o]["table"]["ew"]["cagr_pct"] for o in offs)
        st_w = sum(results["offsets"][o]["table"][arm]["cagr_pct"] > results["offsets"][o]["table"]["strict"]["cagr_pct"] for o in offs)
        dd = max(results["offsets"][o]["table"][arm]["mdd_pct"] for o in offs) if offs else float("nan")
        ok = len(offs) == 3 and ew_w == 3 and st_w >= 2 and dd <= 35
        verdict[arm] = {"beats_ew": int(ew_w), "beats_strict": int(st_w), "worst_mdd": dd, "adopt": bool(ok)}
        print(f"    {arm:14s} beats ew {ew_w}/3, beats strict {st_w}/3, worst mDD {dd:.0f}% -> {'PAPER SLEEVE' if ok else 'tested, not a sleeve'}")
    results["verdict"] = verdict
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
