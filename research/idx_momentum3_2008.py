#!/usr/bin/env python3
"""IDX — the "three names with the most upside" from 2008 (2026-09-14).

The operator asked for the highest-return idea (three momentum leaders out of the value list, IDX_TOP3_UPSIDE) to be
tested from 2008. Fundamentals do not exist before 2020, so the value list cannot be rebuilt; what can be tested over
eighteen years is the price half of the idea on the same 100-name liquid basket used for the long overlay tests (Yahoo
cache, survivors only). Survivorship flatters concentrated momentum most of all: the names that went to zero are not in
the file. Every arm is measured on the same basket, so the comparison is fair even where the level is not.

PRE-REGISTERED MENU (5 trials; cumulative 146 + 5 = 151). Basket: each rebalance the 100 most traded names with a year
of history. Annual rebalance, four calendars (May, Feb, Aug, Nov), reset mode (equal weight), 25 bps + half-tick,
price returns (no dividends), no cash rate, 2008 to 2026-09.
    basket        the 100 names equal weight (reference)
    mom3          the three highest 12-1 momentum names of the basket
    mom10         the ten highest
    mom20         the twenty highest
    recovery3     the three deepest below their 252-day high (the "most room to recover" definition)
    mom3_regime   mom3, all to cash at the rebalance if the IHSG is under its 200-day average (checked monthly: out when
                  under, back in when above, same three names)
READ: total, CAGR, Sharpe, max drawdown, the drawdown inside each crash episode, and for mom3 the same numbers with its
single best-contributing name excluded from every pick. READING RULE (declared before the run): mom3 is "robust across
regimes" only if it beats the basket on CAGR in three of four calendars, its 2008 and 2020 episode drawdowns are not
more than 10 points deeper than the basket's, and the ex-best-name version still beats the basket in three of four.

READ-ONLY. blackheart-ingest/.venv/Scripts/python research/idx_momentum3_2008.py
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

N_TRIALS = 151
TO.N_TRIALS = N_TRIALS
OUT = os.path.join(VQ.OUTDIR, "momentum3_2008_results.json")
ARMS = ("basket", "mom3", "mom10", "mom20", "recovery3", "mom3_regime")


def annual_dates(index: pd.DatetimeIndex, month: int) -> list[pd.Timestamp]:
    out = []
    for y in range(2008, index[-1].year + 1):
        pos = index.searchsorted(pd.Timestamp(f"{y}-{month:02d}-02"))
        if pos < len(index) and index[pos].year == y:
            out.append(index[pos])
    return out


def top(scores: pd.Series, codes: set[str], n: int, exclude: set[str]) -> set[str]:
    s = scores.reindex([c for c in codes if c not in exclude]).dropna().sort_values(ascending=False)
    return set(s.index[:n])


def plans(close: pd.DataFrame, lists: dict, sig: TO.Signals, checks: list[pd.Timestamp], exclude: set[str]) -> dict[str, dict]:
    dd = close / close.rolling(252, min_periods=120).max() - 1
    dd_at = dd.reindex(sorted(lists), method="ffill")
    out: dict[str, dict] = {a: {} for a in ARMS}
    picks: dict[pd.Timestamp, set[str]] = {}
    for D, L in lists.items():
        mom = sig.mom.loc[D] if D in sig.mom.index else (close.shift(21) / close.shift(252) - 1).loc[:D].iloc[-1]
        out["basket"][D] = set(L)
        picks[D] = top(mom, L, 3, exclude)
        out["mom3"][D] = picks[D]
        out["mom10"][D] = top(mom, L, 10, exclude)
        out["mom20"][D] = top(mom, L, 20, exclude)
        out["recovery3"][D] = top(-dd_at.loc[D], L, 3, exclude)
    annual = sorted(lists)
    for m in checks:                                                      # mom3 with the crash filter, monthly
        D = max(a for a in annual if a <= m)
        out["mom3_regime"][m] = picks[D] if sig.regime(m) else set()
    return out


def best_contributor(sel: dict, close: pd.DataFrame, end: pd.Timestamp) -> str:
    dates = sorted(sel)
    total: dict[str, float] = {}
    for a, b in zip(dates, [*dates[1:], end], strict=True):
        for code, ret in VQ.contributions(sel[a], close, TO.EMPTY_DIV, a, b):
            total[code] = total.get(code, 0.0) + ret
    return max(total, key=total.get) if total else ""


def main():
    close, vol, jk = TO.load_yahoo()
    end = close.index[-1]
    eps = tuple(TO.EPISODES)
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "months": {}}
    print(f"=== 2008-2026, {TO.BASKET_N}-name liquid basket ({len(close.columns)} survivors), annual rebalance, reset mode, price returns")
    for month in (5, 2, 8, 11):
        annual = annual_dates(close.index, month)
        lists = TO.baskets(close, vol, annual)
        checks = sorted(set(TO.month_starts(close.index, annual[0], end)) | set(annual))
        sig = TO.Signals(close, jk, checks)
        print(f"\n--- month {month}: {annual[0].date()} .. {annual[-1].date()} ({len(annual)} rebalances)")
        print(f"{'arm':14s} {'total%':>8} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'cash%':>5} {'DSR':>5} | episode drawdowns %")
        table = {}
        P = plans(close, lists, sig, checks, set())
        for arm in ARMS:
            nav = VQ.simulate(P[arm], close, vol, {}, TO.EMPTY_DIV, annual[0], end, True, mode="reset")
            v = TO.read(nav, annual)
            v["yearly"] = v.get("yearly")
            table[arm] = v
            print(TO.line(arm, v, eps))
            sys.stdout.flush()
        best = best_contributor(P["mom3"], close, end)
        P2 = plans(close, lists, sig, checks, {best})
        nav = VQ.simulate(P2["mom3"], close, vol, {}, TO.EMPTY_DIV, annual[0], end, True, mode="reset")
        v = TO.read(nav, annual)
        table["mom3_ex_best"] = v
        table["mom3_best_name"] = best
        print(TO.line(f"mom3 ex-{best}", v, eps))
        table["mom3_picks"] = {str(D.date()): sorted(P["mom3"][D]) for D in sorted(lists)}
        results["months"][str(month)] = table
    months = results["months"]
    print("\n--- reading rule: mom3 beats the basket on CAGR in 3/4 calendars; 2008 and 2020 episode drawdowns not >10 pts deeper; ex-best still 3/4")
    wins = sum(months[m]["mom3"]["cagr_pct"] > months[m]["basket"]["cagr_pct"] for m in months)
    wins_ex = sum(months[m]["mom3_ex_best"]["cagr_pct"] > months[m]["basket"]["cagr_pct"] for m in months)
    crash_ok = all((months[m]["mom3"]["episodes"][e] or 0) >= (months[m]["basket"]["episodes"][e] or 0) - 10 for m in months for e in ("2008", "2020"))
    avg = {a: float(np.mean([months[m][a]["cagr_pct"] for m in months])) for a in (*ARMS, "mom3_ex_best")}
    dd = {a: float(np.max([months[m][a]["mdd_pct"] for m in months])) for a in (*ARMS, "mom3_ex_best")}
    for a in (*ARMS, "mom3_ex_best"):
        print(f"  {a:13s} avg CAGR {avg[a]:5.1f}  worst mDD {dd[a]:3.0f}%")
    ok = wins >= 3 and crash_ok and wins_ex >= 3
    print(f"  mom3 wins {wins}/4, ex-best {wins_ex}/4, crash clause {'ok' if crash_ok else 'FAILS'} -> {'ROBUST' if ok else 'not robust'}")
    results["summary"] = {"avg_cagr": avg, "worst_mdd": dd, "wins": wins, "wins_ex_best": wins_ex, "crash_ok": crash_ok, "robust": ok}
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
