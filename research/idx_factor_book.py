#!/usr/bin/env python3
"""IDX — a factor book from the literature (2026-09-13). The operator asked for a strategy built on quantitative
theory rather than on menus of ideas. Four documented premia and two documented risk rules, stacked so each brick's
contribution is visible:

    value        earnings, book and dividend yields (Fama-French; the desk's composite)
    momentum     12-1 month return (Jegadeesh-Titman; Asness-Moskowitz-Pedersen: value and momentum together)
    quality      ROE, cash conversion, low leverage (Asness-Frazzini-Pedersen, Quality Minus Junk)
    low vol      the inverse of 60-day realised volatility (Frazzini-Pedersen, Betting Against Beta)
    vol target   exposure = min(1, 15 % / realised portfolio volatility), monthly (Moreira-Muir)
    TSMOM        cash while the index's 12-month return is negative, monthly (Moskowitz-Ooi-Pedersen)

PRE-REGISTERED MENU (4 trials; cumulative 126 + 4 = 130). Universe: the desk's liquid pool inside the STRICT quality gate
(the gate is the QMJ screen). Annual rebalance (May, Feb, Aug, Nov = four calendars), monthly exposure checks, real costs,
dividends net of tax, cash 4 %/yr. Composite score = mean of four ranks: value (avg rank E/P, B/P, DY), momentum (rank
12-1), quality (avg rank ROE, cash conversion, -D/E), low vol (rank -vol60); top fifth, at least ten, pool of at least
twenty else cash.
    F1 factor4          equal weight, fully invested
    F2 factor4_iv       inverse-volatility weights, capped at 15 % a name
    F3 factor4_vt       F2 + volatility targeting to 15 % annualised (60-day realised vol of the held basket), monthly
    F4 factor4_vt_tsm   F3 + time-series momentum on the COMPOSITE (12-month return <= 0 -> exposure 0), monthly
    reference: strict composite (value + quality gate, the deployed rule), equal weight, same simulator.

READING RULE (declared before the run): a factor arm becomes the catalog's next candidate only if its Sharpe beats the
strict composite in at least three of four calendars AND its CAGR is at least 90 % of strict's in those calendars AND its
worst-calendar drawdown is not deeper than strict's. Otherwise recorded as tested, with the brick-by-brick reading.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_factor_book.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import equity_screen as ES  # noqa: E402
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

N_TRIALS = 130
OUT = os.path.join(VQ.OUTDIR, "factor_book_results.json")
TARGET_VOL = 0.15
CAP = 0.15
ARMS = ("factor4", "factor4_iv", "factor4_vt", "factor4_vt_tsm")


def _avg_rank(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    return sum(df[c].rank(pct=True).fillna(0.5) for c in cols) / len(cols)


def factor_list(rows: list[dict], vol60: pd.Series) -> pd.DataFrame:
    """The strict pool scored on four factors; returns the top fifth with the factor ranks and vol."""
    pool = [r for r in rows if r.get("gate_strict") and r.get("ep") is not None and r["ep"] > 0 and r.get("tradable", True)]
    if len(pool) < 20:
        return pd.DataFrame()
    df = pd.DataFrame([{"code": r["code"], "ep": float(r["ep"]), "bp": float(r["bp"]) if r.get("bp") is not None else np.nan,
                        "dy": float(r["dy"]) if r.get("dy") is not None else np.nan, "mom": float(r["mom"]) if r.get("mom") is not None else np.nan,
                        "roe": float(r["roe"]) if r.get("roe") is not None else np.nan, "conv": float(r["conv"]) if r.get("conv") is not None else np.nan,
                        "der": float(r["der"]) if r.get("der") is not None else np.nan} for r in pool])
    df["vol60"] = df["code"].map(vol60)
    df["neg_der"], df["neg_vol"] = -df["der"], -df["vol60"]
    df["f_value"] = _avg_rank(df, ["ep", "bp", "dy"])
    df["f_mom"] = df["mom"].rank(pct=True).fillna(0.5)
    df["f_quality"] = _avg_rank(df, ["roe", "conv", "neg_der"])
    df["f_lowvol"] = df["neg_vol"].rank(pct=True).fillna(0.5)
    df["score"] = (df["f_value"] + df["f_mom"] + df["f_quality"] + df["f_lowvol"]) / 4
    k = max(10, len(df) // 5)
    return df.sort_values(["score", "code"], ascending=[False, True]).head(k).reset_index(drop=True)


def inverse_vol_weights(sel: pd.DataFrame, cap: float = CAP) -> dict[str, float]:
    iv = (1 / sel["vol60"].replace(0, np.nan)).fillna((1 / sel["vol60"]).median())
    w = (iv / iv.sum()).to_dict()
    codes = list(sel["code"])
    w = {c: w[i] for i, c in enumerate(codes)}
    for _ in range(20):                                                   # cap and redistribute
        over = {c: v for c, v in w.items() if v > cap}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        under = {c: v for c, v in w.items() if v <= cap}
        tot = sum(under.values())
        for c in over:
            w[c] = cap
        for c in under:
            w[c] = under[c] + excess * (under[c] / tot if tot else 1 / len(under))
    return w


def main():
    conn = VQ.connect()
    close, vol, delisted, div, ix = VQ.load(conn)
    end = close.index[-1]
    logr = np.log(close / close.shift(1))
    vol60_all = logr.rolling(60, min_periods=40).std() * math.sqrt(252)
    jk = ix["COMPOSITE"].reindex(close.index).ffill()
    tsm = (jk / jk.shift(252) - 1)
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "months": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))
        rows_at = {D: cand.build(conn, D.date())["all_rows"] for D in rebals}
        strict = {D: {r["code"] for r in ST.pick("strict", rows_at[D]) if r["selected"]} for D in rebals}
        sel_at = {D: factor_list(rows_at[D], vol60_all.loc[D]) for D in rebals}
        table = {}
        print(f"\n=== month {month}: {[str(r.date()) for r in rebals]}   (DSR at N_trials = {N_TRIALS})")
        print(f"{'arm':16s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | names | avg exposure | overlap w/ strict")
        # reference
        nav = VQ.simulate(strict, close, vol, delisted, div, rebals[0], end, True, cash_rate=TO.CASH_RATE)
        st = VQ.stats(nav, rebals)
        r = list(st.pop("_r"))
        st["dsr"] = round(ES.deflated_sharpe(r, N_TRIALS), 3)
        table["strict"] = st
        print(f"{'strict (ref)':16s} {st['total_pct']:7.1f} {st['cagr_pct']:6.1f} {st['sharpe']:6.2f} {st['mdd_pct']:5.0f} {st['dsr']:5.2f} | {np.mean([len(strict[D]) for D in rebals]):5.1f} |  1.00")
        for arm in ARMS:
            def current(m):
                return sel_at[max(a for a in rebals if a <= m)]
            weights_at = {}
            for D in rebals:
                sel = sel_at[D]
                if sel.empty:
                    weights_at[D] = {}
                elif arm == "factor4":
                    weights_at[D] = {c: 1.0 for c in sel["code"]}
                else:
                    weights_at[D] = inverse_vol_weights(sel)
            plan = {D: weights_at[D] for D in rebals} if arm in ("factor4", "factor4_iv") else {m: weights_at[max(a for a in rebals if a <= m)] for m in checks}
            expo_log = []

            def exposure(d, arm=arm):
                e = 1.0
                if arm in ("factor4_vt", "factor4_vt_tsm"):
                    sel = current(d)
                    if not sel.empty:
                        w = weights_at[max(a for a in rebals if a <= d)]
                        codes = [c for c in sel["code"] if c in close.columns]
                        i = close.index.get_loc(d)
                        seg = logr.iloc[max(0, i - 60):i + 1][codes].fillna(0)
                        ww = np.array([w.get(c, 0.0) for c in codes])
                        ww = ww / ww.sum() if ww.sum() else ww
                        pv = float((seg.values @ ww).std() * math.sqrt(252)) if len(seg) > 20 else TARGET_VOL
                        e = min(1.0, TARGET_VOL / pv) if pv > 0 else 1.0
                if arm == "factor4_vt_tsm" and not (tsm.loc[d] > 0):
                    e = 0.0
                expo_log.append(e)
                return e
            nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, cash_rate=TO.CASH_RATE,
                              exposure=exposure if arm in ("factor4_vt", "factor4_vt_tsm") else None)
            st = VQ.stats(nav, rebals)
            r = list(st.pop("_r"))
            st["dsr"] = round(ES.deflated_sharpe(r, N_TRIALS), 3)
            st["avg_exposure"] = round(float(np.mean(expo_log)), 2) if expo_log else 1.0
            st["overlap_strict"] = round(float(np.mean([len(set(sel_at[D]["code"]) & strict[D]) / max(1, len(strict[D])) for D in rebals if not sel_at[D].empty])), 2)
            st["n"] = round(float(np.mean([len(sel_at[D]) for D in rebals])), 1)
            st["episodes"] = TO.episode_dd(nav)
            table[arm] = st
            print(f"{arm:16s} {st['total_pct']:7.1f} {st['cagr_pct']:6.1f} {st['sharpe']:6.2f} {st['mdd_pct']:5.0f} {st['dsr']:5.2f} | {st['n']:5.1f} |  {st['avg_exposure']:.2f}       |  {st['overlap_strict']:.2f}")
            sys.stdout.flush()
        results["months"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}
    print("\n--- reading rule: Sharpe > strict in >= 3/4 calendars AND CAGR >= 0.9 x strict there AND worst mDD <= strict's worst")
    verdict = {}
    strict_dd = max(results["months"][m]["table"]["strict"]["mdd_pct"] for m in results["months"])
    for arm in ARMS:
        wins = 0
        for m in results["months"]:
            t = results["months"][m]["table"]
            if t[arm]["sharpe"] > t["strict"]["sharpe"] and t[arm]["cagr_pct"] >= 0.9 * t["strict"]["cagr_pct"]:
                wins += 1
        dd = max(results["months"][m]["table"][arm]["mdd_pct"] for m in results["months"])
        ok = wins >= 3 and dd <= strict_dd
        verdict[arm] = {"wins": wins, "worst_mdd": dd, "strict_worst_mdd": strict_dd, "candidate": bool(ok)}
        print(f"    {arm:16s} Sharpe-and-CAGR wins {wins}/4, worst mDD {dd:.0f}% vs strict {strict_dd:.0f}% -> {'CATALOG CANDIDATE' if ok else 'tested'}")
    results["verdict"] = verdict
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
