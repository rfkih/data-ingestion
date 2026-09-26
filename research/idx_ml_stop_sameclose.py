#!/usr/bin/env python3
"""IDX menu ML-9d - the ML stop checked near the close and sold in the SAME closing session (operator, 2026-09-26: "oke boleh").

#281's stop checks the close and sells at the NEXT close (worst case BREN 2024-09: triggered on a -20 % day, sold the next day
at another -20 %: -34.6 %). #287 (Stockbit-style intraday stop) cut the tail but fired on intraday dips that recovered and lost
return (21.3 %/yr vs 34.4 %). Middle way: look at the price just before the close (~15:45 WIB, the desk has it live) and, when it
is under the stop, sell in that day's closing session.

PRE-REGISTERED 2026-09-26 before any result of this script was seen (2 trials; cumulative 989 + 2 = 991):
  Book    ens4 exactly as #281 (base reproduces #261; checked).
  Arms    same_stop5, same_stop10: a close <= fill x (1 - x) sells AT THAT close (bid + fee, as the book's other sells), from the
          day after the fill. Approximation: the 15:45 price is taken as the close.
READING RULE (as #287): PASS if against none: Sharpe >= none + 0.15, mDD not deeper, CAGR >= 0.8 x none, Sharpe >= none in both
  halves (2022-01..2024-04 / 2024-05..end). Reported next to #281's next-close stop of the same level, with the tail.
READ-ONLY; one idx.study row (ml_stop_sameclose).
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

N_BEFORE = 989
STUDY = "ml_stop_sameclose"
HALF_SPLIT = date(2024, 5, 1)


def book_same(A, mask, e, k, c_in, c_out, margin, *, wait, stop, t_start, max_hold=C.MAX_HOLD):
    """X.book with the stop sold at the close that triggers it (not the next one)."""
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
                R[t] += w * (ret[t, j] - c_out[t, j])
                log.append({"j": j, "t_in": p["t"], "t_out": t, "why": why,
                            "net": (A[t, j] / A[p["t"], j]) * (1 - c_out[t, j]) / (1 + c_in[p["t"], j]) - 1, "hold": t - p["t"]})
        for j in pend_buy:
            if j not in held and len(held) < k and not np.isnan(A[t, j]):
                held[j] = {"t": t, "t_sig": watch_sig.get(j, t), "peak": A[t, j]}
                R[t] -= w * c_in[t, j]
        for j, p in held.items():
            R[t] += w * ret[t, j]
        pend_sell, pend_buy = [], []
        # the stop, sold at today's close
        for j in list(held):
            p = held[j]
            if p["t"] < t and not np.isnan(A[t, j]) and A[t, j] <= (1 - stop) * A[p["t"], j]:
                held.pop(j)
                R[t] -= w * c_out[t, j]
                log.append({"j": j, "t_in": p["t"], "t_out": t, "why": "stop_same",
                            "net": (A[t, j] / A[p["t"], j]) * (1 - c_out[t, j]) / (1 + c_in[p["t"], j]) - 1, "hold": t - p["t"]})
        watch_sig = {j: v["t"] for j, v in watch.items()}
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, p in held.items():
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

    def ens(fn, **kw):
        runs = [fn(A, liq, e5, X.K, c_in, c_out, X.MARGIN, wait=r, t_start=t0, **kw) for r in X.ENS4]
        return np.mean([x[0] for x in runs], axis=0), pd.concat([x[1] for x in runs], ignore_index=True)

    def describe(R, log):
        st = M.stats(R, dates, t0)
        n = log["net"] * 100
        st.update({"sharpe_h1": sharpe(R[t0:th]), "sharpe_h2": sharpe(R[th:]), "trades": len(log), "win": float((n > 0).mean()),
                   "avg": float(n.mean()), "median": float(n.median()), "worst": float(n.min()), "p01": float(n.quantile(0.01)),
                   "hold": float(log["hold"].mean()),
                   "exits": {k: {"n": int(v["n"]), "avg": float(v["m"])} for k, v in log.groupby("why")["net"].agg(n="size", m=lambda s: s.mean() * 100).iterrows()}})
        return st

    res = {"none": describe(*ens(X.book))}
    if abs(res["none"]["cagr"] - 0.2786588361410878) > 1e-9:
        M.log("SANITY GATE FAILED: none != #261 ens4")
        return 2
    for x in (0.05, 0.10):
        k = int(x * 100)
        res[f"nextclose_stop{k}"] = describe(*ens(X.book, stop=x))
        res[f"same_stop{k}"] = describe(*ens(book_same, stop=x))
    b = res["none"]
    for k in (5, 10):
        r = res[f"same_stop{k}"]
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
        M.log(f"{name:<16} CAGR {r['cagr'] * 100:6.1f} % Sharpe {r['sharpe']:5.2f} mDD {r['mdd'] * 100:6.1f} % h1/h2 {r['sharpe_h1']:.2f}/{r['sharpe_h2']:.2f} "
              f"trades {r['trades']} win {r['win'] * 100:.0f} % avg {r['avg']:+.2f} % med {r['median']:+.2f} % worst {r['worst']:+.1f} % p1 {r['p01']:+.1f} % "
              f"hold {r['hold']:.1f} | {r.get('verdict', '')}")
    n_trials = N_BEFORE + 2
    L_ = [f"# IDX menu ML-9d - the ML stop sold in the same closing session - {date.today()} - 2 trials, cumulative N = {n_trials}", "",
          "| book | CAGR | Sharpe | mDD | Sharpe H1 / H2 | trades | win | avg | median | worst trade | 1st pct | hold d | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in res.items():
        L_.append(f"| {name} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['sharpe_h1']:.2f} / {r['sharpe_h2']:.2f} | {r['trades']} | "
                  f"{r['win'] * 100:.0f} % | {r['avg']:+.2f} % | {r['median']:+.2f} % | {r['worst']:+.1f} % | {r['p01']:+.1f} % | {r['hold']:.1f} | {r.get('verdict', 'reference')} |")
    text = "\n".join(L_)
    out = os.path.join(HERE, f"IDX_ML_STOP_SAMECLOSE_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["same_stop5", "same_stop10"], "n_trials_cumulative": n_trials, "base": "ens4 as #281"},
                              summary=common.plain({"arms": res}), names=[], report_path=out,
                              note=f"ML-9d same-close stop: same_stop5 {res['same_stop5']['verdict']}, same_stop10 {res['same_stop10']['verdict']}")
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
