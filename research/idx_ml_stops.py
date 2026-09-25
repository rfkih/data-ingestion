#!/usr/bin/env python3
"""IDX menu ML-6e - stop-loss rules on the cost-aware ML book (operator, 2026-09-25: "kalau dibikin stop loss").

PRE-REGISTERED (9 trials; cumulative 765 + 9 = 774). Base = ML-6 e5|2|3|10 on LIQ from 2022-01 (study #154; trail10 and stop15
were already tested in #155). Exits are checked at the close and executed at the next close, like every exit of the book.
  stop5 stop10 stop20 stop25 stop30   fixed stop: close <= (1 - x) x entry close
  time20         close the trade after 20 days if it is under its entry price
  nomfe10        after 10 days, close if the trade has never been up 3 % and is under water
  time20_stop20  both
  nomfe10_stop20 both
READING RULE: whole window vs the base: Sharpe >= base + 0.15, mDD not deeper, CAGR >= 0.8 base -> BETTER; the money rule
(mDD >= -25 %, Sharpe >= 1.0) reported. No placebo (the rules change exits, not selection).
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
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_ml_costaware as C  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 765
STUDY = "ml_stops"
ARMS = {"stop5": dict(stop=0.05), "stop10": dict(stop=0.10), "stop20": dict(stop=0.20), "stop25": dict(stop=0.25), "stop30": dict(stop=0.30),
        "time20": dict(time_stop=20), "nomfe10": dict(nomfe=(10, 0.03)), "time20_stop20": dict(stop=0.20, time_stop=20),
        "nomfe10_stop20": dict(stop=0.20, nomfe=(10, 0.03))}


def book(A, mask, e, k, c_in, c_out, margin, *, stop=None, time_stop=None, nomfe=None, t_start=0, max_hold=C.MAX_HOLD):
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, dict] = {}
    pend_sell: list[tuple[int, str]] = []
    pend_buy: list[int] = []
    log = []
    rt = c_in + c_out
    for t in range(t_start, T - 1):
        for j, why in pend_sell:
            if j in held:
                R[t] += w * ret[t, j] - w * c_out[t, j]
                p = held.pop(j)
                gross = A[t, j] / A[p["t"], j] - 1
                log.append((why, (1 + gross) * (1 - c_out[t, j]) / (1 + c_in[p["t"], j]) - 1, t - p["t"]))
        for j in pend_buy:
            if j not in held and len(held) < k and not np.isnan(A[t, j]):
                held[j] = {"t": t, "entry": A[t, j], "peak": A[t, j]}
                R[t] -= w * c_in[t, j]
        for j, p in held.items():
            if all(j != s for s, _ in pend_sell):
                R[t] += w * ret[t, j]
            if not np.isnan(A[t, j]):
                p["peak"] = max(p["peak"], A[t, j])
        pend_sell, pend_buy = [], []
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, p in held.items():
            px = A[t, j]
            age = t - p["t"]
            under = not np.isnan(px) and px < p["entry"]
            if age >= max_hold:
                pend_sell.append((j, "max_hold"))
            elif np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j]):
                pend_sell.append((j, "gone"))
            elif stop is not None and not np.isnan(px) and px <= (1 - stop) * p["entry"]:
                pend_sell.append((j, "stop"))
            elif time_stop is not None and age >= time_stop and under:
                pend_sell.append((j, "time"))
            elif nomfe is not None and age >= nomfe[0] and under and p["peak"] / p["entry"] - 1 < nomfe[1]:
                pend_sell.append((j, "nomfe"))
            elif e[t, j] < 0 and best - e[t, j] > margin * rt[t, j]:
                pend_sell.append((j, "swap"))
        free = k - (len(held) - len(pend_sell))
        for j in order:
            if free <= 0:
                break
            if j in held or any(j == s for s, _ in pend_sell):
                continue
            if e[t, j] > margin * rt[t, j]:
                pend_buy.append(int(j))
                free -= 1
    return R, pd.DataFrame(log, columns=["why", "net", "hold"])


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    c_in, c_out = M.costs(g("close").to_numpy(float), g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    S = g("s5").to_numpy(float)
    e5 = C.ema(S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True), 3)
    t0 = int(np.searchsorted(dates, np.datetime64(date(2022, 1, 1))))
    res: dict[str, dict] = {}
    for name, kw in {"base": {}, **ARMS}.items():
        R, log = book(A, liq, e5, 10, c_in, c_out, 2.0, t_start=t0, **kw)
        st = M.stats(R, dates, t0)
        by = log.groupby("why")["net"].agg(["size", "mean"])
        res[name] = {**st, "trades": len(log), "win": float((log["net"] > 0).mean()), "avg": float(log["net"].mean()), "hold": float(log["hold"].mean()),
                     "by_reason": {k: {"n": int(v["size"]), "avg": float(v["mean"])} for k, v in by.iterrows()}}
        M.log(f"{name:<15} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % trades {len(log)} win {res[name]['win'] * 100:.0f} % "
              f"avg {res[name]['avg'] * 100:+.2f} % hold {res[name]['hold']:.0f} d " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items())
              + " | " + ", ".join(f"{k}: n {v['n']} avg {v['avg'] * 100:+.1f} %" for k, v in res[name]["by_reason"].items()))
    b = res["base"]
    for name in ARMS:
        r = res[name]
        why = []
        if r["sharpe"] < b["sharpe"] + 0.15:
            why.append(f"sharpe {r['sharpe']:.2f} < base {b['sharpe']:.2f} + 0.15")
        if r["mdd"] < b["mdd"]:
            why.append("mdd deeper")
        if r["cagr"] < 0.8 * b["cagr"]:
            why.append("cagr < 80 % base")
        r["verdict"] = "BETTER" if not why else "no: " + "; ".join(why)
        r["money_rule"] = bool(r["mdd"] >= -0.25 and r["sharpe"] >= 1.0)
    n_trials = N_BEFORE + len(ARMS)
    L = [f"# IDX menu ML-6e - stop-loss rules on the cost-aware ML book - {date.today()} - {len(ARMS)} trials, cumulative N = {n_trials}", "",
         "| arm | trades | win | avg net | hold d | CAGR | Sharpe | mDD | by year | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in res.items():
        L.append(f"| {name} | {r['trades']} | {r['win'] * 100:.0f} % | {r['avg'] * 100:+.2f} % | {r['hold']:.0f} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | "
                 + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items()) + f" | {r.get('verdict', 'reference')} |")
    L += ["", "## Verdict", "", f"BETTER: {', '.join(n for n in ARMS if res[n]['verdict'] == 'BETTER') or 'none'}; "
          f"money rule: {', '.join(n for n in ARMS if res[n]['money_rule']) or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_STOPS_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(ARMS), "n_trials_cumulative": n_trials, "base": "e5|2|3|10"},
                              summary=common.plain(res), names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
