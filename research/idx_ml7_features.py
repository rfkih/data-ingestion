#!/usr/bin/env python3
"""IDX menu ML-7 — can the prediction desk's DAILY models be made more accurate by construction, not by tuning?
(operator, 2026-09-25: "kamu ada ide nggak untuk meningkatkan akurasi dan performance nya" -> "okay boleh lakukan dong").

The desk's ML studies (#151-#159) settled that the cross-sectional signal is real (daily rank IC +0.05..+0.10 every year) and
that its cash value is decided by turnover and costs, not by hit rates. So the accuracy that matters is the RANK accuracy on
the tradeable (LIQ) universe at 5d/20d, and the stability of the ranks day to day (churn). This menu keeps the deployed
learner (LightGBM, same params, same purged 3 x 40-day blocks as `idx/ml/loop.py`, same labels: excess vs COMPOSITE for
20d+) and changes only how the rows are presented to it. The harness figures are directly comparable to the champions
registered in idx.ml_model on 2026-09-24 (ret IC 5d 0.232, 20d 0.142, 250d 0.215).

PRE-REGISTERED (6 trials; cumulative 815 + 6 = 821), `ret` task, horizons 5d, 20d (adoption) and 250d (informative, the
loser filter of #152):
  base   the deployed construction: raw features, equal weights, one seed          (reference, not a trial)
  xs     every per-name feature replaced by its percentile rank among that day's fit rows; day-level, categorical,
         binary and already-ranked features stay raw (XS_SKIP)
  wt     sample weights: time decay (half-life 500 trading days from the fit cut) x liquidity (LIQ = value60 >= Rp 5 bn
         and close >= 100 -> 1.0, else 0.35), the book trades LIQ only
  ens3   three seeds (different bagging draws) averaged
  all    xs + wt + ens3
  rank   `all` rows, objective lambdarank grouped by day (relevance = within-day quintile of the label, linear gain)
  ema    `all` scores smoothed per name with a 3-day EMA (past scores only) - measured on the yearly walk-forward
Two harnesses:
  A. the deployed one: 3 consecutive 40-day blocks at the end of history, purged fit set per block (embargo = horizon);
     pooled Spearman IC (the registry's number) + the mean daily rank IC on LIQ names and its t.
  B. yearly walk-forward 2022..2026: fit on rows before the year (purged), score the year; daily rank IC on LIQ, t, the
     top-minus-bottom decile mean label in bps, and the day-to-day rank autocorrelation of the scores (churn) - base, all,
     rank, ema only.
  Placebo (10 within-day label shuffles of the fit set, newest block, harness A) for the arm that wins on 5d and 20d.
ADOPT an arm into idx/ml/daily.py + loop.py only if, on BOTH 5d and 20d: harness-A pooled IC >= base + 0.02, base beaten
in >= 2 of the 3 blocks, placebo pct >= 95, and harness-B daily IC (LIQ) >= base in >= 4 of 5 years. Otherwise INFORMATIVE.
READ-ONLY on the market tables; one idx.study row. INGEST_DB_DSN (or blackheart-ingest/idx-local.env); IDX_ML7_CACHE for the
panel pickle; IDX_ML7_STATE for the per-fit checkpoint (re-runs resume).
    blackheart-ingest/.venv/Scripts/python research/idx_ml7_features.py [--quick]
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
import time
from datetime import date, datetime

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common, daily  # noqa: E402
from blackheart_ingest.idx.ml.spec import HORIZONS  # noqa: E402

N_BEFORE = 815
STUDY = "ml7_features"
ARMS = ["xs", "wt", "ens3", "all", "rank", "ema"]
N_TRIALS = len(ARMS)
HZ = ["5d", "20d", "250d"]
ADOPT_HZ = ["5d", "20d"]
YEARS = [2022, 2023, 2024, 2025, 2026]
N_VAL, K_BLOCKS, MIN_FIT_DAYS = 40, 3, 5
RET_CLIP = 1.0
LIQ_VALUE, MIN_PRICE = 5e9, 100.0
HALF_LIFE = 500                    # trading days
W_ILLIQ = 0.35
SEEDS = [20260924, 20260925, 20260926]
N_PLACEBO = 10
BAR = {"ic_gain": 0.02, "blocks_won": 2, "placebo_pct": 95.0, "years_won": 4}
CHAMPION = {"5d": 0.232, "20d": 0.142, "250d": 0.215}      # idx.ml_model champions 2026-09-24, for the report only
XS_SKIP = {
    "dow", "month", "sector", "breadth", "comp_r1", "comp_r5", "comp_r20", "comp_r60", "comp_dma200", "comp_vol20",
    "usdidr_r20", "bi_rate", "us10y", "vix", "vix_r20", "brent_r20", "gold_r20", "cpo_r20", "fedfunds", "id_cpi_yoy", "id_gdp_qoq",
    "sec_r20", "xs_r1", "xs_r20", "xs_r60", "cfo_pos", "profitable",
    "ev_ownership", "ev_query", "ev_dividend", "ev_buyback", "ev_material", "ev_rights",
}
T0 = time.time()


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S} +{(time.time() - T0) / 60:5.1f}m] {msg}", flush=True)


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    return env["INGEST_DB_DSN"].strip().strip('"')


# ---- data ----------------------------------------------------------------------------------------------------------------
def load_panel(conn) -> pd.DataFrame:
    cache = os.environ.get("IDX_ML7_CACHE", os.path.join(ROOT, "tmp", "ml7_panel.pkl"))
    if os.path.exists(cache):
        P = pickle.load(open(cache, "rb"))
        log(f"panel from cache {cache}: {len(P):,} rows")
        return P
    log("building the daily panel (idx/ml/daily.build_panel) ...")
    P = daily.fit_rows(daily.build_panel(conn))
    keep = ["code", "d", "close", "value20", "value60"] + daily.FEATURES + [f"fwd_{h}" for h in HZ]
    if "value60" not in P:
        P["value60"] = np.expm1(P["lvalue60"].astype(float))        # daily.py keeps only the log
    keep = [c for c in keep if c in P]
    P = P[keep].sort_values(["code", "d"]).reset_index(drop=True)
    for c in daily.FEATURES + [f"fwd_{h}" for h in HZ]:
        if c in P and P[c].dtype == np.float64:
            P[c] = P[c].astype(np.float32)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    pickle.dump(P, open(cache, "wb"), protocol=5)
    log(f"panel built and cached: {len(P):,} rows, {P['d'].min().date()}..{P['d'].max().date()}")
    return P


def xs_features(P: pd.DataFrame) -> pd.DataFrame:
    """Per-name features as that day's percentile rank; the rest raw. Same column names, so the models are comparable."""
    Q = P.copy()
    cols = [c for c in daily.FEATURES if c not in XS_SKIP]
    g = Q.groupby("d")
    for c in cols:
        Q[c] = g[c].rank(pct=True).astype(np.float32)
    return Q


def weights(P: pd.DataFrame, fit_m: np.ndarray, calendar: np.ndarray) -> np.ndarray:
    """Time decay from the fit set's last day x liquidity."""
    d = P["d"].to_numpy()[fit_m]
    idx = np.searchsorted(calendar, d)
    age = idx.max() - idx
    w = np.power(0.5, age / HALF_LIFE)
    liq = (P["value60"].to_numpy()[fit_m] >= LIQ_VALUE) & (P["close"].to_numpy()[fit_m] >= MIN_PRICE)
    return (w * np.where(liq, 1.0, W_ILLIQ)).astype(np.float32)


# ---- learners ------------------------------------------------------------------------------------------------------------
def fit_lgb(X, y, params, feats, seed, weight=None, group=None):
    import lightgbm as lgb
    p = {k: v for k, v in params.items() if k != "rounds"}
    p["seed"] = seed
    p["num_threads"] = 14
    ds = lgb.Dataset(X, y, feature_name=feats, weight=weight, group=group, free_raw_data=True)
    return lgb.train(p, ds, int(params.get("rounds", 300)))


def rank_labels(y: np.ndarray, days: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rows ordered by day; relevance = within-day quintile (0..4); group sizes per day."""
    order = np.argsort(days, kind="stable")
    ds = days[order]
    ys = y[order]
    df = pd.DataFrame({"d": ds, "y": ys})
    rel = (df.groupby("d")["y"].rank(pct=True, method="first") * 5).clip(upper=4.999).astype(int).to_numpy()
    sizes = df.groupby("d", sort=False).size().to_numpy()
    return order, rel, sizes


def predict_arm(arm: str, Xfit, yfit, Xval, feats, fit_m, P, calendar, days_fit) -> np.ndarray:
    params = dict(common.BASE_PARAMS["ret"])
    w = weights(P, fit_m, calendar) if arm in ("wt", "all", "rank", "ema") else None
    seeds = SEEDS if arm in ("ens3", "all", "ema") else SEEDS[:1]
    if arm == "rank":
        order, rel, sizes = rank_labels(yfit, days_fit)
        rp = {**params, "objective": "lambdarank", "label_gain": [0, 1, 2, 3, 4], "lambdarank_truncation_level": 100,
              "metric": "None"}
        rp.pop("alpha", None)
        bst = fit_lgb(Xfit[order], rel, rp, feats, seeds[0], weight=None if w is None else w[order], group=sizes)
        return np.asarray(bst.predict(Xval), dtype=float)
    preds = []
    for s in seeds:
        bst = fit_lgb(Xfit, yfit, params, feats, s, weight=w)
        preds.append(np.asarray(bst.predict(Xval), dtype=float))
    return np.mean(preds, axis=0)


# ---- metrics -------------------------------------------------------------------------------------------------------------
def daily_ic(days: np.ndarray, pred: np.ndarray, y: np.ndarray, mask: np.ndarray, min_n: int = 20) -> tuple[float, float, int, float]:
    """Mean daily Spearman between pred and y over rows in mask; -> (mean, t, n_days, top-bottom decile mean y)."""
    df = pd.DataFrame({"d": days[mask], "p": pred[mask], "y": y[mask]})
    df = df[np.isfinite(df["p"]) & np.isfinite(df["y"])]
    n = df.groupby("d")["p"].transform("size")
    df = df[n >= min_n].copy()
    if df.empty:
        return float("nan"), float("nan"), 0, float("nan")
    g = df.groupby("d")
    df["rp"] = g["p"].rank() - g["p"].rank().groupby(df["d"]).transform("mean")
    df["ry"] = g["y"].rank() - g["y"].rank().groupby(df["d"]).transform("mean")
    df["pq"] = df["rp"] * df["ry"]
    df["pp"] = df["rp"] ** 2
    df["yy"] = df["ry"] ** 2
    s = df.groupby("d")[["pq", "pp", "yy"]].sum()
    ics = (s["pq"] / np.sqrt(s["pp"] * s["yy"])).replace([np.inf, -np.inf], np.nan).dropna()
    if len(ics) == 0:
        return float("nan"), float("nan"), 0, float("nan")
    g = df.groupby("d")
    df["dec"] = g["p"].rank(pct=True)
    top = df[df["dec"] >= 0.9].groupby("d")["y"].mean()
    bot = df[df["dec"] <= 0.1].groupby("d")["y"].mean()
    spread = float((top - bot).mean() * 1e4)
    return float(ics.mean()), float(ics.mean() / ics.std() * np.sqrt(len(ics))) if ics.std() > 0 else float("nan"), int(len(ics)), spread


def churn(df: pd.DataFrame) -> float:
    """Mean day-to-day Spearman of the score across names present on both days (1 = no churn)."""
    W = df.pivot_table(index="d", columns="code", values="p").sort_index()
    A = W.rank(axis=1, pct=True)
    out = []
    for i in range(1, len(A)):
        a, b = A.iloc[i - 1], A.iloc[i]
        ok = a.notna() & b.notna()
        if ok.sum() >= 30:
            out.append(np.corrcoef(a[ok], b[ok])[0, 1])
    return float(np.nanmean(out)) if out else float("nan")


# ---- state (checkpoint) ----------------------------------------------------------------------------------------------------
class State:
    def __init__(self):
        self.path = os.environ.get("IDX_ML7_STATE", os.path.join(ROOT, "tmp", "ml7_state.json"))
        self.d = json.load(open(self.path)) if os.path.exists(self.path) else {}

    def get(self, key):
        return self.d.get(key)

    def put(self, key, val):
        self.d[key] = val
        json.dump(self.d, open(self.path, "w"), indent=0, default=str)


# ---- harness A: the deployed blocks ----------------------------------------------------------------------------------------
def harness_a(P: pd.DataFrame, PX: pd.DataFrame, st: State, quick: bool) -> dict:
    out = {}
    calendar = np.sort(pd.unique(P["d"]))
    for hk in HZ:
        h = HORIZONS[hk]
        col = f"fwd_{hk}"
        m_lab = P[col].notna().to_numpy()
        R, RX = P[m_lab], PX[m_lab]
        y = R[col].clip(-RET_CLIP, RET_CLIP).to_numpy(dtype=np.float32)
        days = R["d"].to_numpy()
        liq = ((R["value60"] >= LIQ_VALUE) & (R["close"] >= MIN_PRICE)).to_numpy()
        X_raw = common.to_matrix(R, daily.FEATURES).astype(np.float32)
        X_xs = common.to_matrix(RX, daily.FEATURES).astype(np.float32)
        plan = []
        for b_from, b_to in common.blocks(R["d"], N_VAL, K_BLOCKS, MIN_FIT_DAYS):
            cut = common.purge_cut(calendar, b_from, h.steps)
            plan.append({"from": str(pd.Timestamp(b_from).date()), "to": str(pd.Timestamp(b_to).date()), "cut": str(pd.Timestamp(cut).date()),
                         "fit": (R["d"] < cut).to_numpy(), "val": ((R["d"] >= b_from) & (R["d"] <= b_to)).to_numpy()})
        out[hk] = {"blocks": [{k: b[k] for k in ("from", "to", "cut")} for b in plan], "arms": {}}
        arms = ["base"] + [a for a in ARMS if a != "ema"]
        if quick:
            arms = ["base", "all"]
        for arm in arms:
            per_block = []
            for bi, b in enumerate(plan):
                key = f"A|{hk}|{arm}|{bi}"
                cached = st.get(key)
                if cached:
                    per_block.append(cached)
                    continue
                X = X_xs if arm in ("xs", "all", "rank") else X_raw
                fit_m, val_m = b["fit"], b["val"]
                t = time.time()
                pred = predict_arm(arm, X[fit_m], y[fit_m], X[val_m], daily.FEATURES, fit_m, R, calendar, days[fit_m])
                m = common.metrics_for("ret", y[val_m], pred)
                dic, t_ic, nd, spread = daily_ic(days[val_m], pred, y[val_m], liq[val_m])
                rec = {"pooled_ic": m["ic"], "hit": m["hit"], "base": m["base"], "n": m["n"], "daily_ic_liq": dic, "t_liq": t_ic,
                       "days": nd, "spread_bps": spread, "n_fit": int(fit_m.sum()), "sec": round(time.time() - t)}
                st.put(key, rec)
                per_block.append(rec)
                log(f"A {hk} {arm} block {bi} {b['from']}..{b['to']}: pooled IC {m['ic']:.3f} daily IC(LIQ) {dic:.3f} t {t_ic:.1f} "
                    f"spread {spread:.0f} bps ({rec['sec']} s, fit {rec['n_fit']:,})")
            out[hk]["arms"][arm] = {"blocks": per_block,
                                    "pooled_ic": float(np.nanmean([r["pooled_ic"] for r in per_block])),
                                    "pooled_min": float(np.nanmin([r["pooled_ic"] for r in per_block])),
                                    "daily_ic_liq": float(np.nanmean([r["daily_ic_liq"] for r in per_block])),
                                    "spread_bps": float(np.nanmean([r["spread_bps"] for r in per_block]))}
        # placebo for the best non-base arm on this horizon (by pooled IC), newest block
        best = max((a for a in out[hk]["arms"] if a != "base"), key=lambda a: out[hk]["arms"][a]["pooled_ic"])
        if hk in ADOPT_HZ and not quick:
            key = f"A|{hk}|placebo|{best}"
            pl = st.get(key)
            if not pl:
                b = plan[-1]
                X = X_xs if best in ("xs", "all", "rank") else X_raw
                fit_m, val_m = b["fit"], b["val"]
                rng = np.random.default_rng(7)
                dfit = days[fit_m]
                order = np.argsort(dfit, kind="stable")
                ds = dfit[order]
                bounds = np.flatnonzero(np.r_[True, ds[1:] != ds[:-1], True])
                yf = y[fit_m]
                scores = []
                for i in range(N_PLACEBO):
                    ys = yf.copy()
                    for a_, b_ in zip(bounds[:-1], bounds[1:]):
                        seg = order[a_:b_]
                        ys[seg] = yf[rng.permutation(seg)]
                    pred = predict_arm(best, X[fit_m], ys, X[val_m], daily.FEATURES, fit_m, R, calendar, dfit)
                    scores.append(common.metrics_for("ret", y[val_m], pred)["ic"])
                    log(f"A {hk} placebo {best} {i + 1}/{N_PLACEBO}: {scores[-1]:.3f}")
                real = out[hk]["arms"][best]["blocks"][-1]["pooled_ic"]
                pl = {"arm": best, "n": N_PLACEBO, "scores": [round(float(s), 4) for s in scores], "real": real,
                      "pct": float((np.array(scores) < real).mean() * 100)}
                st.put(key, pl)
            out[hk]["placebo"] = pl
            log(f"A {hk} placebo {best}: real {pl['real']:.3f} vs shuffles mean {np.mean(pl['scores']):.3f} -> pct {pl['pct']:.0f}")
        del X_raw, X_xs
    return out


# ---- harness B: yearly walk-forward -----------------------------------------------------------------------------------------
def harness_b(P: pd.DataFrame, PX: pd.DataFrame, st: State, quick: bool) -> dict:
    out = {}
    calendar = np.sort(pd.unique(P["d"]))
    arms = ["base", "all", "rank", "ema"] if not quick else ["base", "all"]
    for hk in HZ:
        h = HORIZONS[hk]
        col = f"fwd_{hk}"
        m_lab = P[col].notna().to_numpy()
        R, RX = P[m_lab], PX[m_lab]
        y = R[col].clip(-RET_CLIP, RET_CLIP).to_numpy(dtype=np.float32)
        days = R["d"].to_numpy()
        liq = ((R["value60"] >= LIQ_VALUE) & (R["close"] >= MIN_PRICE)).to_numpy()
        X_raw = common.to_matrix(R, daily.FEATURES).astype(np.float32)
        X_xs = common.to_matrix(RX, daily.FEATURES).astype(np.float32)
        out[hk] = {}
        for arm in arms:
            out[hk][arm] = {}
            for yr in YEARS:
                key = f"B|{hk}|{arm}|{yr}"
                cached = st.get(key)
                if cached:
                    out[hk][arm][yr] = cached
                    continue
                y0 = np.datetime64(f"{yr}-01-01")
                cut = common.purge_cut(calendar, y0, h.steps)
                fit_m = days < cut
                val_m = (days >= y0) & (days < np.datetime64(f"{yr + 1}-01-01"))
                if val_m.sum() < 1000:
                    continue
                base_arm = "all" if arm == "ema" else arm
                X = X_xs if base_arm in ("xs", "all", "rank") else X_raw
                t = time.time()
                pred_path = os.path.join(ROOT, "tmp", f"ml7_pred_{hk}_{base_arm}_{yr}.npy")
                if os.path.exists(pred_path):
                    pred = np.load(pred_path)
                else:
                    pred = predict_arm(base_arm, X[fit_m], y[fit_m], X[val_m], daily.FEATURES, fit_m, R, calendar, days[fit_m])
                    np.save(pred_path, pred)
                pred = np.asarray(pred, dtype=float)
                df = pd.DataFrame({"d": days[val_m], "code": R["code"].to_numpy()[val_m], "p": pred})
                if arm == "ema":
                    df = df.sort_values(["code", "d"])
                    df["p"] = df.groupby("code")["p"].transform(lambda s: s.ewm(span=3, adjust=False).mean())
                    df = df.sort_index()
                    pred = df["p"].to_numpy()
                dic, t_ic, nd, spread = daily_ic(days[val_m], pred, y[val_m], liq[val_m])
                ch = churn(df[liq[val_m]])
                rec = {"daily_ic_liq": dic, "t_liq": t_ic, "days": nd, "spread_bps": spread, "churn_corr": ch,
                       "pooled_ic": common.metrics_for("ret", y[val_m], pred)["ic"], "sec": round(time.time() - t)}
                st.put(key, rec)
                out[hk][arm][yr] = rec
                log(f"B {hk} {arm} {yr}: daily IC(LIQ) {dic:.3f} t {t_ic:.1f} spread {spread:.0f} bps churn {ch:.2f} ({rec['sec']} s)")
        del X_raw, X_xs
    return out


# ---- verdict + report ---------------------------------------------------------------------------------------------------------
def verdict(A: dict, B: dict) -> dict:
    v = {}
    for arm in ARMS:
        checks = {}
        for hk in ADOPT_HZ:
            a_arm, base = A[hk]["arms"].get(arm), A[hk]["arms"]["base"]
            if arm == "ema" or a_arm is None:
                a_arm = None
            b_arm, b_base = B[hk].get(arm, {}), B[hk].get("base", {})
            yrs = [yr for yr in b_arm if yr in b_base]
            years_won = sum(b_arm[yr]["daily_ic_liq"] >= b_base[yr]["daily_ic_liq"] for yr in yrs)
            if a_arm is not None:
                blocks_won = sum(x["pooled_ic"] > y_["pooled_ic"] for x, y_ in zip(a_arm["blocks"], base["blocks"]))
                gain = a_arm["pooled_ic"] - base["pooled_ic"]
                pl = A[hk].get("placebo") or {}
                pct = pl["pct"] if pl.get("arm") == arm else None
                checks[hk] = {"gain": round(gain, 4), "blocks_won": blocks_won, "placebo_pct": pct, "years_won": years_won, "n_years": len(yrs),
                              "pass": gain >= BAR["ic_gain"] and blocks_won >= BAR["blocks_won"] and (pct is not None and pct >= BAR["placebo_pct"])
                              and years_won >= BAR["years_won"]}
            else:
                checks[hk] = {"years_won": years_won, "n_years": len(yrs), "pass": False, "note": "harness B only"}
        v[arm] = {"checks": checks, "adopt": all(c["pass"] for c in checks.values()) and len(checks) == len(ADOPT_HZ)}
    return v


def report(A: dict, B: dict, V: dict, quick: bool) -> str:
    L = [f"# IDX menu ML-7 — feature construction for the daily prediction desk ({date.today()})", "",
         f"Trials {N_TRIALS} (cumulative {N_BEFORE + N_TRIALS}); learner unchanged (LightGBM, BASE_PARAMS['ret']); labels = the desk's "
         f"(excess vs COMPOSITE for 20d+); harness A = 3 x {N_VAL}-day purged blocks; harness B = yearly walk-forward {YEARS[0]}..{YEARS[-1]}; "
         f"LIQ = value60 >= Rp {LIQ_VALUE / 1e9:.0f} bn & close >= {MIN_PRICE:.0f}. {'QUICK RUN' if quick else ''}", "",
         "## Harness A (the registry's blocks): pooled IC | daily IC on LIQ | top-bottom decile spread", ""]
    for hk in HZ:
        L.append(f"### {hk} (champion 2026-09-24 pooled IC {CHAMPION[hk]:.3f}); blocks " + ", ".join(f"{b['from']}..{b['to']}" for b in A[hk]["blocks"]))
        L += ["", "| arm | pooled IC (mean, min) | per block | daily IC LIQ | spread bps |", "|---|---|---|---|---|"]
        for arm, r in A[hk]["arms"].items():
            L.append(f"| {arm} | {r['pooled_ic']:.3f} ({r['pooled_min']:.3f}) | " + " / ".join(f"{b['pooled_ic']:.3f}" for b in r["blocks"])
                     + f" | {r['daily_ic_liq']:.3f} | {r['spread_bps']:.0f} |")
        pl = A[hk].get("placebo")
        if pl:
            L.append(f"\nPlacebo ({pl['n']} within-day shuffles, newest block, arm `{pl['arm']}`): real {pl['real']:.3f}, shuffles "
                     f"{np.mean(pl['scores']):.3f} ± {np.std(pl['scores']):.3f}, pct {pl['pct']:.0f}.")
        L.append("")
    L += ["## Harness B (yearly walk-forward): daily IC on LIQ (t) | spread bps | churn (day-to-day rank corr)", ""]
    for hk in HZ:
        L += [f"### {hk}", "", "| arm | " + " | ".join(str(y) for y in YEARS) + " | mean IC | years >= base |", "|---|" + "---|" * (len(YEARS) + 2)]
        base = B[hk].get("base", {})
        for arm, yrs in B[hk].items():
            cells = []
            for yr in YEARS:
                r = yrs.get(yr)
                cells.append("—" if not r else f"{r['daily_ic_liq']:.3f} ({r['t_liq']:.1f}) {r['spread_bps']:.0f} c{r['churn_corr']:.2f}")
            won = sum(yrs[y]["daily_ic_liq"] >= base[y]["daily_ic_liq"] for y in yrs if y in base)
            L.append(f"| {arm} | " + " | ".join(cells) + f" | {np.nanmean([r['daily_ic_liq'] for r in yrs.values()]):.3f} | {won}/{len(base)} |")
        L.append("")
    L += ["## Verdict (pre-registered bar: pooled IC >= base + 0.02 on 5d AND 20d, >= 2/3 blocks, placebo >= 95, >= 4/5 years)", ""]
    for arm, v in V.items():
        L.append(f"- `{arm}`: {'ADOPT' if v['adopt'] else 'informative'} — " + "; ".join(
            f"{hk}: " + ", ".join(f"{k} {val}" for k, val in c.items()) for hk, c in v["checks"].items()))
    return "\n".join(L)


def main() -> None:
    quick = "--quick" in sys.argv
    st = State()
    with psycopg.connect(dsn()) as conn:
        P = load_panel(conn)
    P = P[P["d"] >= pd.Timestamp("2020-01-01")]
    log("cross-sectional ranks ...")
    PX = xs_features(P)
    log(f"ranked {len([c for c in daily.FEATURES if c not in XS_SKIP])} of {len(daily.FEATURES)} features")
    A = harness_a(P, PX, st, quick)
    B = harness_b(P, PX, st, quick)
    V = verdict(A, B)
    text = report(A, B, V, quick)
    out = os.path.join(HERE, f"IDX_ML7_FEATURES_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text)
    json.dump({"A": A, "B": B, "verdict": V}, open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    if not quick:
        with psycopg.connect(dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ARMS, "n_trials_cumulative": N_BEFORE + N_TRIALS, "bar": BAR,
                                                                     "horizons": HZ, "years": YEARS, "seeds": SEEDS, "half_life": HALF_LIFE,
                                                                     "w_illiq": W_ILLIQ, "xs_skip": sorted(XS_SKIP)},
                                  summary={"verdict": V, "A": {hk: {a: {k: r[k] for k in ("pooled_ic", "pooled_min", "daily_ic_liq", "spread_bps")}
                                                                    for a, r in A[hk]["arms"].items()} for hk in HZ},
                                           "placebo": {hk: A[hk].get("placebo") for hk in HZ}},
                                  names=[], report_path=out, note="ML-7: feature construction arms for the daily desk (xs ranks, weights, seeds, lambdarank, EMA)")
        log(f"study #{sid} stored; report {out}")


if __name__ == "__main__":
    main()
