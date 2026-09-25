#!/usr/bin/env python3
"""IDX menu ML-6b — risk overlays on the cost-aware ML book (follow-up to ML-6, study #154, same morning 2026-09-25).

ML-6 found the desk's 5d score, used cost-aware (buy when the expected excess pays 2x the round trip, hold ~25 days,
swap only when a better name pays for it), earns +29 %/yr (K 10) / +42 %/yr (K 5) on LIQ 2022-26, 4/5 years positive,
placebo pct 100 - but with -51 % / -61 % drawdowns (2022). The signal is a selection signal; the book has no risk rule.
This menu adds the desk's known risk tools one at a time, on the K 10 book (e5, margin 2, ema 3).

PRE-REGISTERED (6 trials; cumulative 751 + 6 = 757).
  base        e5|2|3|10 as ML-6 (reference, not a trial)
  trail10     sell a holding at the close after the first close <= 90 % of its peak close since entry (the trend book's exit)
  stop15      sell at the close after the first close <= 85 % of the entry close (a fixed stop)
  half_off    while COMPOSITE < its 200-day mean at the signal close, NEW positions take half a slot; sells unchanged
  voltgt      scale the whole book's exposure to a 20 % annualised volatility target from the trailing 20-day realised vol
              (exposure = min(1, 0.20 / vol), applied to the next day's returns; the rest is cash)
  liq10       universe LIQ with 60-day value >= Rp 10 bn (drop the thinnest third)
  combo       trail10 + half_off + liq10
READING RULE: as ML-6 (Sharpe >= 1.2; mDD >= -25 %; >= 4/5 years positive; placebo pct >= 95 on the best arm). Money rule =
  the -25 % drawdown. A CANDIDATE here is a paper-book proposal for the operator; the deployed trend book on the same
  window is +20.1 % / 1.24 / -18 %.
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

N_BEFORE = 751
STUDY = "ml_costaware_risk"
ARMS = ["trail10", "stop15", "half_off", "voltgt", "liq10", "combo"]
MARGIN, SPAN, K = 2.0, 3, 10


def book(A, mask, e, k, c_in, c_out, margin, *, trail=None, stop=None, half_off=None, t_start=0, max_hold=C.MAX_HOLD):
    """ML-6's cost-aware book plus optional exits (trail / fixed stop) and half-size entries while the regime is off."""
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, dict] = {}                     # j -> {"t": entry day, "w": slot fraction, "peak": peak close, "entry": entry close}
    pend_sell: list[int] = []
    pend_buy: list[tuple[int, float]] = []
    trades, holds = 0, []
    rt = c_in + c_out
    for t in range(t_start, T - 1):
        for j in pend_sell:
            if j in held:
                p = held.pop(j)
                R[t] += w * p["w"] * (ret[t, j] - c_out[t, j])
                holds.append(t - p["t"])
        for j, frac in pend_buy:
            if j not in held and len(held) < k and not np.isnan(A[t, j]):
                held[j] = {"t": t, "w": frac, "peak": A[t, j], "entry": A[t, j]}
                R[t] -= w * frac * c_in[t, j]
                trades += 1
        for j, p in held.items():
            if j not in pend_sell:
                R[t] += w * p["w"] * ret[t, j]
            if not np.isnan(A[t, j]):
                p["peak"] = max(p["peak"], A[t, j])
        pend_sell, pend_buy = [], []
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, p in held.items():
            stale = (t - p["t"]) >= max_hold or np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j])
            worse = np.isfinite(e[t, j]) and e[t, j] < 0 and best - e[t, j] > margin * rt[t, j]
            hit_trail = trail is not None and not np.isnan(A[t, j]) and A[t, j] <= (1 - trail) * p["peak"]
            hit_stop = stop is not None and not np.isnan(A[t, j]) and A[t, j] <= (1 - stop) * p["entry"]
            if stale or worse or hit_trail or hit_stop:
                pend_sell.append(j)
        free = k - (len(held) - len(pend_sell))
        frac = 0.5 if (half_off is not None and half_off[t]) else 1.0
        for j in order:
            if free <= 0:
                break
            if j in held or j in pend_sell:
                continue
            if e[t, j] > margin * rt[t, j]:
                pend_buy.append((int(j), frac))
                free -= 1
    return R, trades, (float(np.mean(holds)) if holds else float("nan"))


def vol_target(R: np.ndarray, target: float = 0.20, window: int = 20) -> np.ndarray:
    r = pd.Series(R)
    vol = r.rolling(window, min_periods=window).std() * np.sqrt(252)
    expo = (target / vol).clip(upper=1.0).shift(1).fillna(1.0).to_numpy()
    return R * expo


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
    liq10 = liq & (np.expm1(g("lvalue60").to_numpy(float)) >= 10e9)
    off = ~(g("comp_dma200").max(axis=1).ffill().to_numpy(float) > 0)
    t0 = int(np.searchsorted(dates, np.datetime64(C.FROM)))
    S = g("s5").to_numpy(float)
    e5 = C.ema(S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True), SPAN)
    specs = {"base": {}, "trail10": {"trail": 0.10}, "stop15": {"stop": 0.15}, "half_off": {"half_off": off}, "voltgt": {},
             "liq10": {"mask": liq10}, "combo": {"trail": 0.10, "half_off": off, "mask": liq10}}
    res: dict[str, dict] = {}
    for name, kw in specs.items():
        mask = kw.pop("mask", liq)
        R, n, hold = book(A, mask, e5, K, c_in, c_out, MARGIN, t_start=t0, **kw)
        if name == "voltgt":
            R = vol_target(R)
        st = M.stats(R, dates, t0)
        res[name] = {**st, "trades": n, "hold_days": hold}
        M.log(f"{name:<9} CAGR {st['cagr'] * 100:6.1f} %  Sharpe {st['sharpe']:5.2f}  mDD {st['mdd'] * 100:6.1f} %  trades {n:,} hold {hold:.0f} d  "
              f"years+ {st['years_pos']}/{st['n_years']}  " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
    best = max(ARMS, key=lambda a: res[a]["sharpe"])
    kw = dict(specs[best])
    mask = liq10 if best in ("liq10", "combo") else liq
    rng = np.random.default_rng(M.SEED)
    pl = []
    for _ in range(M.N_PLACEBO):
        sh = S.copy()
        for t in range(t0, len(dates)):
            idx = np.flatnonzero(liq[t] & np.isfinite(sh[t]))
            if len(idx) > 1:
                sh[t, idx] = sh[t, rng.permutation(idx)]
        e_sh = C.ema(sh - np.nanmedian(np.where(liq, sh, np.nan), axis=1, keepdims=True), SPAN)
        R, _, _ = book(A, mask, e_sh, K, c_in, c_out, MARGIN, t_start=t0, **{k: v for k, v in kw.items() if k != "mask"})
        if best == "voltgt":
            R = vol_target(R)
        pl.append(M.stats(R, dates, t0)["sharpe"])
    res[best]["placebo"] = {"n": M.N_PLACEBO, "pct": float((np.array(pl) < res[best]["sharpe"]).mean() * 100), "mean": float(np.mean(pl)), "max": float(np.max(pl))}
    M.log(f"placebo {best}: real {res[best]['sharpe']:.2f} vs shuffled mean {np.mean(pl):.2f} max {np.max(pl):.2f} -> pct {res[best]['placebo']['pct']:.0f}")
    for name in ARMS:
        r = res[name]
        fails = []
        if r["sharpe"] < 1.2:
            fails.append(f"sharpe {r['sharpe']:.2f} < 1.2")
        if r["mdd"] < -0.25:
            fails.append(f"mdd {r['mdd'] * 100:.0f} % < -25 %")
        if r["years_pos"] < min(4, r["n_years"]):
            fails.append(f"{r['years_pos']}/{r['n_years']} years positive")
        if "placebo" in r and r["placebo"]["pct"] < 95:
            fails.append(f"placebo pct {r['placebo']['pct']:.0f}")
        r["verdict"] = "CANDIDATE" if not fails else "not a candidate: " + "; ".join(fails)
    n_trials = N_BEFORE + len(ARMS)
    L = [f"# IDX menu ML-6b — risk overlays on the cost-aware ML book — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
         "Base = ML-6's e5 | margin 2 | ema 3 | K 10 on LIQ from 2022-01 (study #154). Each overlay alone, then the combination.", "",
         "| arm | trades | hold d | CAGR | Sharpe | mDD | years + | by year | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    for name in ["base", *ARMS]:
        r = res[name]
        by = " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items())
        pl_s = f" (placebo pct {r['placebo']['pct']:.0f})" if "placebo" in r else ""
        L.append(f"| {name} | {r['trades']:,} | {r['hold_days']:.0f} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['years_pos']}/{r['n_years']} | {by} | "
                 f"{r.get('verdict', 'reference')}{pl_s} |")
    L += ["", "Deployed trend book on the same window: +20.1 % / 1.24 / -18 %.", "", "## Verdict (menu ML-6b, study stored)", "",
          f"Best arm: **{best}** ({res[best]['cagr'] * 100:+.1f} %/yr, Sharpe {res[best]['sharpe']:.2f}, mDD {res[best]['mdd'] * 100:.0f} %) - {res[best]['verdict']}.",
          f"Candidates: {', '.join(a for a in ARMS if res[a]['verdict'] == 'CANDIDATE') or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_COSTAWARE2_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "base": "e5|2|3|10", "source": "ml_costaware #154"},
                              summary={"arms": common.plain(res), "best": best}, names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
