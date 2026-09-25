#!/usr/bin/env python3
"""IDX menu ML-7c - two models, one book: ORDER the candidates by the lambdarank 5d score, GATE entries and swaps by the
regression's expected excess in bps (operator, 2026-09-25: "okay kerjakan ... 5").

ML-7b (study #174) showed the lambdarank ranker orders LIQ names better than the regression every year (daily rank IC
0.086-0.126 vs 0.050-0.100) and loses in the cost-aware book because it has no magnitude: expressed as a percentile the
cost threshold never binds. This menu keeps the regression where the book needs a bps number (is this name worth 2x its
round trip? does the best candidate pay for the swap?) and uses the ranker only where the book needs an ORDER (which of the
names that pass the gate to buy first, which is "best").

PRE-REGISTERED (3 trials; cumulative 830 + 3 = 833). Same universe, costs, panel, scores and book as ML-6/6f
(`idx_ml_costaware.book` / `idx_ml_confirm.book` with a `rank` matrix): e5 = EMA-3 of the 5d regression excess (bps),
lr = that day's LIQ percentile of the 3-seed lambdarank score from ML-7b (tmp/ml7b_lr5.pkl), EMA-3.
  lrorder|10        plain cost-aware book, K 10: candidates = names with e5 > 2 x round trip, ordered by lr; "best" for
                    the swap test = e5 of the top-ordered candidate
  lrorder|5         the same, K 5
  lrorder+c5/10|10  with the live +5 %/10-day price confirmation
References (same run, not trials): e5|10, e5|5, e5+c5/10|10 = ML-6 / ML-6f recomputed.
Placebo (20 runs, best arm): the lr ORDER shuffled within each day among the names that pass the gate - the gate is kept,
so the placebo asks exactly whether the ranker's order adds anything beyond the regression's gate.
READING RULE: BETTER than the reference with the same K and entry = Sharpe >= ref + 0.15 AND CAGR >= 0.8 x ref AND mDD not
deeper; CANDIDATE (money rule) = Sharpe >= 1.2, mDD >= -25 %, >= 4/5 years, placebo pct >= 95.
READ-ONLY; one idx.study row. IDX_ML_CACHE (default tmp/ml_strategy_cache.pkl), tmp/ml7b_lr5.pkl from ML-7b.
"""
from __future__ import annotations

import json
import os
import pickle
import re
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
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 830
STUDY = "ml7c_twomodel"
ARMS = {"lrorder|10": dict(k=10, wait=None), "lrorder|5": dict(k=5, wait=None), "lrorder+c5/10|10": dict(k=10, wait=(0.05, 10))}
REFS = {"e5|10": dict(k=10, wait=None), "e5|5": dict(k=5, wait=None), "e5+c5/10|10": dict(k=10, wait=(0.05, 10))}
MARGIN, SPAN = 2.0, 3
BAR = {"sharpe": 1.2, "mdd": -0.25, "years_pos": 4, "placebo_pct": 95.0, "better_sharpe": 0.15, "better_cagr": 0.8}


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    return env["INGEST_DB_DSN"].strip().strip('"')


def book(A, mask, e, k, c_in, c_out, margin, *, rank=None, wait=None, t_start=0, max_hold=C.MAX_HOLD):
    """idx_ml_confirm.book with an optional ORDER matrix: candidates still have to pass e > margin x cost (the regression's
    gate) but are taken in `rank` order, and "best" (the swap test) is the e of the top-ordered candidate."""
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, dict] = {}
    watch: dict[int, dict] = {}
    pend_sell: list[int] = []
    pend_buy: list[int] = []
    log = []
    rt = c_in + c_out
    for t in range(t_start, T - 1):
        for j in pend_sell:
            if j in held:
                p = held.pop(j)
                R[t] += w * (ret[t, j] - c_out[t, j])
                log.append({"j": j, "t_in": p["t"], "t_out": t, "net": (A[t, j] / p["fill"]) * (1 - c_out[t, j]) - 1})
        for j in pend_buy:
            if np.isnan(A[t, j]) or j in held or len(held) >= k:
                continue
            held[j] = {"t": t, "fill": A[t, j] * (1 + c_in[t, j])}
            R[t] -= w * c_in[t, j]
        for j in held:
            if j not in pend_sell:
                R[t] += w * ret[t, j]
        pend_sell, pend_buy = [], []
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        passing = np.flatnonzero(ok & (e[t] > margin * rt[t]))
        if rank is not None:
            passing = passing[np.isfinite(rank[t, passing])]
            order = passing[np.argsort(-rank[t, passing], kind="stable")] if len(passing) else passing
        else:
            order = passing[np.argsort(-e[t, passing], kind="stable")] if len(passing) else passing
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, p in held.items():
            stale = (t - p["t"]) >= max_hold or np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j])
            worse = np.isfinite(e[t, j]) and e[t, j] < 0 and best - e[t, j] > margin * rt[t, j]
            if stale or worse:
                pend_sell.append(j)
        for j in list(watch):
            wv = watch[j]
            if t > wv["until"] or j in held:
                watch.pop(j)
                continue
            if ok[j] and e[t, j] > margin * rt[t, j] and A[t, j] >= (1 + wait[0]) * wv["ref"]:
                pend_buy.append(int(j))
                watch.pop(j)
        free = k - (len(held) - len(pend_sell)) - len(pend_buy) - len(watch)
        for j in order:
            if free <= 0:
                break
            if j in held or j in pend_sell or j in watch or j in pend_buy:
                continue
            if wait is not None:
                watch[j] = {"t": t, "ref": A[t, j], "until": t + wait[1]}
            else:
                pend_buy.append(int(j))
            free -= 1
    return R, pd.DataFrame(log)


def main() -> int:
    cache = os.environ.get("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
    P = pickle.load(open(cache, "rb"))
    LR = pickle.load(open(os.path.join(ROOT, "tmp", "ml7b_lr5.pkl"), "rb"))
    P = P.merge(LR[["code", "d", "lr5"]], on=["code", "d"], how="left")
    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    c_in, c_out = M.costs(g("close").to_numpy(float), g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    S = g("s5").to_numpy(float)
    e5 = C.ema(S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True), SPAN)
    LR5 = g("lr5").to_numpy(float)
    lr = C.ema(pd.DataFrame(np.where(liq, LR5, np.nan)).rank(axis=1, pct=True).to_numpy(), SPAN)
    t0 = int(np.searchsorted(dates, np.datetime64(date(2022, 1, 1))))

    res: dict[str, dict] = {}
    for arm, kw in {**REFS, **ARMS}.items():
        R, log = book(A, liq, e5, kw["k"], c_in, c_out, MARGIN, rank=lr if arm.startswith("lrorder") else None, wait=kw["wait"], t_start=t0)
        st = M.stats(R, dates, t0)
        n = len(log)
        res[arm] = {**st, "trades": n, "win": float((log["net"] > 0).mean()) if n else float("nan"), "avg": float(log["net"].mean()) if n else float("nan")}
        M.log(f"{arm:<17} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % trades {n} win {res[arm]['win'] * 100:.0f} % "
              f"avg {res[arm]['avg'] * 100:+.2f} % years+ {st['years_pos']}/{st['n_years']} " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
    best = max(ARMS, key=lambda a: res[a]["sharpe"])
    kw = ARMS[best]
    rng = np.random.default_rng(M.SEED)
    pl = []
    rt = c_in + c_out
    for i in range(M.N_PLACEBO):
        sh = lr.copy()
        for t in range(t0, len(dates)):
            idx = np.flatnonzero(liq[t] & np.isfinite(sh[t]) & np.isfinite(e5[t]) & (e5[t] > MARGIN * rt[t]))
            if len(idx) > 1:
                sh[t, idx] = sh[t, rng.permutation(idx)]
        R, _ = book(A, liq, e5, kw["k"], c_in, c_out, MARGIN, rank=sh, wait=kw["wait"], t_start=t0)
        pl.append(M.stats(R, dates, t0)["sharpe"])
    res[best]["placebo"] = {"n": M.N_PLACEBO, "pct": float((np.array(pl) < res[best]["sharpe"]).mean() * 100), "mean": float(np.mean(pl)), "max": float(np.max(pl))}
    M.log(f"placebo {best} (order shuffled among gated names): real {res[best]['sharpe']:.2f} vs mean {np.mean(pl):.2f} max {np.max(pl):.2f} -> pct {res[best]['placebo']['pct']:.0f}")

    ref_of = {"lrorder|10": "e5|10", "lrorder|5": "e5|5", "lrorder+c5/10|10": "e5+c5/10|10"}
    for arm in ARMS:
        r, ref = res[arm], res[ref_of[arm]]
        r["better"] = bool(r["sharpe"] >= ref["sharpe"] + BAR["better_sharpe"] and r["cagr"] >= BAR["better_cagr"] * ref["cagr"] and r["mdd"] >= ref["mdd"])
        fails = []
        if r["sharpe"] < BAR["sharpe"]:
            fails.append(f"sharpe {r['sharpe']:.2f} < 1.2")
        if r["mdd"] < BAR["mdd"]:
            fails.append(f"mdd {r['mdd'] * 100:.0f} % < -25 %")
        if r["years_pos"] < min(BAR["years_pos"], r["n_years"]):
            fails.append(f"{r['years_pos']}/{r['n_years']} years positive")
        if "placebo" in r and r["placebo"]["pct"] < BAR["placebo_pct"]:
            fails.append(f"placebo pct {r['placebo']['pct']:.0f}")
        r["candidate"] = not fails
        r["verdict"] = ("BETTER than ref" if r["better"] else "not better than ref") + " | " + ("CANDIDATE" if not fails else "not a candidate: " + "; ".join(fails))

    n_trials = N_BEFORE + len(ARMS)
    L = [f"# IDX menu ML-7c - two models, one book: lambdarank order + regression gate - {date.today()} - {len(ARMS)} trials, cumulative N = {n_trials}", "",
         "Cost-aware book on LIQ from 2022-01 (margin 2, EMA-3); the regression's bps decide who may enter and when a swap pays, the lambdarank "
         "percentile decides the order. References = the same book ordered by the regression itself.", "",
         "| arm | trades | win | avg net | CAGR | Sharpe | mDD | years + | by year | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for arm, r in res.items():
        pl_s = f" (placebo pct {r['placebo']['pct']:.0f})" if "placebo" in r else ""
        L.append(f"| {arm} | {r['trades']} | {r['win'] * 100:.0f} % | {r['avg'] * 100:+.2f} % | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | "
                 f"{r['years_pos']}/{r['n_years']} | " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items()) + f" | {r.get('verdict', 'reference')}{pl_s} |")
    better = [a for a in ARMS if res[a]["better"]]
    L += ["", "## Verdict (menu ML-7c, study stored)", "", f"BETTER than the reference: {', '.join(better) or 'none'}. Money-rule candidates: "
          f"{', '.join(a for a in ARMS if res[a]['candidate']) or 'none'}. Best: {best} ({res[best]['cagr'] * 100:+.1f} %/yr, Sharpe {res[best]['sharpe']:.2f}, mDD {res[best]['mdd'] * 100:.0f} %)."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML7C_TWOMODEL_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    json.dump(common.plain(res), open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(dsn()) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(ARMS), "refs": list(REFS), "n_trials_cumulative": n_trials, "bar": BAR, "margin": MARGIN, "ema": SPAN},
                              summary={"arms": common.plain(res), "better": better, "best": best}, names=[], report_path=out,
                              note="ML-7c: lambdarank order + regression gate in one cost-aware book")
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
