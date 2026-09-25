#!/usr/bin/env python3
"""IDX menu 35 - is the 1-day model's dominant feature real or an artefact? (my own finding, 2026-09-25: `bo_imb`, the
closing bid/offer volume imbalance from idx.daily_summary, carries 15.4 % of the 1d champion's gain, roughly twice the
next feature; operator: "okay fix temuan2 mu").

`bo_imb = (bid_volume - offer_volume) / (bid_volume + offer_volume)` at the close. It is known at the 16:00 cut, so it is
PIT-legal, but a queue imbalance at one close need not survive to the next day's trading: the desk's microstructure menus
(28-33) found exactly this pattern - a real lead that is smaller than the spread. If the 1d model's IC rests on it, that
IC is not something a book can collect, and no book should ever be built on the 1d horizon.

PRE-REGISTERED (6 trials; cumulative 843 + 6 = 849). Panel, universe (LIQ = value60 >= Rp 5 bn, close >= 100), costs and
the walk-forward years are ML-4's (`idx_ml_strategy`), so the numbers sit beside every other ML study.
  A. Does the model need it? Walk-forward 1d `ret` models on the deployed feature set, fitted twice per test year:
       all        every feature (the deployed model)                                             (reference)
       no_boimb   the same, `bo_imb` dropped
     Read: mean daily rank IC on LIQ per year, and the difference. If dropping it costs little, the feature is decoration;
     if it costs a lot, the 1d IC IS the imbalance.
  B. Is the imbalance itself tradeable? Sort LIQ names by `bo_imb` at the close, K = 10, hold one day:
       boimb_c2c  buy at the next close (the price the model's label uses), sell the close after   (the label's world)
       boimb_o2c  buy at the next OPEN, sell that close                                            (what an operator can do)
       boimb_top  the same as c2c but only names in the top decile of |bo_imb|
     Net of the desk's costs (closing offer/bid + fees; ~91 bps round trip on LIQ). Gross is printed beside net so the
     cost, not the signal, is visible.
  C. Placebo for the best B arm: `bo_imb` shuffled within each day, 20 runs.
READING RULE: the feature is REAL AND USABLE only if a B arm is net positive with t >= 3 and placebo pct >= 95. If the B
arms are gross-positive but net-negative, the verdict is "real lead, not tradeable" - the same finding as menus 28-33, and
the 1d model stays a forecast. If A shows no IC loss when it is dropped, drop it from FEATURES.
READ-ONLY; one idx.study row. IDX_ML_CACHE (default tmp/ml_strategy_cache.pkl).
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
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common, daily  # noqa: E402

N_BEFORE = 843
STUDY = "boimb"
K = 10
BAR = {"t": 3.0, "placebo_pct": 95.0}
T0 = time.time()


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    return env["INGEST_DB_DSN"].strip().strip('"')


# ---- A: does the 1d model need bo_imb? ------------------------------------------------------------------------------------
def walk_forward_ic(P: pd.DataFrame, feats: list[str], label: str) -> dict[int, dict[str, float]]:
    cal = np.sort(pd.unique(P["d"]))
    days = P["d"].to_numpy()
    year = P["d"].dt.year.to_numpy()
    liq = P["liq"].to_numpy(bool)
    y = np.clip(P["fwd_1d"].to_numpy(float), -1.0, 1.0)
    X = common.to_matrix(P, feats)
    out: dict[int, dict[str, float]] = {}
    for Y in M.TEST_YEARS:
        cut = common.purge_cut(cal, np.datetime64(date(Y, 1, 1)), 1)
        fit_m = (days < cut) & np.isfinite(y) & liq
        val_m = (year == Y) & np.isfinite(y)
        if fit_m.sum() < 20000 or val_m.sum() < 1000:
            continue
        t = time.time()
        bst = common.fit(X[fit_m], y[fit_m], "ret", common.BASE_PARAMS["ret"], feats, seed=M.SEED + Y)
        pred = np.asarray(bst.predict(X[val_m]), dtype=float)
        ic, tt, k = common.cut_ic(days[val_m], pred, y[val_m], liq[val_m])
        out[Y] = {"ic": ic, "t": tt, "days": k}
        M.log(f"A {label} {Y}: daily IC(LIQ) {ic:.4f} (t {tt:.1f}, {k} d), fit {int(fit_m.sum()):,}, {time.time() - t:.0f} s")
    return out


# ---- B: is the imbalance itself tradeable? ---------------------------------------------------------------------------------
def one_day_book(rank: np.ndarray, mask: np.ndarray, A: np.ndarray, op: np.ndarray, raw: np.ndarray,
                 c_in: np.ndarray, c_out: np.ndarray, k: int, t0: int, entry: str = "close") -> tuple[np.ndarray, np.ndarray, int]:
    """Signal at close t -> buy at t+1 (close, or open), sell at the close of t+1 (open entry) or t+2 (close entry).
    -> (net daily returns, gross daily returns, trades). Equal weight 1/k of the sleeve, one day of exposure."""
    T, N = A.shape
    net = np.zeros(T)
    gross = np.zeros(T)
    trades = 0
    for t in range(t0, T - 2):
        ok = mask[t] & np.isfinite(rank[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        if len(cand) < k:
            continue
        pick = cand[np.argsort(-rank[t, cand], kind="stable")[:k]]
        w = 1.0 / k
        for j in pick:
            if entry == "close":
                if np.isnan(A[t + 2, j]):
                    continue
                g = A[t + 2, j] / A[t + 1, j] - 1
                n_ = (A[t + 2, j] / A[t + 1, j]) * (1 - c_out[t + 2, j]) / (1 + c_in[t + 1, j]) - 1
                net[t + 2] += w * n_
                gross[t + 2] += w * g
            else:                                                     # open entry, same-day close exit
                if op[t + 1, j] <= 0 or np.isnan(raw[t + 1, j]):
                    continue
                adj = A[t + 1, j] / raw[t + 1, j]                      # adjusted / raw on the day: corporate actions
                g = raw[t + 1, j] / op[t + 1, j] - 1
                n_ = (raw[t + 1, j] * (1 - c_out[t + 1, j])) / (op[t + 1, j] * (1 + c_in[t + 1, j])) - 1
                net[t + 1] += w * n_ * (adj / adj)
                gross[t + 1] += w * g
            trades += 1
    return net, gross, trades


def main() -> int:
    cache = os.environ.get("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
    P = pickle.load(open(cache, "rb"))
    M.log(f"panel from cache: {len(P):,} rows")
    if "bo_imb" not in P.columns or "fwd_1d" not in P.columns:
        need = [c for c in ("bo_imb", "fwd_1d", "open") if c not in P.columns]
        M.log(f"cache lacks {need}; rebuilding the panel from the DB")
        with psycopg.connect(dsn()) as conn:
            B = daily.fit_rows(daily.build_panel(conn))
        B["value60"] = np.expm1(B["lvalue60"].astype(float))
        B["liq"] = (B["value60"] >= M.LIQ_VALUE) & (B["close"] >= M.MIN_PRICE)
        keep = ["code", "d", "close", "open", "ac", "bid", "offer", "liq", "fwd_1d"] + daily.FEATURES
        P = B[[c for c in dict.fromkeys(keep) if c in B]].copy()
        pickle.dump(P, open(os.path.join(ROOT, "tmp", "boimb_panel.pkl"), "wb"), protocol=5)
    P = P[P["d"] >= "2020-01-01"].sort_values(["code", "d"]).reset_index(drop=True)

    # ---- A
    feats = list(daily.FEATURES)
    A_all = walk_forward_ic(P, feats, "all")
    A_no = walk_forward_ic(P, [f for f in feats if f != "bo_imb"], "no_boimb")

    # ---- B
    W = P[P["d"] >= "2021-06-01"]
    dates = M.wide(W, "close").index
    codes = M.wide(W, "close").columns
    g = lambda c: M.wide(W, c).reindex(index=dates, columns=codes)  # noqa: E731
    Aa, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    op = np.nan_to_num(g("open").to_numpy(float)) if "open" in W.columns else np.zeros_like(raw)
    c_in, c_out = M.costs(raw, np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float)))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    bo = g("bo_imb").to_numpy(float)
    t0 = int(np.searchsorted(dates, np.datetime64(date(2022, 1, 1))))
    top_mask = liq & (np.abs(bo) >= np.nanquantile(np.where(liq, np.abs(bo), np.nan), 0.9, axis=1, keepdims=True))
    arms = {"boimb_c2c": (bo, liq, "close"), "boimb_o2c": (bo, liq, "open"), "boimb_top": (bo, top_mask, "close")}
    res: dict[str, dict] = {}
    for name, (rank, mask, entry) in arms.items():
        if entry == "open" and not op.any():
            M.log(f"B {name}: no open prices in the panel, skipped")
            continue
        net, gross, n = one_day_book(rank, mask, Aa, op, raw, c_in, c_out, K, t0, entry)
        st = M.stats(net, dates, t0)
        stg = M.stats(gross, dates, t0)
        r = net[t0:]
        res[name] = {**st, "trades": n, "gross_cagr": stg["cagr"], "gross_sharpe": stg["sharpe"],
                     "mean_bps": float(np.mean(r) * 1e4), "t": float(np.mean(r) / np.std(r) * np.sqrt(len(r))) if np.std(r) > 0 else float("nan")}
        M.log(f"B {name:<11} net CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.0f} % | gross CAGR {stg['cagr'] * 100:6.1f} % "
              f"| {n:,} trades, mean {res[name]['mean_bps']:+.1f} bps/day t {res[name]['t']:.1f}")

    # ---- C placebo on the best net arm
    best = max(res, key=lambda a: res[a]["sharpe"]) if res else None
    if best:
        rng = np.random.default_rng(M.SEED)
        rank, mask, entry = arms[best]
        pl = []
        for _ in range(M.N_PLACEBO):
            sh = rank.copy()
            for t in range(t0, len(dates)):
                idx = np.flatnonzero(mask[t] & np.isfinite(sh[t]))
                if len(idx) > 1:
                    sh[t, idx] = sh[t, rng.permutation(idx)]
            net, _, _ = one_day_book(sh, mask, Aa, op, raw, c_in, c_out, K, t0, entry)
            pl.append(M.stats(net, dates, t0)["sharpe"])
        res[best]["placebo"] = {"n": M.N_PLACEBO, "pct": float((np.array(pl) < res[best]["sharpe"]).mean() * 100), "mean": float(np.mean(pl))}
        M.log(f"C placebo {best}: real {res[best]['sharpe']:.2f} vs shuffled mean {np.mean(pl):.2f} -> pct {res[best]['placebo']['pct']:.0f}")

    for name, r in res.items():
        fails = []
        if not (r["mean_bps"] > 0):
            fails.append(f"net {r['mean_bps']:+.1f} bps/day")
        if not (r["t"] >= BAR["t"]):
            fails.append(f"t {r['t']:.1f} < 3")
        if "placebo" in r and r["placebo"]["pct"] < BAR["placebo_pct"]:
            fails.append(f"placebo pct {r['placebo']['pct']:.0f}")
        r["usable"] = not fails
        r["verdict"] = "USABLE" if not fails else "no: " + "; ".join(fails)

    yrs = sorted(set(A_all) | set(A_no))
    d_ic = {Y: (A_all.get(Y, {}).get("ic", float("nan")) - A_no.get(Y, {}).get("ic", float("nan"))) for Y in yrs}
    n_trials = N_BEFORE + 6
    L = [f"# IDX menu 35 - is `bo_imb` (the closing book imbalance) real or an artefact? - {date.today()} - 6 trials, cumulative N = {n_trials}", "",
         "`bo_imb` carries 15.4 % of the 1d champion's gain, about twice the next feature. A: does the model lose IC without it? "
         "B: can the imbalance itself be traded after IDX costs? Panel, universe and costs as ML-4.", "",
         "## A. The 1d model with and without the feature (daily rank IC on LIQ)", "",
         "| year | all features | without bo_imb | difference |", "|---|---|---|---|"]
    for Y in yrs:
        a, b = A_all.get(Y, {}), A_no.get(Y, {})
        L.append(f"| {Y} | {a.get('ic', float('nan')):.4f} (t {a.get('t', float('nan')):.1f}) | {b.get('ic', float('nan')):.4f} (t {b.get('t', float('nan')):.1f}) | {d_ic[Y]:+.4f} |")
    L.append(f"| mean | {np.nanmean([A_all[y]['ic'] for y in A_all]):.4f} | {np.nanmean([A_no[y]['ic'] for y in A_no]):.4f} | "
             f"{np.nanmean(list(d_ic.values())):+.4f} |")
    L += ["", "## B. Trading the imbalance directly (K 10, one day, net of closing offer/bid + fees)", "",
          "| arm | trades | net CAGR | net Sharpe | mean bps/day | t | gross CAGR | verdict |", "|---|---|---|---|---|---|---|---|"]
    for name, r in res.items():
        pl_s = f" (placebo pct {r['placebo']['pct']:.0f})" if "placebo" in r else ""
        L.append(f"| {name} | {r['trades']:,} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mean_bps']:+.1f} | {r['t']:.1f} | "
                 f"{r['gross_cagr'] * 100:+.1f} % | {r['verdict']}{pl_s} |")
    usable = [n for n, r in res.items() if r["usable"]]
    loss = float(np.nanmean(list(d_ic.values())))
    L += ["", "## Verdict (menu 35, study stored)", "",
          f"Tradeable arms: {', '.join(usable) or 'none'}. Dropping `bo_imb` changes the 1d model's daily IC by {loss:+.4f} on average "
          f"({'the feature carries the IC' if loss > 0.01 else 'the model barely notices'}).",
          "", "What this means for the desk: the 1d horizon stays a forecast. " +
          ("A book on it would be collecting a spread it has to pay." if not usable else "One arm cleared the bar - re-read it before believing it.")]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_BOIMB_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    json.dump({"A_all": A_all, "A_no": A_no, "B": common.plain(res)}, open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(dsn()) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(arms) + ["all", "no_boimb", "placebo"], "n_trials_cumulative": n_trials,
                                                                 "k": K, "bar": BAR}, summary={"A_all": A_all, "A_no": A_no, "B": common.plain(res),
                                                                                               "usable": usable, "ic_delta": loss},
                              names=[], report_path=out, note="menu 35: is the 1d model's dominant feature (closing book imbalance) tradeable?")
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
