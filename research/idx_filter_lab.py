#!/usr/bin/env python3
"""IDX filter lab (menu FL-2) - shared harness for the search for filters on the C0 radar wide sleeve (operator 2026-09-27:
"analisa filter apa yang bisa memfilter saham2 itu, benar2 cari tau supaya meningkatkan profitabilitas").

BASE TRADES = every C0 flag (close >= 1.3 x close 60 sessions ago, at its 250-day high, day return < 18 %) in U1 (20-day value >=
Rp 1 bn, close >= Rp 50, board on the day), one position per name, fill at the close after the flag (no fill on a >= 18 % day),
exit at the close after the first close <= 85 % of the entry or <= 75 % of the peak (RB-2's sleeve). Every FEATURE is known at the
close of the flag day (index i = e - 1). No ARA-lock / ARA-touch features (the ARA scope is frozen).

SPLIT (fixed before any search): TRAIN = entries 2021-01-04 .. 2023-12-29; HOLDOUT = entries 2024-01-02 .. end. The holdout file
lives in a separate folder and `eval --split holdout` needs FILTERLAB_HOLDOUT=1 and appends every call to holdout_log.jsonl.

  build                      -> research-scratch/idx/filterlab/{trades_train.parquet, arrays.npz, holdout/trades_holdout.parquet}
  eval --split train --expr "<pandas query over the feature columns>"
       prints JSON: kept / dropped trade stats (mean, median, hit, touch 2x, stop, Welch t), by year, and the EXPOSURE-MATCHED
       rupiah book of the kept trades vs the base book over the split window (Rp 20 m; base 1.25 % per position, <= 40 open;
       filtered size = 1.25 % x n_base / n_kept capped at 5 %, positions capped so exposure <= 50 %; lots of 100, offer / bid,
       fees 0.10 / 0.20 %, no sale on a <= -6.5 % day without a bid).
Columns: see FEATURES in build(); outcomes: net, touch2x, stop, hold, mfe, mae.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "research-scratch", "idx", "filterlab")
HOLD = os.path.join(OUT, "holdout")
TRAIN_START, TRAIN_END, HOLD_START = pd.Timestamp("2021-01-04"), pd.Timestamp("2023-12-29"), pd.Timestamp("2024-01-02")
FEE_B, FEE_S, LOT, CAP = 0.0010, 0.0020, 100, 20e6
BASE_PCT, BASE_MAX = 0.0125, 40


def tick(p):
    return np.where(p < 200, 1, np.where(p < 500, 2, np.where(p < 2000, 5, np.where(p < 5000, 10, 25))))


# ---------------------------------------------------------------------------------------------------------------------------
def build():
    sys.path.insert(0, HERE)
    import psycopg
    import idx_c0_filter as FL
    import idx_exit as E
    import idx_radar_book as RB  # noqa: F401
    import idx_swing2 as S
    import idx_trend_c0 as T
    os.makedirs(HOLD, exist_ok=True)
    P, unis, comp, Hp, Lp = E.load_all(T.dsn(), T.CACHE, board="pit")
    c_in, c_out = S.costs(P)
    adj, close, vol = P["adj"], P["close"], P["volume"]
    dates, cols = adj.index, adj.columns
    A, raw = adj.to_numpy(float), close.to_numpy(float)
    value = close * vol
    r = adj / adj.shift(1) - 1
    v20, v250 = value.rolling(20, min_periods=15).mean(), value.rolling(250, min_periods=200).mean()
    board = P["board_ok"].reindex(index=dates, columns=cols).fillna(False).astype(bool)
    u1 = (v20 >= 1e9) & (close >= 50) & (vol > 0) & adj.notna() & board
    c0 = (adj >= 1.3 * adj.shift(60)) & (adj >= adj.rolling(250, min_periods=200).max()) & (r < 0.18) & u1
    ma50 = adj.rolling(50, min_periods=50).mean()
    F = {  # name -> DataFrame aligned to (dates, cols); read at the flag day
        "r1": r, "r5": adj / adj.shift(5) - 1, "r20": adj / adj.shift(20) - 1, "r60": adj / adj.shift(60) - 1,
        "r120": adj / adj.shift(120) - 1, "r250": adj / adj.shift(250) - 1,
        "dist_ma50": adj / ma50 - 1, "dist_ma200": adj / adj.rolling(200, min_periods=200).mean() - 1,
        "vol20": r.rolling(20, min_periods=15).std(), "vol60": r.rolling(60, min_periods=40).std(),
        "attn20": v20 / v250, "attn5": value.rolling(5).mean() / value.rolling(60, min_periods=40).mean(),
        "value20_bn": v20 / 1e9, "price": close, "tick_rel": pd.DataFrame(tick(np.nan_to_num(raw, nan=1.0)), index=dates, columns=cols) / close,
        "spread_rel": (P["offer"] - P["bid"]) / close, "book_imb": P["bv"] / (P["bv"] + P["ov"]),
        "freq_ratio": P["freq"].rolling(20, min_periods=15).mean() / P["freq"].rolling(250, min_periods=200).mean(),
        "fnet5": P["f5"], "fnet20": P["f20"],
        "close_loc": (adj - Lp) / (Hp - Lp), "up20": (r > 0).rolling(20).sum(),
        "age": adj.notna().cumsum(), "prior_flags250": c0.astype(int).rolling(250, min_periods=1).sum().shift(1),
    }
    F["vol_ratio"] = F["vol20"] / F["vol60"]
    up = (r > 0).astype(int)
    cs = up.cumsum()
    F["up_streak"] = cs - cs.where(up == 0).ffill().fillna(0)
    # market-wide, same for every name on a day
    compc = comp.reindex(dates).ffill()
    mkt = pd.DataFrame(index=dates)
    mkt["ihsg_above_ma200"] = (compc > compc.rolling(200, min_periods=200).mean()).astype(float)
    mkt["ihsg_r60"] = compc / compc.shift(60) - 1
    mkt["breadth50"] = ((adj > ma50) & u1).sum(axis=1) / u1.sum(axis=1)
    mkt["flags_today"] = c0.sum(axis=1)
    mkt["flags_20d"] = c0.sum(axis=1).rolling(20, min_periods=1).sum()
    with psycopg.connect(T.dsn()) as conn:
        mac = pd.DataFrame(conn.execute("SELECT series, obs_date, value FROM idx.macro WHERE series IN ('gold','brent','cpo','usdidr','vix')").fetchall(),
                           columns=["s", "d", "v"])
        fd = pd.DataFrame(conn.execute("""SELECT code, trade_date, mcap, ev_ownership_30d, ev_exchange_query_10d, ev_material_30d, ev_rights_60d,
                                                 ev_buyback_30d, ev_dividend_30d FROM idx.feature_daily""").fetchall(),
                          columns=["code", "d", "mcap", "ev_own30", "ev_query10", "ev_material30", "ev_rights60", "ev_buyback30", "ev_div30"])
        lst = pd.DataFrame(conn.execute("SELECT code, sector, board, listing_date FROM idx.listing").fetchall(), columns=["code", "sector", "board_now", "listing_date"])
        tab = FL.earnings_table(conn)
    mac["d"] = pd.to_datetime(mac.d)
    mac["v"] = mac.v.astype(float)
    M = mac.pivot_table(index="d", columns="s", values="v").sort_index().reindex(dates, method="ffill")
    for s_ in ("gold", "brent", "cpo"):
        mkt[f"{s_}_r60"] = M[s_] / M[s_].shift(60) - 1
    mkt["usdidr_r20"] = M["usdidr"] / M["usdidr"].shift(20) - 1
    mkt["vix"] = M["vix"]
    fd["d"] = pd.to_datetime(fd.d)
    for c in fd.columns[2:]:
        fd[c] = fd[c].astype(float)
    fdi = fd.set_index(["d", "code"])
    lst = lst.set_index("code")
    # trades
    value_np = v20.to_numpy(float)
    rows = []
    Tn, N = A.shape
    c0n = c0.to_numpy(bool)
    t_first = int(np.searchsorted(dates, np.datetime64(TRAIN_START))) - 1
    Fn = {k: v.reindex(index=dates, columns=cols).to_numpy(float) for k, v in F.items()}
    for j in range(N):
        i = t_first
        while i < Tn - 2:
            if not c0n[i, j]:
                i += 1
                continue
            e = i + 1
            if np.isnan(A[e, j]) or (raw[e - 1, j] > 0 and raw[e, j] / raw[e - 1, j] - 1 >= 0.18) or not np.isfinite(c_in[e, j]):
                i += 1
                continue
            peak, x = A[e, j], None
            for k in range(e + 1, Tn):
                if np.isnan(A[k, j]):
                    continue
                peak = max(peak, A[k, j])
                if A[k, j] <= 0.85 * A[e, j] or A[k, j] <= 0.75 * peak:
                    x = k + 1
                    break
            open_ = x is None or x >= Tn
            if open_:
                x = Tn - 1
            while x > e and np.isnan(A[x, j]):
                x -= 1
            co = c_out[x, j] if np.isfinite(c_out[x, j]) else 0.004
            seg = A[e:min(e + 251, Tn), j]
            seg = seg[~np.isnan(seg)]
            path = A[e:x + 1, j]
            path = path[~np.isnan(path)]
            code, d_sig = cols[j], dates[i]
            row = dict(code=code, d=dates[e], i=i, e=e, j=j, x=x, open_at_end=open_,
                       net=(A[x, j] / A[e, j]) * (1 - co) / (1 + c_in[e, j]) - 1, touch2x=bool(len(seg) and seg.max() / A[e, j] >= 2),
                       stop=bool(len(path) > 1 and path[-2] <= 0.85 * A[e, j] if len(path) > 1 else False), hold=x - e,
                       mfe=path.max() / A[e, j] - 1, mae=path.min() / A[e, j] - 1)
            for k, arr in Fn.items():
                row[k] = arr[i, j]
            for k in mkt.columns:
                row[k] = mkt.iat[i, mkt.columns.get_loc(k)]
            try:
                f = fdi.loc[(d_sig, code)]
                for k in ("mcap", "ev_own30", "ev_query10", "ev_material30", "ev_rights60", "ev_buyback30", "ev_div30"):
                    row[k] = float(f[k])
            except KeyError:
                pass
            if code in lst.index:
                row["sector"] = lst.at[code, "sector"]
                row["board_now"] = lst.at[code, "board_now"]
            st = FL.state_at(tab, code, d_sig)
            if st:
                row.update(ytd_profit_bn=st["v"] / 1e9, earn_up=float(st["up"]), loss=float(st["loss"]),
                           earn_yoy=(st["v"] / abs(st["prev"]) - 1) if st["prev"] not in (None, 0) else np.nan)
                if row.get("mcap"):
                    row["ep_ytd"] = st["v"] / row["mcap"]
            rows.append(row)
            i = x + 1
    df = pd.DataFrame(rows)
    df["mcap_tn"] = df.get("mcap") / 1e12
    tr = df[(df.d >= TRAIN_START) & (df.d <= TRAIN_END)]
    ho = df[df.d >= HOLD_START]
    tr.to_parquet(os.path.join(OUT, "trades_train.parquet"))
    ho.to_parquet(os.path.join(HOLD, "trades_holdout.parquet"))
    np.savez(os.path.join(OUT, "arrays.npz"), A=A, raw=raw, offer=P["offer"].to_numpy(float), bid=P["bid"].to_numpy(float),
             dates=dates.values.astype("datetime64[ns]").astype(np.int64))
    print(f"built: train {len(tr)} trades ({tr.code.nunique()} names), holdout {len(ho)} trades; columns {len(df.columns)}")
    print(sorted(c for c in df.columns))


# ---------------------------------------------------------------------------------------------------------------------------
def replay(trades, arr, t0, t1, pct, maxpos):
    A, raw, off, bid = arr["A"], arr["raw"], arr["offer"], arr["bid"]
    entries = {}
    for e, j, x, s in trades:
        entries.setdefault(int(e), []).append((int(j), int(x), s))
    cash, held, nav = CAP, {}, np.full(t1 + 1, np.nan)
    for t in range(t0, t1 + 1):
        for j in [j for j, p in held.items() if p["x"] <= t]:
            p = held[j]
            rr = raw[t, j] / raw[t - 1, j] - 1 if raw[t - 1, j] > 0 else 0.0
            if np.isnan(A[t, j]) or (rr <= -0.065 and not (bid[t, j] > 0) and t - p["x"] < 10):
                continue
            px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])
            cash += p["u"] * (A[t, j] / p["a"]) * (px / raw[t, j]) * (1 - FEE_S)
            held.pop(j)
        mv = sum(p["u"] * A[t, j] / p["a"] for j, p in held.items() if not np.isnan(A[t, j]))
        nav_now = cash + mv
        for j, x, s in sorted(entries.get(t, []), key=lambda z: -z[2]):
            if j in held or len(held) >= maxpos or np.isnan(A[t, j]) or not raw[t, j] > 0:
                continue
            px = off[t, j] if off[t, j] > 0 and off[t, j] >= raw[t, j] else raw[t, j] + tick(raw[t, j])
            lots = int((pct * nav_now) // (px * LOT * (1 + FEE_B)))
            cost = lots * LOT * px * (1 + FEE_B)
            if lots < 1 or cost > cash:
                continue
            cash -= cost
            held[j] = {"a": A[t, j], "u": lots * LOT * raw[t, j], "x": x}
        mv = sum(p["u"] * A[t, j] / p["a"] for j, p in held.items() if not np.isnan(A[t, j]))
        nav[t] = cash + mv
    s = pd.Series(nav[t0:t1 + 1]).ffill()
    rr = s.pct_change().fillna(0)
    yrs = (t1 - t0) / 244
    return dict(cagr=float((s.iloc[-1] / CAP) ** (1 / yrs) - 1), sharpe=float(rr.mean() / rr.std() * np.sqrt(244)) if rr.std() > 0 else 0.0,
                mdd=float((s / s.cummax() - 1).min()))


def evaluate(split, expr):
    from scipy import stats
    if split == "holdout":
        if os.environ.get("FILTERLAB_HOLDOUT") != "1":
            raise SystemExit("holdout is locked: set FILTERLAB_HOLDOUT=1 (every call is logged)")
        df = pd.read_parquet(os.path.join(HOLD, "trades_holdout.parquet"))
        with open(os.path.join(HOLD, "holdout_log.jsonl"), "a") as fh:
            fh.write(json.dumps({"expr": expr}) + "\n")
    else:
        df = pd.read_parquet(os.path.join(OUT, "trades_train.parquet"))
    keep = df.eval(expr).fillna(False).astype(bool) if expr else pd.Series(True, index=df.index)
    k, d = df[keep], df[~keep]
    t = float(stats.ttest_ind(k.net, d.net, equal_var=False).statistic) if len(k) > 2 and len(d) > 2 else None
    arr = dict(np.load(os.path.join(OUT, "arrays.npz")))
    dates = pd.to_datetime(arr["dates"])
    t0 = int(np.searchsorted(dates, np.datetime64(TRAIN_START if split == "train" else HOLD_START)))
    t1 = int(np.searchsorted(dates, np.datetime64(TRAIN_END), side="right")) - 1 if split == "train" else len(dates) - 1
    base_tr = [(r.e, r.j, r.x, r.attn20 if np.isfinite(r.attn20) else 0.0) for r in df.itertuples()]
    kept_tr = [(r.e, r.j, r.x, r.attn20 if np.isfinite(r.attn20) else 0.0) for r in k.itertuples()]
    pct = min(0.05, BASE_PCT * len(df) / max(1, len(k)))
    maxpos = max(10, int(0.5 / pct))
    bb, kb = replay(base_tr, arr, t0, t1, BASE_PCT, BASE_MAX), replay(kept_tr, arr, t0, t1, pct, maxpos)
    stat = lambda z: dict(n=len(z), mean=float(z.net.mean()) if len(z) else None, median=float(z.net.median()) if len(z) else None,
                          hit=float((z.net > 0).mean()) if len(z) else None, touch2x=float(z.touch2x.mean()) if len(z) else None,
                          stop=float(z.stop.mean()) if len(z) else None)
    by_year = {int(y): dict(kept=stat(g[keep.loc[g.index]]), dropped=stat(g[~keep.loc[g.index]])) for y, g in df.groupby(df.d.dt.year)}
    out = dict(split=split, expr=expr, kept=stat(k), dropped=stat(d), welch_t=t, by_year=by_year,
               book_filtered=dict(**kb, pct=pct, maxpos=maxpos), book_base=bb)
    print(json.dumps(out, indent=1, default=lambda o: None if isinstance(o, float) and np.isnan(o) else str(o)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "eval"])
    ap.add_argument("--split", default="train", choices=["train", "holdout"])
    ap.add_argument("--expr", default="")
    a = ap.parse_args()
    build() if a.cmd == "build" else evaluate(a.split, a.expr)
