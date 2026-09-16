#!/usr/bin/env python3
"""IDX doublers — second opinion (Fable, 2026-09-17): every feature weighed at once, validated out-of-sample by year.

Pre-registered before the first run:
  panel      research-scratch/idx-screen/doublers_panel_2026-09-17.csv (the idx_doublers.py panel: 22 quarterly PIT snapshots)
  features   within-date percentiles of the 15 quintile features + flags (turnaround, gate_strict, gate_loose) + the 5 screen
             memberships; a missing percentile = 0.5, a missing flag = 0
  target     touched2x_24m (primary), end2x_24m (secondary)
  model 1    logistic regression, L2 (lambda 1.0 on standardized inputs), numpy Newton steps          -> trial 195
  model 2    LightGBM if importable (depth 3, 300 rounds, lr 0.03, min_child 30), else skipped         -> trial 196
  validation leave-one-snapshot-year-out (2020..2024): AUC, hit rate of the top decile and of the top 8 per date vs the
             year's base rate. A model "passes" when the OOS top-decile lift >= 1.5 in >= 4 of 5 years.
  today      fit on every complete window, score the 2026-09-16 snapshot, list the top 20 with probabilities, SSIA's rank.
Output: research-scratch/idx-screen/doublers_model_2026-09-17.md/.json; stored as study `doublers_model` with --store.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_doublers as X  # noqa: E402

PANEL = os.path.join(X.VQ.OUTDIR, "doublers_panel_2026-09-17.csv")
OUT_MD = os.path.join(X.VQ.OUTDIR, "doublers_model_2026-09-17.md")
OUT_JSON = os.path.join(X.VQ.OUTDIR, "doublers_model_2026-09-17.json")
PCT = [f"{f}_pct" for f in X.QUINT_FEATURES]
FLAGS = ["turnaround", "gate_strict", "gate_loose"]
SCREENS = ["A_cheap_growth", "B_beaten_value", "C_small_quality", "D_turnaround", "E_accel_cheap"]


def design(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(index=df.index)
    for c in PCT:
        d[c] = df[c].astype(float).fillna(0.5)
    for c in FLAGS:
        d[c] = df[c].fillna(False).astype(float)
    m = X.screens(df)
    for c in SCREENS:
        d[c] = m[c].astype(float)
    return d


def logit_fit(Xm: np.ndarray, y: np.ndarray, lam: float = 1.0, iters: int = 50) -> tuple[np.ndarray, float]:
    mu, sd = Xm.mean(0), Xm.std(0) + 1e-9
    Z = (Xm - mu) / sd
    Z1 = np.hstack([np.ones((len(Z), 1)), Z])
    w = np.zeros(Z1.shape[1])
    R = lam * np.eye(Z1.shape[1])
    R[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Z1 @ w))
        g = Z1.T @ (p - y) + R @ w
        H = (Z1 * (p * (1 - p))[:, None]).T @ Z1 + R
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w, (mu, sd)


def logit_predict(w, norm, Xm: np.ndarray) -> np.ndarray:
    mu, sd = norm
    Z1 = np.hstack([np.ones((len(Xm), 1)), (Xm - mu) / sd])
    return 1 / (1 + np.exp(-Z1 @ w))


def auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")


def evaluate(name: str, fit, predict, D: pd.DataFrame, df: pd.DataFrame, target: str) -> dict:
    ok = df[target].notna()
    D, df = D[ok], df[ok]
    y = df[target].astype(float).values
    years = df["D"].dt.year.values
    out = {"model": name, "target": target, "years": {}}
    passes = 0
    for yr in sorted(set(years)):
        tr, te = years != yr, years == yr
        model = fit(D[tr].values, y[tr])
        p = predict(model, D[te].values)
        yt = y[te]
        base = yt.mean()
        dec = p >= np.quantile(p, 0.9)
        top8 = pd.Series(p, index=df.index[te]).groupby(df["D"][te]).rank(ascending=False) <= 8
        lift = yt[dec].mean() / base if base else float("nan")
        out["years"][int(yr)] = {"n": int(te.sum()), "base": float(base), "auc": auc(yt, p), "top_decile_hit": float(yt[dec].mean()),
                                 "top_decile_lift": float(lift), "top8_per_date_hit": float(yt[top8.values].mean())}
        passes += int(lift >= 1.5)
    out["passes"] = f"{passes}/{len(out['years'])}"
    return out


def main():
    df = pd.read_csv(PANEL, parse_dates=["D"])
    D = design(df)
    models = {}
    models["logistic"] = (lambda Xm, y: logit_fit(Xm, y), lambda m, Xm: logit_predict(m[0], m[1], Xm))
    try:
        import lightgbm as lgb
        def lgb_fit(Xm, y):
            return lgb.train({"objective": "binary", "max_depth": 3, "num_leaves": 7, "learning_rate": 0.03, "min_data_in_leaf": 30,
                              "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1, "seed": 7},
                             lgb.Dataset(Xm, label=y), num_boost_round=300)
        models["lightgbm"] = (lgb_fit, lambda m, Xm: m.predict(Xm))
    except ImportError:
        print("lightgbm not importable: model 2 skipped")
    results = []
    for name, (fit, predict) in models.items():
        for target in ("touched2x_24m", "end2x_24m"):
            r = evaluate(name, fit, predict, D, df, target)
            results.append(r)
            print(f"{name:9s} {target:14s} passes {r['passes']} | " + " ".join(f"{y}: auc {v['auc']:.2f} top10% {v['top_decile_hit']:.0%} (base {v['base']:.0%}, lift {v['top_decile_lift']:.1f}) top8/date {v['top8_per_date_hit']:.0%}" for y, v in r["years"].items()))
    # coefficients of the logistic model on the full panel (standardized) - which features carry the weight
    ok = df["touched2x_24m"].notna()
    w, norm = logit_fit(D[ok].values, df.loc[ok, "touched2x_24m"].astype(float).values)
    coefs = sorted(zip(D.columns, w[1:], strict=True), key=lambda t: -abs(t[1]))
    print("\nlogistic weights (standardized):", ", ".join(f"{c} {v:+.2f}" for c, v in coefs[:12]))
    # today
    conn = X.VQ.connect()
    close, _v, _dl, _dv, _ix = X.VQ.load(conn)
    fund = X.load_fundamentals(conn)
    t = X.add_quintiles(X.features_at(conn, fund, close.index[-1], close))
    Dt = design(t)
    t["p_logit"] = logit_predict(w, norm, Dt.values)
    if "lightgbm" in models:
        fit, predict = models["lightgbm"]
        mdl = fit(D[ok].values, df.loc[ok, "touched2x_24m"].astype(float).values)
        t["p_lgb"] = predict(mdl, Dt.values)
        t["p"] = (t["p_logit"] + t["p_lgb"]) / 2
    else:
        t["p"] = t["p_logit"]
    t = t.sort_values("p", ascending=False).reset_index(drop=True)
    t["rank"] = t.index + 1
    cols = ["rank", "code", "sector", "p", "p_logit"] + (["p_lgb"] if "p_lgb" in t else []) + ["mcap", "ep_ttm", "q_np_yoy", "q_rev_yoy", "accel", "dist_high", "mom", "turnaround", "gate_strict"]
    top = t.head(25)[cols]
    print(f"\nTODAY {close.index[-1].date()} — top 25 by model probability of touching 2x within 24 months (base 17%)")
    for r in top.itertuples(index=False):
        print(f"{r.rank:3d} {r.code:5s} {r.sector[:16]:16s} p={r.p:.0%} (logit {r.p_logit:.0%}" + (f", lgb {r.p_lgb:.0%}" if "p_lgb" in t else "") +
              f") mcap {r.mcap/1e12:6.2f}T E/P {r.ep_ttm if r.ep_ttm == r.ep_ttm else float('nan'):+6.1%} npYoY {r.q_np_yoy if r.q_np_yoy == r.q_np_yoy else float('nan'):+7.0%} revYoY {r.q_rev_yoy if r.q_rev_yoy == r.q_rev_yoy else float('nan'):+6.0%} accel {r.accel if r.accel == r.accel else float('nan'):+7.0%} hi {r.dist_high:+.0%} mom {r.mom if r.mom == r.mom else float('nan'):+.0%} {'T' if r.turnaround else ' '}{'S' if r.gate_strict else ' '}")
    for code in ("SSIA", "BULL", "MBMA", "KOTA", "DMAS", "GJTL", "INKP", "TKIM", "MDKA", "AMMN"):
        row = t[t.code == code]
        if len(row):
            print(f"   {code}: rank {int(row['rank'].iloc[0])} of {len(t)}, p={row['p'].iloc[0]:.0%}")
    json.dump({"validation": results, "weights": coefs, "today": top.to_dict(orient="records")}, open(OUT_JSON, "w"), indent=1, default=str)
    t.to_csv(os.path.join(X.VQ.OUTDIR, "doublers_model_today_2026-09-17.csv"), index=False)
    if "--store" in sys.argv:
        from blackheart_ingest.idx import research_store as rs
        names = [{"code": r.code, "screens": [], "score": float(r.p), "rank": int(r.rank),
                  "features": {k: (None if pd.isna(getattr(r, k)) else getattr(r, k)) for k in ("mcap", "ep_ttm", "q_np_yoy", "q_rev_yoy", "accel", "dist_high", "mom", "turnaround", "gate_strict")},
                  "context": {"p_logit": float(r.p_logit), **({"p_lgb": float(r.p_lgb)} if "p_lgb" in t else {})}} for r in t.head(40).itertuples(index=False)]
        sid = rs.record_study(conn, "doublers_model", close.index[-1].date(), params={"models": list(models), "trials": [195, 196][:len(models)], "n_trials_cumulative": 194 + len(models)},
                              summary={"validation": results, "weights": coefs[:20]}, names=names, report_path="research/IDX_DOUBLERS_2026-09-17.md",
                              note="second opinion: logistic + lightgbm on the same PIT panel, leave-one-year-out")
        print("stored study #", sid)


if __name__ == "__main__":
    main()
