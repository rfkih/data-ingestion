#!/usr/bin/env python3
"""IDX — the Buffett question, quantified (2026-09-12, late): durable, high-quality businesses at a fair price, held while
the quality lasts. Is that better than the value rule?

PRE-REGISTERED MENU (written before the run; each cell one trial; cumulative trials this session 56 + 12 = 68).
Universe and pool as in rev. 3: the light-gate liquid pool (audited profit > 0, ROE >= 5 %, traded, Utama/Pengembangan on
the day). Quality inputs are all point-in-time from the audited reports published by the rebalance day's close:
  roe        return on equity, latest audited year
  conv       cash conversion = CFO / net profit, latest audited year (capped at 3)
  lev        leverage = debt / equity (financials sit at the pool median: the gate exempts them too)
  margin     net margin, latest audited year
  min_roe    the lowest ROE across the audited years available on the day (up to three; only one exists in 2021)
Quality score = average ranks of roe + conv + (-lev) + margin + min_roe.

  family        which names                                                          hypothesis
    quality     top fifth by quality score, price ignored                             great businesses win at any price
    qarp        top fifth by rank(quality score) + rank(earnings yield)               great businesses at a fair price
    compounder  min_roe >= 15 %, lev <= 1 (financials exempt), CFO > 0, then the       durable compounding bought cheaply
                cheapest fifth by earnings yield
  holding
    reset       the rule's annual re-weighting
    hold        sell only when the latest audited ROE falls under 10 % or the year is a loss (or the name is no longer
                eligible); everything else is kept whatever its rank; new entrants are bought with the freed cash
  sizes: natural fifth, and ten names

DIAGNOSTIC: Spearman of the quality score (and of ROE alone) with the forward one-year return over the whole pool.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_quality.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import equity_screen as ES  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx.metrics import as_of_close  # noqa: E402

N_TRIALS = 68
OUT = os.path.join(VQ.OUTDIR, "quality_results.json")
FAMILIES = ("quality", "qarp", "compounder")
MODES = ("reset", "hold")
SIZES = (None, 10)


def audited_history(conn, D, codes) -> dict[str, list[dict]]:
    """Per code, the audited rows published by D's close (last four years), oldest first."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT code, period_end, roe, net_margin, cfo, net_profit, der FROM idx.fundamental
             WHERE period_label = 'TAHUNAN' AND published_at <= %s AND period_end >= %s AND code = ANY(%s)
             ORDER BY code, period_end, published_at""", (as_of_close(D.date()), D.date() - timedelta(days=4 * 366), list(codes)))
        rows = cur.fetchall()
    out: dict[str, list[dict]] = {}
    cols = ["code", "period_end", "roe", "net_margin", "cfo", "net_profit", "der"]
    for r in rows:
        d = r if isinstance(r, dict) else dict(zip(cols, r, strict=True))
        lst = out.setdefault(d["code"], [])
        if lst and lst[-1]["period_end"] == d["period_end"]:
            lst[-1] = d                                                  # a restatement replaces the earlier filing
        else:
            lst.append(d)
    return out


def quality_frame(conn, D, rows) -> pd.DataFrame:
    """The light-gate pool with quality inputs and ranks."""
    pool = [r for r in rows if r["gate_loose"] and r["ep"] is not None and r["ep"] > 0 and r.get("tradable", True)]
    hist = audited_history(conn, D, [r["code"] for r in pool])
    recs = []
    for r in pool:
        h = hist.get(r["code"], [])
        if not h:
            continue
        last = h[-1]
        roes = [float(x["roe"]) for x in h[-3:] if x["roe"] is not None]
        np_ = float(last["net_profit"]) if last["net_profit"] is not None else None
        cfo = float(last["cfo"]) if last["cfo"] is not None else None
        conv = min(cfo / np_, 3.0) if (cfo is not None and np_) else np.nan
        recs.append({"code": r["code"], "ep": float(r["ep"]), "roe": float(last["roe"]) if last["roe"] is not None else np.nan,
                     "conv": conv, "lev": float(last["der"]) if last["der"] is not None else np.nan,
                     "margin": float(last["net_margin"]) if last["net_margin"] is not None else np.nan,
                     "min_roe": min(roes) if roes else np.nan, "years": len(roes), "cfo": cfo,
                     "fin": bool(r.get("is_financial")), "sector": r.get("sector")})
    df = pd.DataFrame(recs)
    if df.empty:
        return df
    lev = df["lev"].copy()
    lev[df["fin"]] = np.nan
    lev = lev.fillna(lev.median())
    df["q"] = (df["roe"].rank() + df["conv"].rank() + (-lev).rank() + df["margin"].rank() + df["min_roe"].rank()) / 5
    df["q_rank"] = df["q"].rank(ascending=False, method="first")
    return df


def choose(fam: str, df: pd.DataFrame, size: int | None) -> list[str]:
    if df.empty:
        return []
    if fam == "quality":
        ordered = df.sort_values("q", ascending=False)
    elif fam == "qarp":
        ordered = df.assign(s=df["q"].rank() + df["ep"].rank()).sort_values("s", ascending=False)
    else:
        ok = df[(df["min_roe"] >= 0.15) & ((df["lev"] <= 1.0) | df["fin"] | df["lev"].isna()) & (df["cfo"] > 0)]
        ordered = ok.sort_values("ep", ascending=False)
    n = len(ordered)
    if fam == "compounder":
        k = max(min(10, n), n // 5)                                      # the filter is the selection; take what passes
    else:
        k = max(10, n // 5) if n >= 20 else 0
    if size:
        k = min(k, size) if k else 0
    return list(ordered["code"].head(k))


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    end = close.index[-1]
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "months": {}, "diagnostic": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        frames, still_ok = {}, {}
        for D in rebals:
            rows = cand.build(conn, D.date())["all_rows"]
            frames[D] = quality_frame(conn, D, rows)
            f = frames[D]
            still_ok[D] = set(f[(f["roe"] >= 0.10)]["code"]) if not f.empty else set()
        table = {}
        for fam in FAMILIES:
            for size in SIZES:
                picks = {D: choose(fam, frames[D], size) for D in rebals}
                for mode in MODES:
                    if mode == "reset":
                        plan = {D: set(picks[D]) for D in rebals}
                        nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="reset")
                    else:
                        plan = {D: (lambda held, D=D: (held & still_ok[D]) | set(picks[D])) for D in rebals}
                        nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="drift")
                    st = VQ.stats(nav, rebals)
                    r = list(st.pop("_r"))
                    st["dsr"] = round(ES.deflated_sharpe(r, N_TRIALS), 3)
                    st["psr"] = round(ES.deflated_sharpe(r, 1), 3)
                    st["n"] = [len(picks[D]) for D in rebals]
                    st["holdings"] = {str(D.date()): picks[D] for D in rebals}
                    table[f"{fam}{size or ''}/{mode}"] = st
        results["months"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}
        print(f"\n=== month {month}: {[str(r.date()) for r in rebals]}   (DSR at N_trials = {N_TRIALS})")
        print(f"{'portfolio':20s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | names | rebalance-period returns %")
        for k, v in table.items():
            per = " ".join(f"{d[:4]}:{x:+.0f}" for d, x in v["periods"].items())
            print(f"{k:20s} {v['total_pct']:7.1f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v['dsr']:5.2f} | {v['n']} | {per}")
        sys.stdout.flush()
        if month == 5:
            pooled = []
            for i, D in enumerate(rebals):
                e = rebals[i + 1] if i + 1 < len(rebals) else end
                f = frames[D]
                for _, x in f.iterrows():
                    c = x["code"]
                    if c not in close.columns:
                        continue
                    s = close[c].loc[D:e].dropna()
                    p0 = close.at[D, c]
                    if s.empty or np.isnan(p0) or p0 <= 0:
                        continue
                    pooled.append({"year": D.year, "code": c, "fwd": float(s.iloc[-1] / p0 - 1), "q": x["q"], "roe": x["roe"],
                                   "min_roe": x["min_roe"], "conv": x["conv"], "margin": x["margin"], "ep": x["ep"]})
            dfp = pd.DataFrame(pooled)
            print(f"\n--- does quality on the day predict the forward year? pooled over {len(dfp)} (year, name) rows of the light-gate pool")
            diag = {}
            for f_, label in (("q", "quality score"), ("roe", "ROE"), ("min_roe", "lowest ROE, up to 3 yrs"), ("conv", "cash conversion"),
                              ("margin", "net margin"), ("ep", "earnings yield")):
                sub = dfp[["fwd", f_]].dropna()
                rho = sub["fwd"].corr(sub[f_], method="spearman")
                per_year = [round(float(g[["fwd", f_]].dropna()["fwd"].corr(g[["fwd", f_]].dropna()[f_], method="spearman")), 2)
                            for _, g in dfp.groupby("year") if len(g[["fwd", f_]].dropna()) > 10]
                diag[f_] = {"rho": round(float(rho), 3), "n": int(len(sub)), "per_year": per_year}
                print(f"    {label:26s} rho {rho:+.2f} (n={len(sub)})  per year {per_year}")
            top = dfp[dfp["q"] >= dfp.groupby("year")["q"].transform(lambda s: s.quantile(0.8))]
            bot = dfp[dfp["q"] <= dfp.groupby("year")["q"].transform(lambda s: s.quantile(0.2))]
            print(f"    top quality fifth: mean fwd {100*top['fwd'].mean():+.0f}% median {100*top['fwd'].median():+.0f}% (n={len(top)})  |  "
                  f"bottom fifth: mean {100*bot['fwd'].mean():+.0f}% median {100*bot['fwd'].median():+.0f}% (n={len(bot)})")
            results["diagnostic"] = diag
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
