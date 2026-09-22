#!/usr/bin/env python3
"""IDX menu ML-3 — can a model say in advance which names will lock at ARA tomorrow? (operator, 2026-09-22: "bisa nggak
research model lain, atau memprediksi kapan saham akan ARA").

Menu 16 showed that buying AFTER an ARA loses: the continuation lives in the fills nobody gets. The mirror question is open:
if a name can be picked at today's close and it locks tomorrow, the holder sells INTO the lock (the bid queue at the limit
takes sellers) and keeps ~+25 %. That only needs precision, not liquidity - so it is a classification problem with a hard,
pre-declared bar: buying the model's top names every day must beat their cost.

PRE-REGISTERED (3 trials; cumulative 403 + 3 = 406). Declared before the run; nothing tuned afterwards.
  Sample: every (name, day) 2020-01 -> 2026-09-21 on the main boards (notation digit 1/2), previous >= Rp 50, value traded
    on the day >= Rp 1 bn (a lot can be bought). ~1M rows.
  Labels: ARA1 = the next close is the ARA price (menu-16 definition: highest tick <= previous x (1 + 35/25/20 %));
          ARA5 = any ARA close in the next 5 days; UP10 = next close >= +10 %.
  Features at close t: ret1, ret5, ret20, ret60, vr (volume / 20d median), vr5, log_value, log_price, range_pos, dist_hi60,
    vol20, ara_today, near_ara_today (>= 60 % of the band), days_since_ara, n_ara20, n_ara60, breadth_ara (ARA names that day),
    breadth_near, comp_ret20, comp_ma50, f5, f20 (foreign share), band, board, sector; PIT fundamentals (latest report
    published <= t): profitable, np_yoy, rev_yoy; disclosures since 2023-07 (NaN before): n_ev30, material30, ownership30.
  Models (fixed): LightGBM binary (num_leaves 15, 300 rounds, lr 0.05, min_child_samples 200, feature_fraction 0.8, bagging 0.8,
    scale_pos_weight = neg/pos of the training set, seed 20260922) - one per label. Reference (not a trial): the naive rule
    "rank by ret1 x vr" (what a human ARA hunter looks at), and random names.
  Walk-forward: test years 2022..2026, train on all earlier rows (labels fully realised before the test year begins).
  Trade test (the bar): each day buy the top 5 names by score at the CLOSING OFFER (skip a locked close: no offer quoted),
    sell at the next CLOSING BID (a locked-up close still has a bid queue: sold at the limit; a locked-down close has no bid:
    sold at close - 1 tick the day after), Stockbit fees 0.10/0.20 %. K = 5 slots, one day. Random reference on the same days.
READING RULE (declared before the run): a label's model is a CANDIDATE only if ALL hold: precision@5 >= 11 % for ARA1 (the
  break-even: +25 % x p > 1 % cost + 2 % x (1-p)) in >= 4 of 5 test years; the top-5 daily book is positive after costs in
  >= 4 of 5 years, Sharpe >= 1.0, max drawdown <= 25 %, Sharpe >= random + 0.5 and >= the naive rule + 0.3. Anything else:
  tested, no edge - with AUC, lift and precision reported so the size of the miss is visible.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_ml_ara.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_ara as AR  # noqa: E402

AR.END = date(2026, 9, 21)
N_BEFORE = 403
LABELS = ["ARA1", "ARA5", "UP10"]
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
SEED = 20260922
K = 5
FEE_BUY, FEE_SELL = 0.0010, 0.0020
PARAMS = {"objective": "binary", "num_leaves": 15, "learning_rate": 0.05, "min_child_samples": 200, "feature_fraction": 0.8,
          "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0, "seed": SEED, "verbose": -1, "num_threads": 4}
ROUNDS = 300
FEATURES = ["ret1", "ret5", "ret20", "ret60", "vr", "vr5", "log_value", "log_price", "range_pos", "dist_hi60", "vol20", "ara_today",
            "near_today", "days_since_ara", "n_ara20", "n_ara60", "breadth_ara", "breadth_near", "comp_ret20", "comp_ma50", "f5", "f20",
            "band", "board", "sector", "profitable", "np_yoy", "rev_yoy", "n_ev30", "material30", "ownership30"]


def load(dsn):
    with psycopg.connect(dsn) as conn:
        bars, listing, idx = AR.load(conn)
        bars = bars.merge(pd.read_sql("SELECT code, trade_date, foreign_net_share_5d AS f5, foreign_net_share_20d AS f20 FROM idx.feature_daily WHERE trade_date BETWEEN %s AND %s",
                                      conn, params=(AR.START, AR.END)), on=["code", "trade_date"], how="left")
        sector = pd.read_sql("SELECT code, sector FROM idx.listing", conn)
        fund = pd.read_sql("SELECT code, published_at::date AS pub, net_profit, net_profit_yoy, revenue_yoy FROM idx.fundamental WHERE published_at IS NOT NULL", conn)
        ev = pd.read_sql("SELECT code, event_date, kind FROM idx.event WHERE event_date >= '2023-07-01'", conn)
    return bars, listing, idx, sector, fund, ev


def panels(bars):
    P = AR.panels(bars)
    for c in ("f5", "f20"):
        b = bars[["code", "trade_date", c]].copy()
        b[c] = pd.to_numeric(b[c], errors="coerce")
        P[c] = b.pivot(index="trade_date", columns="code", values=c).sort_index()
        P[c].index = pd.to_datetime(P[c].index)
    return P


def frame(P, M, listing, idx, sector, fund, ev):
    """The long (name, day) table with labels and features, built from panels (vectorised)."""
    dates, cols = M.dates, M.cols
    T, N = M.T, M.N
    A = M.adj * M.close
    close = M.close
    base = M.main & (M.prev >= 50) & (M.val >= 1e9) & np.isfinite(close)
    ara = M.ara
    lim_next = np.full_like(close, np.nan)
    lim_next[:-1] = M.lim[1:]
    ara_next = np.zeros_like(ara)
    ara_next[:-1] = ara[1:]
    ara5 = np.zeros_like(ara)
    for k in range(1, 6):
        ara5[:-k] |= ara[k:]
    ret_next = np.full_like(close, np.nan)
    ret_next[:-1] = A[1:] / A[:-1] - 1
    up10 = ret_next >= 0.10

    def lag(k):
        out = np.full_like(A, np.nan)
        out[k:] = A[:-k]
        return out

    ret1, ret5, ret20, ret60 = (A / lag(k) - 1 for k in (1, 5, 20, 60))
    vol_df = pd.DataFrame(M.vol)
    vmed = vol_df.rolling(20, min_periods=20).median().shift(1).to_numpy()
    vr = M.vol / vmed
    vr5 = pd.DataFrame(vr).rolling(5, min_periods=1).mean().to_numpy()
    hi60 = pd.DataFrame(A).rolling(60, min_periods=60).max().to_numpy()
    vol20 = pd.DataFrame(A).pct_change().rolling(20, min_periods=20).std().to_numpy()
    rng_pos = np.where(M.high > M.low, (close - M.low) / (M.high - M.low), np.nan)
    near = M.near
    # days since the last ARA, counts in windows
    idx_t = np.arange(T)[:, None] * np.ones((1, N))
    last_ara = np.where(ara, idx_t, np.nan)
    last_ara = pd.DataFrame(last_ara).ffill().to_numpy()
    days_since = idx_t - last_ara
    ara_f = pd.DataFrame(ara.astype(float))
    n_ara20 = ara_f.rolling(20, min_periods=1).sum().to_numpy()
    n_ara60 = ara_f.rolling(60, min_periods=1).sum().to_numpy()
    breadth_ara = (ara & base).sum(axis=1)
    breadth_near = (near & base).sum(axis=1)
    comp = M.comp
    comp_ret20 = (comp / comp.shift(20) - 1).to_numpy()
    comp_ma50 = (comp / comp.rolling(50, min_periods=50).mean() - 1).to_numpy()
    band = AR.up_band(M.prev)
    board_digit = np.where(M.main, 1.0, 0.0)          # 1 = main boards (all rows in the sample); kept for completeness
    sec = sector.set_index("code")["sector"].reindex(cols)
    sec_codes = {s: i for i, s in enumerate(sorted(sec.dropna().unique()))}
    sec_arr = np.array([sec_codes.get(s, -1) for s in sec], dtype=float)
    ts, js = np.nonzero(base[:-1])            # need a next day
    df = pd.DataFrame({"t": ts, "j": js})
    df["date"] = dates[ts]
    df["code"] = np.asarray(cols)[js]
    df["year"] = df["date"].dt.year
    df["ARA1"] = ara_next[ts, js].astype(int)
    df["ARA5"] = ara5[ts, js].astype(int)
    df["UP10"] = np.where(np.isnan(ret_next[ts, js]), 0, up10[ts, js]).astype(int)
    df["ret_next"] = ret_next[ts, js]
    for name, arr in (("ret1", ret1), ("ret5", ret5), ("ret20", ret20), ("ret60", ret60), ("vr", vr), ("vr5", vr5), ("vol20", vol20),
                      ("range_pos", rng_pos), ("days_since_ara", days_since), ("n_ara20", n_ara20), ("n_ara60", n_ara60)):
        df[name] = arr[ts, js]
    df["log_value"] = np.log10(np.maximum(M.val[ts, js], 1))
    df["log_price"] = np.log10(close[ts, js])
    df["dist_hi60"] = A[ts, js] / hi60[ts, js] - 1
    df["ara_today"] = ara[ts, js].astype(int)
    df["near_today"] = near[ts, js].astype(int)
    df["breadth_ara"] = breadth_ara[ts]
    df["breadth_near"] = breadth_near[ts]
    df["comp_ret20"] = comp_ret20[ts]
    df["comp_ma50"] = comp_ma50[ts]
    df["f5"] = M.f5[ts, js]
    df["f20"] = M.f20[ts, js]
    df["band"] = band[ts, js]
    df["board"] = board_digit[ts, js]
    df["sector"] = sec_arr[js]
    # execution prices for the trade test
    df["offer"] = M.offer[ts, js]
    df["has_offer"] = (M.ov[ts, js] > 0) & np.isfinite(M.offer[ts, js])
    df["close"] = close[ts, js]
    df["adj"] = M.adj[ts, js]
    nxt = np.minimum(ts + 1, T - 1)
    df["close_next"] = close[nxt, js]
    df["adj_next"] = M.adj[nxt, js]
    df["bid_next"] = M.bid[nxt, js]
    df["has_bid_next"] = (M.bv[nxt, js] > 0) & np.isfinite(M.bid[nxt, js])
    # PIT fundamentals via merge_asof per code
    fund = fund.copy()
    fund["pub"] = pd.to_datetime(fund["pub"])
    for c in ("net_profit", "net_profit_yoy", "revenue_yoy"):
        fund[c] = pd.to_numeric(fund[c], errors="coerce")
    fund = fund.sort_values("pub")
    df = df.sort_values("date")
    df = pd.merge_asof(df, fund.rename(columns={"pub": "date"})[["code", "date", "net_profit", "net_profit_yoy", "revenue_yoy"]], on="date", by="code", direction="backward")
    df["profitable"] = np.where(df["net_profit"].isna(), np.nan, (df["net_profit"] > 0).astype(float))
    df["np_yoy"], df["rev_yoy"] = df["net_profit_yoy"], df["revenue_yoy"]
    # disclosures: rolling 30-day counts from a date x code event panel (NaN before 2023-08)
    ev = ev.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    ev = ev[ev["code"].isin(cols)]
    for name, kinds in (("n_ev30", None), ("material30", ["material_info"]), ("ownership30", ["ownership_change"])):
        e = ev if kinds is None else ev[ev["kind"].isin(kinds)]
        cnt = e.groupby(["event_date", "code"]).size().unstack(fill_value=0).reindex(index=dates, columns=cols, fill_value=0)
        roll = cnt.rolling(30, min_periods=1).sum()
        vals = roll.to_numpy()[ts, js]
        df[name] = np.where(df["date"] >= pd.Timestamp("2023-08-01"), vals, np.nan)
    return df


def trade_test(sub, k=K):
    """Daily top-k by score at the closing offer -> next closing bid. Returns the daily return series and per-trade nets."""
    rows = []
    for d, g in sub.groupby("date", sort=True):
        g = g[g["has_offer"]].nlargest(k, "score")
        if g.empty:
            rows.append((d, 0.0, []))
            continue
        nets = []
        for _, r in g.iterrows():
            px_in = r["offer"] * r["adj"]
            if r["has_bid_next"]:
                px_out = r["bid_next"] * r["adj_next"]
            else:
                px_out = (r["close_next"] - AR.tick(r["close_next"])) * r["adj_next"]
            if not (px_in > 0 and np.isfinite(px_out)):
                continue
            nets.append(px_out * (1 - FEE_SELL) / (px_in * (1 + FEE_BUY)) - 1)
        rows.append((d, float(np.sum(nets)) / k if nets else 0.0, nets))
    R = pd.Series({d: r for d, r, _ in rows}).sort_index()
    nets = [x for _, _, ns in rows for x in ns]
    return R, nets


def book_stats(R, nets):
    eq = (1 + R).cumprod()
    years = R.groupby(R.index.year).apply(lambda s: (1 + s).prod() - 1)
    vol = R.std() * math.sqrt(250)
    sharpe = R.mean() * 250 / vol if vol > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    n = len(nets)
    return {"n": n, "avg_net": float(np.mean(nets)) if n else 0.0, "hit": float(np.mean(np.array(nets) > 0)) if n else 0.0,
            "cagr": float(eq.iloc[-1] ** (250 / len(R)) - 1) if len(R) else 0.0, "sharpe": float(sharpe), "mdd": float(dd),
            "years": {int(y): float(v) for y, v in years.items()}}


def auc(y, p):
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main():
    import lightgbm as lgb
    dsn = os.environ["INGEST_DB_DSN"]
    bars, listing, idx, sector, fund, ev = load(dsn)
    P = panels(bars)
    M = AR.Market(P, listing, idx)
    M.f5, M.f20 = P["f5"].reindex(columns=M.cols).to_numpy(float), P["f20"].reindex(columns=M.cols).to_numpy(float)
    df = frame(P, M, listing, idx, sector, fund, ev)
    n_trials = N_BEFORE + len(LABELS)
    print(f"rows {len(df):,}  base rates: " + "  ".join(f"{lb} {df[lb].mean() * 100:.2f} %" for lb in LABELS), flush=True)
    results, lines = {}, []
    rng = np.random.default_rng(SEED)
    df["naive"] = df["ret1"].fillna(0) * df["vr"].fillna(0)
    df["random"] = rng.random(len(df))
    for lb in LABELS:
        per_year, scores = {}, pd.Series(np.nan, index=df.index)
        for y in TEST_YEARS:
            train = df[df["year"] < y]
            test = df[df["year"] == y]
            if len(train) < 5000 or len(test) < 500:
                continue
            pos = train[lb].sum()
            params = dict(PARAMS, scale_pos_weight=float((len(train) - pos) / max(pos, 1)))
            m = lgb.train(params, lgb.Dataset(train[FEATURES], label=train[lb], categorical_feature=["sector"]), num_boost_round=ROUNDS)
            p = m.predict(test[FEATURES])
            scores.loc[test.index] = p
            top = test.assign(p=p).sort_values(["date", "p"], ascending=[True, False]).groupby("date").head(K)
            base = test[lb].mean()
            prec = top[lb].mean()
            naive_top = test.sort_values(["date", "naive"], ascending=[True, False]).groupby("date").head(K)
            per_year[y] = {"n_test": len(test), "base": float(base), "auc": auc(test[lb].to_numpy(), p), "prec5": float(prec),
                           "lift": float(prec / base) if base else float("nan"), "naive_prec5": float(naive_top[lb].mean()),
                           "top_ret_next": float(top["ret_next"].mean()), "imp": {}}
            if y == TEST_YEARS[-1]:
                g = m.feature_importance("gain")
                tot = g.sum() or 1
                per_year[y]["imp"] = {f: float(v / tot) for f, v in sorted(zip(FEATURES, g, strict=True), key=lambda x: -x[1])[:10]}
        sub = df[scores.notna()].copy()
        sub["score"] = scores[sub.index]
        R, nets = trade_test(sub)
        Rn, netsn = trade_test(sub.assign(score=sub["naive"]))
        Rr, netsr = trade_test(sub.assign(score=sub["random"]))
        st, stn, str_ = book_stats(R, nets), book_stats(Rn, netsn), book_stats(Rr, netsr)
        why = []
        if lb == "ARA1" and sum(1 for v in per_year.values() if v["prec5"] >= 0.11) < 4:
            why.append("precision@5<11% in <4/5 years")
        if sum(1 for v in st["years"].values() if v > 0) < 4:
            why.append("book positive <4/5 years")
        if st["sharpe"] < 1.0:
            why.append("sharpe<1")
        if st["mdd"] < -0.25:
            why.append("mdd>25%")
        if st["sharpe"] < str_["sharpe"] + 0.5:
            why.append("vs random")
        if st["sharpe"] < stn["sharpe"] + 0.3:
            why.append("vs naive")
        verdict = "CANDIDATE" if not why else "tested: " + ", ".join(why)
        results[lb] = {"per_year": per_year, "book": st, "naive": stn, "random": str_, "verdict": verdict}

        def yrs(d):
            return " ".join(f"{yy % 100:02d}:{v * 100:+.0f}" for yy, v in sorted(d.items()))

        lines += [f"## Label {lb} — base rate {df[lb].mean() * 100:.2f} %", "",
                  "| test year | rows | base | AUC | precision@5 | lift | naive precision@5 | top-5 next-day return |", "|---|---|---|---|---|---|---|---|"]
        for y, v in per_year.items():
            lines.append(f"| {y} | {v['n_test']:,} | {v['base'] * 100:.2f} % | {v['auc']:.3f} | **{v['prec5'] * 100:.1f} %** | {v['lift']:.1f}x | {v['naive_prec5'] * 100:.1f} % | {v['top_ret_next'] * 100:+.2f} % |")
        lines += ["", "| daily top-5 book 2022-2026 | trades | hit | avg net | CAGR | Sharpe | mDD | years |", "|---|---|---|---|---|---|---|---|"]
        for label, s in (("model", st), ("naive ret1 x vr", stn), ("random", str_)):
            lines.append(f"| {label} | {s['n']} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} |")
        imp = per_year.get(TEST_YEARS[-1], {}).get("imp", {})
        lines += ["", f"**Verdict {lb}: {verdict}**", "", "Top features (gain, last model): " + ", ".join(f"{k} {v * 100:.0f} %" for k, v in imp.items()), ""]
        print("\n".join(lines[-6:]), flush=True)
    text = "\n".join([f"# IDX menu ML-3 — predicting tomorrow's ARA — {date.today()} — {len(LABELS)} trials, cumulative N = {n_trials}", "",
                      f"{len(df):,} name-days on the main boards (value >= Rp 1 bn), walk-forward by year; LightGBM binary; trade test = daily top-5 at the "
                      "closing offer -> next closing bid, fees 0.10/0.20 %. Break-even precision for ARA1 ~11 %.", ""] + lines)
    out = os.path.join(HERE, f"IDX_ML_ARA_{date.today().isoformat()}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"wrote {out}")
    if "--no-store" not in sys.argv:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "ml_ara_predict", AR.END, params={"trials": LABELS, "n_trials_cumulative": n_trials, "model": PARAMS, "rounds": ROUNDS,
                                                                        "features": FEATURES, "K": K}, summary=json.loads(json.dumps(results, default=str)),
                                  names=[], report_path=out, note="; ".join(f"{lb}: {results[lb]['verdict']}" for lb in LABELS))
            print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
