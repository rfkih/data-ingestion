#!/usr/bin/env python3
"""IDX — the doublers (2026-09-13). Which names rose more than 100 % within one to two years, what did they look like
BEFORE the run, and can a statistical model see them coming?

PRE-REGISTERED (written before the run; one model, one label, one evaluation; cumulative trials 109 + 1 = 110).

Sample. The bar table from 2020-01 (989 names, delisted included, so no survivorship in the universe) and the
point-in-time fundamentals used by the desk (audited year, published-date discipline). One snapshot on the first trading
day of each month from 2021-01 to 2025-09; the universe at a snapshot is the desk's liquid pool (boards Utama/Pengembangan,
60-day median value above the floor) as candidates.build() sees it that day. Every feature is known at the snapshot close.

Labels (forward, from the snapshot close, adjusted prices; a delisted name stays at its last close):
    touch12   the close reaches 2x within the next 252 bars   (the model's label)
    touch24   the close reaches 2x within the next 504 bars   (descriptive: "within 1-2 years")
    fwd12     the plain 252-bar return                        (what a buyer at the snapshot got)

Features. Valuation: E/P, B/P, DY, P/E of the audited year. Quality: ROE, D/E, cash conversion, profit and revenue growth.
Price: 1/3/6/12-1-month returns, 60-day volatility, drawdown from the 252-day high, rise from the 252-day low.
Size and trading: log market cap, log 60-day median value, turnover (value / mcap), 20-day foreign net share. Sector.

Model. LightGBM binary classifier, fixed parameters (15 leaves, 300 trees, learning rate 0.03, min 50 rows per leaf,
80 % feature and row sampling), and an L2 logistic regression on standardised features for the signs. Walk-forward by
test year with a 12-month purge: a test snapshot in year Y is scored by a model trained only on snapshots whose label
window closed before that snapshot (snapshot date <= test date - 252 bars). Test years 2023, 2024, 2025.

Evaluation. Per test year: base rate, AUC, hit rate and lift of the top decile, and the realised 12-month return of the
ten highest-scored names at each snapshot (equal weight) against the universe mean. READING RULE: the model is a finding
worth building on only if the top-decile lift is above 2x in every test year AND the top-ten's 12-month return beats the
universe mean in at least two of three years. Otherwise the descriptive tables are the result and the model is recorded as
not predictive.

Why they rose. For every doubler with an audited profit at both ends of its 12-month window, the price move is split into
earnings growth and P/E re-rating (P1/P0 = E1/E0 x PE1/PE0); names that went from a loss to a profit are their own class.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_multibagger.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import UTC, datetime

import lightgbm as lgb
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402

OUT = os.path.join(VQ.OUTDIR, "multibagger_results.json")
FEATURES = ["ep", "bp", "dy", "pe", "roe", "der", "conv", "np_yoy", "rev_yoy", "r1m", "r3m", "r6m", "mom", "vol60", "dd252", "up_low252",
            "log_mcap", "log_v60", "turnover", "f20"]
CAT = ["sector"]
PARAMS = {"objective": "binary", "num_leaves": 15, "learning_rate": 0.03, "min_data_in_leaf": 50,
          "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1, "seed": 7}
ROUNDS = 300
PANEL = os.path.join(VQ.OUTDIR, "multibagger_panel.parquet")
# the listing table carries two sector codings (the old numbered JASICA classes and the IDX-IC letters)
SECTOR = {"1": "Agriculture (old)", "2": "Mining (old)", "3": "Basic industry (old)", "4": "Misc industry (old)", "5": "Consumer goods (old)",
          "6": "Property (old)", "7": "Infrastructure (old)", "8": "Finance (old)", "9": "Trade & services (old)",
          "A": "Energy", "B": "Basic materials", "C": "Industrials", "D": "Consumer non-cyclicals", "E": "Consumer cyclicals", "F": "Healthcare",
          "G": "Financials", "H": "Property", "I": "Technology", "J": "Infrastructure", "K": "Transportation", "?": "unknown"}
TEST_YEARS = (2023, 2024, 2025)


def f(v):
    return float(v) if v is not None else np.nan


def auc(y: np.ndarray, s: np.ndarray) -> float:
    """Mann-Whitney AUC."""
    order = np.argsort(s)
    ranks = np.empty(len(s))
    ranks[order] = np.arange(1, len(s) + 1)
    # ties: average ranks
    _, inv, counts = np.unique(s, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=ranks)
    ranks = sums[inv] / counts[inv]
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def logistic_fit(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 50) -> np.ndarray:
    """IRLS with an L2 penalty on standardised features; returns the coefficient vector (intercept first)."""
    Xb = np.hstack([np.ones((len(X), 1)), X])
    w = np.zeros(Xb.shape[1])
    R = l2 * np.eye(Xb.shape[1])
    R[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ w))
        W = p * (1 - p)
        H = (Xb * W[:, None]).T @ Xb + R
        g = Xb.T @ (y - p) - R @ w
        step = np.linalg.solve(H, g)
        w = w + step
        if np.abs(step).max() < 1e-6:
            break
    return w


def build_panel(conn, close: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    idx = close.index
    logr = np.log(close / close.shift(1))
    hi252 = close.rolling(252, min_periods=120).max()
    lo252 = close.rolling(252, min_periods=120).min()
    vol60 = logr.rolling(60, min_periods=40).std() * math.sqrt(252)
    ff = close.ffill()
    snaps = [d for d in TO.month_starts(idx, pd.Timestamp("2021-01-01"), pd.Timestamp("2025-09-30"))]
    rows = []
    for D in snaps:
        i = idx.get_loc(D)
        if i + 252 > len(idx) - 1:
            break
        cands = cand.build(conn, D.date())["all_rows"]
        c0 = close.loc[D]
        j12 = min(i + 252, len(idx) - 1)
        j24 = min(i + 504, len(idx) - 1)
        seg12 = close.iloc[i + 1:j12 + 1]
        seg24 = close.iloc[i + 1:j24 + 1]
        max12 = seg12.max()
        max24 = seg24.max() if i + 504 <= len(idx) - 1 else pd.Series(np.nan, index=close.columns)
        p12 = ff.iloc[j12]
        for r in cands:
            c = r["code"]
            if c not in close.columns or np.isnan(c0.get(c, np.nan)) or c0[c] <= 0 or not r.get("tradable", True):
                continue
            p0 = c0[c]
            ep = f(r.get("ep"))
            rows.append({
                "date": D, "year": D.year, "code": c, "sector": (r.get("sector") or "?")[:2],
                "ep": ep, "bp": f(r.get("bp")), "dy": f(r.get("dy")), "pe": (1 / ep) if ep and ep > 0 else np.nan,
                "roe": f(r.get("roe")), "der": f(r.get("der")), "conv": f(r.get("conv")), "np_yoy": f(r.get("np_yoy")), "rev_yoy": f(r.get("rev_yoy")),
                "r1m": p0 / close.iloc[i - 21][c] - 1 if i >= 21 else np.nan,
                "r3m": p0 / close.iloc[i - 63][c] - 1 if i >= 63 else np.nan,
                "r6m": p0 / close.iloc[i - 126][c] - 1 if i >= 126 else np.nan,
                "mom": f(r.get("mom")), "vol60": vol60.iloc[i][c], "dd252": p0 / hi252.iloc[i][c] - 1, "up_low252": p0 / lo252.iloc[i][c] - 1,
                "log_mcap": math.log(float(r["mcap"])) if r.get("mcap") else np.nan, "log_v60": math.log(float(r["v60"])) if r.get("v60") else np.nan,
                "turnover": (float(r["v60"]) / float(r["mcap"])) if r.get("v60") and r.get("mcap") else np.nan, "f20": f(r.get("f20")),
                "gate_strict": bool(r.get("gate_strict")), "gate_loose": bool(r.get("gate_loose")),
                "price": p0, "fwd12": p12[c] / p0 - 1, "max12": max12[c] / p0 - 1, "max24": (max24[c] / p0 - 1) if not np.isnan(max24.get(c, np.nan)) else np.nan,
            })
        print(f"  snapshot {D.date()}: {sum(1 for x in rows if x['date'] == D)} names", flush=True)
    df = pd.DataFrame(rows)
    df["touch12"] = (df["max12"] >= 1.0).astype(int)
    df["touch24"] = np.where(df["max24"].isna(), np.nan, (df["max24"] >= 1.0).astype(float))
    return df


def quintile_table(df: pd.DataFrame, col: str, label: str = "touch12") -> list[tuple[str, float, int]]:
    d = df[[col, label]].dropna()
    if len(d) < 50:
        return []
    q = pd.qcut(d[col].rank(method="first"), 5, labels=["Q1 low", "Q2", "Q3", "Q4", "Q5 high"])
    g = d.groupby(q, observed=True)[label]
    return [(str(k), float(v), int(n)) for k, v, n in zip(g.mean().index, g.mean().values, g.size().values, strict=True)]


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    if os.path.exists(PANEL):
        df = pd.read_parquet(PANEL)
        print(f"panel loaded from {PANEL}")
    else:
        print("building the panel (one snapshot per month, point-in-time)…")
        df = build_panel(conn, close, vol)
        df.to_parquet(PANEL)
    out: dict = {"generated": datetime.now(UTC).isoformat(), "n_rows": int(len(df)), "n_names": int(df["code"].nunique())}
    print(f"\npanel: {len(df)} name-months, {df['code'].nunique()} names, {df['date'].nunique()} snapshots")

    # ---- descriptives: how often does a liquid name double?
    print("\n=== base rates by snapshot year (share of names that reached 2x within 12 / 24 months)")
    by = df.groupby("year").agg(n=("code", "size"), touch12=("touch12", "mean"), touch24=("touch24", "mean"), fwd12=("fwd12", "mean"))
    for y, r in by.iterrows():
        print(f"  {y}: {int(r['n']):5d} rows  2x within 12m {100 * r['touch12']:5.1f}%   within 24m {100 * r['touch24']:5.1f}%   mean 12m return {100 * r['fwd12']:+.0f}%"
              if not np.isnan(r["touch24"]) else f"  {y}: {int(r['n']):5d} rows  2x within 12m {100 * r['touch12']:5.1f}%   (24m window open)   mean 12m return {100 * r['fwd12']:+.0f}%")
    out["base_rates"] = {int(y): {k: (None if pd.isna(v) else float(v)) for k, v in r.items()} for y, r in by.iterrows()}
    winners = df[df["touch12"] == 1].sort_values("date").drop_duplicates("code")
    print(f"\n{df[df['touch12'] == 1]['code'].nunique()} distinct names doubled within 12 months of some snapshot; {int((df['touch24'] == 1).sum())} name-months within 24 months")
    print("first snapshot at which each name later doubled within 12 months (name: year, max12, sector, P/E then, drawdown from 252d high then):")
    for _, w in winners.iterrows():
        print(f"  {w['code']:5s} {w['year']}  +{100 * w['max12']:.0f}%  {w['sector']}  P/E {w['pe']:.1f}  dd {100 * w['dd252']:+.0f}%  mcap Rp {math.exp(w['log_mcap']) / 1e12:.2f} T" if not np.isnan(w["pe"]) else
              f"  {w['code']:5s} {w['year']}  +{100 * w['max12']:.0f}%  {w['sector']}  P/E n/a  dd {100 * w['dd252']:+.0f}%  mcap Rp {math.exp(w['log_mcap']) / 1e12:.2f} T")
    out["winners"] = [{"code": w["code"], "year": int(w["year"]), "max12": float(w["max12"]), "sector": w["sector"]} for _, w in winners.iterrows()]

    # ---- what did they look like before? univariate hit rates by quintile
    print("\n=== hit rate of 'doubles within 12 months' by feature quintile (pooled; Q1 = lowest value)")
    out["quintiles"] = {}
    for col, label in (("log_mcap", "market cap"), ("log_v60", "liquidity"), ("pe", "P/E"), ("bp", "book yield"), ("dy", "dividend yield"),
                       ("roe", "ROE"), ("np_yoy", "profit growth (audited)"), ("dd252", "drawdown from 252d high"), ("up_low252", "rise from 252d low"),
                       ("mom", "12-1 momentum"), ("r3m", "3-month return"), ("vol60", "60-day volatility"), ("turnover", "turnover"), ("f20", "foreign flow 20d")):
        t = quintile_table(df, col)
        out["quintiles"][col] = t
        print(f"  {label:26s} " + "  ".join(f"{k}: {100 * v:4.1f}%" for k, v, n in t))
    sec = df.groupby("sector")["touch12"].agg(["mean", "size"]).sort_values("mean", ascending=False)
    print("  by sector: " + ", ".join(f"{SECTOR.get(k[0], k)} {100 * v['mean']:.1f}% (n={int(v['size'])})" for k, v in sec.iterrows()))
    out["sectors"] = {SECTOR.get(k[0], k): {"rate": float(v["mean"]), "n": int(v["size"])} for k, v in sec.iterrows()}
    gate = df.groupby("gate_strict")["touch12"].mean()
    print(f"  strict gate: passes {100 * gate.get(True, np.nan):.1f}%  fails {100 * gate.get(False, np.nan):.1f}%")

    # ---- why did they rise: earnings vs re-rating over the 12-month window
    snap_dates = sorted(df["date"].unique())
    look = df.set_index(["date", "code"])
    dec = []
    for _, w in df[df["touch12"] == 1].iterrows():
        later = [d for d in snap_dates if d >= w["date"] + pd.Timedelta(days=365)]
        if not later:
            continue
        key = (later[0], w["code"])
        if key not in look.index:
            continue
        w1 = look.loc[key]
        if np.isnan(w["ep"]) or np.isnan(w1["ep"]):
            continue
        e0, e1 = w["ep"] * w["price"], w1["ep"] * w1["price"]
        pr = w1["price"] / w["price"]
        if e0 <= 0 and e1 > 0:
            dec.append({"code": w["code"], "year": int(w["year"]), "kind": "loss to profit", "price_x": pr, "earn_x": np.nan, "pe_x": np.nan})
        elif e0 > 0 and e1 > 0:
            dec.append({"code": w["code"], "year": int(w["year"]), "kind": "earnings-led" if (e1 / e0) >= pr / (e1 / e0) else "re-rating-led",
                        "price_x": pr, "earn_x": e1 / e0, "pe_x": (1 / w1["ep"]) / (1 / w["ep"])})
        else:
            dec.append({"code": w["code"], "year": int(w["year"]), "kind": "profit to loss", "price_x": pr, "earn_x": np.nan, "pe_x": np.nan})
    dd = pd.DataFrame(dec).drop_duplicates(["code", "year"])
    print(f"\n=== why they rose: the 12-month move split into earnings growth x P/E change ({len(dd)} doubler-years with audited profit data at both ends)")
    for kind, g in dd.groupby("kind"):
        if kind in ("earnings-led", "re-rating-led"):
            print(f"  {kind:14s} {len(g):3d}  median price x{g['price_x'].median():.2f} = earnings x{g['earn_x'].median():.2f} x P/E x{g['pe_x'].median():.2f}")
        else:
            print(f"  {kind:14s} {len(g):3d}  median price x{g['price_x'].median():.2f}")
    out["decomposition"] = dd.to_dict(orient="records")

    # ---- the model: walk-forward with a 12-month purge
    print("\n=== model: LightGBM (fixed parameters) and an L2 logistic regression, walk-forward by test year, 12-month purge")
    X_all = df[FEATURES].astype(float)
    df["sector_cat"] = df["sector"].astype("category")
    results = {}
    for ty in TEST_YEARS:
        test = df[df["year"] == ty]
        if test.empty:
            continue
        cutoff = test["date"].min() - pd.Timedelta(days=372)
        train = df[df["date"] <= cutoff]
        if train["touch12"].sum() < 20:
            print(f"  {ty}: not enough positives in the training window ({int(train['touch12'].sum())})")
            continue
        Xtr = pd.concat([X_all.loc[train.index], train[["sector_cat"]]], axis=1)
        Xte = pd.concat([X_all.loc[test.index], test[["sector_cat"]]], axis=1)
        dtr = lgb.Dataset(Xtr, label=train["touch12"].values, categorical_feature=["sector_cat"], free_raw_data=False)
        m = lgb.train(PARAMS, dtr, num_boost_round=ROUNDS)
        s = m.predict(Xte)
        y = test["touch12"].values
        base = y.mean()
        k = max(1, len(test) // 10)
        top = np.argsort(-s)[:k]
        hit = y[top].mean()
        # the top ten per snapshot, held twelve months, against the universe mean
        t2 = test.assign(score=s)
        port = []
        for d, g in t2.groupby("date"):
            g10 = g.sort_values("score", ascending=False).head(10)
            port.append((g10["fwd12"].mean(), g["fwd12"].mean(), g10["touch12"].mean()))
        p_top = float(np.mean([p[0] for p in port]))
        p_uni = float(np.mean([p[1] for p in port]))
        p_hit = float(np.mean([p[2] for p in port]))
        # logistic for the signs
        mu, sd = X_all.loc[train.index].mean(), X_all.loc[train.index].std().replace(0, 1)
        Ztr = ((X_all.loc[train.index] - mu) / sd).fillna(0).values
        Zte = ((X_all.loc[test.index] - mu) / sd).fillna(0).values
        w = logistic_fit(Ztr, train["touch12"].values.astype(float))
        s_lr = 1 / (1 + np.exp(-(np.hstack([np.ones((len(Zte), 1)), Zte]) @ w)))
        imp = sorted(zip(m.feature_name(), m.feature_importance(importance_type="gain"), strict=True), key=lambda x: -x[1])[:8]
        results[ty] = {"train_rows": int(len(train)), "train_pos": int(train["touch12"].sum()), "test_rows": int(len(test)), "base": float(base),
                       "auc_gbm": auc(y, s), "auc_lr": auc(y, s_lr), "top_decile_hit": float(hit), "lift": float(hit / base) if base else None,
                       "top10_fwd12": p_top, "universe_fwd12": p_uni, "top10_hit": p_hit,
                       "importance": [(n, float(v)) for n, v in imp], "lr_coef": {n: float(c) for n, c in zip(FEATURES, w[1:], strict=True)}}
        print(f"  test {ty}: train {len(train)} rows ({int(train['touch12'].sum())} doublers) -> test {len(test)} rows, base rate {100 * base:.1f}%")
        print(f"     AUC gbm {auc(y, s):.3f} / logistic {auc(y, s_lr):.3f};  top decile hit {100 * hit:.1f}% (lift {hit / base:.1f}x)")
        print(f"     top-10 per snapshot, 12m return {100 * p_top:+.1f}% vs universe {100 * p_uni:+.1f}%; top-10 doubled {100 * p_hit:.0f}% of the time")
        print("     gbm gain: " + ", ".join(f"{n} {v:.0f}" for n, v in imp))
        big = sorted(results[ty]["lr_coef"].items(), key=lambda x: -abs(x[1]))[:6]
        print("     logistic signs (std. units): " + ", ".join(f"{n} {c:+.2f}" for n, c in big))
    out["model"] = results
    # reading rule
    ok_lift = all(r["lift"] is not None and r["lift"] > 2 for r in results.values()) if results else False
    beats = sum(r["top10_fwd12"] > r["universe_fwd12"] for r in results.values())
    print(f"\n--- reading rule: lift > 2x in every test year: {ok_lift}; top-10 beats the universe in {beats}/{len(results)} years -> "
          f"{'a finding worth building on' if ok_lift and beats >= 2 else 'not predictive enough to act on'}")
    out["verdict"] = {"lift_ok": bool(ok_lift), "beats": int(beats), "years": len(results)}
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
