#!/usr/bin/env python3
"""IDX — when to sell a name that has become expensive (2026-09-13). The book's only valuation exit today is the annual
rebalance: a name that is no longer in the cheapest fifth leaves in May. The operator asks whether a sell rule between
rebalances, when a name is "indicated over-priced", does better.

PRE-REGISTERED MENU (4 trials; cumulative 100 + 4 = 104). The strict composite, 2021-2026, four calendars, the rev. 3
simulator (drift mode, one-slot cap, cash 4 %/yr), checked on the first trading day of each month at that close; a name
sold by a rule stays in cash until the next annual rebalance (no replacement: the question is whether selling early helps).
    none        hold everything to the next rebalance (the reference)
    val_median  sell a held name when its earnings yield (audited profit / today's market value, point-in-time) falls
                under the median of the light-gate pool that day: it is no longer cheap relative to peers
    pe15        sell a held name when its price/earnings on audited profit exceeds 15 (earnings yield under 6.7 %)
    tp50        sell a held name at +50 % over its purchase close (take profit)
    tp100       sell at +100 %

READING RULE (declared before the run): a rule replaces "hold to the rebalance" only if its total return is higher in at
least three of four calendars and its worst-calendar drawdown is not deeper. Otherwise the annual rebalance stays the
book's valuation exit and the rule is recorded as tested.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_sell_rules.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

N_TRIALS = 104
TO.N_TRIALS = N_TRIALS
OUT = os.path.join(VQ.OUTDIR, "sell_rules_results.json")
RULES = ("none", "val_median", "pe15", "tp50", "tp100")
PE_MAX = Decimal(15)


def valuation_at(conn, D: pd.Timestamp, cache: dict) -> tuple[dict[str, Decimal | None], Decimal | None]:
    """Per code the earnings yield on the day, and the light-gate pool's median; built once per date."""
    if D in cache:
        return cache[D]
    rows = cand.build(conn, D.date())["all_rows"]
    ep = {r["code"]: (Decimal(r["ep"]) if r["ep"] is not None else None) for r in rows}
    pool = sorted(Decimal(r["ep"]) for r in rows if r["gate_loose"] and r["ep"] is not None and r["ep"] > 0 and r.get("tradable", True))
    med = pool[len(pool) // 2] if pool else None
    cache[D] = (ep, med)
    return cache[D]


def build_plan(kind: str, lists: dict, checks: list[pd.Timestamp], close: pd.DataFrame, conn, cache: dict) -> dict:
    annual = sorted(lists)
    dates = sorted(set(checks) | set(annual))

    def current(m):
        return lists[max(a for a in annual if a <= m)]

    plan: dict = {}
    state = {"entry": {}, "prev_held": set(), "prev_date": None, "sold": set(), "list_date": None}
    for m in dates:
        L = current(m)
        list_date = max(a for a in annual if a <= m)
        if kind == "none":
            plan[m] = set(L)
            continue

        def rule(held, m=m, L=L, list_date=list_date):
            if state["list_date"] != list_date:                          # a new list: the early-sold names are forgiven
                state["sold"], state["list_date"] = set(), list_date
            entry, prev = state["entry"], state["prev_held"]
            for c in held - prev:
                entry[c] = state["prev_date"] if state["prev_date"] is not None else m
            for c in prev - held:
                entry.pop(c, None)
            keep = set()
            if kind in ("val_median", "pe15"):
                ep, med = valuation_at(conn, m, cache)
            for c in held & L:
                sell = False
                if kind == "val_median":
                    e = ep.get(c)
                    sell = e is not None and med is not None and e < med
                elif kind == "pe15":
                    e = ep.get(c)
                    sell = e is not None and e > 0 and (Decimal(1) / e) > PE_MAX
                else:
                    since = entry.get(c, m)
                    p0 = close[c].asof(since) if c in close.columns else np.nan
                    p1 = close[c].asof(m) if c in close.columns else np.nan
                    gain = Decimal("0.5") if kind == "tp50" else Decimal(1)
                    sell = not (np.isnan(p0) or np.isnan(p1)) and Decimal(str(p1)) >= (1 + gain) * Decimal(str(p0))
                if sell:
                    state["sold"].add(c)
                    entry.pop(c, None)
                else:
                    keep.add(c)
            # the list's names not held and not sold early (e.g. unfillable at the rebalance) may still enter
            out = keep | {c for c in L if c not in held and c not in state["sold"]}
            state["prev_held"], state["prev_date"] = set(held), m
            return out
        plan[m] = rule
    return plan


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    end = close.index[-1]
    cache: dict = {}
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "months": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        rows_at = {D: cand.build(conn, D.date())["all_rows"] for D in rebals}
        lists = {D: {r["code"] for r in ST.pick("strict", rows_at[D]) if r["selected"]} for D in rebals}
        checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))

        def slot(d, lists=lists):
            return 1 / max(1, len(lists[max(a for a in lists if a <= d)]))

        table = {}
        print(f"\n=== month {month}: strict composite {[str(r.date()) for r in rebals]}, monthly checks, sell rules  (DSR at N_trials = {N_TRIALS})")
        print(f"{'rule':12s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | rebalance-period returns %")
        for kind in RULES:
            plan = build_plan(kind, lists, checks, close, conn, cache)
            nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="drift", cap=slot, cash_rate=TO.CASH_RATE)
            v = TO.read(nav, rebals)
            table[kind] = v
            per = " ".join(f"{d[:4]}:{x:+.0f}" for d, x in v["periods"].items())
            print(f"{kind:12s} {v['total_pct']:7.1f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v['dsr']:5.2f} | {per}")
            sys.stdout.flush()
        results["months"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}
    print("\n--- reading rule: a sell rule replaces 'hold to the rebalance' only if ahead in >= 3 of 4 calendars with no deeper worst drawdown")
    verdict = {}
    for kind in RULES[1:]:
        wins = sum(results["months"][m]["table"][kind]["total_pct"] > results["months"][m]["table"]["none"]["total_pct"] for m in results["months"])
        dd_ok = max(results["months"][m]["table"][kind]["mdd_pct"] for m in results["months"]) <= max(results["months"][m]["table"]["none"]["mdd_pct"] for m in results["months"])
        verdict[kind] = {"wins": int(wins), "dd_ok": bool(dd_ok), "adopt": bool(wins >= 3 and dd_ok)}
        print(f"    {kind:12s} ahead in {wins}/4, drawdown ok {dd_ok} -> {'ADOPT' if verdict[kind]['adopt'] else 'keep the annual rebalance'}")
    results["verdict"] = verdict
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
