#!/usr/bin/env python3
"""IDX — cash conversion as a rank input (2026-09-12, late). The quality menu's diagnostic found one quality input with
forward power, CFO / net profit (rho +0.16, positive in all six years). That was post-hoc; this is the pre-registered test.

PRE-REGISTERED MENU (written before the run; each cell one trial; cumulative trials this session 68 + 3 = 71):
  rule+conv      the light gate; composite of FOUR average ranks: E/P, B/P, DY, cash conversion; top fifth, equal weight
  strict+conv    the strict gate; the same four ranks; top fifth, equal weight
  strict10+conv  strict+conv cut to ten names
Cash conversion = CFO / net profit from the same audited year the yields use, capped at 3; a name without it ranks lowest
on that input (the strict gate already requires CFO > 0, so this only bites in the light pool).
Reference lines (not new trials): the rule, strict, strict ten, recomputed from the catalog with the same simulator.

ADOPTION CRITERION (declared before the run): a +conv variant replaces its base only if its total return beats the base
in at least three of the four calendars AND its worst-calendar drawdown is not more than three points deeper. Otherwise
the base stays and the cash-conversion idea is filed as "tested, not better".

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_cash_conversion.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import equity_screen as ES  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402
from blackheart_ingest.idx.candidates import KEYS, rank_pool  # noqa: E402

N_TRIALS = 71
OUT = os.path.join(VQ.OUTDIR, "cash_conversion_results.json")
KEYS4 = tuple(KEYS) + ("conv",)
MENU = (("rule+conv", "loose", None), ("strict+conv", "strict", None), ("strict10+conv", "strict", 10))
REFS = (("rule", "rule", None), ("strict", "strict", None), ("strict10", "strict", 10))


def with_conv(rows):
    out = []
    for r in rows:
        r = dict(r)
        cfo, ep, mcap = r.get("cfo"), r.get("ep"), r.get("mcap")
        np_ = r.get("net_profit")
        if np_ is None and ep is not None and mcap:
            np_ = Decimal(ep) * Decimal(mcap)
        r["conv"] = min(Decimal(cfo) / Decimal(np_), Decimal(3)) if (cfo is not None and np_ and Decimal(np_) > 0) else None
        out.append(r)
    return out


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    end = close.index[-1]
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "months": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        rows_at = {D: with_conv(cand.build(conn, D.date())["all_rows"]) for D in rebals}
        table = {}
        for label, gate, size in REFS:
            sel = {D: {r["code"] for r in ST.pick(gate, rows_at[D], size=size) if r["selected"]} for D in rebals}
            table[label] = (sel, False)
        for label, gate, size in MENU:
            sel = {}
            for D in rebals:
                pool = rank_pool(rows_at[D], gate=gate, keys=KEYS4)
                chosen = [r["code"] for r in pool if r["selected"]]
                sel[D] = set(chosen[:size] if size else chosen)
            table[label] = (sel, True)
        out = {}
        for label, (sel, is_trial) in table.items():
            nav = VQ.simulate(sel, close, vol, delisted, div, rebals[0], end, True)
            st = VQ.stats(nav, rebals)
            r = list(st.pop("_r"))
            st["dsr"] = round(ES.deflated_sharpe(r, N_TRIALS), 3)
            st["psr"] = round(ES.deflated_sharpe(r, 1), 3)
            st["n"] = [len(sel[D]) for D in rebals]
            st["holdings"] = {str(D.date()): sorted(sel[D]) for D in rebals}
            st["trial"] = is_trial
            out[label] = st
        results["months"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": out}
        print(f"\n=== month {month}: {[str(r.date()) for r in rebals]}   (DSR at N_trials = {N_TRIALS})")
        print(f"{'portfolio':14s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | names | rebalance-period returns %")
        for k, v in out.items():
            per = " ".join(f"{d[:4]}:{x:+.0f}" for d, x in v["periods"].items())
            print(f"{k:14s} {v['total_pct']:7.1f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v['dsr']:5.2f} | {v['n']} | {per}")
        sys.stdout.flush()
    # the adoption criterion, mechanically
    print("\n--- adoption criterion: beats the base in >= 3 of 4 calendars and worst drawdown <= base + 3 pts")
    verdict = {}
    for var, base in (("rule+conv", "rule"), ("strict+conv", "strict"), ("strict10+conv", "strict10")):
        wins = sum(results["months"][m]["table"][var]["total_pct"] > results["months"][m]["table"][base]["total_pct"] for m in results["months"])
        dd_v = max(results["months"][m]["table"][var]["mdd_pct"] for m in results["months"])
        dd_b = max(results["months"][m]["table"][base]["mdd_pct"] for m in results["months"])
        ok = wins >= 3 and dd_v <= dd_b + 3
        verdict[var] = {"wins": int(wins), "worst_mdd": dd_v, "base_worst_mdd": dd_b, "adopt": bool(ok)}
        print(f"    {var:14s} beats {base} in {wins}/4 calendars; worst mDD {dd_v:.0f} vs {dd_b:.0f}  -> {'ADOPT' if ok else 'keep ' + base}")
    results["verdict"] = verdict
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
