"""IDX menu 31 - does the allocation layer still help when the equity sleeve is the DESK'S BOOK, not the index?
2026-09-23, operator's open brief ("lakukan apapun yang kamu mau, ini hanya research").

Menu 21 family D tested the allocation layer with IHSG as the equity sleeve (EW3 Sharpe 1.14 vs IHSG 0.53, 2006-26).
But the desk does not hold IHSG - it holds the value book (Sharpe 1.06) and the trend book (Sharpe 1.31). Diversification
pays least when the sleeve it dilutes is already good, so the result does NOT carry over. Untested until now.

S&P 500 is not in the local macro store, so the diversifier here is GOLD IN RUPIAH only (idx.macro 'gold' x 'usdidr',
2005-2026) plus cash at BI - 1.5 pts. That is also the implementable version: gold is available to an Indonesian retail
investor (Antam / Pegadaian / digital); the S&P is not, without an offshore account.

PRE-REGISTERED before the run:
  reference   book5050 = value 50 % + trend 50 %, rebalanced monthly (the ROBUST combination of menu 21 family B)
  BETTER      Sharpe >= reference + 0.15 AND max drawdown no deeper than the reference
  anything else is reported as tested. No weight is tuned after reading the table; the grid is fixed here.
  Window is the overlap, which the value book starts in 2020-05 - about 6.4 years. That is SHORT, and it is the main
  limitation of this menu: family D had 20 years and covered 2008; this cannot.

INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_allocbook.py [--no-store] [--report PATH]
Reads the desk; its only write is the idx.study row 'allocbook' (added 2026-09-26: the 2026-09-23 run #92 was stored by hand).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idx_beyond as B  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402

SWITCH_COST = 0.003
GRID = [("book5050 (REF)", 1.00), ("book90/gold10", 0.90), ("book80/gold20", 0.80),
        ("book70/gold30", 0.70), ("book60/gold40", 0.60), ("book50/gold50", 0.50)]


def monthly(daily: pd.Series) -> pd.Series:
    return (1 + daily).resample("ME").prod() - 1


def stats(m: pd.Series, label: str) -> dict:
    m = m.dropna()
    if len(m) < 24:
        return {}
    yrs = len(m) / 12
    tot = float((1 + m).prod())
    cagr = tot ** (1 / yrs) - 1
    vol = float(m.std() * np.sqrt(12))
    sharpe = float(m.mean() * 12 / vol) if vol > 0 else 0.0
    eq = (1 + m).cumprod()
    mdd = float((eq / eq.cummax() - 1).min())
    by_year = {str(y)[2:]: f"{(1 + g).prod() - 1:+.0%}" for y, g in m.groupby(m.index.year)}
    return {"label": label, "cagr": cagr, "vol": vol, "sharpe": sharpe, "mdd": mdd, "n": len(m), "years": by_year}


def rebalanced(parts: dict[str, pd.Series], weights: dict[str, float]) -> pd.Series:
    """Fixed-weight monthly rebalance with a switch cost on the drift that has to be traded back."""
    idx = None
    for k in weights:
        idx = parts[k].index if idx is None else idx.intersection(parts[k].index)
    out = []
    for t in idx:
        r = sum(weights[k] * parts[k].loc[t] for k in weights)
        drift = sum(abs(weights[k] * (1 + parts[k].loc[t]) / (1 + r) - weights[k]) for k in weights) / 2 if r > -1 else 0
        out.append(r - SWITCH_COST * drift)
    return pd.Series(out, index=idx)


N_TRIALS_CUMULATIVE = 585            # menu 31: 6 arms, cumulative as stored on #92


def summarize(rows, halves, idx) -> tuple[dict, str]:
    """The stored summary, with #92's keys (of, better, ref, gold30, halves, status, operator) plus every arm and the IHSG row."""
    by = {st["label"]: st for st in rows if st}
    ref = by["book5050 (REF)"]
    arms = [k for k in by if k.startswith("book") and k != "book5050 (REF)"] + ["EW3 v/t/gold"]
    r = lambda st: {"mdd": round(st["mdd"], 3), "cagr": round(st["cagr"], 3), "sharpe": round(st["sharpe"], 2)}  # noqa: E731
    sh_ok = [k for k in arms if by[k]["sharpe"] >= ref["sharpe"] + 0.15]
    dd_ok = [k for k in arms if by[k]["mdd"] >= ref["mdd"]]
    better = [k for k in sh_ok if k in dd_ok]
    miss = sorted((ref["mdd"] - by[k]["mdd"]) * 100 for k in sh_ok if k not in dd_ok)
    h1, h2 = halves
    status = ("BETTER: " + ", ".join(better) if better else
              f"PARTIAL: Sharpe bar cleared by {len(sh_ok)} of {len(arms)} arms"
              + (f", drawdown bar missed by {miss[0]:.1f}-{miss[-1]:.1f}pt" if miss else "")
              + f"; Sharpe gain in H1 {sum(1 for k in h1 if k != 'book5050 (REF)' and h1[k]['sharpe'] > h1['book5050 (REF)']['sharpe'])}"
              f"/5 and H2 {sum(1 for k in h2 if k != 'book5050 (REF)' and h2[k]['sharpe'] > h2['book5050 (REF)']['sharpe'])}/5 gold arms"
              if sh_ok else "tested: no arm clears the Sharpe bar")
    summary = {"of": len(arms), "better": len(better), "ref": r(ref), "gold30": r(by["book70/gold30"]),
               "halves": {"H1_gold_flat": {"ref_mdd": round(h1["book5050 (REF)"]["mdd"], 3), "gold40_mdd": round(h1["book60/gold40"]["mdd"], 3),
                                           "ref_sharpe": round(h1["book5050 (REF)"]["sharpe"], 2),
                                           "gold40_sharpe": round(h1["book60/gold40"]["sharpe"], 2)},
                          "H2_gold_boom": {"ref_sharpe": round(h2["book5050 (REF)"]["sharpe"], 2),
                                           "gold50_sharpe": round(h2["book50/gold50"]["sharpe"], 2)}},
               "status": status, "operator": "parked - equities only",
               "arms": {k: r(v) for k, v in by.items()}, "ihsg": r(by["IHSG"]) if "IHSG" in by else None,
               "window": f"{idx[0]:%Y-%m}..{idx[-1]:%Y-%m}", "months": len(idx)}
    note = (f"{len(better)}/{len(arms)} by the letter; book70/gold30 Sharpe {by['book70/gold30']['sharpe']:.2f} vs ref "
            f"{ref['sharpe']:.2f}, mDD {by['book70/gold30']['mdd']:.1%} vs {ref['mdd']:.1%}; parked by the operator (no gold)")
    return summary, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--report", default=None, help="report_path recorded on the study row (e.g. this run's log)")
    args = ap.parse_args()
    dsn = os.environ["INGEST_DB_DSN"]
    print("loading value book NAV (this regenerates the screen per rebalance) ...", flush=True)
    nav_v = B.value_nav(dsn)
    nav_v.index = pd.to_datetime(nav_v.index)
    v_m = monthly(nav_v.pct_change().dropna())

    print("running the trend book ...", flush=True)
    P, unis, comp, Hp, Lp, sectors, brent = B.load_all(dsn, os.environ.get("IDX_BEYOND_CACHE"))
    c_in, c_out = S.costs(P)
    A, H, L, entry, score, ATR, SIG, trail10, universes = B.prep_panels(P, unis, Hp, Lp)
    Rt, trt, _ = E.run_book(A, H, L, c_in, c_out, entry, score, trail10, universes["small"])
    Rt.index = pd.to_datetime(P["adj"].index)
    t_m = monthly(Rt)

    with psycopg.connect(dsn) as conn:
        m = pd.read_sql("SELECT series, obs_date, value FROM idx.macro WHERE series IN ('gold','usdidr','bi_rate_hist','bi_rate') ORDER BY 2", conn)
    m["obs_date"] = pd.to_datetime(m["obs_date"])
    gold = m[m.series == "gold"].set_index("obs_date")["value"].astype(float)
    fx = m[m.series == "usdidr"].set_index("obs_date")["value"].astype(float)
    g_idr = (gold.resample("ME").last() * fx.resample("ME").last()).dropna()
    g_m = g_idr.pct_change().dropna()

    jk = pd.read_csv(os.path.join(B.YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    i_m = jk.resample("ME").last().pct_change().dropna()

    idx = v_m.index.intersection(t_m.index).intersection(g_m.index)
    v_m, t_m, g_m = v_m.reindex(idx), t_m.reindex(idx), g_m.reindex(idx)
    i_m2 = i_m.reindex(idx)
    print(f"\noverlap {idx[0]:%Y-%m} .. {idx[-1]:%Y-%m}  ({len(idx)} months, {len(idx)/12:.1f} years)\n")

    parts = {"v": v_m, "t": t_m, "g": g_m}
    rows = [stats(v_m, "value only"), stats(t_m, "trend only"), stats(i_m2, "IHSG"), stats(g_m, "gold IDR only")]
    ref = None
    for label, w_book in GRID:
        w = {"v": w_book / 2, "t": w_book / 2, "g": 1 - w_book}
        w = {k: x for k, x in w.items() if x > 0}
        st = stats(rebalanced(parts, w), label)
        if ref is None:
            ref = st
        rows.append(st)
    rows.append(stats(rebalanced(parts, {"v": 1/3, "t": 1/3, "g": 1/3}), "EW3 v/t/gold"))

    print(f"{'arm':22} {'CAGR':>8} {'vol':>6} {'Sharpe':>7} {'mDD':>7}   verdict")
    for st in rows:
        if not st:
            continue
        v = ""
        if ref and st["label"] not in ("value only", "trend only", "IHSG", "gold IDR only"):
            v = "BETTER" if (st["sharpe"] >= ref["sharpe"] + 0.15 and st["mdd"] >= ref["mdd"]) else "tested"
        print(f"{st['label']:22} {st['cagr']*100:>7.1f}% {st['vol']*100:>5.0f}% {st['sharpe']:>7.2f} {st['mdd']*100:>6.1f}%   {v}")

    print("")
    print("=== robustness: the same grid in each half (diversification, or gold's run?) ===")
    half = idx[len(idx) // 2]
    halves = ({}, {})
    for hi, (name, sl) in enumerate((("H1 " + f"{idx[0]:%Y-%m}..{half:%Y-%m}", idx[:len(idx)//2]),
                                     ("H2 " + f"{half:%Y-%m}..{idx[-1]:%Y-%m}", idx[len(idx)//2:]))):
        p2 = {k: v.reindex(sl) for k, v in parts.items()}
        g_st = stats(parts["g"].reindex(sl), "gold")
        print("")
        print(f"  {name}   [gold alone: sharpe={g_st['sharpe']:.2f} cagr={g_st['cagr']*100:+.1f}%]")
        for label, w_book in GRID:
            w = {"v": w_book/2, "t": w_book/2, "g": 1-w_book}
            w = {k: x for k, x in w.items() if x > 0}
            st = stats(rebalanced(p2, w), label)
            if st:
                halves[hi][label] = st
                print(f"    {label.split()[0]:16} sharpe={st['sharpe']:5.2f} mdd={st['mdd']*100:6.1f}% cagr={st['cagr']*100:+6.1f}%")
    print()
    for st in rows:
        if st and st["label"] in ("value only", "trend only", "book5050 (REF)", "book70/gold30", "EW3 v/t/gold", "IHSG"):
            print(f"  {st['label']:16} " + " ".join(f"{y}:{r}" for y, r in st["years"].items()))

    summary, note = summarize(rows, halves, idx)
    print("\n" + note + "\n" + summary["status"])
    if not args.no_store:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blackheart-ingest", "src"))
        from blackheart_ingest.idx import research_store as rs
        params = {"bar": "Sharpe >= ref+0.15 AND mdd no deeper (ref = value50/trend50)", "menu": 31,
                  "trials": [g[0] for g in GRID[1:]] + ["EW3 value/trend/gold", "reference book50/50"],
                  "window": f"{summary['window']} ({summary['months']} months)", "rebalance": "monthly, 0.30% switch cost",
                  "diversifier": "gold IDR (idx.macro gold x usdidr) + cash BI-1.5", "n_trials_cumulative": N_TRIALS_CUMULATIVE}
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "allocbook", date(2026, 9, 23), params=params, summary=summary, names=[],
                                  report_path=args.report, note=note)
        print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
