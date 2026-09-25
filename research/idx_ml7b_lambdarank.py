#!/usr/bin/env python3
"""IDX menu ML-7b — the lambdarank 5d score through the cost-aware book (operator, 2026-09-25: "okay lakukan 1 dan 2").

ML-7 (study #173) found that a LightGBM trained with the lambdarank objective (grouped by day, relevance = within-day
quintile of the 5-day return) is the best 5d ranker on the metric a book can use - the daily rank IC on LIQ names: mean
0.110 vs 0.085 for the deployed return regression, 5/5 years >= base, t 14-19 - and that it collapses at 20d/250d. ML-6
(studies #154-157) found that the SAME 5d regression score, used cost-aware (expected excess in bps vs margin x the name's
round trip; hold until the score turns negative AND a better name pays for the swap; EMA-3), earns +29.1 %/yr Sharpe 0.91
mDD -51 % (K 10) and +41.6 %/1.04/-61 % (K 5), 4/5 years, placebo pct 100. This menu asks whether the better ranker makes
that book better.

PRE-REGISTERED (5 trials; cumulative 821 + 5 = 826). Universe, costs, panel, walk-forward years and the position book are
ML-4's / ML-6's, unchanged (IDX_ML_CACHE, `idx_ml_costaware.book`); the only new ingredient is the score:
  lr5    lambdarank 5d, fitted walk-forward per test year on LIQ rows before the (purged) cut, 3 seeds averaged
         (BASE_PARAMS['ret'] with objective=lambdarank, label_gain 0..4, truncation 100). Its score is only comparable
         within a day, so it enters the book as ML-6's rank5 did: that day's LIQ percentile minus 0.5, scaled to
         log-return units by the training years' realised top-minus-bottom decile spread of the 5d return.
  arms (score | margin | ema | K):
         lr5|2|3|10   lr5|2|3|5   lr5|1|3|10   lr5|2|1|10
         lrblend|2|3|10 = mean of the lr5 expectation and ML-6's e5 (both in log-return units)
  references (same run, not trials): e5|2|3|10 and e5|2|3|5 = ML-6's numbers, recomputed from the cached scores.
  Also reported: the per-year daily rank IC on LIQ of lr5 vs s5 on this universe (the ML-7 finding, replicated on ML-4's
  fit mask), and the day-to-day rank autocorrelation (churn).
READING RULE (ML-6's): CANDIDATE = Sharpe >= 1.2, mDD >= -25 %, >= 4/5 years positive, placebo pct >= 95 (20 within-day
  shuffles of the score, best arm). BETTER than the reference with the same K = Sharpe >= ref + 0.15 AND CAGR >= 0.8 x ref
  AND drawdown not deeper. A BETTER arm replaces the ML sleeve's score only by the operator's decision (the combined live book
  runs the regression score today).
READ-ONLY; one idx.study row. IDX_ML_CACHE (default tmp/ml_strategy_cache.pkl); lr5 scores cached in tmp/ml7b_lr5.pkl.
    blackheart-ingest/.venv/Scripts/python research/idx_ml7b_lambdarank.py
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
import time
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
from blackheart_ingest.idx.ml import common, daily  # noqa: E402

N_BEFORE = 821
STUDY = "ml7b_lambdarank"
ARMS = ["lr5|2|3|10", "lr5|2|3|5", "lr5|1|3|10", "lr5|2|1|10", "lrblend|2|3|10"]
REFS = ["e5|2|3|10", "e5|2|3|5"]
SEEDS = [20260924, 20260925, 20260926]
BAR = {"sharpe": 1.2, "mdd": -0.25, "years_pos": 4, "placebo_pct": 95.0, "better_sharpe": 0.15, "better_cagr": 0.8}


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    return env["INGEST_DB_DSN"].strip().strip('"')


# ---- the lambdarank walk-forward ------------------------------------------------------------------------------------------------
def lambdarank_scores(P: pd.DataFrame) -> pd.DataFrame:
    """-> (code, d, lr5, lr5_scale): the 3-seed lambdarank score per name-day of each test year, and the training years'
    realised decile spread (log return) that turns a percentile gap into an expectation."""
    import lightgbm as lgb
    feats = daily.FEATURES
    P = P.sort_values(["code", "d"]).reset_index(drop=True)
    cal = np.sort(pd.unique(P["d"]))
    days = P["d"].to_numpy()
    year = P["d"].dt.year.to_numpy()
    liq = P["liq"].to_numpy(bool)
    fwd = P["fwd_5d"].to_numpy(float)
    rel_all = (P.groupby("d")["fwd_5d"].rank(pct=True, method="first") * 5).clip(upper=4.999).to_numpy()
    X = common.to_matrix(P, feats)
    out = P[["code", "d"]].copy()
    out["lr5"] = np.nan
    out["lr5_scale"] = np.nan
    params = {k: v for k, v in common.BASE_PARAMS["ret"].items() if k not in ("rounds", "alpha")}
    params.update({"objective": "lambdarank", "label_gain": [0, 1, 2, 3, 4], "lambdarank_truncation_level": 100, "metric": "None",
                   "num_threads": 14})
    for Y in M.TEST_YEARS:
        cut = common.purge_cut(cal, np.datetime64(date(Y, 1, 1)), 5)
        fit_m = (days < cut) & np.isfinite(fwd) & liq
        test_m = year == Y
        if fit_m.sum() < 20000 or test_m.sum() == 0:
            continue
        t0 = time.time()
        idx = np.flatnonzero(fit_m)
        order = idx[np.argsort(days[idx], kind="stable")]
        d_sorted = days[order]
        sizes = np.diff(np.flatnonzero(np.r_[True, d_sorted[1:] != d_sorted[:-1], True]))
        # relevance = within-day quintile among the FIT rows (LIQ names), recomputed on that subset
        F = pd.DataFrame({"d": d_sorted, "y": fwd[order]})
        rel = (F.groupby("d")["y"].rank(pct=True, method="first") * 5).clip(upper=4.999).astype(int).to_numpy()
        preds = []
        for s in SEEDS:
            ds = lgb.Dataset(X[order], rel, group=sizes, feature_name=feats, free_raw_data=True)
            bst = lgb.train({**params, "seed": s}, ds, 300)
            preds.append(np.asarray(bst.predict(X[test_m]), dtype=float))
        out.loc[test_m, "lr5"] = np.mean(preds, axis=0)
        q = F.groupby("d")["y"].transform(lambda s: s.rank(pct=True))
        spread = float(F.loc[q >= 0.9, "y"].mean() - F.loc[q <= 0.1, "y"].mean())
        out.loc[test_m, "lr5_scale"] = spread
        M.log(f"lambdarank {Y}: fit {int(fit_m.sum()):,} LIQ rows (cut {pd.Timestamp(cut).date()}), scored {int(test_m.sum()):,}, "
              f"training decile spread {spread * 1e4:+.0f} bps, {time.time() - t0:.0f} s")
    return out


def yearly_ic(P: pd.DataFrame, col: str) -> dict[int, dict[str, float]]:
    """Per test year: mean daily rank IC on LIQ names of ``col`` vs fwd_5d, its t, and the day-to-day rank autocorrelation."""
    out = {}
    L = P[P["liq"] & P[col].notna() & P["fwd_5d"].notna()]
    for Y in M.TEST_YEARS:
        S = L[L["d"].dt.year == Y]
        if len(S) < 1000:
            continue
        ic, t, k = common.cut_ic(S["d"].to_numpy(), S[col].to_numpy(float), S["fwd_5d"].to_numpy(float))
        W = S.pivot_table(index="d", columns="code", values=col).sort_index().rank(axis=1, pct=True)
        ac = [np.corrcoef(a[ok], b[ok])[0, 1] for a, b in zip(W.to_numpy()[:-1], W.to_numpy()[1:])
              if (ok := np.isfinite(a) & np.isfinite(b)).sum() >= 30]
        out[Y] = {"ic": ic, "t": t, "days": k, "churn": float(np.nanmean(ac)) if ac else float("nan")}
    return out


# ---- main ----------------------------------------------------------------------------------------------------------------------
def main() -> int:
    cache = os.environ.get("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
    P = pickle.load(open(cache, "rb"))
    M.log(f"panel + ML-4 scores from cache: {len(P):,} rows")
    lr_cache = os.path.join(ROOT, "tmp", "ml7b_lr5.pkl")
    if os.path.exists(lr_cache):
        LR = pickle.load(open(lr_cache, "rb"))
    else:
        LR = lambdarank_scores(P)
        pickle.dump(LR, open(lr_cache, "wb"), protocol=5)
    P = P.merge(LR, on=["code", "d"], how="left")
    ic_lr, ic_s5 = yearly_ic(P, "lr5"), yearly_ic(P, "s5")
    for Y in ic_lr:
        M.log(f"IC {Y}: lr5 {ic_lr[Y]['ic']:.3f} (t {ic_lr[Y]['t']:.1f}, churn {ic_lr[Y]['churn']:.2f})  s5 {ic_s5[Y]['ic']:.3f} "
              f"(t {ic_s5[Y]['t']:.1f}, churn {ic_s5[Y]['churn']:.2f})")

    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    c_in, c_out = M.costs(g("close").to_numpy(float), g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    t0 = int(np.searchsorted(dates, np.datetime64(C.FROM)))

    S5 = g("s5").to_numpy(float)
    e5 = S5 - np.nanmedian(np.where(liq, S5, np.nan), axis=1, keepdims=True)
    LR5 = g("lr5").to_numpy(float)
    pct = pd.DataFrame(np.where(liq, LR5, np.nan)).rank(axis=1, pct=True).to_numpy()
    scale = g("lr5_scale").max(axis=1).ffill().to_numpy(float)[:, None]
    e_lr = (pct - 0.5) * scale
    e_blend = np.where(np.isfinite(e_lr) & np.isfinite(e5), (e_lr + e5) / 2, np.nan)
    SRC = {"lr5": e_lr, "lrblend": e_blend, "e5": e5}

    res: dict[str, dict] = {}
    for arm in REFS + ARMS:
        name, margin, span, k = arm.split("|")
        margin, span, k = float(margin), int(span), int(k)
        R, n, hold = C.book(A, liq, C.ema(SRC[name], span), k, c_in, c_out, margin, t_start=t0)
        st = M.stats(R, dates, t0)
        res[arm] = {**st, "trades": n, "hold_days": hold, "turnover_per_year": n / st["years"] / k}
        M.log(f"{arm:<15} CAGR {st['cagr'] * 100:6.1f} %  Sharpe {st['sharpe']:5.2f}  mDD {st['mdd'] * 100:6.1f} %  trades {n:,} hold {hold:.0f} d  "
              f"years+ {st['years_pos']}/{st['n_years']}  " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
    best = max(ARMS, key=lambda a: res[a]["sharpe"])
    name, margin, span, k = best.split("|")
    rng = np.random.default_rng(M.SEED)
    pl = []
    for i in range(M.N_PLACEBO):
        sh = SRC[name].copy()
        for t in range(t0, len(dates)):
            idx = np.flatnonzero(liq[t] & np.isfinite(sh[t]))
            if len(idx) > 1:
                sh[t, idx] = sh[t, rng.permutation(idx)]
        R, _, _ = C.book(A, liq, C.ema(sh, int(span)), int(k), c_in, c_out, float(margin), t_start=t0)
        pl.append(M.stats(R, dates, t0)["sharpe"])
    res[best]["placebo"] = {"n": M.N_PLACEBO, "pct": float((np.array(pl) < res[best]["sharpe"]).mean() * 100), "mean": float(np.mean(pl)), "max": float(np.max(pl))}
    M.log(f"placebo {best}: real {res[best]['sharpe']:.2f} vs shuffled mean {np.mean(pl):.2f} max {np.max(pl):.2f} -> pct {res[best]['placebo']['pct']:.0f}")

    for arm in ARMS:
        r = res[arm]
        ref = res["e5|2|3|5" if arm.endswith("|5") else "e5|2|3|10"]
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
        r["better"] = (r["sharpe"] >= ref["sharpe"] + BAR["better_sharpe"] and r["cagr"] >= BAR["better_cagr"] * ref["cagr"] and r["mdd"] >= ref["mdd"])
        r["verdict"] = ("CANDIDATE" if not fails else "not a candidate: " + "; ".join(fails)) + (" | BETTER than ML-6 ref" if r["better"] else " | not better than ML-6 ref")

    n_trials = N_BEFORE + len(ARMS)
    L = [f"# IDX menu ML-7b — lambdarank 5d through the cost-aware book — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
         "Same universe (LIQ), costs, panel, walk-forward years and position book as ML-6 (`idx_ml_costaware.book`); the score is the 3-seed "
         "lambdarank 5d percentile gap scaled by the training years' decile spread. References e5|... are ML-6's arms recomputed here.", "",
         "## Ranking accuracy on this universe: daily rank IC on LIQ vs the 5d return (t) | churn = day-to-day rank corr", "",
         "| year | lr5 | s5 (deployed regression) |", "|---|---|---|"]
    for Y in ic_lr:
        a, b = ic_lr[Y], ic_s5.get(Y, {})
        L.append(f"| {Y} | {a['ic']:.3f} ({a['t']:.1f}) c{a['churn']:.2f} | {b.get('ic', float('nan')):.3f} ({b.get('t', float('nan')):.1f}) c{b.get('churn', float('nan')):.2f} |")
    L += ["", "## The book", "", "| arm (score, margin, ema, K) | trades | hold d | turns/yr/slot | CAGR | Sharpe | mDD | years + | by year | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for arm in REFS + ARMS:
        r = res[arm]
        by = " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items())
        pl_s = f" (placebo pct {r['placebo']['pct']:.0f})" if "placebo" in r else ""
        L.append(f"| {arm} | {r['trades']:,} | {r['hold_days']:.0f} | {r['turnover_per_year']:.1f} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | "
                 f"{r['mdd'] * 100:.0f} % | {r['years_pos']}/{r['n_years']} | {by} | {r.get('verdict', 'reference')}{pl_s} |")
    better = [a for a in ARMS if res[a]["better"]]
    cands = [a for a in ARMS if res[a]["candidate"]]
    L += ["", "## Verdict (menu ML-7b, study stored)", "",
          f"Best arm: **{best}** ({res[best]['cagr'] * 100:+.1f} %/yr, Sharpe {res[best]['sharpe']:.2f}, mDD {res[best]['mdd'] * 100:.0f} %, hold "
          f"{res[best]['hold_days']:.0f} d) - {res[best]['verdict']}.",
          f"CANDIDATES (ML-6 bar): {', '.join(cands) or 'none'}. BETTER than the ML-6 reference with the same K: {', '.join(better) or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML7B_LAMBDARANK_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    json.dump({"arms": common.plain(res), "ic": {"lr5": ic_lr, "s5": ic_s5}, "best": best}, open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(dsn()) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ARMS, "refs": REFS, "n_trials_cumulative": n_trials, "bar": BAR,
                                                                 "seeds": SEEDS, "max_hold": C.MAX_HOLD, "from": str(C.FROM)},
                              summary={"arms": common.plain(res), "best": best, "ic": {"lr5": ic_lr, "s5": ic_s5}, "better": better, "candidates": cands},
                              names=[], report_path=out, note="ML-7b: lambdarank 5d score through the ML-6 cost-aware book")
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
