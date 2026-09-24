#!/usr/bin/env python3
"""IDX menu 29e — the three knobs the flaw analysis pointed at (operator, 2026-09-23: "berapa improvement profit atau
drawdown nya?").

The flaw list gave three things worth testing rather than accepting: the profit sits in a handful of trades (more, smaller
trades would spread it), 6 % of events close locked at ARB with no way out (the open's distance from the floor may warn),
and on a crash day eighty names qualify for five slots (which five has never been tested).

PRE-REGISTERED (declared before the run; nothing tuned afterwards). 8 trials (cumulative 558 + 8 = 566).
  Population  the clean one: IDX-sourced opens only, 2023-2026, main board, v60 >= Rp 5 bn, previous close >= Rp 50,
              not locked, no corporate action or dividend ex-date, gap not deeper than the auto-rejection band.
  Deployed    gap <= -7 %, K = 5 slots, deepest gap first, buy open + 1 tick, sell close - 1 tick, 0.10 / 0.20 %.
  A. room     the deployed rule plus "the open must sit at least 8 % above the day's ARB floor". 1 trial.
              (Today's quartiles suggested it; they were post-hoc, so this is the declared test, and the bar below is
              what decides - not the quartile table.)
  B. size     thresholds -5 %, -7 %, -10 % x K = 5, 10. 6 trials, of which -7 %/K5 is the deployed reference.
  C. pick     at the deployed threshold, choose the most liquid instead of the deepest when there are more candidates
              than slots. 1 trial.
  Reads       events, capital actually deployed, mean per trade, sleeve total / CAGR / Sharpe / max drawdown, and the
              share of events that closed at ARB.
  Bar         BETTER than deployed requires ALL of: Sharpe >= deployed + 0.3, max drawdown no deeper than deployed,
              total return >= deployed. A risk rule may also be adopted on drawdown alone if it cuts the maximum
              drawdown by >= 3 points while giving up no more than 10 % of the total return.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_gapfade_tune.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_daytrade as D  # noqa: E402

ROOM = 0.08
N_TRIALS_BEFORE = 558


def population(dsn: str) -> pd.DataFrame:
    """Every event the rule could ever see, before the threshold and the slot limit: one row per gap-down name-day."""
    with psycopg.connect(dsn) as conn:
        bars = D.load(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT code, ex_date FROM idx.corporate_action")
            ca = {(r["code"], r["ex_date"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()}
            cur.execute("SELECT code, ex_date FROM idx.dividend")
            ca |= {(r["code"], r["ex_date"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()}
    b = bars[(bars["open_src"] == "idx") & bars["open"].notna() & bars["close"].notna() & bars["main"]].copy()
    b = b.sort_values(["code", "trade_date"])
    b["prev"] = b.groupby("code")["close"].shift(1)
    b["v60_prev"] = b.groupby("code")["v60"].shift(1)
    b["gap"] = b["open"] / b["prev"] - 1
    locked = (b["open"] == b["high"]) & (b["high"] == b["low"])
    ev = b[(b["prev"] >= 50) & (b["v60_prev"] >= 5e9) & ~locked & b["gap"].notna()].copy()
    ev = ev[np.array([(c, t) not in ca for c, t in zip(ev["code"], ev["trade_date"], strict=True)])]
    band = np.select([ev["prev"] <= 200, ev["prev"] <= 5000], [0.35, 0.25], 0.20)
    ev["arb"] = np.maximum(ev["prev"] * (1 - band), 50)
    ev["room"] = ev["open"] / ev["arb"] - 1
    ev = ev[ev["gap"] >= -band]
    o, c = ev["open"].to_numpy(dtype=float), ev["close"].to_numpy(dtype=float)
    ev["r"] = ((c - D.tick(c)) * (1 - D.FEE_SELL)) / ((o + D.tick(o)) * (1 + D.FEE_BUY)) - 1
    ev["at_arb"] = c <= ev["arb"].to_numpy() * 1.005
    ev["date"] = pd.to_datetime(ev["trade_date"])
    return ev.reset_index(drop=True)


def arm(ev: pd.DataFrame, gap: float, k: int, pick: str = "deepest", room: float | None = None) -> dict:
    x = ev[ev["gap"] <= gap]
    if room is not None:
        x = x[x["room"] >= room]
    key = "gap" if pick == "deepest" else "v60_prev"
    asc = pick == "deepest"
    x = x.sort_values(["date", key], ascending=[True, asc]).groupby("date").head(k)
    if len(x) < 20:
        return {"events": len(x), "verdict": "too few"}
    day = x.groupby("date")["r"].mean()
    n = x.groupby("date").size().clip(upper=k)
    sleeve = (day * (n / k)).sort_index()
    eq = (1 + sleeve).cumprod()
    years = (x["date"].max() - x["date"].min()).days / 365.25
    bdays = len(pd.bdate_range(x["date"].min(), x["date"].max()))
    return {"events": len(x), "active_days": len(day), "capital_pct": float((n / k).sum() / bdays * 100),
            "mean_bps": float(x["r"].mean() * 1e4), "median_bps": float(np.median(x["r"]) * 1e4),
            "hit": float((x["r"] > 0).mean()), "at_arb_pct": float(x["at_arb"].mean() * 100),
            "total_pct": float((eq.iloc[-1] - 1) * 100), "cagr_pct": float((eq.iloc[-1] ** (1 / years) - 1) * 100),
            "sharpe": float(sleeve.mean() / sleeve.std(ddof=1) * np.sqrt(252)) if sleeve.std(ddof=1) > 0 else float("nan"),
            "mdd_pct": float((eq / eq.cummax() - 1).min() * 100), "worst_trade_pct": float(x["r"].min() * 100)}


def run(dsn: str, out: str, store: bool, study_name: str) -> dict:
    ev = population(dsn)
    res: dict = {"arms": {}, "population": {"events": len(ev), "start": str(ev["date"].min().date()), "end": str(ev["date"].max().date())}}
    base = arm(ev, -0.07, 5)
    res["arms"]["deployed: -7 %, K=5, deepest"] = base
    res["arms"][f"A. room >= {ROOM:.0%} above ARB"] = arm(ev, -0.07, 5, room=ROOM)
    for g in (-0.05, -0.07, -0.10):
        for k in (5, 10):
            if (g, k) == (-0.07, 5):
                continue
            res["arms"][f"B. gap {g*100:.0f} %, K={k}"] = arm(ev, g, k)
    res["arms"]["C. most liquid first"] = arm(ev, -0.07, 5, pick="liquid")
    for name, a in res["arms"].items():
        if "sharpe" not in a or name.startswith("deployed"):
            continue
        better = a["sharpe"] >= base["sharpe"] + 0.3 and a["mdd_pct"] >= base["mdd_pct"] and a["total_pct"] >= base["total_pct"]
        risk = (a["mdd_pct"] - base["mdd_pct"]) >= 3 and a["total_pct"] >= base["total_pct"] * 0.9
        a["verdict"] = "BETTER" if better else ("risk rule" if risk else "no")
    res["verdict"] = [k for k, v in res["arms"].items() if v.get("verdict") in ("BETTER", "risk rule")]
    write(res, out)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            res["study_id"] = rs.record_study(conn, study_name, date.fromisoformat(res["population"]["end"]),
                                              params={"trials": list(res["arms"]), "n_trials_cumulative": N_TRIALS_BEFORE + 8, "room": ROOM},
                                              summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out,
                                              note=f"{len(res['verdict'])} of 8 pass: {res['verdict'] or 'none'}")
    return res


def write(res: dict, path: str) -> None:
    p = res["population"]
    L = [f"# IDX menu 29e — threshold, slots, selection and the ARB floor — {p['start']} -> {p['end']}", "",
         f"IDX-sourced opens only, {p['events']} gap-down name-days before any threshold. Pre-registered in",
         "`research/idx_gapfade_tune.py`; 8 trials (cumulative 566). The deployed rule is the reference row.", "",
         "| arm | events | capital | mean | median | hit | closed at ARB | total | CAGR | Sharpe | max DD | worst trade | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, a in res["arms"].items():
        if "sharpe" not in a:
            L.append(f"| {k} | {a['events']} | | | | | | | | | | | {a.get('verdict', 'too few')} |")
            continue
        L.append(f"| {k} | {a['events']} | {a['capital_pct']:.1f} % | **{a['mean_bps']:+.0f}** | {a['median_bps']:+.0f} | "
                 f"{a['hit']*100:.0f} % | {a['at_arb_pct']:.1f} % | {a['total_pct']:+.0f} % | {a['cagr_pct']:+.0f} % | "
                 f"{a['sharpe']:.2f} | {a['mdd_pct']:.1f} % | {a['worst_trade_pct']:.0f} % | {a.get('verdict', 'reference')} |")
    L += ["", "## Reading", "", f"- Passing the bar: {', '.join(res['verdict']) or 'none'}.",
          "- BETTER needs Sharpe >= deployed + 0.3, no deeper drawdown and no less total return; a risk rule needs a",
          "  drawdown at least 3 points shallower for no more than a tenth of the return.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="gapfade_tune")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_GAPFADE_TUNE_{date.today().isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], out, not a.no_store, a.study_name)
    print(json.dumps({"verdict": res["verdict"], "arms": {k: {x: v.get(x) for x in ("events", "capital_pct", "mean_bps", "total_pct", "cagr_pct", "sharpe", "mdd_pct", "at_arb_pct", "verdict")}
                                                          for k, v in res["arms"].items()}, "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
