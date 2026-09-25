#!/usr/bin/env python3
"""IDX menu ML-4b — cost-aware follow-up to ML-4 (same evening, 2026-09-24).

ML-4 (study #151) found the walk-forward scores carry a real cross-sectional signal every year (daily rank IC +0.05..+0.10
at 5 and 20 days, top-bottom decile +190..+400 bps per 5 days) but the fixed-horizon top-10 books pay ~91 bps per round trip
on LIQ and end up negative net (5d: +26 %/yr gross, -20 % net). At 250 days the decile spread is the bottom decile falling,
not the top rising. This follow-up sweeps the two levers that follow from that: cheaper names and less turnover, plus the
loser-avoidance use of the long score. Same OOS scores (the ML-4 cache), same costs and fees.

PRE-REGISTERED (8 trials; cumulative 723 + 8 = 731).
  Universes: LIQ as ML-4; BLUE = LIQ and 60-day value >= Rp 20 bn and close >= Rp 1,000 (the desk's BLUE: a tick <= 0.5 %).
  Arms:
    blue5        top-5 by the 5d score on BLUE, H 5 (cohorts as ML-4)
    blue20       top-5 by the 20d excess score on BLUE, H 20
    liq5_top3    top-3 by the 5d score on LIQ, H 5 (the extreme end of the ranking)
    hyst5_liq    position book, K 10 on LIQ: enter the best-ranked names by the 5d score, HOLD while the name stays in the top
                 30 % of that day's ranking, sell when it drops out or after 60 days; signals at close t, trades at close t+1
    hyst5_blue   the same on BLUE, K 5
    hyst20_liq   the same with the 20d excess score, K 10, LIQ
    blend_hyst   the same with the rank-mean of the 5d and 20d scores, K 10, LIQ
    avoid250     equal-weight LIQ cohorts H 250 (every liquid name, K = all) EXCLUDING the bottom 30 % by the 250d score,
                 against the same book with nothing excluded: does the long score earn its keep as a loser filter?
  References: random on BLUE (H 5, H 20), the ML-4 references, and the all-names LIQ H-250 book.
READING RULE: as ML-4 (Sharpe >= 1.2, mDD >= -25 %, >= 4/5 years positive, Sharpe >= random + 0.5, placebo pct >= 95 on the
  best arm). avoid250 is read on its own terms: EXCESS CAGR over the unfiltered book, positive in >= 4/5 years -> the filter is
  informative for the annual book; it is not a strategy by itself.
READ-ONLY on the market tables; one idx.study row. Needs IDX_ML_CACHE from the ML-4 run.
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
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 723
STUDY = "ml_strategy_costaware"
BLUE_VALUE, BLUE_PRICE = 20e9, 1000.0
ARMS = ["blue5", "blue20", "liq5_top3", "hyst5_liq", "hyst5_blue", "hyst20_liq", "blend_hyst", "avoid250"]
HOLD_PCT, MAX_HOLD = 0.30, 60


def hysteresis(A, mask, score, k, c_in, c_out, hold_pct=HOLD_PCT, max_hold=MAX_HOLD, t_start=0):
    """Position book: K slots, equal weight 1/K of NAV each (cash earns 0). At close t: rank the maskable names by score;
    a held name is sold at close t+1 (bid + fee) when its rank falls below the top ``hold_pct`` share, when it has been held
    ``max_hold`` days, or when its price disappears; empty slots are filled at close t+1 (offer + fee) with the best-ranked
    names not held. -> daily returns, trades, mean holding days."""
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, int] = {}                 # j -> entry day
    pend_sell: list[int] = []
    pend_buy: list[int] = []
    trades, holds = 0, []
    for t in range(t_start, T - 1):
        # execute yesterday's decisions at today's close (t is "t+1" for them)
        for j in pend_sell:
            if j in held:
                R[t] += w * ret[t, j]
                R[t] -= w * c_out[t, j]
                holds.append(t - held.pop(j))
        for j in pend_buy:
            if j not in held and len(held) < k and not np.isnan(A[t, j]):
                held[j] = t
                R[t] -= w * c_in[t, j]
                trades += 1
        for j in held:
            if j not in pend_sell:
                R[t] += w * ret[t, j]
        pend_sell, pend_buy = [], []
        # decide at close t
        sc = np.where(mask[t] & np.isfinite(score[t]) & ~np.isnan(A[t]), score[t], -np.inf)
        order = np.argsort(-sc, kind="stable")
        n_ok = int(np.isfinite(sc).sum() - (sc == -np.inf).sum())
        if n_ok == 0:
            pend_sell = list(held)
            continue
        rank = np.empty(N, dtype=int)
        rank[order] = np.arange(N)
        keep_rank = max(k, int(hold_pct * n_ok))
        for j, t_in in held.items():
            if rank[j] >= keep_rank or (t - t_in) >= max_hold or np.isnan(A[t + 1, j]) or sc[j] == -np.inf:
                pend_sell.append(j)
        free = k - (len(held) - len(pend_sell))
        for j in order[:n_ok]:
            if free <= 0:
                break
            if j not in held:
                pend_buy.append(int(j))
                free -= 1
    return R, trades, (float(np.mean(holds)) if holds else float("nan"))


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[P["d"] >= "2021-06-01"].copy()
    P["blue"] = P["liq"] & (np.expm1(P["lvalue60"]) >= BLUE_VALUE) & (P["close"] >= BLUE_PRICE)
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    close, offer, bid = g("close").to_numpy(float), g("offer").to_numpy(float), g("bid").to_numpy(float)
    c_in, c_out = M.costs(close, offer, bid)
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    blue = g("blue").fillna(False).astype(bool).to_numpy()
    s5, s20, s250 = g("s5").to_numpy(float), g("s20").to_numpy(float), g("s250").to_numpy(float)
    blend = M.rank_mean(s5, s20)
    t0 = int(np.searchsorted(dates, np.datetime64(date(2022, 1, 1))))
    M.log(f"round-trip cost LIQ {np.nanmean((c_in + c_out)[liq]) * 1e4:.0f} bps, BLUE {np.nanmean((c_in + c_out)[blue]) * 1e4:.0f} bps; "
          f"names/day LIQ {liq[t0:].sum(1).mean():.0f}, BLUE {blue[t0:].sum(1).mean():.0f}")
    res: dict[str, dict] = {}
    for name, (score, H, k, mask) in {"blue5": (s5, 5, 5, blue), "blue20": (s20, 20, 5, blue), "liq5_top3": (s5, 5, 3, liq)}.items():
        R, n = M.simulate(A, mask, score, H, k, c_in, c_out, t_start=t0)
        res[name] = {**M.stats(R, dates, t0), "H": H, "k": k, "trades": n}
    for name, (score, k, mask) in {"hyst5_liq": (s5, 10, liq), "hyst5_blue": (s5, 5, blue), "hyst20_liq": (s20, 10, liq), "blend_hyst": (blend, 10, liq)}.items():
        R, n, hold = hysteresis(A, mask, score, k, c_in, c_out, t_start=t0)
        res[name] = {**M.stats(R, dates, t0), "H": f"hyst({hold:.0f} d)", "k": k, "trades": n, "hold_days": hold}
    # avoid250: every liquid name (k = all) H 250, with / without the bottom 30 % by s250
    pct = pd.DataFrame(np.where(liq, s250, np.nan)).rank(axis=1, pct=True).to_numpy()
    keep = liq & (pct >= 0.30)
    R_all, n_all = M.simulate(A, liq, np.zeros_like(A), 250, 400, c_in, c_out, t_start=t0)     # k = 400 > names: takes every name
    R_flt, n_flt = M.simulate(A, keep, np.zeros_like(A), 250, 400, c_in, c_out, t_start=t0)
    st_all, st_flt = M.stats(R_all, dates, t0), M.stats(R_flt, dates, t0)
    exc = {y: round(st_flt["by_year"][y] - st_all["by_year"][y], 4) for y in st_flt["by_year"]}
    res["avoid250"] = {**st_flt, "H": 250, "k": "all-30%", "trades": n_flt, "unfiltered": st_all, "excess_by_year": exc,
                       "excess_cagr": st_flt["cagr"] - st_all["cagr"]}
    for name in ARMS:
        r = res[name]
        M.log(f"{name:<11} CAGR {r['cagr'] * 100:6.1f} %  Sharpe {r['sharpe']:5.2f}  mDD {r['mdd'] * 100:6.1f} %  trades {r['trades']:,}  years+ {r['years_pos']}/{r['n_years']}")
    refs = {}
    for H in (5, 20):
        runs = [M.stats(M.simulate(A, blue, None, H, 5, c_in, c_out, rng=np.random.default_rng(M.SEED + s), t_start=t0)[0], dates, t0) for s in range(5)]
        refs[f"random_blue_H{H}"] = {k: float(np.mean([r[k] for r in runs])) for k in ("cagr", "sharpe", "mdd")}
    refs["liq_all_H250"] = {k: st_all[k] for k in ("cagr", "sharpe", "mdd")}
    # placebo on the best arm
    best = max((a for a in ARMS if a != "avoid250"), key=lambda a: res[a]["sharpe"])
    rng = np.random.default_rng(M.SEED)
    pl = []
    spec = {"blue5": (s5, blue), "blue20": (s20, blue), "liq5_top3": (s5, liq), "hyst5_liq": (s5, liq), "hyst5_blue": (s5, blue),
            "hyst20_liq": (s20, liq), "blend_hyst": (blend, liq)}[best]
    for _ in range(M.N_PLACEBO):
        sh = spec[0].copy()
        for t in range(t0, len(dates)):
            idx = np.flatnonzero(spec[1][t] & np.isfinite(sh[t]))
            if len(idx) > 1:
                sh[t, idx] = sh[t, rng.permutation(idx)]
        if best.startswith("hyst") or best == "blend_hyst":
            R, _, _ = hysteresis(A, spec[1], sh, res[best]["k"], c_in, c_out, t_start=t0)
        else:
            R, _ = M.simulate(A, spec[1], sh, res[best]["H"], res[best]["k"], c_in, c_out, t_start=t0)
        pl.append(M.stats(R, dates, t0)["sharpe"])
    res[best]["placebo"] = {"n": M.N_PLACEBO, "pct": float((np.array(pl) < res[best]["sharpe"]).mean() * 100), "mean": float(np.mean(pl)), "max": float(np.max(pl))}
    M.log(f"placebo {best}: real {res[best]['sharpe']:.2f} vs shuffled mean {np.mean(pl):.2f} max {np.max(pl):.2f} -> pct {res[best]['placebo']['pct']:.0f}")
    for name in ARMS:
        r = res[name]
        if name == "avoid250":
            pos = sum(v > 0 for v in exc.values())
            r["verdict"] = (f"loser filter {'INFORMATIVE' if pos >= 4 else 'not informative'}: excess {r['excess_cagr'] * 100:+.1f} %/yr over the unfiltered "
                            f"LIQ book, positive {pos}/{len(exc)} years")
            continue
        fails = []
        if r["sharpe"] < M.BAR["sharpe"]:
            fails.append(f"sharpe {r['sharpe']:.2f} < 1.2")
        if r["mdd"] < M.BAR["mdd"]:
            fails.append(f"mdd {r['mdd'] * 100:.0f} % < -25 %")
        if r["years_pos"] < min(4, r["n_years"]):
            fails.append(f"{r['years_pos']}/{r['n_years']} years positive")
        if "placebo" in r and r["placebo"]["pct"] < 95:
            fails.append(f"placebo pct {r['placebo']['pct']:.0f}")
        r["verdict"] = ("CANDIDATE" if not fails else "not a candidate: " + "; ".join(fails))
    n_trials = N_BEFORE + len(ARMS)
    L = [f"# IDX menu ML-4b — cost-aware strategies on the prediction desk's scores — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
         f"Same OOS scores and costs as ML-4 (#151). Round trip: LIQ {np.nanmean((c_in + c_out)[liq]) * 1e4:.0f} bps, BLUE {np.nanmean((c_in + c_out)[blue]) * 1e4:.0f} bps. "
         f"Hysteresis books hold while the name stays in the top {HOLD_PCT * 100:.0f} % of the day's ranking, max {MAX_HOLD} days. Book 2022-01 -> {dates[-1].date()}.", "",
         "| arm | hold | K | trades | CAGR | Sharpe | mDD | years + | by year | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name in ARMS:
        r = res[name]
        by = " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items())
        pl_s = f" (placebo pct {r['placebo']['pct']:.0f})" if "placebo" in r else ""
        L.append(f"| {name} | {r['H']} | {r['k']} | {r['trades']:,} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['years_pos']}/{r['n_years']} | {by} | {r['verdict']}{pl_s} |")
    L += ["", "| reference | CAGR | Sharpe | mDD |", "|---|---|---|---|"]
    for name, r in refs.items():
        L.append(f"| {name} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % |")
    L += ["", "avoid250 excess by year vs the unfiltered LIQ book: " + " ".join(f"{y}:{v * 100:+.1f}" for y, v in exc.items()), "",
          "## Verdict (menu ML-4b, study stored)", "",
          f"Best arm by Sharpe: **{best}** ({res[best]['cagr'] * 100:+.1f} %/yr, Sharpe {res[best]['sharpe']:.2f}, mDD {res[best]['mdd'] * 100:.0f} %) - {res[best]['verdict']}.",
          f"Candidates: {', '.join(a for a in ARMS if res[a]['verdict'].startswith('CANDIDATE')) or 'none'}. {res['avoid250']['verdict']}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_STRATEGY2_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "bar": M.BAR, "hold_pct": HOLD_PCT,
                                                                       "max_hold": MAX_HOLD, "blue": [BLUE_VALUE, BLUE_PRICE], "source_study": "ml_strategy #151"},
                              summary={"arms": common.plain(res), "refs": common.plain(refs), "best": best}, names=[])
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
