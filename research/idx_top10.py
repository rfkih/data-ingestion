#!/usr/bin/env python3
"""IDX — an N-name book (N = 10 or 15), and whether the weights can lean toward the eventual winners (2026-09-12).

PRE-REGISTERED MENU (written before the run; every cell is one trial in the DSR count). Universe, rule and selection are
the production code: blackheart_ingest.idx.candidates.build() for the rows (incl. the 12-1 momentum feature) and
blackheart_ingest.idx.strategies.pick() for "which names, what weights" — the same function the app and the ticket use,
so what is tested here is exactly what the desk would buy.

  family (which names)                                    hypothesis
    rule       composite rank within the light gate        the rank carries information within the list
    strict     the strict-gate composite                    quality screens out the traps (the May-2027 candidate rule)
    value      earnings yield alone within the rule's list  deepest value wins (the quintile ladder, pushed further)
    momentum   12-1 month price momentum within the list    value + momentum: cheap names already recovering
    growth     audited profit growth within the list        earnings momentum: cheap names whose profits are rising
  weighting (within the N, by the family's own order)
    eq        equal
    top5x2    first half 2x the second half
    rank      linear N..1 (18 % down to 1.8 % at N = 10)

  5 x 3 = 15 portfolios x 4 rebalance months (May reported, Feb/Aug/Nov robustness). Trials counted cumulatively with
  the session's earlier menus: 13 (rev.3) + 4 (book size) + 15 per size run (32 at N = 10, 47 with N = 15).

DIAGNOSTIC (not a strategy, N = 10 run only): who were the real winners each year, what did they look like on the day
they were picked, and does any at-selection feature rank-correlate with the forward one-year return inside the list.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_top10.py [10|15]
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

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
N_TRIALS = 17 + 15 * (1 if N == 10 else 2)
OUT = os.path.join(VQ.OUTDIR, f"top{N}_results.json")
FAMILIES = ("rule", "strict", "value", "momentum", "growth")
WEIGHTS = ("eq", "top5x2", "rank")


def forward_return(close: pd.DataFrame, div: pd.DataFrame, code: str, D: pd.Timestamp, end: pd.Timestamp) -> float | None:
    if code not in close.columns:
        return None
    s = close[code].loc[D:end].dropna()
    p0 = close.at[D, code]
    if s.empty or np.isnan(p0) or p0 <= 0:
        return None
    dv = div[(div["code"] == code) & (div["ex"] > D) & (div["ex"] <= end)]["dps"].sum()
    return float(s.iloc[-1] / p0 - 1 + dv / p0)


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    end = close.index[-1]
    results = {"generated": datetime.now(UTC).isoformat(), "size": N, "n_trials": N_TRIALS, "months": {}, "diagnostic": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        rows_at = {D: cand.build(conn, D.date())["all_rows"] for D in rebals}
        table = {}
        for fam in FAMILIES:
            for wsch in WEIGHTS:
                plan = {}
                for D in rebals:
                    picked = ST.pick(fam, rows_at[D], size=N, weight=wsch)
                    plan[D] = {r["code"]: float(r["weight"]) for r in picked if r["selected"]}
                nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True)
                st = VQ.stats(nav, rebals)
                r = list(st.pop("_r"))
                st["dsr"] = round(ES.deflated_sharpe(r, N_TRIALS), 3)
                st["psr"] = round(ES.deflated_sharpe(r, 1), 3)
                st["holdings"] = {str(D.date()): list(plan[D]) for D in rebals}
                table[f"{fam}/{wsch}"] = st
        whole = {D: {r["code"] for r in ST.pick("rule", rows_at[D]) if r["selected"]} for D in rebals}
        nav = VQ.simulate(whole, close, vol, delisted, div, rebals[0], end, True)
        st = VQ.stats(nav, rebals)
        st.pop("_r")
        table["whole_fifth/eq"] = st
        results["months"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}
        print(f"\n=== N = {N}, month {month}: {[str(r.date()) for r in rebals]}   (DSR at N_trials = {N_TRIALS})")
        print(f"{'portfolio':20s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | rebalance-period returns %")
        for k, v in table.items():
            per = " ".join(f"{d[:4]}:{x:+.0f}" for d, x in v["periods"].items())
            print(f"{k:20s} {v['total_pct']:7.1f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v.get('dsr', 0):5.2f} | {per}")
        sys.stdout.flush()

        if month == 5 and N == 10:
            pooled = []
            print("\n--- who carried each year (the rule's list, May): top 3 by forward total return, with at-selection features")
            for i, D in enumerate(rebals):
                e = rebals[i + 1] if i + 1 < len(rebals) else end
                fifth = [r for r in ST.pick("rule", rows_at[D]) if r["selected"]]
                rows = []
                for r in fifth:
                    fr = forward_return(close, div, r["code"], D, e)
                    if fr is None:
                        continue
                    rows.append({"year": D.year, "code": r["code"], "fwd": fr, "rank": r["rank"], "ep": float(r["ep"]),
                                 "mom": float(r["mom"]) if r.get("mom") is not None else None,
                                 "npy": float(r["np_yoy"]) if r.get("np_yoy") is not None else None,
                                 "dy": float(r["dy"] or 0), "roe": float(r["roe"]), "mcap": float(r["mcap"]),
                                 "strict": bool(r["gate_strict"]), "sector": (r.get("sector") or "?")[:22]})
                pooled += rows
                rows.sort(key=lambda x: -x["fwd"])
                med = np.median([x["fwd"] for x in rows])
                print(f"  {D.date()} (n={len(rows)}, median fwd {100*med:+.0f}%):")
                for x in rows[:3]:
                    mom = f"{100*x['mom']:+.0f}%" if x["mom"] is not None else "n/a"
                    npy = f"{100*x['npy']:+.0f}%" if x["npy"] is not None else "n/a"
                    print(f"     {x['code']:5s} fwd {100*x['fwd']:+5.0f}%  rank {x['rank']:2d}  E/P {100*x['ep']:4.1f}%  mom12-1 {mom:>6}  "
                          f"profit yoy {npy:>6}  strict {'yes' if x['strict'] else 'no'}  {x['sector']}")
            df = pd.DataFrame(pooled)
            print(f"\n--- Spearman rank correlation of forward return with each at-selection feature, pooled over {len(df)} (year, name) rows")
            diag = {}
            for f, label in (("rank", "composite rank (1 = cheapest)"), ("ep", "earnings yield"), ("dy", "dividend yield"), ("roe", "ROE"),
                             ("mom", "12-1m momentum"), ("npy", "profit growth yoy"), ("mcap", "market cap")):
                sub = df[["fwd", f]].dropna()
                rho = sub["fwd"].corr(sub[f], method="spearman") if len(sub) > 5 else float("nan")
                per_year = [round(float(g[["fwd", f]].dropna()["fwd"].corr(g[["fwd", f]].dropna()[f], method="spearman")), 2)
                            for _, g in df.groupby("year") if len(g[["fwd", f]].dropna()) > 5]
                diag[f] = {"rho": round(float(rho), 3), "n": int(len(sub)), "per_year": per_year}
                print(f"    {label:30s} rho {rho:+.2f}  (n={len(sub)})  per year {per_year}")
            s_yes, s_no = df[df["strict"]]["fwd"], df[~df["strict"]]["fwd"]
            print(f"    strict-gate pass vs fail: mean fwd {100*s_yes.mean():+.0f}% (n={len(s_yes)}) vs {100*s_no.mean():+.0f}% (n={len(s_no)}); "
                  f"median {100*s_yes.median():+.0f}% vs {100*s_no.median():+.0f}%")
            results["diagnostic"] = {"spearman": diag, "rows": pooled}
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
