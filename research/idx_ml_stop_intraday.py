#!/usr/bin/env python3
"""IDX menu ML-9c - the ML stop as Stockbit's Auto Order runs it (intraday trigger + limit order) instead of at the close
(operator, 2026-09-26: "bukannya stoploss di stockbit itu ga gitu ya cara hitungnya?" ... "iyaa").

#281 checked the stop at the CLOSE and sold at the NEXT close. Stockbit's Auto Order watches the last price all session: when it
is <= the trigger, a LIMIT sell is sent at the price the user set, and it fills only at that price or better with a buyer.
Worst case in #281: BREN 2024-09 - stop level 10,212, the day opened at 10,200 and closed at the -20 % limit (8,825); sold the
next day, locked at the limit all day (7,075): -34.6 %. An intraday stop would have been triggered at the open.

PRE-REGISTERED 2026-09-26 before any result of this script was seen (2 trials; cumulative 987 + 2 = 989):
  Book    ens4 exactly as #281 (reproduces #261; checked), daily bars, no intraday data.
  Stockbit-style stop at x (5 % and 10 %) from the fill close, active from the day after the fill:
    trigger = fill x (1 - x); limit = trigger - 2 ticks (snapped to the IDX grid).
    a day with low <= trigger fires it:
      open <= trigger and open >= limit  -> filled at the open
      open  > trigger                    -> filled at trigger - 1 tick (the price fell through it during the day)
      open  < limit                      -> filled at the limit only if the day's high reaches it; else UNFILLED
    unfilled (gap / locked at the lower limit) -> sold at the next day's open (the user cancels and sells at market)
    cost: the sell fee (the fill is a traded price, so no extra spread); the close-based arms keep the bid/offer model of #281
  Arms    sb_stop5, sb_stop10; compared with none and with #281's close-based stop5 / stop10 (re-run here).
READING RULE: an sb arm PASSES if against none: Sharpe >= none + 0.15, mDD not deeper, CAGR >= 0.8 x none (#281's bar), and
  Sharpe >= none in both halves (2022-01..2024-04 / 2024-05..end). Reported against the close-based stop of the same level:
  CAGR, Sharpe, mDD, and the tail (worst trade, 1st percentile).
Limits: daily bars cannot see the ORDER of prices in the day (a day that dips and recovers counts as triggered, which is what a
real intraday stop does), nor the queue at the lower limit. READ-ONLY; one idx.study row (ml_stop_intraday).
"""
from __future__ import annotations

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
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_ml_costaware as C  # noqa: E402
import idx_ml_ens4_exits as X  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 987
STUDY = "ml_stop_intraday"
LIMIT_TICKS = 2
HALF_SPLIT = date(2024, 5, 1)


def tick(px: float) -> float:
    return common.tick(px)


def snap_down(px: float) -> float:
    t = tick(px)
    return float(np.floor(px / t + 1e-9) * t)


def book_sb(A, raw, O, H, L, mask, e, k, c_in, c_out, margin, *, wait, stop, t_start, max_hold=C.MAX_HOLD, limit_ticks=LIMIT_TICKS):
    """X.book with a Stockbit-style intraday stop instead of the close check. Raw OHLC for the trigger/fill, A (adjusted) for
    the book's returns; f = A / raw converts a raw fill price into the adjusted series."""
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, dict] = {}
    watch: dict[int, dict] = {}
    pend_sell: list[tuple[int, str]] = []
    pend_buy: list[int] = []
    log = []
    rt = c_in + c_out
    watch_sig: dict[int, int] = {}
    for t in range(t_start, T - 1):
        for j, why in pend_sell:
            if j in held:
                p = held.pop(j)
                if why == "sb_unfilled":                         # cancelled and sold at today's open (market)
                    fo = O[t, j] if np.isfinite(O[t, j]) and O[t, j] > 0 else raw[t, j]
                    fill_adj = fo * A[t, j] / raw[t, j]
                    R[t] += w * (fill_adj / A[t - 1, j] - 1 - M.FEE_SELL)
                    net = fill_adj / A[p["t"], j] * (1 - M.FEE_SELL) / (1 + c_in[p["t"], j]) - 1
                else:
                    R[t] += w * (ret[t, j] - c_out[t, j])
                    net = (A[t, j] / A[p["t"], j]) * (1 - c_out[t, j]) / (1 + c_in[p["t"], j]) - 1
                log.append({"j": j, "t_in": p["t"], "t_out": t, "why": why, "net": net, "hold": t - p["t"]})
        for j in pend_buy:
            if j not in held and len(held) < k and not np.isnan(A[t, j]):
                held[j] = {"t": t, "t_sig": watch_sig.get(j, t), "peak": A[t, j]}
                R[t] -= w * c_in[t, j]
        pend_ids = {s for s, _ in pend_sell}
        pend_sell, pend_buy = [], []
        # the intraday stop, before today's close is booked
        for j in list(held):
            p = held[j]
            if p["t"] >= t or j in pend_ids or not (np.isfinite(L[t, j]) and np.isfinite(O[t, j]) and raw[t, j] > 0):
                continue
            f = A[t, j] / raw[t, j]
            trig = (1 - stop) * A[p["t"], j] / f                    # the trigger in today's raw prices
            if L[t, j] > trig:
                continue
            lim = snap_down(trig) - limit_ticks * tick(trig)
            o, h = O[t, j], H[t, j]
            if o <= trig:
                fill = o if o >= lim else (lim if h >= lim else None)
            else:
                fill = max(lim, snap_down(trig) - tick(trig))
            if fill is None:                                        # gapped under the limit and never came back: tomorrow's open
                pend_sell.append((j, "sb_unfilled"))
                continue
            fill_adj = fill * f
            R[t] += w * (fill_adj / A[t - 1, j] - 1 - M.FEE_SELL)
            held.pop(j)
            log.append({"j": j, "t_in": p["t"], "t_out": t, "why": "sb_stop", "net": fill_adj / A[p["t"], j] * (1 - M.FEE_SELL) / (1 + c_in[p["t"], j]) - 1,
                        "hold": t - p["t"]})
        blocked = {s for s, _ in pend_sell}                          # stop fired but not filled: sold at tomorrow's open
        for j, p in held.items():
            R[t] += w * ret[t, j]                                     # still held through today's close, loss included
            if not np.isnan(A[t, j]):
                p["peak"] = max(p["peak"], A[t, j])
        watch_sig = {j: v["t"] for j, v in watch.items()}
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, p in held.items():
            if j in blocked:
                continue
            if (t - p["t"]) >= max_hold:
                pend_sell.append((j, "max_hold"))
            elif np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j]):
                pend_sell.append((j, "gone"))
            elif e[t, j] < 0 and best - e[t, j] > margin * rt[t, j]:
                pend_sell.append((j, "swap"))
        for j in list(watch):
            v = watch[j]
            if t > v["until"] or j in held:
                watch.pop(j)
                continue
            if ok[j] and e[t, j] > margin * rt[t, j] and A[t, j] >= (1 + wait[0]) * v["ref"]:
                pend_buy.append(j)
                watch_sig[j] = v["t"]
                watch.pop(j)
        free = k - (len(held) - len(pend_sell)) - len(pend_buy) - len(watch)
        for j in order:
            if free <= 0:
                break
            if j in held or any(j == s for s, _ in pend_sell) or j in watch or j in pend_buy:
                continue
            if e[t, j] > margin * rt[t, j]:
                watch[j] = {"t": t, "ref": A[t, j], "until": t + wait[1]}
                free -= 1
    return R, pd.DataFrame(log)


def sharpe(r: np.ndarray) -> float:
    return float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 1 and r.std() > 0 else float("nan")


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    c_in, c_out = M.costs(raw, g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    S = g("s5").to_numpy(float)
    e5 = C.ema(S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True), X.SPAN)
    t0 = int(np.searchsorted(dates, np.datetime64(date(2022, 1, 1))))
    th = int(np.searchsorted(dates, np.datetime64(HALF_SPLIT)))
    with psycopg.connect(dsn) as conn:
        bars = pd.DataFrame(conn.execute("""SELECT code, trade_date, open::float8, high::float8, low::float8 FROM idx.bar
                                            WHERE trade_date >= '2021-06-01' AND source = 'idx'""").fetchall(),
                            columns=["code", "d", "open", "high", "low"])
    bars["d"] = pd.to_datetime(bars["d"])
    w = lambda c: bars.pivot(index="d", columns="code", values=c).reindex(index=dates, columns=codes).to_numpy(float)  # noqa: E731
    O, H, L = w("open"), w("high"), w("low")
    O = np.where(np.isfinite(O), O, raw)                          # no open on file: the close stands in (rare after the fill)

    def ens(fn, **kw):
        runs = [fn(wait=r, **kw) for r in X.ENS4]
        return np.mean([x[0] for x in runs], axis=0), pd.concat([x[1] for x in runs], ignore_index=True)

    close_bk = lambda **kw: X.book(A, liq, e5, X.K, c_in, c_out, X.MARGIN, t_start=t0, **kw)  # noqa: E731
    sb_bk = lambda **kw: book_sb(A, raw, O, H, L, liq, e5, X.K, c_in, c_out, X.MARGIN, t_start=t0, **kw)  # noqa: E731

    def describe(R, log):
        st = M.stats(R, dates, t0)
        n = log["net"] * 100
        st.update({"sharpe_h1": sharpe(R[t0:th]), "sharpe_h2": sharpe(R[th:]), "trades": len(log), "win": float((n > 0).mean()),
                   "avg": float(n.mean()), "median": float(n.median()), "worst": float(n.min()), "p01": float(n.quantile(0.01)),
                   "hold": float(log["hold"].mean()),
                   "exits": {k: {"n": int(v["n"]), "avg": float(v["m"])} for k, v in log.groupby("why")["net"].agg(n="size", m=lambda s: s.mean() * 100).iterrows()}})
        return st

    res = {"none": describe(*ens(close_bk))}
    ref = {"cagr": 0.2786588361410878}
    if abs(res["none"]["cagr"] - ref["cagr"]) > 1e-9:
        M.log(f"SANITY GATE FAILED: none {res['none']['cagr']} != #261 ens4")
        return 2
    for x in (0.05, 0.10):
        k = int(x * 100)
        res[f"close_stop{k}"] = describe(*ens(close_bk, stop=x))
        res[f"sb_stop{k}"] = describe(*ens(sb_bk, stop=x))
    b = res["none"]
    for k in (5, 10):
        r = res[f"sb_stop{k}"]
        why = []
        if r["sharpe"] < b["sharpe"] + 0.15:
            why.append(f"sharpe {r['sharpe']:.2f} < none {b['sharpe']:.2f} + 0.15")
        if r["mdd"] < b["mdd"]:
            why.append("mdd deeper")
        if r["cagr"] < 0.8 * b["cagr"]:
            why.append("cagr < 80 % none")
        if r["sharpe_h1"] < b["sharpe_h1"] or r["sharpe_h2"] < b["sharpe_h2"]:
            why.append("not better in both halves")
        r["verdict"] = "PASS" if not why else "no: " + "; ".join(why)
    for name, r in res.items():
        M.log(f"{name:<12} CAGR {r['cagr'] * 100:6.1f} % Sharpe {r['sharpe']:5.2f} mDD {r['mdd'] * 100:6.1f} % h1/h2 {r['sharpe_h1']:.2f}/{r['sharpe_h2']:.2f} "
              f"trades {r['trades']} win {r['win'] * 100:.0f} % avg {r['avg']:+.2f} % med {r['median']:+.2f} % worst {r['worst']:+.1f} % p1 {r['p01']:+.1f} % "
              f"hold {r['hold']:.1f} | {r.get('verdict', '')} | " + ", ".join(f"{k}: {v['n']} ({v['avg']:+.1f} %)" for k, v in r["exits"].items()))
    n_trials = N_BEFORE + 2
    L_ = [f"# IDX menu ML-9c - the ML stop run as Stockbit's Auto Order - {date.today()} - 2 trials, cumulative N = {n_trials}", "",
          "Pre-registered rule in the script's docstring. Intraday stop from daily bars: trigger = fill x (1 - x), limit 2 ticks under.", "",
          "| book | CAGR | Sharpe | mDD | Sharpe H1 / H2 | trades | win | avg | median | worst trade | 1st pct | hold d | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in res.items():
        L_.append(f"| {name} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['sharpe_h1']:.2f} / {r['sharpe_h2']:.2f} | {r['trades']} | "
                  f"{r['win'] * 100:.0f} % | {r['avg']:+.2f} % | {r['median']:+.2f} % | {r['worst']:+.1f} % | {r['p01']:+.1f} % | {r['hold']:.1f} | {r.get('verdict', 'reference')} |")
    text = "\n".join(L_)
    out = os.path.join(HERE, f"IDX_ML_STOP_INTRADAY_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(),
                              params={"trials": ["sb_stop5", "sb_stop10"], "n_trials_cumulative": n_trials, "limit_ticks": LIMIT_TICKS, "base": "ens4 as #281"},
                              summary=common.plain({"arms": res}), names=[], report_path=out,
                              note=f"ML-9c Stockbit-style intraday stop: sb_stop5 {res['sb_stop5']['verdict']}, sb_stop10 {res['sb_stop10']['verdict']}")
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
