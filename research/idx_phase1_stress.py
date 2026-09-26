#!/usr/bin/env python3
"""Phase 1, item 3 - the combined book under crashes its 2022-26 backtest never saw (operator 2026-09-26: "oke jalankan fase 1").

The #348 backtest's worst drawdown is -17.1 %, but 2022-26 contains no 2020-type crash. Question: on every day of the backtest,
if a historical crash had started with the book AS IT WAS HELD that day, what would it have lost?

Declared before any result was seen (2026-09-26):
  BOOK   the deployed configuration's trade list (#348 combined, research-scratch/combo_live_combined.csv) and its NAV path.
         Holdings on day d = the overnight trades open at d's close (gap-fade is intraday: flat overnight, not stressed), market
         value = cost x adjusted close(d) / adjusted close(entry). Cash earns 0.
  SCENARIOS (idx/risk.py conventions: each name's OWN adjusted return over the window; not listed then -> beta x COMPOSITE,
         beta vs COMPOSITE over 2022-26, flagged):
         covid    COMPOSITE peak -> trough with the trough in 2020-01..2020-04
         y2025    the 2025 drawdown
         worst5   the worst 5-session COMPOSITE move in the data
         shock10  COMPOSITE -10 % through each beta
         arb2     every held name closes at the lower auto-rejection limit two sessions running, ASSUMED 15 % a day
                  (-27.75 %): the "cannot get out" case - no exit is possible, so the stop does not help.
  READ   per scenario the distribution over days of the stressed loss (% of that day's NAV): median, 95th percentile, worst
         and its date. Compared with the planning drawdown (-20..-25 % normal, -30 % review trigger).
READ-ONLY; one idx.study row (phase1_stress, kind audit, no trial).
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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx import risk  # noqa: E402

STUDY = "phase1_stress"
TRADES = os.path.join(ROOT, "research-scratch", "combo_live_combined.csv")
ARB = 0.15
PLAN = {"normal": -0.25, "review": -0.30}


def main() -> int:
    store = "--no-store" not in sys.argv
    dsn = AF.dsn()
    T = pd.read_csv(TRADES, parse_dates=["d_in", "d_out"])
    T = T[T["sleeve"] != "gap"].copy()
    with psycopg.connect(dsn) as conn:
        summ = conn.execute("SELECT summary FROM idx.study WHERE id = 348").fetchone()[0]
        summ = json.loads(summ) if isinstance(summ, str) else summ
        codes = sorted(T["code"].unique())
        px = pd.read_sql("SELECT code, trade_date, close * adj_factor AS c FROM idx.bar WHERE source = 'idx' AND code = ANY(%s) AND trade_date >= '2019-06-01'",
                         conn, params=(codes,))
        comp = pd.read_sql("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' ORDER BY trade_date", conn)
    nav = pd.Series({pd.Timestamp(d): v for d, v in summ["combined"]["nav"]}).sort_index()
    P = px.pivot(index="trade_date", columns="code", values="c").astype(float)
    P.index = pd.to_datetime(P.index)
    comp = comp.set_index(pd.to_datetime(comp["trade_date"]))["close"].astype(float)
    r_all, cr = P.pct_change(), comp.pct_change()
    w = (r_all.index >= "2022-01-01")
    betas = pd.Series({c: risk.beta_of(r_all.loc[w, c].dropna(), cr) for c in P.columns})
    wins = {"covid": risk.drawdown_episode(comp, date(2020, 1, 1), date(2020, 4, 30)),
            "y2025": risk.drawdown_episode(comp, date(2025, 1, 1), date(2025, 12, 31)),
            "worst5": risk.worst_move(comp, 5)}
    print({k: (str(v["start"]), str(v["end"]), round(v["composite"], 3)) for k, v in wins.items()})
    Pf = P.ffill()
    rows = []
    for d in nav.index:
        open_ = T[(T["d_in"] <= d) & (T["d_out"] > d)]
        if not len(open_):
            rows.append({"d": d, "invested": 0.0, **{k: 0.0 for k in (*wins, "shock10", "arb2")}, "proxied": 0})
            continue
        vals = {}
        for x in open_.itertuples():
            a, b = Pf[x.code].asof(x.d_in), Pf[x.code].asof(d)
            vals[x.code] = vals.get(x.code, 0.0) + float(x.cost) * (b / a if a and a > 0 and pd.notna(b) else 1.0)
        v = pd.Series(vals)
        n = float(nav[d])
        out = {"d": d, "invested": float(v.sum() / n), "proxied": 0}
        for k, win in wins.items():
            rp = risk.replay(v, P, win, betas)
            out[k] = rp["pnl"] / n
            out["proxied"] = max(out["proxied"], len(rp["proxied"]))
        out["shock10"] = float(sum(val * (betas.get(c, 1.0) if pd.notna(betas.get(c)) else 1.0) * -0.10 for c, val in v.items()) / n)
        out["arb2"] = float(v.sum() * ((1 - ARB) ** 2 - 1) / n)
        rows.append(out)
    D = pd.DataFrame(rows).set_index("d")
    res = {"windows": {k: {kk: str(vv) if kk != "composite" else vv for kk, vv in v.items()} for k, v in wins.items()},
           "invested": {"median": float(D["invested"].median()), "max": float(D["invested"].max())}, "scenarios": {}}
    L = [f"# Phase 1 - the combined book under crashes it never saw - {date.today()}", "",
         "Deployed configuration (#348 trade list), overnight holdings on each backtest day, each name's own return over the window",
         "(beta x COMPOSITE when it was not listed). Loss as % of that day's NAV. Audit, no trial.", "",
         f"Invested share (overnight): median {res['invested']['median'] * 100:.0f} %, max {res['invested']['max'] * 100:.0f} % (cash floor 30 % caps new buys at 70 %).", "",
         "| scenario | window | COMPOSITE | median day | 95th pct day | worst day | worst date | days past -25 % | past -30 % |",
         "|---|---|---|---|---|---|---|---|---|"]
    for k in (*wins, "shock10", "arb2"):
        s = D[k]
        wd = s.idxmin()
        res["scenarios"][k] = {"median": float(s.median()), "p05": float(s.quantile(0.05)), "worst": float(s.min()), "worst_date": str(wd.date()),
                               "share_past_25": float((s <= PLAN["normal"]).mean()), "share_past_30": float((s <= PLAN["review"]).mean())}
        win = wins.get(k)
        wtxt = f"{win['start']} -> {win['end']}" if win else ("-10 % x beta" if k == "shock10" else f"2 x -{ARB * 100:.0f} % (assumed ARB)")
        ctxt = f"{win['composite'] * 100:.1f} %" if win else "-"
        r = res["scenarios"][k]
        L.append(f"| {k} | {wtxt} | {ctxt} | {r['median'] * 100:.1f} % | {r['p05'] * 100:.1f} % | {r['worst'] * 100:.1f} % | {r['worst_date']} | "
                 f"{r['share_past_25'] * 100:.0f} % | {r['share_past_30'] * 100:.0f} % |")
    L += ["", "Limits: holdings are replayed as a block with no exits during the window (the trail-10 and the ML stop would cut part",
          "of a slow fall, nothing of a gap-down); 2020 names that were not listed move by beta x COMPOSITE, which understates a small",
          f"cap's own fall; the ARB level is an assumption ({ARB * 100:.0f} %/day)."]
    text = "\n".join(L)
    print(text)
    out = os.path.join(HERE, f"IDX_PHASE1_STRESS_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": [], "kind": "audit", "arb": ARB, "sources": [348]},
                                  summary=res, names=[], report_path=out, note="Phase 1 stress replay of the deployed combo holdings; no trial")
            conn.commit()
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
