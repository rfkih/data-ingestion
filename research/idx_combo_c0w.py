#!/usr/bin/env python3
"""IDX menu CB-1 - the C0 radar wide sleeve (with the FL-2 liquidity cap) inside the LIVE combined book (operator 2026-09-27:
"kalau dimasukan ke combo gimana").

Sleeve C0W = every C0 flag (close >= 1.3 x close 60 sessions ago, 250-day high, day return < 18 %) in U1 (20-day value >= Rp 1 bn,
close >= Rp 50, board on the day) with 20-day value < Rp 50 bn (FL-2 #407, the only filter that survived its holdout); one position
per name; entry at the close after the flag; exit at the close after the first close <= 85 % of entry or <= 75 % of the peak.
Trades are generated on the PIT exit cache (research/idx_c0_wide.all_trades) and replayed by date/code inside the combo engine.

ENGINE = the deployed combined book exactly as research/idx_combo_live.py (#386): idx_alloc_frontier.engine, Rp 20 m, cash floor
30 %, gap-fade 10 % / trend 5 % / ML ens4 10 % (stop 5 %), lots, offer/bid, 2022-01 -> 2026-09-16. C0W entries queue after trend
and ML entries on the same day (conservative). The engine shares ONE position cap across sleeves (CR.MAX_POS = 20).

References (not trials): REF = as deployed (cap 20) - must reproduce #386 (48.7 % / 2.15 / -18.0 %); REF40 = REF with cap 40.
PRE-REGISTERED (3 trials; cumulative 1103 + 3 = 1106), all with cap 40:
  K1 ADD       REF + C0W at 1.25 % of NAV per position
  K2 ADD_HALF  REF + C0W at 0.625 %
  K3 REPLACE   gap 10 % / ML 10 % / C0W 1.25 % (the trend sleeve removed)
READING RULE - BETTER only if ALL: Sharpe > max(REF, REF40); CAGR >= REF's; mDD no more than 5 points deeper than REF's; Sharpe in
EACH half (split 2024-05-01) >= REF's; Sharpe ex-2025 >= REF's ex-2025. A BETTER arm is a proposal for the paper book first.
READ-ONLY on the DB except one idx.study row (--no-store to skip).
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
os.environ.setdefault("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
os.environ.setdefault("IDX_EXIT_CACHE", os.path.join(ROOT, "tmp", "exit_cache_pit.pkl"))
os.environ.setdefault("IDX_BOARD_MODE", "pit")
import idx_alloc_frontier as AF  # noqa: E402
import idx_c0_wide as W  # noqa: E402
import idx_combo_live as CL  # noqa: E402
import idx_combo_rupiah as CR  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_ens4_exits as X  # noqa: E402
import idx_ml_stop_sameclose as SC  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
import idx_radar_book as RB  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_trend_c0 as T  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY, N_BEFORE = "combo_c0w", 1103
CAP_C0 = 50e9


def c0w_trades(dates, codes):
    P, unis, comp, Hp, Lp = E.load_all(T.dsn(), T.CACHE, board="pit")
    c_in, _ = S.costs(P)
    pd_ = P["adj"].index
    A, raw = P["adj"].to_numpy(float), P["close"].to_numpy(float)
    arms, vr, c0_entry, u1, tier = RB.masks(P, unis, comp)
    value = P["close"] * P["volume"]
    v20 = value.rolling(20, min_periods=15).mean()
    attn = (v20 / value.rolling(250, min_periods=200).mean()).to_numpy(float)
    flag = c0_entry & u1 & (v20 < CAP_C0).to_numpy(bool)
    t_first = int(np.searchsorted(pd_, np.datetime64(CR.START))) - 2
    tr = W.all_trades(A, raw, c_in, flag, attn, t0=t_first)
    pos = {d: i for i, d in enumerate(dates)}
    cset = set(codes)
    out, miss = [], 0
    for e, j, x, s in tr:
        code, d_in, d_out = P["adj"].columns[j], pd_[e], pd_[x]
        if code not in cset or d_in not in pos or d_out not in pos:
            miss += 1
            continue
        out.append({"strat": "c0w", "code": code, "t_in": pos[d_in], "t_out": pos[d_out], "why": "c0w"})
    M.log(f"C0W: {len(tr)} trades on the PIT panel, {len(out)} mapped into the combo panel, {miss} unmapped")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    dsn = AF.dsn()
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    c_in, c_out = M.costs(raw, offer, bid)
    S_ = g("s5").to_numpy(float)
    e5 = C.ema(S_ - np.nanmedian(np.where(liq, S_, np.nan), axis=1, keepdims=True), X.SPAN)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    tr = CR.trend_trades(dsn, dates)
    gap = CR.gap_events(dsn, dates)
    ml = []
    for i, rule in enumerate(X.ENS4, start=1):
        _, log = SC.book_same(A, liq, e5, X.K, c_in, c_out, X.MARGIN, wait=rule, stop=CL.STOP, t_start=t0)
        ml += [{"strat": f"ML{i}", "code": codes[r.j], "t_in": int(r.t_in), "t_out": int(r.t_out), "why": r.why} for r in log.itertuples()]
    c0w = c0w_trades(dates, codes)
    ml_pct = {f"ML{i}": CL.PCT["ML"] / 4 for i in range(1, 5)}
    arms = {
        "REF": (20, {"gap": CL.PCT["gap"], "trend": CL.PCT["trend"], **ml_pct}, False),
        "REF40": (40, {"gap": CL.PCT["gap"], "trend": CL.PCT["trend"], **ml_pct}, False),
        "K1_ADD": (40, {"gap": CL.PCT["gap"], "trend": CL.PCT["trend"], **ml_pct, "c0w": 0.0125}, True),
        "K2_ADD_HALF": (40, {"gap": CL.PCT["gap"], "trend": CL.PCT["trend"], **ml_pct, "c0w": 0.00625}, True),
        "K3_REPLACE": (40, {"gap": CL.PCT["gap"], "trend": 0.0, **ml_pct, "c0w": 0.0125}, True),
    }
    res = {}
    for name, (cap, pct, use_c0) in arms.items():
        CR.MAX_POS = cap
        lg: dict = {}
        use_tr = [x for x in tr if pct.get("trend", 0) > 0] + (c0w if use_c0 else [])
        full_pct = {"gap": 0.0, "trend": 0.0, "c0w": 0.0, **{k: 0.0 for k in ml_pct}, **pct}
        nav, _ = AF.engine(dates, codes, A, raw, offer, bid, ml, use_tr, gap, full_pct, cash_floor=CL.FLOOR, log=lg)
        Tt = pd.DataFrame(lg.get("trades", []))
        if len(Tt):
            Tt["pnl"] = Tt["proceeds"] - Tt["cost"]
            Tt["hold"] = Tt["t_out"] - Tt["t_in"]
            Tt["sleeve"] = Tt["strat"].map(lambda s: "ML" if s.startswith("ML") else s)
        st = CL.book_stats(nav, lg.get("invested", []))
        ts = CL.trade_stats(Tt) if len(Tt) else {}
        st.pop("nav", None), st.pop("by_month", None)
        res[name] = {**st, "trades": ts.get("trades"), "per_strategy": ts.get("per_strategy")}
        M.log(f"{name:<12} cap {cap} CAGR {st['cagr'] * 100:5.1f} % Sharpe {st['sharpe']:.2f} mDD {st['mdd'] * 100:5.1f} % "
              f"H1/H2 {st['sharpe_h1']:.2f}/{st['sharpe_h2']:.2f} ex-2025 CAGR {st['cagr_ex2025'] * 100:.1f} % Sh {st['sharpe_ex2025']:.2f} "
              f"invested {st['invested_share'] * 100:.0f} % | {{{', '.join(f'{k}: {v:+.1f}' for k, v in ((y, r * 100) for y, r in st['by_year'].items()))}}}")
        if ts.get("per_strategy"):
            M.log("             per sleeve: " + "; ".join(f"{s} n {v['n']} pnl Rp {v['pnl'] / 1e6:+.1f} m avg {v['avg'] * 100:+.1f} %" for s, v in ts["per_strategy"].items()))
    CR.MAX_POS = 20
    ref, ref40 = res["REF"], res["REF40"]
    ver = {}
    for name in ("K1_ADD", "K2_ADD_HALF", "K3_REPLACE"):
        r = res[name]
        chk = dict(sharpe=r["sharpe"] > max(ref["sharpe"], ref40["sharpe"]), cagr=r["cagr"] >= ref["cagr"], mdd=r["mdd"] >= ref["mdd"] - 0.05,
                   halves=r["sharpe_h1"] >= ref["sharpe_h1"] and r["sharpe_h2"] >= ref["sharpe_h2"], ex2025=r["sharpe_ex2025"] >= ref["sharpe_ex2025"])
        ver[name] = dict(checks=chk, better=all(chk.values()))
        M.log(f"{name}: {chk} -> {'BETTER' if all(chk.values()) else 'no'}")
    res["verdicts"] = ver
    json.dump(res, open(os.path.join(HERE, "IDX_COMBO_C0W_2026-09-27.json"), "w"), indent=1, default=str)
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["K1_ADD", "K2_ADD_HALF", "K3_REPLACE"], "n_trials_cumulative": N_BEFORE + 3,
                                  "cap_c0": CAP_C0}, summary=common.plain(res), names=[], report_path="research/IDX_COMBO_C0W_2026-09-27.md")
            conn.commit()
        M.log(f"study #{sid} stored")


if __name__ == "__main__":
    main()
