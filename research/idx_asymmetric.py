#!/usr/bin/env python3
"""IDX — the operator's asymmetric rule (2026-09-13): sell a name when its trend breaks (a cross from above to below its
200-day average), but do not wait for the trend to turn to buy; buy a listed name when it is oversold, on the view that
an oversold price is unlikely to keep falling.

PRE-REGISTERED MENU (3 trials; cumulative 130 + 3 = 133; plus asym_base below, 134).
  BASE (added at the operator's clarification, before its run): an accumulation base = under the MA200, 60-day close range
     at most 20 %, 60-day OBV balance positive, 20-day mean at or above the 60-day mean. asym_base uses it as the entry. Strict composite lists, four calendars, monthly checks at the
close of the first trading day of the month, drift mode with a one-slot cap, real costs, dividends net of tax, cash 4 %/yr.
  "oversold" is defined mechanically, two ways:
     RSI    14-day RSI at or under 30
     BB     close under the lower Bollinger band (20-day mean minus two standard deviations)
  exits (all arms): at a monthly check, sell a held name that was ABOVE its MA200 at the previous check and is BELOW it
     now (a trend break); a name bought oversold is not sold merely for being under the average. A name that left the
     list at the annual rebalance is sold there as usual.
  entries: a listed name not held is bought at a check when it is oversold (RSI or BB) OR above its MA200 (the normal
     entry); at the annual rebalance the list's names are bought if oversold or above MA200, the rest wait.
    asym_rsi      as above with RSI
    asym_bb       as above with the Bollinger band
    asym_rsi_stop asym_rsi plus a 20 % stop: a held name 20 % under its purchase close at a check is sold
  references (not trials): none (hold to the rebalance), entry_only (buy above MA200, never sell on trend),
    name_trend (symmetric: hold only while above MA200).

READING RULE (declared before the run): an asymmetric arm is a candidate only if its Sharpe beats `none` in at least
three of four calendars with a CAGR of at least 90 % of none's there, and its worst-calendar drawdown is shallower than
none's. Otherwise recorded as tested.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_asymmetric.py
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

N_TRIALS = 134
TO.N_TRIALS = N_TRIALS
OUT = os.path.join(VQ.OUTDIR, "asymmetric_results.json")
RSI_N, RSI_MAX, BB_N, BB_K, STOP = 14, 30.0, 20, 2.0, 0.20
ARMS = ("asym_rsi", "asym_bb", "asym_rsi_stop", "asym_base")
RANGE_MAX = 0.20


def rsi(close: pd.DataFrame, n: int = RSI_N) -> pd.DataFrame:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def build_asym(kind: str, lists: dict, sig: TO.Signals, close: pd.DataFrame, rsi_at: pd.DataFrame, bb_lo: pd.DataFrame,
               base_at: pd.DataFrame | None = None) -> dict:
    annual = sorted(lists)
    dates = sorted(set(sig.checks) | set(annual))
    px = close.reindex(dates, method="ffill")

    def current(m):
        return lists[max(a for a in annual if a <= m)]

    def oversold(m, codes):
        row = px.loc[m]
        if kind == "asym_base":
            b = base_at.loc[m]
            return {c for c in codes if c in b.index and bool(b[c])}
        if kind == "asym_bb":
            lo = bb_lo.loc[m]
            return {c for c in codes if c in row.index and not np.isnan(lo.get(c, np.nan)) and row[c] < lo[c]}
        r = rsi_at.loc[m]
        return {c for c in codes if c in r.index and not np.isnan(r.get(c, np.nan)) and r[c] <= RSI_MAX}

    state = {"above": {}, "entry": {}, "prev_held": set(), "prev_date": None}
    plan = {}
    for m in dates:
        L = current(m)

        def rule(held, m=m, L=L):
            above_now = sig.above_sma(m, L | held)
            entry, prev = state["entry"], state["prev_held"]
            for c in held - prev:                                          # bought at the previous check
                entry[c] = px.loc[state["prev_date"]][c] if state["prev_date"] is not None and c in px.columns else px.loc[m][c]
            for c in prev - held:
                entry.pop(c, None)
            keep = set()
            for c in held & L:
                broke = state["above"].get(c, False) and c not in above_now       # was above, now below: trend break
                stopped = kind == "asym_rsi_stop" and c in entry and not np.isnan(entry[c]) and px.loc[m][c] < (1 - STOP) * entry[c]
                if not broke and not stopped:
                    keep.add(c)
            candidates = L - held
            entrants = (candidates & above_now) | oversold(m, candidates)
            out = keep | entrants
            state["above"] = {c: (c in above_now) for c in out}
            state["prev_held"], state["prev_date"] = set(held), m
            return out
        plan[m] = rule
    return plan


def main():
    conn = VQ.connect()
    close, vol, delisted, div, ix = VQ.load(conn)
    end = close.index[-1]
    jk = ix["COMPOSITE"].dropna()
    rsi_all = rsi(close)
    mean20 = close.rolling(BB_N, min_periods=BB_N).mean()
    sd20 = close.rolling(BB_N, min_periods=BB_N).std()
    bb_lo_all = mean20 - BB_K * sd20
    logr = np.log(close / close.shift(1))
    obv60 = (np.sign(logr) * vol).rolling(60, min_periods=40).sum() / vol.rolling(60, min_periods=40).sum()
    rng60 = close.rolling(60, min_periods=40).max() / close.rolling(60, min_periods=40).min() - 1
    mean60 = close.rolling(60, min_periods=40).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    base_all = (close < sma200) & (rng60 <= RANGE_MAX) & (obv60 > 0) & (mean20 >= mean60)
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "months": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        lists = {D: {r["code"] for r in ST.pick("strict", cand.build(conn, D.date())["all_rows"]) if r["selected"]} for D in rebals}
        checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))
        sig = TO.Signals(close, jk, checks)
        rsi_at = rsi_all.reindex(checks, method="ffill")
        bb_lo = bb_lo_all.reindex(checks, method="ffill")
        base_at = base_all.reindex(checks, method="ffill").fillna(False)

        def slot(d, lists=lists):
            return 1 / max(1, len(lists[max(a for a in lists if a <= d)]))

        table = {}
        print(f"\n=== month {month}: strict composite {[str(r.date()) for r in rebals]}   (DSR at N_trials = {N_TRIALS})")
        print(f"{'arm':14s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | 2022 / 2025 episode dd")
        for kind in ("none", "entry_only", "name_trend", *ARMS):
            plan = TO.build_plan(kind, lists, sig) if kind in ("none", "entry_only", "name_trend") else build_asym(kind, lists, sig, close, rsi_at, bb_lo, base_at)
            nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="drift", cap=slot, cash_rate=TO.CASH_RATE)
            v = TO.read(nav, rebals)
            table[kind] = v
            e = v["episodes"]
            print(f"{kind:14s} {v['total_pct']:7.1f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v['dsr']:5.2f} | {e['2022']} / {e['2025']}")
            sys.stdout.flush()
        results["months"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}
    print("\n--- reading rule vs none: Sharpe higher with CAGR >= 90 % in >= 3/4 calendars AND shallower worst drawdown")
    verdict = {}
    none_dd = max(results["months"][m]["table"]["none"]["mdd_pct"] for m in results["months"])
    for kind in ARMS:
        wins = sum(1 for m in results["months"] if results["months"][m]["table"][kind]["sharpe"] > results["months"][m]["table"]["none"]["sharpe"]
                   and results["months"][m]["table"][kind]["cagr_pct"] >= 0.9 * results["months"][m]["table"]["none"]["cagr_pct"])
        dd = max(results["months"][m]["table"][kind]["mdd_pct"] for m in results["months"])
        ok = wins >= 3 and dd < none_dd
        verdict[kind] = {"wins": wins, "worst_mdd": dd, "none_worst_mdd": none_dd, "candidate": bool(ok)}
        print(f"    {kind:14s} wins {wins}/4, worst mDD {dd:.0f}% vs none {none_dd:.0f}% -> {'CANDIDATE' if ok else 'tested'}")
    results["verdict"] = verdict
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
