#!/usr/bin/env python3
"""IDX menu ML-1 — a LightGBM loser-filter for the trend entry (operator, 2026-09-22: "okay boleh" + "tambahkan juga semua
informasi yang kita punya: fundamental, berita, sentiment").

The trend book (menus 6-7, 13-14; `idx/trend_book.py`, books `paper_trend` + `trend_live`) takes every breakout the rule fires.
Menus 10-11 showed point-in-time fundamentals separate losers from the rest at a one-year horizon. This menu asks whether a
small gradient-boosted model over everything the desk knows at the close of the signal day can tell the breakouts that will
be stopped out from the ones that will run - and whether SKIPPING its worst third makes the book better after costs.

PRE-REGISTERED (2 trials: the filter on the `small` universe (deployed) and on `LIQ`; cumulative 401 + 2 = 403). Declared before
the run; nothing tuned afterwards.
  Events: every (name, day t) where the deployed entry fires (close = 60-day high, close > MA200, volume >= 1.5x its 20-day
    median) inside the universe, deduplicated: no signal on the same name in the prior 10 days.
  Label: the net return of the trail-10 trade from that signal alone - entry close t+1 at the closing offer, exit at the close
    after the first close <= 90 % of the peak close, at the closing bid; max 250 days; sold at the last close when the name
    disappears. Secondary (reported): 60-day excess return vs COMPOSITE.
  Features, all known at close t:
    price/volume  mom20, mom60, mom120, dist_ma50, dist_ma200, vr (volume / 20d median), vr5 (5-day mean of vr), ret1
                  (the breakout day), range_pos ((close-low)/(high-low)), vol20 (daily-return sd), atr_pct (ATR20 / close),
                  n_sig60 (signals on the name in the prior 60 days), log_v60, log_price
    flow          f5, f20, f60 (foreign net share of volume; idx.feature_daily)
    market        comp_ma50, comp_ma200 (COMPOSITE vs its means), comp_ret20, breadth (signals that day / universe size)
    fundamentals  latest report with published_at <= t (idx.fundamental, PIT): profitable, np_yoy, rev_yoy, roe, der,
                  net_margin, cfo_pos, months (report length), stale_days (t - published_at)
    disclosures   idx.event since 2023-07 (NaN before): n_ev30, n_ev90, ownership_change30, affiliated30, exchange_query30,
                  material30, buyback90
    sector        listing sector (categorical)
  NOT usable for training - their history starts in September 2026: news RSS, pack sentiment (idx.sentiment_score), analyst
    consensus, broker summary. They are logged from now on; a retrain can add them once they cover >= 2 test years.
  Model (fixed): LightGBM regression, objective huber, num_leaves 8, 400 rounds, learning rate 0.03, min_child_samples 40,
    feature_fraction 0.8, bagging_fraction 0.8 (freq 1), lambda_l2 1.0, seed 20260922.
  Walk-forward: test years 2022, 2023, 2024, 2025, 2026 (to 09-21). For each, train on events whose trade EXITED before
    Jan 1 of the test year (no label leakage), predict every event in the test year. Filter threshold for the year = the 33rd
    percentile of the model's predictions on its own training events (known ex-ante).
  Book test: the deployed K = 10 trail-10 book (idx_exit.run_book) from 2022-01-01 to the end, plain vs filtered (a signal
    below its year's threshold is not taken), same costs (closing offer/bid + Stockbit fees), ranked by volume ratio as deployed.
  References: random entries + trail10 on the same window; the plain rule.
READING RULE (declared before the run): the filter is BETTER on a universe only if ALL hold: >= 100 closed trades in the filtered
  book; Sharpe >= plain + 0.15; CAGR >= 0.8 x plain; max drawdown not deeper than plain; OOS tercile spread (mean net of the
  model's top third minus its bottom third, terciles by the year's own predictions) > 0 in >= 4 of the 5 test years.
  ADOPTION: BETTER on `small` -> the filter enters the PAPER trend book (skip signals below the threshold); the live book only
  by the operator's decision (two-key). BETTER on LIQ only = informative. Otherwise: tested, not adopted; IC and feature
  importances are reported either way.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_ml_trend.py
  (IDX_ML_CACHE=<file.pkl> caches the loaded panels.)
"""
from __future__ import annotations

import json
import math
import os
import pickle
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_swing2 as S  # noqa: E402

S.END = date(2026, 9, 21)
import idx_exit as E  # noqa: E402

N_BEFORE = 401
UNIS = ["small", "LIQ"]
ARMS = [f"mlfilter|{u}" for u in UNIS]
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
SEED = 20260922
PARAMS = {"objective": "huber", "num_leaves": 8, "learning_rate": 0.03, "min_child_samples": 40, "feature_fraction": 0.8,
          "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0, "seed": SEED, "verbose": -1, "num_threads": 4}
ROUNDS = 400
FEATURES = ["mom20", "mom60", "mom120", "dist_ma50", "dist_ma200", "vr", "vr5", "ret1", "range_pos", "vol20", "atr_pct", "n_sig60",
            "log_v60", "log_price", "f5", "f20", "f60", "comp_ma50", "comp_ma200", "comp_ret20", "breadth",
            "profitable", "np_yoy", "rev_yoy", "roe", "der", "net_margin", "cfo_pos", "months", "stale_days",
            "n_ev30", "n_ev90", "ownership_change30", "affiliated30", "exchange_query30", "material30", "buyback90", "sector"]


def load_all(dsn, cache=None):
    if cache and os.path.exists(cache):
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        P = S.panels(bars, listing)
        _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
        H, L = E.load_hl(conn, P)
        fund = pd.read_sql("""SELECT code, published_at::date AS pub, months, net_profit, net_profit_yoy, revenue_yoy, roe, der, net_margin, cfo
                                FROM idx.fundamental WHERE published_at IS NOT NULL ORDER BY code, published_at""", conn)
        ev = pd.read_sql("SELECT code, event_date, kind FROM idx.event WHERE event_date >= '2023-07-01'", conn)
    data = (P, unis, comp, H, L, listing, fund, ev)
    if cache:
        with open(cache, "wb") as fh:
            pickle.dump(data, fh)
    return data


def trade_outcome(A, c_in, c_out, t, j, max_hold=250):
    """The trail-10 trade from signal t on name j: (net, gross, exit index, hold days) or None when no entry is possible."""
    Tn = A.shape[0]
    e = t + 1
    if e >= Tn or np.isnan(A[e, j]) or not np.isfinite(c_in[e, j]):
        return None
    a0 = A[e, j]
    peak = a0
    x = None
    last = e
    for d in range(e, min(e + max_hold, Tn - 1)):
        a = A[d, j]
        if np.isnan(a):
            x = last          # name disappeared: sold at the last close seen
            break
        last = d
        peak = max(peak, a)
        if a <= 0.9 * peak:
            x = d + 1 if d + 1 < Tn and not np.isnan(A[d + 1, j]) else d
            break
    if x is None:
        x = min(e + max_hold, Tn - 1)
        while x > e and np.isnan(A[x, j]):
            x -= 1
    co = c_out[x, j] if np.isfinite(c_out[x, j]) else 0.003
    gross = A[x, j] / a0 - 1
    return gross - c_in[e, j] - co, gross, x, x - e


def build_events(P, unis, comp, H, L, listing, fund, ev, uni_name):
    adj, close, vol = P["adj"], P["close"], P["volume"]
    dates, cols = adj.index, adj.columns
    A = adj.to_numpy(float)
    c_in, c_out = S.costs(P)
    ma50, ma200 = adj.rolling(50, min_periods=50).mean(), adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(60, min_periods=60).max()
    entry_df = (adj >= hi) & (adj > ma200) & (vr >= 1.5)
    uni_df = (unis["LIQ"] & ~unis["BLUE"]) if uni_name == "small" else unis["LIQ"]
    sig = (entry_df & uni_df)
    # dedupe: no signal on the same name in the prior 10 days
    prior = sig.astype(float).rolling(10, min_periods=1).sum().shift(1).fillna(0)
    fresh = sig & (prior == 0)
    Hp, Lp = H, L
    ret = adj.pct_change()
    vol20 = ret.rolling(20, min_periods=20).std()
    prev = adj.shift(1)
    tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=cols)
    atr = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean()
    n_sig60 = sig.astype(float).rolling(60, min_periods=1).sum().shift(1).fillna(0)
    breadth_s = sig.sum(axis=1) / uni_df.sum(axis=1).replace(0, np.nan)
    comp_ma50 = comp / comp.rolling(50, min_periods=50).mean() - 1
    comp_ma200 = comp / comp.rolling(200, min_periods=200).mean() - 1
    comp_ret20 = comp / comp.shift(20) - 1
    comp60 = comp.shift(-60) / comp - 1
    sector = listing.set_index("code")["sector"].reindex(cols)
    sec_codes = {s: i for i, s in enumerate(sorted(sector.dropna().unique()))}
    # fundamentals PIT lookup: per code, arrays of pub dates
    fund = fund.copy()
    fund["pub"] = pd.to_datetime(fund["pub"])
    for c in ("net_profit", "net_profit_yoy", "revenue_yoy", "roe", "der", "net_margin", "cfo", "months"):
        fund[c] = pd.to_numeric(fund[c], errors="coerce")
    fgroups = {c: g.sort_values("pub") for c, g in fund.groupby("code")}
    ev = ev.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    egroups = {c: g.sort_values("event_date") for c, g in ev.groupby("code")}
    ev_start = pd.Timestamp("2023-08-01")
    rows = []
    ts, js = np.nonzero(fresh.to_numpy(bool))
    for t, j in zip(ts, js, strict=True):
        out = trade_outcome(A, c_in, c_out, t, j)
        if out is None:
            continue
        net, gross, x, hold = out
        code = cols[j]
        d = dates[t]
        f: dict = {"t": int(t), "j": int(j), "code": code, "date": d, "exit_date": dates[x], "net": net, "gross": gross, "hold": hold,
                   "year": d.year, "exc60": (A[min(t + 60, len(dates) - 1), j] / A[t, j] - 1) - (comp60.iloc[t] if not np.isnan(comp60.iloc[t]) else 0.0)}
        a = A[t, j]
        f["mom20"] = a / A[t - 20, j] - 1 if t >= 20 else np.nan
        f["mom60"] = a / A[t - 60, j] - 1 if t >= 60 else np.nan
        f["mom120"] = a / A[t - 120, j] - 1 if t >= 120 else np.nan
        f["dist_ma50"] = a / ma50.iat[t, j] - 1
        f["dist_ma200"] = a / ma200.iat[t, j] - 1
        f["vr"] = vr.iat[t, j]
        f["vr5"] = vr.iloc[max(0, t - 4):t + 1, j].mean()
        f["ret1"] = ret.iat[t, j]
        hh, ll = Hp.iat[t, j], Lp.iat[t, j]
        f["range_pos"] = (a - ll) / (hh - ll) if hh > ll else np.nan
        f["vol20"] = vol20.iat[t, j]
        f["atr_pct"] = atr.iat[t, j] / a if a else np.nan
        f["n_sig60"] = n_sig60.iat[t, j]
        v60 = P["v60"].iat[t, j]
        f["log_v60"] = math.log10(v60) if v60 and v60 > 0 else np.nan
        f["log_price"] = math.log10(close.iat[t, j]) if close.iat[t, j] > 0 else np.nan
        f["f5"], f["f20"] = P["f5"].iat[t, j], P["f20"].iat[t, j]
        f["f60"] = np.nan
        f["comp_ma50"], f["comp_ma200"], f["comp_ret20"] = comp_ma50.iloc[t], comp_ma200.iloc[t], comp_ret20.iloc[t]
        f["breadth"] = breadth_s.iloc[t]
        g = fgroups.get(code)
        if g is not None:
            g2 = g[g["pub"] <= d]
            if len(g2):
                r = g2.iloc[-1]
                f["profitable"] = float(r["net_profit"] > 0) if not np.isnan(r["net_profit"]) else np.nan
                f["np_yoy"], f["rev_yoy"], f["roe"], f["der"], f["net_margin"] = r["net_profit_yoy"], r["revenue_yoy"], r["roe"], r["der"], r["net_margin"]
                f["cfo_pos"] = float(r["cfo"] > 0) if not np.isnan(r["cfo"]) else np.nan
                f["months"] = r["months"]
                f["stale_days"] = (d - r["pub"]).days
        eg = egroups.get(code)
        if d >= ev_start:
            if eg is not None:
                w90 = eg[(eg["event_date"] <= d) & (eg["event_date"] > d - pd.Timedelta(days=90))]
                w30 = w90[w90["event_date"] > d - pd.Timedelta(days=30)]
            else:
                w90 = w30 = ev.iloc[0:0]
            f["n_ev30"], f["n_ev90"] = len(w30), len(w90)
            f["ownership_change30"] = int((w30["kind"] == "ownership_change").sum())
            f["affiliated30"] = int((w30["kind"] == "affiliated_tx").sum())
            f["exchange_query30"] = int((w30["kind"] == "exchange_query").sum())
            f["material30"] = int((w30["kind"] == "material_info").sum())
            f["buyback90"] = int((w90["kind"] == "buyback").sum())
        f["sector"] = sec_codes.get(sector.get(code), -1)
        rows.append(f)
    df = pd.DataFrame(rows)
    # f60 from the 60-day foreign net share (volume-weighted) - computed once on the panel for the events only
    fsh = (P["fnet"] / close).rolling(60, min_periods=40).sum() / vol.rolling(60, min_periods=40).sum()
    df["f60"] = [fsh.iat[t, j] for t, j in zip(df["t"], df["j"], strict=True)]
    for c in FEATURES:
        if c not in df:
            df[c] = np.nan
    return df, A, c_in, c_out, entry_df.to_numpy(bool), vr.to_numpy(float), uni_df.to_numpy(bool), dates


def walk_forward(df):
    import lightgbm as lgb
    preds = pd.Series(np.nan, index=df.index)
    thr = {}
    per_year = {}
    models = {}
    for y in TEST_YEARS:
        start = pd.Timestamp(y, 1, 1)
        train = df[df["exit_date"] < start]
        test = df[df["year"] == y]
        if len(train) < 200 or len(test) < 20:
            continue
        X, Xt = train[FEATURES], test[FEATURES]
        m = lgb.train(PARAMS, lgb.Dataset(X, label=train["net"].clip(-0.5, 1.5), categorical_feature=["sector"]), num_boost_round=ROUNDS)
        p_train = m.predict(X)
        p_test = m.predict(Xt)
        thr[y] = float(np.percentile(p_train, 100 / 3))
        preds.loc[test.index] = p_test
        q = pd.qcut(pd.Series(p_test, index=test.index).rank(method="first"), 3, labels=["bottom", "mid", "top"])
        ic = pd.Series(p_test).corr(test["net"].reset_index(drop=True), method="spearman")
        per_year[y] = {"n_train": len(train), "n_test": len(test), "ic": float(ic),
                       "top_net": float(test.loc[q == "top", "net"].mean()), "bottom_net": float(test.loc[q == "bottom", "net"].mean()),
                       "top_hit": float((test.loc[q == "top", "net"] > 0).mean()), "bottom_hit": float((test.loc[q == "bottom", "net"] > 0).mean()),
                       "skipped_share": float((p_test < thr[y]).mean()), "skipped_net": float(test.loc[p_test < thr[y], "net"].mean()) if (p_test < thr[y]).any() else float("nan"),
                       "kept_net": float(test.loc[p_test >= thr[y], "net"].mean()) if (p_test >= thr[y]).any() else float("nan")}
        models[y] = m
    return preds, thr, per_year, models


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    P, unis, comp, H, L, listing, fund, ev = load_all(dsn, os.environ.get("IDX_ML_CACHE"))
    n_trials = N_BEFORE + len(ARMS)
    Hn, Ln = H.to_numpy(float), L.to_numpy(float)
    dates = P["adj"].index
    s0 = int(dates.searchsorted(pd.Timestamp("2022-01-01")))
    results, report = {}, []
    for u in UNIS:
        df, A, c_in, c_out, entry, vr, uni, dates = build_events(P, unis, comp, H, L, listing, fund, ev, u)
        preds, thr, per_year, models = walk_forward(df)
        df["pred"] = preds
        # filtered entry mask: signals in test years below the year's threshold are dropped; other years unchanged
        keep = np.ones_like(entry, dtype=bool)
        for _, r in df[df["pred"].notna()].iterrows():
            if r["pred"] < thr.get(int(r["year"]), -np.inf):
                keep[int(r["t"]), int(r["j"])] = False
        # every (t, j) signal day that is a duplicate of a fresh signal within 10 days inherits that decision
        sl = slice(s0, None)
        z = np.zeros_like(A[sl])
        rules = E.make_rules(A[sl], Hn[sl], Ln[sl], z, z, z, z, z, z)      # the rule closes over the SLICED array (t is book-relative)
        trail = rules["trail10"]
        args = (A[sl], Hn[sl], Ln[sl], c_in[sl], c_out[sl])
        R0, tr0, _ = E.run_book(*args, entry[sl], vr[sl], trail, uni[sl])
        R1, tr1, _ = E.run_book(*args, (entry & keep)[sl], vr[sl], trail, uni[sl])
        Rr, trr, _ = E.run_book(*args, None, None, trail, uni[sl], rng=np.random.default_rng(SEED))
        d2 = dates[sl]
        plain, filt, rnd = E.stats(R0, tr0, d2, n_trials), E.stats(R1, tr1, d2, n_trials), E.stats(Rr, trr, d2, n_trials)
        spread_pos = sum(1 for y, v in per_year.items() if v["top_net"] - v["bottom_net"] > 0)
        why = []
        if filt["n"] < 100:
            why.append("n<100")
        if filt["sharpe"] < plain["sharpe"] + 0.15:
            why.append("sharpe<plain+0.15")
        if filt["cagr"] < 0.8 * plain["cagr"]:
            why.append("cagr<80%plain")
        if filt["mdd"] < plain["mdd"]:
            why.append("mdd deeper")
        if spread_pos < 4:
            why.append(f"tercile spread {spread_pos}/5")
        verdict = "BETTER" if not why else "not adopted: " + ", ".join(why)
        imp = {}
        if models:
            m = models[max(models)]
            g = m.feature_importance("gain")
            tot = g.sum() or 1
            imp = {f: float(v / tot) for f, v in sorted(zip(FEATURES, g, strict=True), key=lambda x: -x[1])[:12]}
        results[u] = {"events": len(df), "per_year": per_year, "thresholds": thr, "plain": plain, "filtered": filt, "random": rnd, "verdict": verdict,
                      "importance": imp, "label_stats": {"mean_net": float(df["net"].mean()), "hit": float((df["net"] > 0).mean()), "hold": float(df["hold"].mean())}}

        def yrs(d):
            return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

        report += [f"## Universe `{u}` — {len(df)} fresh signals 2020-2026, label mean net {df['net'].mean() * 100:+.2f} %, hit {(df['net'] > 0).mean() * 100:.0f} %, hold {df['hold'].mean():.0f} d", "",
                   "| test year | train n | test n | IC (Spearman) | top third net | bottom third net | top hit | bottom hit | skipped share | skipped net | kept net |",
                   "|---|---|---|---|---|---|---|---|---|---|---|"]
        for y, v in per_year.items():
            report.append(f"| {y} | {v['n_train']} | {v['n_test']} | {v['ic']:+.3f} | {v['top_net'] * 100:+.2f} % | {v['bottom_net'] * 100:+.2f} % | {v['top_hit'] * 100:.0f} % | "
                          f"{v['bottom_hit'] * 100:.0f} % | {v['skipped_share'] * 100:.0f} % | {v['skipped_net'] * 100:+.2f} % | {v['kept_net'] * 100:+.2f} % |")
        report += ["", "| book 2022-01 -> 2026-09 | trades | hold | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for label, s in (("plain rule (deployed)", plain), ("rule + ML filter", filt), ("random + trail10", rnd)):
            report.append(f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | "
                          f"{s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} |")
        report += ["", f"**Verdict `{u}`: {verdict}**", "", "Top features by gain (last model): " + ", ".join(f"{k} {v * 100:.0f} %" for k, v in imp.items()), ""]
        print("\n".join(report[-8:]), flush=True)
    text = "\n".join([f"# IDX menu ML-1 — LightGBM loser-filter for the trend entry — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
                      "Walk-forward by year (train on trades exited before the test year); filter = skip signals below the 33rd percentile of the "
                      "training predictions; book = deployed K=10 trail-10, closing offer/bid + fees. Features: price/volume, foreign flow, market, PIT "
                      "fundamentals, disclosures since 2023-07 (NaN before), sector. News / pack sentiment / consensus excluded: history starts Sep 2026.", ""] + report)
    out = os.path.join(HERE, f"IDX_ML_TREND_{date.today().isoformat()}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"wrote {out}")
    if "--no-store" not in sys.argv:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "ml_trend_filter", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "model": PARAMS, "rounds": ROUNDS,
                                                                                    "features": FEATURES, "test_years": TEST_YEARS},
                                  summary=json.loads(json.dumps(results, default=str)), names=[], report_path=out,
                                  note="; ".join(f"{u}: {results[u]['verdict']}" for u in UNIS))
            print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
