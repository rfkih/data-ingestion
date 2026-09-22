#!/usr/bin/env python3
"""IDX menu 20 — "buy at support, sell at resistance" (operator, 2026-09-22). The textbook range trade, run through the same
book engine, costs and reading rule as the trend and exit menus, so it can be compared with what the desk already runs.

PRE-REGISTERED (4 trials; cumulative 406 + 4 = 410). Declared before the run; nothing tuned afterwards.
  Support / resistance: the 60-day low / high of adjusted closes (the same window the trend rule uses for its breakout).
  Entry ("buy at support"): close within 2 % of the 60-day low AND the day closed up (a bounce, so the knife has at least
    paused), name inside the universe; ranked by 60-day traded value (most liquid first). Buy close t+1 at the closing offer.
  Exits:
    res60   sell when the close reaches the 60-day high that stood at entry (resistance); stop when the close is 7 % below
            the entry (support broke). Whichever first.
    trail10 the deployed trailing stop (10 % off the peak close) - to show whether the entry or the exit carries the result.
  Universes: BLUE (>= Rp 20 bn/day, >= Rp 1,000 - where ranges are cleanest) and LIQ (>= Rp 5 bn/day).
  Book: K = 10 slots of 1/K, one position per name, Stockbit fees 0.10/0.20 % plus the closing spread; 2020-01 -> 2026-09-21.
  References (not trials): random entries with the same exit and universe; the trend rule (hi60|trail10) on the same universe.
READING RULE (the desk's money rule): CANDIDATE only if ALL hold: >= 150 closed trades; avg net > 0 with t >= 2.5; Sharpe
  >= 1.0; max drawdown <= 25 %; >= 5 of 7 calendar years positive; Sharpe >= random + same exit + 0.5.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_support.py
"""
from __future__ import annotations

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
import idx_exit as E  # noqa: E402
import idx_ml_trend as ML  # noqa: E402
import idx_swing2 as S  # noqa: E402

N_BEFORE = 406
UNIS = ["BLUE", "LIQ"]
EXITS = ["res60", "trail10"]
ARMS = [f"sup60|{x}|{u}" for u in UNIS for x in EXITS]
SEED = 20260922


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    P, unis, comp, H, L, listing, fund, ev = ML.load_all(dsn, os.environ.get("IDX_ML_CACHE"))
    c_in, c_out = S.costs(P)
    adj, vol = P["adj"], P["volume"]
    dates = adj.index
    A = adj.to_numpy(float)
    Hn, Ln = H.to_numpy(float), L.to_numpy(float)
    lo60 = adj.rolling(60, min_periods=60).min()
    hi60 = adj.rolling(60, min_periods=60).max()
    HI60 = hi60.shift(1).to_numpy(float)                       # the resistance that stood before the entry day
    up = adj > adj.shift(1)
    entry = ((adj <= 1.02 * lo60) & up).to_numpy(bool)
    score = P["v60"].to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    trend_entry = ((adj >= hi60) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool)
    z = np.zeros_like(A)
    rules = E.make_rules(A, Hn, Ln, z, z, z, z, z, z)
    trail10 = rules["trail10"]

    def res60(t, j, p):
        r = p["state"].get("res")
        if r is None:
            r = HI60[p["e"], j]
            r = p["a0"] * 1.15 if (np.isnan(r) or r <= p["a0"]) else r
            p["state"]["res"] = r
        if A[t, j] >= r:
            return 1.0
        if A[t, j] <= 0.93 * p["a0"]:
            return 1.0
        return 0

    exits = {"res60": res60, "trail10": trail10}
    n_trials = N_BEFORE + len(ARMS)
    res, rnd, trend = {}, {}, {}
    for u in UNIS:
        uni = unis[u].to_numpy(bool)
        R, tr, _ = E.run_book(A, Hn, Ln, c_in, c_out, trend_entry, vr.to_numpy(float), trail10, uni)
        trend[u] = E.stats(R, tr, dates, n_trials)
        for x in EXITS:
            arm = f"sup60|{x}|{u}"
            R, tr, open_ = E.run_book(A, Hn, Ln, c_in, c_out, entry, score, exits[x], uni)
            s = E.stats(R, tr, dates, n_trials)
            s["open"] = len(open_)
            res[arm] = s
            R, tr, _ = E.run_book(A, Hn, Ln, c_in, c_out, None, None, exits[x], uni, rng=np.random.default_rng(SEED))
            rnd[arm] = E.stats(R, tr, dates, n_trials)
            print(f"{arm:20s} n={s['n']:4d} hold={s['hold']:4.0f} hit={s['hit'] * 100:3.0f}% net={s['avg_net'] * 100:+5.2f}% t={s['tstat']:4.1f} "
                  f"cagr={s['cagr'] * 100:+5.1f}% sharpe={s['sharpe']:4.2f} mdd={s['mdd'] * 100:4.0f}% | rnd sharpe {rnd[arm]['sharpe']:.2f}", flush=True)
    verdict = {}
    for arm in ARMS:
        s, rn = res[arm], rnd[arm]
        why = []
        if s["n"] < 150:
            why.append("n<150")
        if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
            why.append("t<2.5")
        if s["sharpe"] < 1.0:
            why.append("sharpe<1")
        if s["mdd"] < -0.25:
            why.append("mdd>25%")
        if sum(1 for v in s["years"].values() if v > 0) < 5:
            why.append("years<5/7")
        if s["sharpe"] < rn["sharpe"] + 0.5:
            why.append("vs random")
        verdict[arm] = "CANDIDATE" if not why else "tested: " + ",".join(why)

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, s, v):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | "
                f"{s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {v} |")
    lines = [f"# IDX menu 20 — buy at support, sell at resistance — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             "Entry: close within 2 % of the 60-day low on an up day, ranked by liquidity; buy close t+1 @offer. res60 = sell at the 60-day high that stood at "
             "entry or stop 7 % below entry; trail10 = deployed trailing stop. K = 10, fees 0.10/0.20 % + closing spread, 2020-01 -> 2026-09-21.", "",
             "| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for u in UNIS:
        for x in EXITS:
            arm = f"sup60|{x}|{u}"
            lines.append(row(arm, res[arm], verdict[arm]))
            lines.append(row(f"random|{x}|{u}", rnd[arm], "reference"))
        lines.append(row(f"trend hi60|trail10|{u}", trend[u], "reference (the deployed idea, opposite entry)"))
    n_c = sum(1 for v in verdict.values() if v == "CANDIDATE")
    lines += ["", f"Reading rule applied as declared: {n_c} candidate(s) of {len(ARMS)}."]
    text = "\n".join(lines)
    print(text)
    out = os.path.join(HERE, f"IDX_SUPPORT_{date.today().isoformat()}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"wrote {out}")
    if "--no-store" not in sys.argv:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "support_resistance", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "K": 10, "seed": SEED},
                                  summary=json.loads(json.dumps({"results": res, "random": rnd, "trend": trend, "verdicts": verdict}, default=str)),
                                  names=[], report_path=out, note=f"{n_c} candidates of {len(ARMS)}")
            print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
