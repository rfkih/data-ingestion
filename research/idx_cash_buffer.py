#!/usr/bin/env python3
"""IDX — a standing cash buffer and a stress detector that raises it (2026-09-14).

The operator's rule: hold 30 % cash at all times in case of a crash, and when the market turns bad raise cash to 50 %.
"Bad" has to be measured; there is no news or sentiment feed on the desk yet, so the detector is built from market data,
four signals tested one by one and combined, each read at the monthly check from data up to that day:
    ma        the IHSG closes under its 200-day average
    vol       the IHSG's 20-day realised volatility is above the 80th percentile of its own trailing three years
    dd        the IHSG is more than 10 % under its 252-day high
    breadth   fewer than 40 % of the liquid names close above their own 200-day average
    any2      at least two of the four

PRE-REGISTERED MENU (7 trials; cumulative 155 + 7 = 162). Exposure = the fraction of the book in the list, the rest in
cash at 4 %/yr, re-set at every monthly check (so every arm, the reference included, is the list re-weighted monthly):
    full            1.00 always (the rule, monthly re-weighted)
    cash30          0.70 always
    ma / vol / dd / breadth / any2   0.70 normally, 0.50 while the signal is on
    detector_only   1.00 normally, 0.50 while any2 is on
    regime          1.00 / 0.00 on ma (the existing crash filter, reference)
Part A: the strict book 2021-2026, four calendars, rev. 3 simulator, real costs, dividends net of tax.
Part B: the 100-name liquid basket 2008-2026 (Yahoo cache, survivors), May calendar, price returns; breadth on the basket.

READING RULE, written before the run. A cash rule is worth building only if, on the strict book, its Sharpe beats
full's in at least three of four calendars, its worst-calendar drawdown is at least 5 points shallower than full's,
and its CAGR is at least 75 % of full's; and on the 2008 basket its max drawdown is 40 % or less with the 2008 and 2020
episodes no worse than -30 %. A constant buffer is expected to scale return and drawdown together (that is what it is);
the question is whether the detector adds anything to the buffer.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_cash_buffer.py
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
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

OUT = os.path.join(VQ.OUTDIR, "cash_buffer_results.json")
TRIALS = 162
CASH_RATE = 0.04
SIGNALS = ("ma", "vol", "dd", "breadth", "any2")
ARMS = ("full", "cash30", *SIGNALS, "detector_only", "regime")


class Stress:
    """The four signals at each check date, from data up to that day only."""

    def __init__(self, jk: pd.Series, close: pd.DataFrame, checks: list[pd.Timestamp]):
        jk = jk.dropna()
        ma = jk.rolling(200, min_periods=200).mean()
        r = np.log(jk / jk.shift(1))
        vol20 = r.rolling(20).std() * np.sqrt(252)
        vol_p80 = vol20.rolling(750, min_periods=250).quantile(0.8)
        hi252 = jk.rolling(252, min_periods=120).max()
        above = (close > close.rolling(200, min_periods=200).mean())
        valid = close.rolling(200, min_periods=200).mean().notna() & close.notna()
        breadth = above.sum(axis=1) / valid.sum(axis=1).replace(0, np.nan)
        self.s = {}
        for m in checks:
            j = jk.loc[:m]
            d = j.index[-1] if len(j) else None
            if d is None:
                self.s[m] = {k: False for k in SIGNALS}
                continue
            s_ma = bool(j.iloc[-1] < ma.loc[d]) if not np.isnan(ma.loc[d]) else False
            s_vol = bool(vol20.loc[d] > vol_p80.loc[d]) if not (np.isnan(vol20.loc[d]) or np.isnan(vol_p80.loc[d])) else False
            s_dd = bool(j.iloc[-1] / hi252.loc[d] - 1 < -0.10) if not np.isnan(hi252.loc[d]) else False
            b = breadth.loc[:m]
            s_br = bool(b.iloc[-1] < 0.40) if len(b) and not np.isnan(b.iloc[-1]) else False
            n_on = sum((s_ma, s_vol, s_dd, s_br))
            self.s[m] = {"ma": s_ma, "vol": s_vol, "dd": s_dd, "breadth": s_br, "any2": n_on >= 2}

    def on(self, m: pd.Timestamp, key: str) -> bool:
        return self.s[m][key]


def exposure_fn(arm: str, stress: Stress):
    if arm == "full":
        return lambda d: 1.0
    if arm == "cash30":
        return lambda d: 0.7
    if arm == "detector_only":
        return lambda d: 0.5 if stress.on(d, "any2") else 1.0
    if arm == "regime":
        return lambda d: 0.0 if stress.on(d, "ma") else 1.0
    return lambda d: 0.5 if stress.on(d, arm) else 0.7


def monthly_plan(lists: dict, checks: list[pd.Timestamp]) -> dict:
    annual = sorted(lists)
    return {m: set(lists[max(a for a in annual if a <= m)]) for m in sorted(set(checks) | set(annual))}


def stress_share(stress: Stress, checks: list, key: str) -> float:
    return 100 * float(np.mean([stress.on(m, key) for m in checks]))


def part_a(conn, results: dict) -> None:
    close, vol, delisted, div, ix = VQ.load(conn)
    end = close.index[-1]
    jk = ix["COMPOSITE"].dropna()
    results["part_a"] = {}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        lists = {D: {r["code"] for r in ST.pick("strict", cand.build(conn, D.date())["all_rows"]) if r["selected"]} for D in rebals}
        checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))
        stress = Stress(jk, close, checks)
        plan = monthly_plan(lists, checks)
        print(f"\n=== strict book, month {month}: {[str(r.date()) for r in rebals]}   signal on-time: " +
              ", ".join(f"{k} {stress_share(stress, checks, k):.0f}%" for k in SIGNALS))
        print(f"{'arm':14s} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'2025 dip':>8}")
        table = {}
        for arm in ARMS:
            nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="reset", cash_rate=CASH_RATE,
                              exposure=exposure_fn(arm, stress))
            st = VQ.stats(nav, rebals); st.pop("_r")
            seg = nav.loc["2025-01-01":"2025-04-30"]
            st["dip_2025"] = round(100 * (seg.min() / seg.cummax().max() - 1), 1) if len(seg) else None
            table[arm] = st
            print(f"{arm:14s} {st['cagr_pct']:6.1f} {st['sharpe']:6.2f} {st['mdd_pct']:5.0f} {st['dip_2025'] if st['dip_2025'] is not None else float('nan'):8.0f}")
            sys.stdout.flush()
        table["signal_on_pct"] = {k: stress_share(stress, checks, k) for k in SIGNALS}
        results["part_a"][str(month)] = table


def part_b(results: dict) -> None:
    close, vol, jk = TO.load_yahoo()
    end = close.index[-1]
    annual = []
    for y in range(2008, end.year + 1):
        pos = close.index.searchsorted(pd.Timestamp(f"{y}-05-02"))
        if pos < len(close.index):
            annual.append(close.index[pos])
    lists = TO.baskets(close, vol, annual)
    checks = sorted(set(TO.month_starts(close.index, annual[0], end)) | set(annual))
    basket_close = close[[c for c in close.columns]]
    stress = Stress(jk, basket_close, checks)
    plan = monthly_plan(lists, checks)
    eps = tuple(TO.EPISODES)
    print(f"\n=== 2008-2026 basket, May calendar   signal on-time: " + ", ".join(f"{k} {stress_share(stress, checks, k):.0f}%" for k in SIGNALS))
    print(f"{'arm':14s} {'total%':>8} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'cash%':>5} {'DSR':>5} | episode drawdowns %")
    table = {}
    TO.N_TRIALS = TRIALS
    for arm in ARMS:
        nav = VQ.simulate(plan, close, vol, {}, TO.EMPTY_DIV, annual[0], end, True, mode="reset", cash_rate=CASH_RATE,
                          exposure=exposure_fn(arm, stress))
        v = TO.read(nav, annual)
        table[arm] = v
        print(TO.line(arm, v, eps))
        sys.stdout.flush()
    table["signal_on_pct"] = {k: stress_share(stress, checks, k) for k in SIGNALS}
    results["part_b"] = table


def main():
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": TRIALS}
    conn = VQ.connect()
    part_a(conn, results)
    part_b(results)
    A, B = results["part_a"], results["part_b"]
    print("\n--- reading rule: Sharpe > full in >=3/4 calendars, worst mDD >=5 pts shallower, CAGR >= 75% of full; 2008 basket mDD <= 40%, 2008/2020 episodes >= -30%")
    verdicts = {}
    full_dd = max(A[m]["full"]["mdd_pct"] for m in A)
    full_avg = float(np.mean([A[m]["full"]["cagr_pct"] for m in A]))
    for arm in ARMS:
        if arm == "full":
            continue
        sh = sum(A[m][arm]["sharpe"] > A[m]["full"]["sharpe"] for m in A)
        dd = max(A[m][arm]["mdd_pct"] for m in A)
        avg = float(np.mean([A[m][arm]["cagr_pct"] for m in A]))
        b = B[arm]
        e08, e20 = b["episodes"].get("2008"), b["episodes"].get("2020")
        crash_ok = b["mdd_pct"] <= 40 and (e08 is None or e08 >= -30) and (e20 is None or e20 >= -30)
        ok = sh >= 3 and dd <= full_dd - 5 and avg >= 0.75 * full_avg and crash_ok
        verdicts[arm] = {"avg_cagr": avg, "sharpe_wins": sh, "worst_mdd": dd, "basket_cagr": b["cagr_pct"], "basket_mdd": b["mdd_pct"],
                         "ep_2008": e08, "ep_2020": e20, "candidate": ok}
        print(f"  {arm:14s} strict avg CAGR {avg:5.1f} ({100*avg/full_avg:3.0f}% of full)  Sharpe wins {sh}/4  worst mDD {dd:3.0f}% (full {full_dd:.0f}%) | "
              f"2008 basket CAGR {b['cagr_pct']:5.1f} mDD {b['mdd_pct']:3.0f}% 2008 {e08:+.0f} 2020 {e20:+.0f}  -> {'CANDIDATE' if ok else 'tested'}")
    print(f"  {'full':14s} strict avg CAGR {full_avg:5.1f}  worst mDD {full_dd:.0f}% | 2008 basket CAGR {B['full']['cagr_pct']:5.1f} mDD {B['full']['mdd_pct']:.0f}%")
    results["verdicts"] = verdicts
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
