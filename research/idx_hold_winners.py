#!/usr/bin/env python3
"""IDX — hold the winners? (2026-09-12, late). The operator's point: Buffett's weights are outcomes of holding, not inputs
at purchase. Rev. 3 and the ten-name menu tested weights AT PURCHASE (rank tilts) and found nothing robust. This tests the
other thing: what happens AFTER purchase.

PRE-REGISTERED MENU (written before the run; each cell one trial; cumulative trials this session 47 + 9 = 56):
  reset   the rule as deployed: every May, sell what left the list, re-weight everything held to equal weight
  drift   never trim: sell only what left the list; the cash goes to the new entrants equally; winners keep the
          weight they have grown into
  hold    sell only when the thesis breaks (the name no longer passes the light gate that day); keep everything
          else whatever its rank; the list's new entrants are bought with whatever cash the exits and dividends
          freed. Closest to "hold while the business is fine"
  x  families rule (natural size), strict (natural size), strict at ten names

DIAGNOSTIC: persistence — among names in two consecutive May lists, does last year's return say anything about the
next year's (Spearman)? That is the empirical content of "the winner keeps winning".

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_hold_winners.py
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
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

N_TRIALS = 56
OUT = os.path.join(VQ.OUTDIR, "hold_winners_results.json")
FAMILIES = (("rule", None), ("strict", None), ("strict", 10))
MODES = ("reset", "drift", "hold")


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    end = close.index[-1]
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "months": {}, "persistence": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        rows_at = {D: cand.build(conn, D.date())["all_rows"] for D in rebals}
        gate_at = {D: {r["code"] for r in rows_at[D] if r["gate_loose"] and r["tradable"]} for D in rebals}
        table = {}
        for fam, size in FAMILIES:
            label = f"{fam}{size or ''}"
            selected = {D: {r["code"] for r in ST.pick(fam, rows_at[D], size=size) if r["selected"]} for D in rebals}
            for mode in MODES:
                if mode == "hold":
                    plan = {D: (lambda held, D=D: (held & gate_at[D]) | selected[D]) for D in rebals}
                    nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="drift")
                else:
                    nav = VQ.simulate({D: selected[D] for D in rebals}, close, vol, delisted, div, rebals[0], end, True, mode=mode)
                st = VQ.stats(nav, rebals)
                r = list(st.pop("_r"))
                st["dsr"] = round(ES.deflated_sharpe(r, N_TRIALS), 3)
                st["psr"] = round(ES.deflated_sharpe(r, 1), 3)
                table[f"{label}/{mode}"] = st
        results["months"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}
        print(f"\n=== month {month}: {[str(r.date()) for r in rebals]}   (DSR at N_trials = {N_TRIALS})")
        print(f"{'portfolio':16s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | rebalance-period returns %")
        for k, v in table.items():
            per = " ".join(f"{d[:4]}:{x:+.0f}" for d, x in v["periods"].items())
            print(f"{k:16s} {v['total_pct']:7.1f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v['dsr']:5.2f} | {per}")
        sys.stdout.flush()

        if month == 5:
            # persistence: names in consecutive lists, return in year t vs year t+1
            pairs = []
            sel = {D: {r["code"] for r in ST.pick("rule", rows_at[D]) if r["selected"]} for D in rebals}
            for i in range(len(rebals) - 2):
                D0, D1, D2 = rebals[i], rebals[i + 1], rebals[i + 2]
                for c in sel[D0] & sel[D1]:
                    if c not in close.columns:
                        continue
                    p0, p1, p2 = close.at[D0, c], close.at[D1, c], close.at[D2, c]
                    if any(np.isnan(x) or x <= 0 for x in (p0, p1, p2)):
                        continue
                    pairs.append({"code": c, "year": D0.year, "r_t": p1 / p0 - 1, "r_t1": p2 / p1 - 1})
            df = pd.DataFrame(pairs)
            rho = df["r_t"].corr(df["r_t1"], method="spearman") if len(df) > 5 else float("nan")
            up = df[df["r_t"] > df["r_t"].median()]["r_t1"]
            dn = df[df["r_t"] <= df["r_t"].median()]["r_t1"]
            print(f"\n--- persistence inside the rule's list (May): {len(df)} names in two consecutive lists")
            print(f"    Spearman(return year t, return year t+1) = {rho:+.2f}")
            print(f"    last year's better half: next-year mean {100*up.mean():+.0f}% median {100*up.median():+.0f}%  |  worse half: mean {100*dn.mean():+.0f}% median {100*dn.median():+.0f}%")
            results["persistence"] = {"n": int(len(df)), "rho": round(float(rho), 3), "up_mean": float(up.mean()), "dn_mean": float(dn.mean()),
                                      "up_median": float(up.median()), "dn_median": float(dn.median())}
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
