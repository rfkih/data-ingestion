#!/usr/bin/env python3
"""IDX menu BK-1 - does a breakout HOLD or is it FALSE? A model on the deployed trend rule's own signals, judged as a filter
on the trend book (operator, 2026-09-25: "model untuk klasifikasi trend ... sideways atau uptrend atau breakout volume" ->
"iya boleh dong lakukan").

Why this and not a state classifier: WHICH state a name is in (sideways / uptrend / breakout) is a rule on prices, not a
forecast - it is built as a rule in idx/stock_state.py. The open forecasting question is what the state is worth. Study #130
counted it: 45 % of volume breakouts of a 60-day base close back inside it within 5 days, and volume separates only at the
extremes. Menu 27 (#69) showed the trap: a model that sees the channel position learns the label's geometry (AUC 0.76 from
position alone) and makes no money. So here the bar is set against the geometry and the money decides.

EVENTS: the deployed trend rule's entry signal (idx/trend_book: close = 60-day high, close > 200-day mean, volume >= 1.5x
the 20-day median) on the LIQ universe (>= Rp 5 bn/day, px >= 100; small = LIQ minus BLUE is the live book's), 2020-2026.
Model rows: one per name per 20 trading days (the first signal); the book uses every signal, as deployed.
LABEL hold5 = no close in t+1..t+5 below the breakout level (the 60-day high of the closes ending t-1). Informative label:
clean10 = the high reaches +10 % before any close below that level, within 20 days.
FEATURES, all known at close t: breakout-day volume ratio, return, close position in the day's range (wick), distance above
the level, the 60 closes before t (width, efficiency ratio, net move, in a base60 per #130), volatility compression (20 vs
120-day), distance to MA50 / MA200, returns 20/60/120/250, breakouts in the past 120 days, traded value and its jump, price
level, foreign net flow 5/20 days, COMPOSITE regime and 20-day return, breadth (share of LIQ names above MA200), sector.

PRE-REGISTERED (4 trials; cumulative 853 + 4 = 857).
  M     LightGBM on hold5, walk-forward by year 2022..2026 (trained on events whose 20-day outcome closed before Jan 1 of Y).
  F30   the trend book (K = 10, trail10 exit, costs of the desk; entry t+1 close) with the bottom 30 % of signals by predicted
        hold5 dropped (threshold = the 30th percentile of the training predictions of that year's model).
  RANK  every signal kept; the free slots go to the highest predicted hold5 instead of the highest volume ratio.
  VR3   rule baseline: only signals with volume ratio >= 3 (study #130: the gradient lives at the extremes).
  Reference: the deployed rule (all signals, ranked by volume ratio) over the same stitched window.
READING RULE (the money decides; the model's AUC is reported but is not a verdict):
  a book arm IMPROVES the trend book if, on the SMALL universe (the live book), Sharpe >= deployed + 0.15 AND CAGR >= 0.9 x
  deployed, OR mDD >= 5 pp shallower AND CAGR >= 0.9 x deployed; AND it is not worse than deployed in more than 2 of the 5
  calendar years. LIQ is reported as the robustness read. The model's AUC must beat the best single feature among
  {volume ratio, distance above the level} by >= 0.03 pooled to be called informative.
READ-ONLY; one idx.study row. INGEST_DB_DSN (or idx-local.env); cache IDX_BEYOND_CACHE (default tmp/beyond_cache.pkl).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import lightgbm as lgb
import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_beyond as B  # noqa: E402
import idx_breakout_stats as BS  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 853
N_TRIALS = 4
STUDY = "breakout_filter"
K = 10
YEARS = [2022, 2023, 2024, 2025, 2026]
GAP = 20
DROP_Q = 0.30
BAR = {"sharpe_up": 0.15, "cagr_keep": 0.9, "mdd_up": 0.05, "max_worse_years": 2, "auc_lift": 0.03}
PARAMS = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=50, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=11)
ROUNDS = 300


def log(m: str) -> None:
    print(f"[bk1] {m}", flush=True)


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    for line in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"), encoding="utf-8"):
        if line.startswith("INGEST_DB_DSN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("INGEST_DB_DSN not set")


def main() -> int:
    d = dsn()
    os.environ["INGEST_DB_DSN"] = d
    with psycopg.connect(d) as conn:
        last_bar = pd.read_sql("SELECT max(trade_date) AS d FROM idx.bar WHERE source = 'idx'", conn)["d"].iloc[0]
    B.S.END = last_bar
    cache = os.environ.get("IDX_BEYOND_CACHE", os.path.join(ROOT, "tmp", "beyond_cache.pkl")) + f".{last_bar}"
    P, unis, comp, Hp, Lp, sectors, _ = B.load_all(d, cache)
    adj, vol = P["adj"], P["volume"]
    dates, cols = adj.index, adj.columns
    A, H, L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    Tn, N = A.shape
    c_in, c_out = S.costs(P)
    liq = unis["LIQ"].to_numpy(bool)
    small = (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool)
    log(f"panel {dates[0].date()} -> {dates[-1].date()}, {N} names")

    # ---- the deployed signal
    ma50, ma200 = (adj.rolling(n, min_periods=n).mean() for n in (50, 200))
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi60 = adj.rolling(60, min_periods=60).max()
    level = hi60.shift(1)                                                  # the breakout level: the 60-day high before t
    sig = ((adj >= hi60) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool) & liq

    # ---- features (all at close t)
    base, _, W = BS.base_panels(adj, 60, 0.25, 0.15, 0.30)
    ret = adj.pct_change(fill_method=None)
    er60 = ((adj.shift(1) - adj.shift(61)).abs() / adj.diff().abs().rolling(60, min_periods=60).sum().shift(1))
    comp_c = comp.reindex(dates).ffill()
    regime = (comp_c >= comp_c.rolling(200, min_periods=200).mean()).astype(float)
    above200 = (adj > ma200).where(unis["LIQ"])
    breadth = above200.sum(axis=1) / unis["LIQ"].sum(axis=1).replace(0, np.nan)
    sig_df = pd.DataFrame(sig, index=dates, columns=cols).astype(float)
    sec = sectors.set_index("code")["sector"].reindex(cols).astype("category").cat.codes.astype(float)
    fnet = P["fnet"] if "fnet" in P else None
    value = P["close"] * vol
    F = {
        "vr": vr, "log_vr": np.log(vr.where(vr > 0)), "r1": ret,
        "wick": ((Hp - P["close"]) / (Hp - Lp).replace(0, np.nan)).reindex(columns=cols),
        "gap": adj / level - 1,
        "base_w": W, "base_er": er60, "base_net": (adj.shift(1) / adj.shift(61) - 1), "in_base60": base.astype(float),
        "squeeze": ret.rolling(20, min_periods=15).std().shift(1) / ret.rolling(120, min_periods=80).std().shift(1),
        "d_ma50": adj / ma50 - 1, "d_ma200": adj / ma200 - 1,
        "r20": adj / adj.shift(20) - 1, "r60": adj / adj.shift(60) - 1, "r120": adj / adj.shift(120) - 1, "r250": adj / adj.shift(250) - 1,
        "n_sig120": sig_df.rolling(120, min_periods=1).sum().shift(1),
        "log_v60": np.log(P["v60"].where(P["v60"] > 0)), "val_jump": value / value.rolling(60, min_periods=20).mean().shift(1),
        "log_px": np.log(P["close"].where(P["close"] > 0)),
    }
    if fnet is not None:
        F["f5"] = fnet.rolling(5, min_periods=3).sum() / vol.rolling(5, min_periods=3).sum()
        F["f20"] = fnet.rolling(20, min_periods=10).sum() / vol.rolling(20, min_periods=10).sum()
    FA = {k: v.reindex(index=dates, columns=cols).to_numpy(float) for k, v in F.items()}
    row_feats = {"regime": regime.to_numpy(float), "comp_r20": (comp_c / comp_c.shift(20) - 1).to_numpy(float), "breadth": breadth.to_numpy(float)}
    feat_names = list(FA) + list(row_feats) + ["sector"]

    def feats_at(ti, tj):
        X = {k: v[ti, tj] for k, v in FA.items()}
        X.update({k: v[ti] for k, v in row_feats.items()})
        X["sector"] = sec.to_numpy(float)[tj]
        return pd.DataFrame(X)[feat_names]

    # ---- labels
    LV = level.to_numpy(float)

    def labels(ti, tj):
        hold5, clean10, known = np.full(len(ti), np.nan), np.full(len(ti), np.nan), np.zeros(len(ti), bool)
        for i, (t, j) in enumerate(zip(ti, tj, strict=True)):
            if t + 20 >= Tn:
                continue
            lv, p0 = LV[t, j], A[t, j]
            fut = A[t + 1:t + 21, j]
            if not np.isfinite(lv) or not np.isfinite(p0) or np.isnan(fut[:5]).all():
                continue
            below = np.where(np.nan_to_num(fut, nan=np.inf) < lv)[0]
            first_fail = below[0] + 1 if len(below) else 999
            up = np.where(np.nan_to_num(H[t + 1:t + 21, j], nan=-np.inf) >= p0 * 1.10)[0]
            first_up = up[0] + 1 if len(up) else 999
            hold5[i] = float(first_fail > 5)
            clean10[i] = float(first_up < 999 and first_up < first_fail)
            known[i] = True
        return hold5, clean10, known

    prior = sig_df.rolling(GAP, min_periods=1).sum().shift(1).fillna(0).to_numpy()
    ev = sig & (prior == 0)
    ti, tj = np.nonzero(ev)
    X = feats_at(ti, tj)
    y, yc, known = labels(ti, tj)
    ev_df = pd.DataFrame({"t": ti, "j": tj, "date": dates[ti], "y": y, "yc": yc, "known": known})
    ev_df["label_date"] = [dates[min(t + 20, Tn - 1)] for t in ti]
    ev_df["small"] = small[ti, tj]
    log(f"events {len(ev_df):,} (labelled {int(known.sum()):,}), hold5 base rate {np.nanmean(y):.1%}, clean10 {np.nanmean(yc):.1%}")

    # ---- walk-forward: model per test year; predictions for EVERY signal cell of that year (the book uses all)
    all_ti, all_tj = np.nonzero(sig)
    all_X = feats_at(all_ti, all_tj)
    pred_all = np.full(len(all_ti), np.nan)
    pred_ev = np.full(len(ev_df), np.nan)
    thr = {}
    imp: dict[str, float] = {}
    for yr in YEARS:
        start = pd.Timestamp(f"{yr}-01-01")
        tr = ev_df["known"] & (ev_df["label_date"] < start)
        m = lgb.train(PARAMS, lgb.Dataset(X[tr.values], ev_df.loc[tr, "y"]), ROUNDS)
        thr[yr] = float(np.quantile(m.predict(X[tr.values]), DROP_Q))
        te = (ev_df["date"].dt.year == yr).values
        pred_ev[te] = m.predict(X[te])
        ta = dates[all_ti].year == yr
        pred_all[ta] = m.predict(all_X[ta])
        for k, v in zip(feat_names, m.feature_importance("gain"), strict=True):
            imp[k] = imp.get(k, 0.0) + float(v)
        log(f"  {yr}: train {int(tr.sum()):,} events, threshold {thr[yr]:.3f}, test events {int(te.sum())}")
    ev_df["p"] = pred_ev

    # ---- accuracy (informative)
    acc = {}
    for yr in YEARS:
        s = ev_df[(ev_df["date"].dt.year == yr) & ev_df["known"]]
        if len(s) < 50:
            continue
        acc[yr] = {"n": int(len(s)), "hold5": round(float(s["y"].mean()), 3),
                   "model": round(common.auc(s["y"].values, s["p"].values), 3),
                   "vr": round(common.auc(s["y"].values, X.loc[s.index, "vr"].values), 3),
                   "gap": round(common.auc(s["y"].values, X.loc[s.index, "gap"].values), 3),
                   "model_clean10": round(common.auc(s["yc"].values, s["p"].values), 3)}
    s = ev_df[ev_df["date"].dt.year.isin(YEARS) & ev_df["known"]]
    pooled = {"n": int(len(s)), "model": round(common.auc(s["y"].values, s["p"].values), 3),
              "vr": round(common.auc(s["y"].values, X.loc[s.index, "vr"].values), 3),
              "gap": round(common.auc(s["y"].values, X.loc[s.index, "gap"].values), 3),
              "model_clean10": round(common.auc(s["yc"].values, s["p"].values), 3)}
    informative = pooled["model"] >= max(pooled["vr"], pooled["gap"]) + BAR["auc_lift"]
    top = s[s["p"] >= s.groupby(s["date"].dt.year)["p"].transform(lambda q: q.quantile(0.7))]
    bot = s[s["p"] <= s.groupby(s["date"].dt.year)["p"].transform(lambda q: q.quantile(0.3))]
    split = {"top30_hold5": round(float(top["y"].mean()), 3), "bottom30_hold5": round(float(bot["y"].mean()), 3),
             "top30_clean10": round(float(top["yc"].mean()), 3), "bottom30_clean10": round(float(bot["yc"].mean()), 3)}
    log(f"pooled AUC {pooled}, informative={informative}; {split}")

    # ---- the money: the trend book, stitched over the walk-forward window
    P_ = np.full((Tn, N), np.nan)
    P_[all_ti, all_tj] = pred_all
    in_wf = np.zeros(Tn, bool)
    in_wf[np.searchsorted(dates, pd.Timestamp(f"{YEARS[0]}-01-01")):] = True
    sig_wf = sig & in_wf[:, None]
    th = np.array([thr.get(d.year, np.nan) for d in dates])
    keep30 = sig_wf & (np.nan_to_num(P_, nan=-1.0) >= th[:, None])
    vr_arr = vr.to_numpy(float)
    z = np.zeros_like(A)
    trail10 = E.make_rules(A, H, L, z, z, z, z, z, z)["trail10"]
    arms = {"deployed": (sig_wf, vr_arr), "F30": (keep30, vr_arr), "RANK": (sig_wf, np.nan_to_num(P_, nan=-1.0)),
            "VR3": (sig_wf & (vr_arr >= 3), vr_arr)}
    wf_dates = dates[in_wf]
    t0 = int(np.argmax(in_wf))
    books: dict = {}
    for uname, uni in (("small", small), ("LIQ", liq)):
        books[uname] = {}
        for arm, (mask, score) in arms.items():
            R, tr, _ = B.run_book_sized(A, H, c_in, c_out, mask, score, trail10, uni, lambda t, j: 1.0 / K)
            R = R.iloc[t0:].reset_index(drop=True)
            trw = [x for x in tr if x[0] >= t0]
            st = E.stats(R.copy(), [(e - t0, j, g, n, h, m) for e, j, g, n, h, m in trw], wf_dates, N_BEFORE + N_TRIALS)
            books[uname][arm] = {k: st[k] for k in ("n", "hit", "avg_net", "cagr", "sharpe", "mdd", "years")}
            log(f"{uname:5s} {arm:8s} n={st['n']:4d} hit={st['hit']:.0%} net={st['avg_net']:+.2%} cagr={st['cagr']:+.1%} "
                f"sharpe={st['sharpe']:.2f} mdd={st['mdd']:.0%} years={ {y: round(v * 100, 1) for y, v in st['years'].items()} }")

    def improves(u: str, arm: str) -> tuple[bool, int]:
        a, dp = books[u][arm], books[u]["deployed"]
        worse = sum(1 for y, v in a["years"].items() if v < dp["years"].get(y, 0.0) - 1e-9)
        keep = a["cagr"] >= BAR["cagr_keep"] * dp["cagr"]
        better = (a["sharpe"] >= dp["sharpe"] + BAR["sharpe_up"]) or (a["mdd"] >= dp["mdd"] + BAR["mdd_up"])
        return bool(keep and better and worse <= BAR["max_worse_years"]), worse
    verdict = {arm: improves("small", arm) for arm in ("F30", "RANK", "VR3")}
    verdict_liq = {arm: improves("LIQ", arm) for arm in ("F30", "RANK", "VR3")}

    # ---- report
    n_trials = N_BEFORE + N_TRIALS
    tot = sum(imp.values()) or 1.0
    top_imp = sorted(imp.items(), key=lambda kv: -kv[1])[:10]
    Lr = [f"# IDX menu BK-1 - breakout holds or fails: a model as a filter on the trend book - {date.today()} - {N_TRIALS} trials, cumulative N = {n_trials}", "",
          f"Events: the deployed trend signal on LIQ, one per name per {GAP} days: {len(ev_df):,} ({int(known.sum()):,} with a full 20-day outcome); "
          f"hold5 base rate {np.nanmean(y):.0%}, clean +10 % run {np.nanmean(yc):.0%}. Walk-forward {YEARS[0]}-{YEARS[-1]}.", "",
          "## Accuracy (informative)", "", "| year | events | P(hold5) | model AUC | volume-ratio AUC | distance-above-level AUC | model AUC on clean10 |",
          "|---|---|---|---|---|---|---|"]
    for yr, a in acc.items():
        Lr.append(f"| {yr} | {a['n']} | {a['hold5']:.0%} | {a['model']:.3f} | {a['vr']:.3f} | {a['gap']:.3f} | {a['model_clean10']:.3f} |")
    Lr += ["", f"Pooled: model {pooled['model']:.3f}, volume ratio {pooled['vr']:.3f}, distance {pooled['gap']:.3f} -> "
           f"**{'informative' if informative else 'NOT informative'}** (bar: +{BAR['auc_lift']} over the best single feature). "
           f"Top 30 % by prediction held {split['top30_hold5']:.0%} vs bottom 30 % {split['bottom30_hold5']:.0%}; clean +10 % runs "
           f"{split['top30_clean10']:.0%} vs {split['bottom30_clean10']:.0%}.", "",
           "Top features (gain share): " + ", ".join(f"{k} {v / tot:.0%}" for k, v in top_imp), "",
           "## The money: trend book (K = 10, trail10, desk costs), stitched walk-forward window", ""]
    for u in ("small", "LIQ"):
        Lr += [f"### {u}" + (" (the live book's universe - the verdict)" if u == "small" else " (robustness)"), "",
               "| arm | trades | hit | net/trade | CAGR | Sharpe | mDD | " + " | ".join(str(y) for y in YEARS) + " |",
               "|---|---|---|---|---|---|---|" + "---|" * len(YEARS)]
        for arm, b in books[u].items():
            Lr.append(f"| {arm} | {b['n']} | {b['hit']:.0%} | {b['avg_net']:+.2%} | {b['cagr']:+.1%} | {b['sharpe']:.2f} | {b['mdd']:.0%} | "
                      + " | ".join(f"{b['years'].get(y, float('nan')) * 100:+.1f}" for y in YEARS) + " |")
        Lr.append("")
    Lr += ["## Verdict (pre-registered rule)", ""]
    for arm in ("F30", "RANK", "VR3"):
        ok, worse = verdict[arm]
        okl, worsel = verdict_liq[arm]
        Lr.append(f"- **{arm}**: small {'IMPROVES' if ok else 'does not improve'} (worse years {worse}); LIQ {'improves' if okl else 'does not'} (worse years {worsel})")
    text = "\n".join(Lr)
    out = os.path.join(HERE, f"IDX_BREAKOUT_FILTER_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    res = {"accuracy": acc, "pooled": pooled, "informative": informative, "split": split, "books": books,
           "verdict": {k: v[0] for k, v in verdict.items()}, "verdict_liq": {k: v[0] for k, v in verdict_liq.items()},
           "importance": {k: round(v / tot, 4) for k, v in top_imp}, "thresholds": thr}
    json.dump(common.plain(res), open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["M", "F30", "RANK", "VR3"], "n_trials_cumulative": n_trials,
                                                                 "years": YEARS, "bar": BAR, "drop_q": DROP_Q, "lgb": PARAMS, "rounds": ROUNDS},
                              summary=common.plain({k: v for k, v in res.items() if k != "importance"}), names=[], report_path=out,
                              note="menu BK-1: breakout hold/false model as a filter/ranker on the trend book")
        conn.commit()
    log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
