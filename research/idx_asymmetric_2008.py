#!/usr/bin/env python3
"""IDX — the asymmetric rule from 2008 (2026-09-13). The operator's rule (sell on a cross under the 200-day average, buy
when oversold or above it) passed on the strict book 2021-2026 (idx_asymmetric.py). Fundamentals do not exist before
2020, so from 2008 the rule is tested as a PRICE overlay on the same 100-name liquid basket used for the regime filter's
long test (Yahoo cache, survivors only: per-name rules are flattered a little; every arm is measured on the same basket).

PRE-REGISTERED MENU (3 trials; cumulative 134 + 3 = 137). Basket: each May the 100 most traded names with a year of
history, equal weight, drift mode with a 1/100 cap, monthly checks, 25 bps + half-tick, price returns (no dividends),
cash 4 %/yr, 2008-05 to 2026-09.
    none, entry_only, name_trend, index   (references from IDX_TREND_OVERLAY, recomputed)
    asym_rsi         sell on a cross from above to below MA200; buy when RSI-14 <= 30 or above MA200
    asym_bb          the same with the lower Bollinger band as the oversold entry
    asym_rsi_regime  asym_rsi, and all to cash while the IHSG is under its MA200 (the two halves of "no falling knives")
READ: total, CAGR, Sharpe, max drawdown, and the drawdown inside each episode (2008, 2011, 2013, 2015, 2018, 2020, 2022,
2025). READING RULE (declared before the run): the asymmetric rule is confirmed as a per-name drawdown reducer if its
max drawdown is shallower than none's by at least 5 points with a CAGR within 2 points of none's; it is NOT expected to
be crash insurance (that is the regime filter's job) and the 2008/2020 episodes are reported to show it.

READ-ONLY. blackheart-ingest/.venv/Scripts/python research/idx_asymmetric_2008.py
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
import idx_asymmetric as AS  # noqa: E402
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402

N_TRIALS = 137
TO.N_TRIALS = N_TRIALS
OUT = os.path.join(VQ.OUTDIR, "asymmetric_2008_results.json")
ARMS = ("none", "entry_only", "name_trend", "index", "asym_rsi", "asym_bb", "asym_rsi_regime")


def main():
    close, vol, jk = TO.load_yahoo()
    end = close.index[-1]
    annual = []
    for y in range(2008, end.year + 1):
        pos = close.index.searchsorted(pd.Timestamp(f"{y}-05-02"))
        if pos < len(close.index):
            annual.append(close.index[pos])
    lists = TO.baskets(close, vol, annual)
    checks = sorted(set(TO.month_starts(close.index, annual[0], end)) | set(annual))
    sig = TO.Signals(close, jk, checks)
    rsi_at = AS.rsi(close).reindex(checks, method="ffill")
    mean20 = close.rolling(AS.BB_N, min_periods=AS.BB_N).mean()
    sd20 = close.rolling(AS.BB_N, min_periods=AS.BB_N).std()
    bb_lo = (mean20 - AS.BB_K * sd20).reindex(checks, method="ffill")
    eps = tuple(TO.EPISODES)
    print(f"=== 2008-2026 price overlay on the {TO.BASKET_N}-name basket ({len(close.columns)} survivors), monthly checks, cash {100 * TO.CASH_RATE:.0f} %/yr  (DSR at N_trials = {N_TRIALS})")
    print(f"{'arm':16s} {'total%':>8} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'cash%':>5} {'DSR':>5} | episode drawdowns %")
    table = {}
    for arm in ARMS:
        if arm in ("none", "entry_only", "name_trend", "index"):
            plan = TO.build_plan(arm, lists, sig)
        elif arm == "asym_rsi_regime":
            inner = AS.build_asym("asym_rsi", lists, sig, close, rsi_at, bb_lo)
            plan = {m: (inner[m] if sig.regime(m) else set()) for m in inner}
        else:
            plan = AS.build_asym(arm, lists, sig, close, rsi_at, bb_lo)
        nav = VQ.simulate(plan, close, vol, {}, TO.EMPTY_DIV, annual[0], end, True, mode="drift", cap=1 / TO.BASKET_N, cash_rate=TO.CASH_RATE)
        v = TO.read(nav, annual)
        table[arm] = v
        print(TO.line(arm, v, eps))
        sys.stdout.flush()
    base = table["none"]
    print("\n--- reading rule: max drawdown at least 5 points shallower than none with CAGR within 2 points")
    verdict = {}
    for arm in ("asym_rsi", "asym_bb", "asym_rsi_regime"):
        v = table[arm]
        ok = (base["mdd_pct"] - v["mdd_pct"]) >= 5 and v["cagr_pct"] >= base["cagr_pct"] - 2
        verdict[arm] = {"mdd_cut": round(base["mdd_pct"] - v["mdd_pct"], 1), "cagr_diff": round(v["cagr_pct"] - base["cagr_pct"], 1), "confirmed": bool(ok)}
        print(f"    {arm:16s} mDD {v['mdd_pct']:.0f}% vs {base['mdd_pct']:.0f}% (cut {base['mdd_pct'] - v['mdd_pct']:+.0f}), CAGR {v['cagr_pct']:.1f}% vs {base['cagr_pct']:.1f}% "
              f"-> {'CONFIRMED' if ok else 'not confirmed'};  2008 {v['episodes']['2008']}% / 2020 {v['episodes']['2020']}%")
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "table": table, "verdict": verdict}
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
