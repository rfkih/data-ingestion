#!/usr/bin/env python3
"""IDX menu ML-6f - two-step entries on the cost-aware ML book (operator, 2026-09-25: "sinyal 2 kali konfirmasi: sinyal pertama
track atau beli sedikit, kalau turun 25 % tambah posisi, atau baru masuk ketika turun 10-15 %").

PRE-REGISTERED (6 trials; cumulative 774 + 6 = 780). Base = ML-6 e5|2|3|10 on LIQ from 2022-01. A "signal" is the base book's buy
decision (best e5 above 2x the round trip, a free slot). The two-step variants change only what happens after the signal:
  wait_dip10   TRACK: do not buy; enter the name only if within 20 days its close is <= 90 % of the signal close and the score
               still qualifies (e > 2x cost). The slot stays in cash while tracking.
  wait_dip15   the same at 85 %.
  half_add10   BUY HALF a slot at the signal; add the other half if the close falls to <= 90 % of the first fill within 30 days
               (score still qualifying); exits as the base, on the whole position.
  half_add25   the same at 75 %.
  half_add_up5 CONTROL in the other direction: buy half; add the other half when the close is >= 105 % of the first fill within
               30 days (an up-confirmation / pyramid).
  wait_up5     TRACK: enter only when the close is >= 105 % of the signal close within 10 days (breakout confirmation).
The tracked name keeps its slot reserved only when a fill happens; until then that capital is cash (no other name takes it),
which is what an operator watching a name would do. Fills at the next close at the offer, as everywhere in the desk.
READING RULE: vs the base on the whole window: Sharpe >= base + 0.15, mDD not deeper, CAGR >= 0.8 base -> BETTER; money rule reported.
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

N_BEFORE = 774
STUDY = "ml_confirm"
ARMS = {"wait_dip10": dict(wait=(-0.10, 20)), "wait_dip15": dict(wait=(-0.15, 20)), "half_add10": dict(add=(-0.10, 30)),
        "half_add25": dict(add=(-0.25, 30)), "half_add_up5": dict(add=(0.05, 30)), "wait_up5": dict(wait=(0.05, 10))}


def book(A, mask, e, k, c_in, c_out, margin, *, wait=None, add=None, t_start=0, max_hold=C.MAX_HOLD):
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, dict] = {}                     # j -> {t, w (slot fraction), fill, added}
    watch: dict[int, dict] = {}                    # j -> {t, ref, until}   (tracking, slot reserved as cash)
    pend_sell: list[int] = []
    pend_buy: list[tuple[int, float]] = []
    log = []
    rt = c_in + c_out
    for t in range(t_start, T - 1):
        for j in pend_sell:
            if j in held:
                p = held.pop(j)
                R[t] += w * p["w"] * (ret[t, j] - c_out[t, j])
                log.append({"j": j, "t_in": p["t"], "t_out": t, "w": p["w"], "added": p["added"],
                            "net": (A[t, j] / p["fill"]) * (1 - c_out[t, j]) - 1})     # fill already includes entry cost, capital-weighted
        for j, frac in pend_buy:
            if np.isnan(A[t, j]):
                continue
            if j in held:                                     # the add
                p = held[j]
                tot = p["w"] + frac
                p["fill"] = (p["fill"] * p["w"] + A[t, j] * (1 + c_in[t, j]) * frac) / tot
                p["w"] = tot
                p["added"] = True
                R[t] -= w * frac * c_in[t, j]
            elif len(held) < k:
                held[j] = {"t": t, "w": frac, "fill": A[t, j] * (1 + c_in[t, j]), "added": False}
                R[t] -= w * frac * c_in[t, j]
        for j, p in held.items():
            if j not in pend_sell:
                R[t] += w * p["w"] * ret[t, j]
        pend_sell, pend_buy = [], []
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, p in held.items():
            stale = (t - p["t"]) >= max_hold or np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j])
            worse = np.isfinite(e[t, j]) and e[t, j] < 0 and best - e[t, j] > margin * rt[t, j]
            if stale or worse:
                pend_sell.append(j)
            elif add is not None and not p["added"] and (t - p["t"]) <= add[1] and ok[j] and e[t, j] > margin * rt[t, j]:
                lvl, first = add[0], p["fill"] / (1 + c_in[p["t"], j])
                if (lvl < 0 and A[t, j] <= (1 + lvl) * first) or (lvl > 0 and A[t, j] >= (1 + lvl) * first):
                    pend_buy.append((j, 1.0 - p["w"]))
        # tracked names: fill or expire
        for j in list(watch):
            wv = watch[j]
            if t > wv["until"] or j in held:
                watch.pop(j)
                continue
            if ok[j] and e[t, j] > margin * rt[t, j]:
                lvl = wait[0]
                if (lvl < 0 and A[t, j] <= (1 + lvl) * wv["ref"]) or (lvl > 0 and A[t, j] >= (1 + lvl) * wv["ref"]):
                    pend_buy.append((j, 1.0))
                    watch.pop(j)
        reserved = len(watch)
        free = k - (len(held) - len(pend_sell)) - len([1 for j, f in pend_buy if j not in held]) - reserved
        for j in order:
            if free <= 0:
                break
            if j in held or j in pend_sell or j in watch or any(j == b for b, _ in pend_buy):
                continue
            if e[t, j] > margin * rt[t, j]:
                if wait is not None:
                    watch[j] = {"t": t, "ref": A[t, j], "until": t + wait[1]}
                else:
                    pend_buy.append((int(j), 0.5 if add is not None else 1.0))
                free -= 1
    return R, pd.DataFrame(log)


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
        n = len(log)
        res[name] = {**st, "trades": n, "win": float((log["net"] > 0).mean()) if n else float("nan"), "avg": float(log["net"].mean()) if n else float("nan"),
                     "added_share": float(log["added"].mean()) if n else float("nan"), "avg_w": float(log["w"].mean()) if n else float("nan")}
        M.log(f"{name:<13} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % trades {n} win {res[name]['win'] * 100:.0f} % avg {res[name]['avg'] * 100:+.2f} % "
              f"added/filled {res[name]['added_share'] * 100:.0f} % avg slot {res[name]['avg_w']:.2f} " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
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
    L = [f"# IDX menu ML-6f - two-step (confirmation) entries on the cost-aware ML book - {date.today()} - {len(ARMS)} trials, cumulative N = {n_trials}", "",
         "| arm | trades | win | avg net | added or 2nd-step fills | CAGR | Sharpe | mDD | by year | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in res.items():
        L.append(f"| {name} | {r['trades']} | {r['win'] * 100:.0f} % | {r['avg'] * 100:+.2f} % | {r['added_share'] * 100:.0f} % | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | "
                 f"{r['mdd'] * 100:.0f} % | " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items()) + f" | {r.get('verdict', 'reference')} |")
    L += ["", "## Verdict", "", f"BETTER: {', '.join(n for n in ARMS if res[n]['verdict'] == 'BETTER') or 'none'}; money rule: {', '.join(n for n in ARMS if res[n]['money_rule']) or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_CONFIRM_{date.today()}.md")
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
