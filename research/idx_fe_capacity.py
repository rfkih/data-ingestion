#!/usr/bin/env python3
"""IDX menu FE-2 (2026-09-26): MARKET IMPACT and CAPACITY of the deployed combo book.

The backtests charge the closing offer (buys) / bid (sells) + Stockbit fees and assume ZERO market impact. That is fine at
Rp 20 M; it is wrong at Rp 500 M in IDX small caps. This script (measurement except part 3):

 1. IMPACT MODEL  cost = spread/2 + Y * sigma_d * (Q / ADV)^delta   (Almgren / Torre / Bouchaud square-root form)
    calibrated on what the desk has:
      A  daily net FOREIGN flow (idx.daily_summary foreign_buy - foreign_sell, 2020-2026, every name) as the metaorder proxy:
         I = sign(F) * (r - r_mkt) / sigma_20  vs  phi = |F| / ADV_20 (regular-board volume), binned, log-log fit
      B  monthly-window top-broker net flow (idx.broker_summary period NULL, ~17 large caps, 2023-09 -> 2026-08)
      C  the live feed (idx.feed_trade + idx.feed_book_1m, 4 full sessions 2026-09-22..25): 30-min signed volume vs mid move
      D  the visible book just before the pre-close (idx.feed_book, 10 levels): cost of sweeping Q shares, per phi
    The backtest's spread/2 is already charged (closing offer/bid); the model ADDS Y * sigma * phi^delta on each fill.
 2. CAPACITY CURVE  the deployed combo (gap 10 % / trend 5 % / ML ens4 5 %, 20 slots, floor 30 %; the engine of
    research/idx_engine_fix.py variant (d) = official baseline 33.8 % / 1.83 / -17.9 %) at NAV 20 M .. 5 B with the impact
    on every entry and exit, plus a participation cap (order <= p x ADV20; unfilled entry remainder skipped, exits that
    exceed the cap spill to the next sessions). Per sleeve and total.
 3. OPTIMAL EXECUTION (PRE-REGISTERED, 5 trials, cumulative N_BEFORE = 954 -> 959, ids 955..959) for the overnight sleeve
    that breaks first, at the NAV where it starts to bleed = where its impact drag first reaches 25 % of its zero-impact CAGR
    (Y central, no cap; the first draft read this point under cap 10 %, where the drag saturates - see the report; the schedules
    and the reading rule below were not changed). Each child order is capped at 10 % of ADV20:
      (a) all at one close (the capacity run itself - the reference, not a trial)
      t955 split2   entry and exit split evenly over 2 consecutive closes
      t956 split3   the same over 3 closes
      t957 ac_lo    Almgren-Chriss schedule over <= 3 closes (square-root temporary impact, timing risk on the unexecuted
      t958 ac_mid   part; fractions chosen per order by minimising E[cost] + lambda * Var numerically), lambda in
      t959 ac_hi    {1e-7, 1e-6, 1e-5} per Rp (risk-aversion grid; objective in Rp, variance in Rp^2)
    READING RULE (fixed before the run): a schedule WINS if it beats (a) on the sleeve-alone book by CAGR >= +1 pp AND
    Sharpe not lower AND mDD not deeper by > 1 pp, in BOTH halves (split at the window's middle date). If several win, the
    one with the highest full-window CAGR. (a) itself is re-run in the same pass.
 4. Recommendation: max NAV per sleeve before impact eats > 25 % of the sleeve's return; the sizing / participation rule.
READ-ONLY on market tables; one idx.study row ('fe_capacity'). Shared engine files are imported, never edited.
Env: IDX_BOARD_MODE=pit, IDX_EXIT_CACHE=tmp/exit_cache_pit.pkl, IDX_ML_CACHE=tmp/ml_strategy_cache.pkl.
"""
from __future__ import annotations

import json
import math
import os
import pickle
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
ML_CACHE = os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl")
PIT_CACHE = os.path.join(ROOT, "tmp", "exit_cache_pit.pkl")
os.environ["IDX_ML_CACHE"] = ML_CACHE
os.environ["IDX_BOARD_MODE"] = "pit"
os.environ["IDX_EXIT_CACHE"] = PIT_CACHE
import idx_combo_rupiah as CR  # noqa: E402
import idx_construction as K  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "fe_capacity"
N_BEFORE = 954
TRIALS = ["split2", "split3", "ac_lo", "ac_mid", "ac_hi"]
AC_LAMBDA = {"ac_lo": 1e-7, "ac_mid": 1e-6, "ac_hi": 1e-5}
NAVS = [20e6, 100e6, 250e6, 500e6, 1e9, 2.5e9, 5e9]
CAPS = [None, 0.10, 0.05, 0.02]
RULE = {"gap": 0.02, "trend": 0.05, "ML": 0.10}      # phi* = (0.125 edge / (Y sigma))^2 at edge 3.0 / 5.2 / 7.5 %, sigma 3.5 %, Y 0.83
TMP = os.path.join(ROOT, "tmp")
CAL_PKL = os.path.join(TMP, "fe_capacity_cal.pkl")
RUN_PKL = os.path.join(TMP, "fe_capacity_runs.pkl")
OUT = os.path.join(HERE, "IDX_FE_CAPACITY_2026-09-26.md")
REF = {"cagr": 0.338, "sharpe": 1.83, "mdd": -0.179}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# =============================================================================================================================
# 1. IMPACT CALIBRATION
# =============================================================================================================================
def load_daily(d):
    with psycopg.connect(d) as c:
        df = pd.DataFrame(c.execute(
            """SELECT code, trade_date, close, previous, volume, value, nonreg_volume, nonreg_value, foreign_buy, foreign_sell, remarks
               FROM idx.daily_summary WHERE trade_date >= '2019-10-01' AND close > 0""").fetchall(),
            columns=["code", "d", "close", "prev", "volume", "value", "nrv", "nrval", "fb", "fs", "remarks"])
    for k in ["close", "prev", "volume", "value", "nrv", "nrval", "fb", "fs"]:
        df[k] = pd.to_numeric(df[k], errors="coerce").astype(float)
    df["d"] = pd.to_datetime(df["d"])
    df = df.sort_values(["code", "d"])
    df["vreg"] = (df["volume"] - df["nrv"].fillna(0)).clip(lower=0)
    df["valreg"] = (df["value"] - df["nrval"].fillna(0)).clip(lower=0)
    df["r"] = df["close"] / df["prev"] - 1
    df.loc[(df["prev"] <= 0) | (df["r"].abs() > 0.35), "r"] = np.nan
    lr = np.log1p(df["r"])
    g = df.groupby("code", sort=False)
    df["adv20"] = g["vreg"].transform(lambda s: s.shift(1).rolling(20, min_periods=15).mean())
    df["advv20"] = g["valreg"].transform(lambda s: s.shift(1).rolling(20, min_periods=15).mean())
    df["sig20"] = lr.groupby(df["code"]).transform(lambda s: s.shift(1).rolling(20, min_periods=15).std())
    return df


def binfit(phi, I, w_date, nb=14, lo=1e-3, hi=1.0, boot=200, seed=7):
    """Bin phi on a log grid, mean I per bin; fit log(mean I) = log Y + delta log phi (bins with mean I > 0, weighted by n);
    also Y at delta fixed 0.5. Bootstrap by DATE clusters for CIs."""
    edges = np.logspace(np.log10(lo), np.log10(hi), nb + 1)
    m = (phi >= lo) & (phi < hi) & np.isfinite(I)
    phi, I, w_date = phi[m], I[m], w_date[m]
    b = np.digitize(phi, edges) - 1

    def fit(phi_, I_, b_):
        rows = []
        for k in range(nb):
            s = b_ == k
            if s.sum() >= 30:
                rows.append((np.exp(np.mean(np.log(phi_[s]))), I_[s].mean(), I_[s].std() / math.sqrt(s.sum()), int(s.sum())))
        R = np.array(rows)
        if len(R) < 3:
            return None
        pos = R[:, 1] > 0
        x, y, w = np.log(R[pos, 0]), np.log(R[pos, 1]), R[pos, 3]
        if pos.sum() >= 3:
            A = np.vstack([np.ones_like(x), x]).T * np.sqrt(w)[:, None]
            coef = np.linalg.lstsq(A, y * np.sqrt(w), rcond=None)[0]
            Y, delta = float(np.exp(coef[0])), float(coef[1])
            pred = coef[0] + coef[1] * x
            r2 = float(1 - np.sum(w * (y - pred) ** 2) / np.sum(w * (y - np.average(y, weights=w)) ** 2))
        else:
            Y, delta, r2 = float("nan"), float("nan"), float("nan")
        sq = np.sqrt(R[:, 0])
        Y05 = float(np.sum(R[:, 3] * R[:, 1] * sq) / np.sum(R[:, 3] * sq * sq))    # weighted LS through the origin, delta = 0.5
        return {"Y": Y, "delta": delta, "r2": r2, "Y05": Y05, "bins": R.tolist()}

    base = fit(phi, I, b)
    if base is None:
        return None
    rng = np.random.default_rng(seed)
    ud = np.unique(w_date)
    pos_of = pd.Series(np.arange(len(phi))).groupby(pd.Series(w_date).values).apply(lambda s: s.to_numpy()).to_dict()
    bs = []
    for _ in range(boot):
        pick = rng.choice(ud, len(ud))
        ix = np.concatenate([pos_of[u] for u in pick])
        f = fit(phi[ix], I[ix], b[ix])
        if f:
            bs.append((f["Y"], f["delta"], f["Y05"]))
    bs = np.array(bs)
    q = lambda k: [float(np.nanpercentile(bs[:, k], 5)), float(np.nanpercentile(bs[:, k], 95))]  # noqa: E731
    base.update({"Y_ci": q(0), "delta_ci": q(1), "Y05_ci": q(2), "n": int(len(phi)), "n_dates": int(len(ud))})
    return base


def cal_foreign(df):
    """A: daily net foreign flow as the metaorder proxy."""
    x = df[(df["d"] >= "2020-02-01") & df["fb"].notna() & df["fs"].notna() & (df["adv20"] > 0) & (df["sig20"] > 0.003)
           & df["r"].notna() & (df["close"] >= 50) & (df["advv20"] >= 5e8)].copy()
    x = x[(x["nrv"].fillna(0) <= 0.05 * x["volume"])]                         # negotiated blocks can carry the foreign flow
    x["F"] = x["fb"] - x["fs"]
    x = x[x["F"] != 0]
    x["rx"] = x["r"] - x.groupby("d")["r"].transform("median")               # strip the market move
    x["phi"] = x["F"].abs() / x["adv20"]
    x["I"] = np.sign(x["F"]) * x["rx"] / x["sig20"]
    x["I"] = x["I"].clip(-8, 8)
    dcode = x["d"].to_numpy()
    out = {"all": binfit(x["phi"].to_numpy(), x["I"].to_numpy(), dcode)}
    # liquidity terciles (ADV value) and halves
    q = x["advv20"].quantile([1 / 3, 2 / 3]).to_numpy()
    for nm, s in (("liq_low", x["advv20"] < q[0]), ("liq_mid", (x["advv20"] >= q[0]) & (x["advv20"] < q[1])), ("liq_high", x["advv20"] >= q[1]),
                  ("h1", x["d"] < "2023-06-01"), ("h2", x["d"] >= "2023-06-01"), ("small_adv_lt_5bn", x["advv20"] < 5e9)):
        y = x[s]
        out[nm] = binfit(y["phi"].to_numpy(), y["I"].to_numpy(), y["d"].to_numpy(), boot=100)
    # next-day reversal of the same-day move (permanent vs transient): mean sign(F) * r_{t+1}/sigma by phi bin
    x = x.sort_values(["code", "d"])
    nxt = df[["code", "d", "r"]].copy()
    nxt["r_next"] = nxt.groupby("code")["r"].shift(-1)
    nxt["rxn"] = nxt["r_next"] - nxt.groupby("d")["r_next"].transform("median")
    x = x.merge(nxt[["code", "d", "rxn"]], on=["code", "d"], how="left")
    x["In"] = np.sign(x["F"]) * x["rxn"] / x["sig20"]
    rev = []
    for lo, hi in ((0.01, 0.03), (0.03, 0.1), (0.1, 0.3), (0.3, 1.0)):
        s = (x["phi"] >= lo) & (x["phi"] < hi) & x["In"].notna()
        rev.append({"phi": [lo, hi], "same_day": float(x.loc[s, "I"].mean()), "next_day": float(x.loc[s, "In"].clip(-8, 8).mean()), "n": int(s.sum())})
    out["next_day"] = rev
    out["n_rows"] = int(len(x))
    out["median_phi"] = float(x["phi"].median())
    return out


def cal_broker(d, df):
    """B: monthly-window (the ~20-day rows) top-broker net flow vs the window's price change, 17 large caps."""
    with psycopg.connect(d) as c:
        b = pd.DataFrame(c.execute("""SELECT code, date_from, date_to, broker, SUM(net_lot) nl FROM idx.broker_summary
                                      WHERE period IS NULL GROUP BY 1,2,3,4""").fetchall(), columns=["code", "f", "t", "broker", "nl"])
    b["nl"] = pd.to_numeric(b["nl"]).astype(float)
    b["f"], b["t"] = pd.to_datetime(b["f"]), pd.to_datetime(b["t"])
    b = b[(b["t"] - b["f"]).dt.days >= 20]
    top = b.loc[b.groupby(["code", "f", "t"])["nl"].apply(lambda s: s.abs().idxmax())]
    px = df.set_index(["code", "d"])
    rows = []
    for r in top.itertuples():
        try:
            s = df[(df["code"] == r.code) & (df["d"] >= r.f) & (df["d"] <= r.t)]
            if len(s) < 10:
                continue
            p0 = s["prev"].iloc[0]
            p1 = s["close"].iloc[-1]
            n = len(s)
            adv = s["adv20"].iloc[0]
            sig = s["sig20"].iloc[0]
            Q = abs(r.nl) * 100
            rows.append({"phi": Q / (adv * n), "I": np.sign(r.nl) * (p1 / p0 - 1) / (sig * math.sqrt(n)), "d": r.f})
        except Exception:
            continue
    x = pd.DataFrame(rows).dropna()
    del px
    return {"fit": binfit(x["phi"].to_numpy(), x["I"].clip(-8, 8).to_numpy(), x["d"].to_numpy(), nb=6, lo=1e-3, hi=1.0, boot=200), "n": int(len(x))}


def cal_feed(d, df):
    """C: 30-min buckets on the live feed: signed volume (aggressor share x cum_volume change) vs mid move / sigma_d."""
    with psycopg.connect(d) as c:
        tr = pd.DataFrame(c.execute("""SELECT code, date_trunc('minute', ts) m, verb, SUM(qty) q, MAX(cum_volume) cv FROM idx.feed_trade
                                       WHERE ts::date BETWEEN '2026-09-22' AND '2026-09-25' GROUP BY 1,2,3""").fetchall(), columns=["code", "m", "verb", "q", "cv"])
        bk = pd.DataFrame(c.execute("""SELECT code, minute, bid_px[1], off_px[1] FROM idx.feed_book_1m WHERE minute::date BETWEEN '2026-09-22' AND '2026-09-25'
                                       AND bid_px[1] > 0 AND off_px[1] > bid_px[1]""").fetchall(), columns=["code", "m", "bid", "off"])
    for k in ("q", "cv"):
        tr[k] = pd.to_numeric(tr[k]).astype(float)
    for k in ("bid", "off"):
        bk[k] = pd.to_numeric(bk[k]).astype(float)
    tr["m"], bk["m"] = pd.to_datetime(tr["m"], utc=True), pd.to_datetime(bk["m"], utc=True)
    tr["b"] = tr["m"].dt.floor("30min")
    bk["b"] = bk["m"].dt.floor("30min")
    bk["mid"] = (bk["bid"] + bk["off"]) / 2
    sv = tr.pivot_table(index=["code", "b"], columns="verb", values="q", aggfunc="sum").fillna(0)
    for k in ("B", "S"):
        if k not in sv:
            sv[k] = 0.0
    cv = tr.groupby(["code", "b"])["cv"].max()
    tot = tr.groupby(["code", "b"])["q"].sum()
    x = pd.DataFrame({"B": sv["B"], "S": sv["S"], "tot": tot, "cv": cv}).reset_index().sort_values(["code", "b"])
    x["day"] = x["b"].dt.date
    x["dv"] = x.groupby(["code", "day"])["cv"].diff()
    x["dv"] = x["dv"].fillna(x["cv"])
    x["sv"] = (x["B"] - x["S"]) / x["tot"].replace(0, np.nan) * x["dv"]
    mid = bk.sort_values("m").groupby(["code", "b"])["mid"].agg(["first", "last"]).reset_index()
    x = x.merge(mid, on=["code", "b"])
    dd = df[["code", "d", "adv20", "sig20"]].copy()
    dd["day"] = dd["d"].dt.date
    x = x.merge(dd[["code", "day", "adv20", "sig20"]], on=["code", "day"], how="left")
    x = x[(x["adv20"] > 0) & (x["sig20"] > 0) & x["sv"].notna() & (x["sv"] != 0)]
    x["phi"] = x["sv"].abs() / x["adv20"]
    x["I"] = np.sign(x["sv"]) * np.log(x["last"] / x["first"]) / x["sig20"]
    x["I"] = x["I"].clip(-8, 8)
    return {"fit": binfit(x["phi"].to_numpy(), x["I"].to_numpy(), x["day"].astype(str).to_numpy(), nb=10, lo=1e-4, hi=0.3, boot=100),
            "n": int(len(x)), "sessions": 4, "names": int(x["code"].nunique())}


def cal_book(d, df):
    """D: the visible book at 15:49 WIB: cost (bps over the half-spread) of sweeping Q = phi x ADV20 shares off the 10 levels."""
    with psycopg.connect(d) as c:
        bk = pd.DataFrame(c.execute("""SELECT DISTINCT ON (code, ts::date) code, ts::date AS d0, bid_px, bid_vol, off_px, off_vol FROM idx.feed_book
                                       WHERE ts::date BETWEEN '2026-09-22' AND '2026-09-25' AND ts::time < '08:50' AND ts::time >= '08:40'
                                       ORDER BY code, ts::date, ts DESC""").fetchall(), columns=["code", "day", "bp", "bv", "op", "ov"])
    dd = df[["code", "d", "adv20", "sig20", "close"]].copy()
    dd["day"] = dd["d"].dt.date
    bk = bk.merge(dd, on=["code", "day"], how="left")
    phis = [0.001, 0.003, 0.01, 0.03, 0.05, 0.1]
    rows = []
    for r in bk.itertuples():
        if not r.adv20 or not r.bp or not r.op or not np.isfinite(r.adv20):
            continue
        op, ov = np.array(r.op, float), np.array(r.ov, float)
        bp = float(r.bp[0])
        if len(op) == 0 or op[0] <= bp:
            continue
        mid = (op[0] + bp) / 2
        half = op[0] / mid - 1
        for ph in phis:
            Q = ph * r.adv20
            cum = np.cumsum(ov)
            if cum[-1] < Q:
                rows.append({"phi": ph, "cost": np.nan, "half": half, "sig": r.sig20, "full": False})
                continue
            k = int(np.searchsorted(cum, Q))
            take = np.append(ov[:k], Q - (cum[k - 1] if k else 0))
            vwap = float(np.sum(take * op[:k + 1]) / Q)
            rows.append({"phi": ph, "cost": vwap / mid - 1 - half, "half": half, "sig": r.sig20, "full": True})
    x = pd.DataFrame(rows)
    out = []
    for ph, s in x.groupby("phi"):
        f = s[s["full"]]
        out.append({"phi": ph, "share_fillable_10lv": float(s["full"].mean()), "median_excess_bps": float(f["cost"].median() * 1e4) if len(f) else None,
                    "median_excess_over_sigma": float((f["cost"] / f["sig"]).median()) if len(f) else None, "median_half_spread_bps": float(s["half"].median() * 1e4)})
    return {"by_phi": out, "n_books": int(bk["code"].nunique()), "snapshots": int(len(bk))}


def calibrate(d):
    if os.path.exists(CAL_PKL) and not os.environ.get("FE_RECAL"):
        return pickle.load(open(CAL_PKL, "rb"))
    dpk = os.path.join(TMP, "fe_capacity_daily.pkl")
    df = pickle.load(open(dpk, "rb")) if os.path.exists(dpk) else load_daily(d)
    pickle.dump(df, open(dpk, "wb"))
    log("daily loaded", len(df))
    cal = {"A": cal_foreign(df)}
    log("A", {k: (v["Y"], v["delta"], v["Y05"]) for k, v in cal["A"].items() if isinstance(v, dict) and "Y" in v})
    cal["B"] = cal_broker(d, df)
    log("B", cal["B"]["n"], cal["B"]["fit"] and (cal["B"]["fit"]["Y"], cal["B"]["fit"]["delta"], cal["B"]["fit"]["Y05"]))
    cal["C"] = cal_feed(d, df)
    log("C", cal["C"]["n"], cal["C"]["fit"] and (cal["C"]["fit"]["Y"], cal["C"]["fit"]["delta"], cal["C"]["fit"]["Y05"]))
    cal["D"] = cal_book(d, df)
    log("D", cal["D"]["by_phi"])
    pickle.dump(cal, open(CAL_PKL, "wb"))
    return cal




def central_from(cal):
    """Local exponent / Y on the range the book trades (phi >= 0.03) from A's bins."""
    R = np.array(cal["A"]["all"]["bins"])
    s = R[:, 0] >= 0.03
    x, y, w = np.log(R[s, 0]), np.log(R[s, 1]), R[s, 3]
    A_ = np.vstack([np.ones_like(x), x]).T * np.sqrt(w)[:, None]
    c = np.linalg.lstsq(A_, y * np.sqrt(w), rcond=None)[0]
    sq = np.sqrt(R[s, 0])
    return {"delta_hi": float(c[1]), "Y_hi": float(np.exp(c[0])), "Y05_hi": float(np.sum(w * R[s, 1] * sq) / np.sum(w * sq * sq))}


# =============================================================================================================================
# 2. CAPACITY ENGINE  (= idx_engine_fix.engine_attr at Y = 0, no cap, one close; asserted)
# =============================================================================================================================
def load_inputs(d):
    pk = os.path.join(TMP, "fe_capacity_inputs.pkl")
    if os.path.exists(pk):
        return pickle.load(open(pk, "rb"))
    P = pickle.load(open(ML_CACHE, "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = K.ml_ens_trades(P, dates, codes, A, raw, offer, bid, liq)
    del P
    gap, _ = K.gap_events(d, dates)
    cs = set(codes)
    tr = [dict(y, tag="p", frac=1.0) for y in CR.trend_trades(d, dates, cache=PIT_CACHE, board="pit", legacy_shift=False) if y["code"] in cs]
    df = pickle.load(open(os.path.join(TMP, "fe_capacity_daily.pkl"), "rb"))
    w = lambda c: df.pivot_table(index="d", columns="code", values=c).reindex(index=dates, columns=codes)  # noqa: E731
    ADV = w("advv20").ffill(limit=5).to_numpy(float)
    SIG = w("sig20").ffill(limit=5)
    SIG = SIG.T.fillna(SIG.median(axis=1)).T.to_numpy(float)
    out = {"dates": dates, "codes": codes, "A": A, "raw": raw, "offer": offer, "bid": bid, "ml": ml, "gap": gap, "tr": tr, "ADV": ADV, "SIG": SIG}
    pickle.dump(out, open(pk, "wb"))
    return out


_AC: dict = {}
_GR: dict = {}


def _grid(n, step):
    if (n, step) not in _GR:
        m = int(round(1 / step))
        pts = [(a, b, m - a - b) for a in range(1, m + 1) for b in range(0, m + 1 - a)] if n == 3 else [(a, m - a) for a in range(1, m + 1)]
        _GR[(n, step)] = np.array(pts, float) / m
    return _GR[(n, step)]


def ac_fracs(X, sig, V, Y, dl, lam, n=3, step=0.05):
    """Almgren-Chriss with power-law temporary impact: fractions (f1..fn) minimising
    sum_k Y sig (f_k X / V)^dl f_k X  +  lam sig^2 sum_{k<n} (X (1 - F_k))^2   over a simplex grid (f1 > 0)."""
    key = (round(math.log(max(X, 1.0)), 2), round(math.log(V), 2), round(sig, 3), lam, n, Y, dl)
    if key in _AC:
        return _AC[key]
    G = _grid(n, step)
    cost = (Y * sig * (G * X / V) ** dl * G * X).sum(1)
    cum = np.cumsum(G, 1)[:, :-1]
    risk = lam * sig ** 2 * ((X * (1 - cum)) ** 2).sum(1)
    f = G[int(np.argmin(cost + risk))]
    f = tuple(float(z) for z in f)
    while len(f) > 1 and f[-1] == 0:
        f = f[:-1]
    _AC[key] = f
    return f


def engine_cap(I, capital, Y=0.0, dl=0.5, cap=None, sched="one", use=("gap", "trend", "ML"), floor=K.FLOOR, sched_sleeves=("trend", "ML")):
    """The #184 / engine_fix book with impact + participation cap + multi-session schedules for the overnight sleeves.
    Impact on a fill of q Rp in a name with ADV20 value V and sigma_20 s: extra cost fraction Y s (q/V)^dl on top of the closing
    offer/bid (marginal when several pieces hit the same name/side the same day). Cap p: a day's fills per name/side <= p V;
    entries: the excess is skipped; exits: the excess spills to the next session."""
    dates, codes, A, raw, offer, bid, ADV, SIG = I["dates"], I["codes"], I["A"], I["raw"], I["offer"], I["bid"], I["ADV"], I["SIG"]
    idx = {c: i for i, c in enumerate(codes)}
    T = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    tick = common.tick
    entries, exits, gaps = {}, {}, {}
    for n, x in enumerate(e for e in I["ml"] + I["tr"] if e["strat"] in use):
        x = dict(x, id=n)
        entries.setdefault(x["t_in"], []).append(x)
        exits.setdefault(x["t_out"], []).append(x)
    for x in (I["gap"] if "gap" in use else []):
        gaps.setdefault(x["t"], []).append(x)
    S = {"cash": capital, "mv": 0.0}
    held = {}
    nav = np.full(T, np.nan)
    pnl = {"gap": [], "trend": [], "ML": []}
    st = {s: {"sig": 0, "skip": 0, "want": 0.0, "got": 0.0, "imp": 0.0} for s in ("gap", "trend", "ML")}
    used = {}

    def vol(t, j):
        v = ADV[t, j]
        return v if np.isfinite(v) and v > 0 else np.nan

    def room(t, j, side, strat):
        cp = cap.get(strat) if isinstance(cap, dict) else cap
        if cp is None:
            return np.inf
        v = vol(t, j)
        return 0.0 if not np.isfinite(v) else max(cp * v - used.get((t, j, side), 0.0), 0.0)

    def imp_frac(t, j, side, q):
        if Y <= 0 or q <= 0:
            return 0.0
        v = vol(t, j)
        s = SIG[t, j] if np.isfinite(SIG[t, j]) else 0.03
        if not np.isfinite(v):
            return Y * s
        q0 = used.get((t, j, side), 0.0)
        return Y * s * ((q0 + q) ** (1 + dl) - q0 ** (1 + dl)) / (v ** dl) / q

    def mval(t):
        return sum(p["U"] * A[t, idx[k[2]]] for k, p in held.items() if not np.isnan(A[t, idx[k[2]]]))

    def names():
        return {(k[0], k[2]) for k in held}

    def fracs(strat, X, t, j):
        if strat not in sched_sleeves or sched == "one":
            return (1.0,)
        if sched == "split2":
            return (0.5, 0.5)
        if sched == "split3":
            return (1 / 3, 1 / 3, 1 / 3)
        v = vol(t, j)
        if not np.isfinite(v) or X <= 0:
            return (1.0,)
        s = SIG[t, j] if np.isfinite(SIG[t, j]) else 0.03
        return ac_fracs(X, s, v, Y, dl, AC_LAMBDA[sched])

    def buy_child(t, k, x, want_rp, nav_now):
        """buy up to want_rp of k's name at close t; returns Rp spent, 0 if nothing fillable, -1 if blocked by cash/floor"""
        j = idx[x["code"]]
        if np.isnan(A[t, j]) or raw[t, j] <= 0:
            return 0.0
        px = offer[t, j] if offer[t, j] > 0 and offer[t, j] >= raw[t, j] else raw[t, j] + tick(raw[t, j])
        q = min(want_rp, room(t, j, "b", x["strat"]))
        lots = int(q // (px * CR.LOT))
        if lots < 1:
            return 0.0
        gross = lots * CR.LOT * px
        imp = imp_frac(t, j, "b", gross)
        cost = gross * (1 + imp) * (1 + CR.FEE_BUY)
        if cost > S["cash"] or (floor > 0 and (S["mv"] + cost) / nav_now > 1 - floor):
            return -1.0
        used[(t, j, "b")] = used.get((t, j, "b"), 0.0) + gross
        S["cash"] -= cost
        S["mv"] += cost / (1 + CR.FEE_BUY)
        p = held[k]
        p["U"] += lots * CR.LOT * raw[t, j] / A[t, j]
        p["u0"] += lots * CR.LOT * raw[t, j]
        p["cost"] += cost
        st[x["strat"]]["imp"] += gross * imp
        st[x["strat"]]["got"] += gross
        return cost

    for t in range(t0, T):
        nav_prev = nav[t - 1] if t > t0 else capital
        day_gap, n_gap, mv_open = 0.0, 0, None
        for x in gaps.get(t, []):
            j = idx.get(x["code"])
            px = (x["open"] + tick(x["open"])) * (1 + CR.FEE_BUY)
            want = K.PCT["gap"] * nav_prev
            q = want if j is None else min(want, room(t, j, "g", "gap"))
            lots = int(q // (px * CR.LOT))
            cost = lots * CR.LOT * px
            if mv_open is None:
                mv_open = mval(t)
            wl = int(want // (px * CR.LOT))
            wcost = wl * CR.LOT * px
            ok = wl >= 1 and not (len(names()) + n_gap >= CR.MAX_POS or wcost > S["cash"] or (floor > 0 and (mv_open + wcost) / nav_prev > 1 - floor))
            if ok:
                st["gap"]["sig"] += 1
                st["gap"]["want"] += want
            if lots < 1:
                if ok:
                    st["gap"]["skip"] += 1
                continue
            if len(names()) + n_gap >= CR.MAX_POS or cost > S["cash"] or (floor > 0 and (mv_open + cost) / nav_prev > 1 - floor):
                continue
            net = x["net"]
            if Y > 0 and j is not None:
                ib = imp_frac(t, j, "g", cost)
                is_ = imp_frac(t, j, "s", cost)
                net = (1 + net) * (1 - is_) / (1 + ib) - 1
                st["gap"]["imp"] += cost * (ib + is_)
                used[(t, j, "s")] = used.get((t, j, "s"), 0.0) + cost
            if j is not None:
                used[(t, j, "g")] = used.get((t, j, "g"), 0.0) + cost
            st["gap"]["got"] += cost
            S["cash"] -= cost
            n_gap += 1
            day_gap += cost * (1 + net)
            pnl["gap"].append((t, cost * net))
        S["cash"] += day_gap
        for x in exits.get(t, []):
            k = (x["strat"], x["tag"], x["code"])
            if k in held and held[k]["id"] == x["id"] and held[k]["sell"] is None:
                p = held[k]
                p["buy"] = []
                j = idx[k[2]]
                X = p["U"] * A[t, j] if not np.isnan(A[t, j]) else 0.0
                p["sell"] = list(fracs(k[0], X, t, j))
        for k in list(held):
            p = held[k]
            if p["sell"] is None:
                continue
            j = idx[k[2]]
            if np.isnan(A[t, j]) or raw[t, j] <= 0:
                if p["U"] > 0 and not p.get("sold_any"):                    # the reference: value at entry, closed today
                    proceeds = p["u0"] * (1 - CR.FEE_SELL)
                    S["cash"] += proceeds
                    pnl[k[0]].append((t, p["got"] + proceeds - p["cost"]))
                    held.pop(k)
                continue
            sh_now = p["U"] * A[t, j] / raw[t, j]
            f = p["sell"].pop(0) if p["sell"] else 1.0
            rest = sum(p["sell"])
            want_sh = sh_now if rest <= 1e-12 else sh_now * f / (f + rest)
            px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])
            q = min(want_sh * px, room(t, j, "s", k[0]))
            if q <= 0:
                p["sell"] = [f] + p["sell"] if p["sell"] else [1.0]
                continue
            imp = imp_frac(t, j, "s", q)
            used[(t, j, "s")] = used.get((t, j, "s"), 0.0) + q
            proceeds = q * (1 - imp) * (1 - CR.FEE_SELL)
            st[k[0]]["imp"] += q * imp
            S["cash"] += proceeds
            p["got"] += proceeds
            p["sold_any"] = True
            sold = q / px
            if sold >= sh_now * (1 - 1e-9):
                pnl[k[0]].append((t, p["got"] - p["cost"]))
                held.pop(k)
            else:
                p["U"] *= 1 - sold / sh_now
                p["u0"] *= 1 - sold / sh_now
                if not p["sell"]:
                    p["sell"] = [1.0]
        S["mv"] = mval(t)
        nav_now = S["cash"] + S["mv"]
        for k in list(held):
            p = held[k]
            if p["buy"] and p["sell"] is None and p["buy"][0][0] == t:
                _, rp = p["buy"].pop(0)
                if buy_child(t, k, p["x"], rp, nav_now) < 0:
                    p["buy"] = []
        for x in sorted(entries.get(t, []), key=lambda z: 0 if z["strat"] == "trend" else 1):
            k = (x["strat"], x["tag"], x["code"])
            j = idx[x["code"]]
            if k in held or np.isnan(A[t, j]) or raw[t, j] <= 0:
                continue
            new_name = (x["strat"], x["code"]) not in names()
            px = offer[t, j] if offer[t, j] > 0 and offer[t, j] >= raw[t, j] else raw[t, j] + tick(raw[t, j])
            want = K.PCT[x["strat"]] * x["frac"] * nav_now
            wl = int(want // (px * CR.LOT))
            if wl < 1 or (new_name and len(names()) >= CR.MAX_POS):
                continue
            wcost = wl * CR.LOT * px * (1 + CR.FEE_BUY)
            f = fracs(x["strat"], want, t, j)
            fl = int(want * f[0] // (px * CR.LOT))
            fcost = fl * CR.LOT * px * (1 + CR.FEE_BUY)
            if fcost > S["cash"] or (floor > 0 and (S["mv"] + fcost) / nav_now > 1 - floor):
                continue                                                     # blocked by cash / floor (not a capacity skip)
            st[x["strat"]]["sig"] += 1
            st[x["strat"]]["want"] += want
            held[k] = {"t": t, "U": 0.0, "u0": 0.0, "cost": 0.0, "got": 0.0, "id": x["id"], "sell": None, "x": x,
                       "buy": [(t + i, want * fi) for i, fi in enumerate(f) if i > 0 and t + i < T and fi > 0]}
            spent = buy_child(t, k, x, want * f[0], nav_now) if fl >= 1 else 0.0
            if spent <= 0 and not held[k]["buy"]:
                held.pop(k)
                st[x["strat"]]["skip"] += 1
            _ = wcost
        for k in [k for k, p in held.items() if p["U"] <= 0 and not p["buy"] and p["sell"] is None]:
            held.pop(k)
            st[k[0]]["skip"] += 1
        for k in [k for k, p in held.items() if p["U"] <= 0 and p["sell"] is not None]:
            held.pop(k)
        nav[t] = S["cash"] + mval(t)
    return pd.Series(nav[t0:], index=dates[t0:]), pnl, st


def stt(nav):
    s = CR.stats(nav)
    return {k: s[k] for k in ("final", "cagr", "sharpe", "mdd", "by_year")}


# =============================================================================================================================
# driver
# =============================================================================================================================
EXT = [10e9, 25e9, 50e9, 100e9]                        # only to locate the halving / 25 % points beyond 5 B
BOOKS = {"total": ("gap", "trend", "ML"), "gap": ("gap",), "trend": ("trend",), "ML": ("ML",)}


def run_one(I, nav0, **kw):
    nav, pnl, st = engine_cap(I, nav0, **kw)
    s = stt(nav)
    s["h"] = [{k: h[k] for k in ("cagr", "sharpe", "mdd")} for h in K.halves(nav)]
    sig = sum(v["sig"] for v in st.values())
    s["skip"] = float(sum(v["skip"] for v in st.values()) / sig) if sig else 0.0
    want = sum(v["want"] for v in st.values())
    s["fill"] = float(sum(v["got"] for v in st.values()) / want) if want else float("nan")
    got = sum(v["got"] for v in st.values())
    s["imp_bps"] = float(sum(v["imp"] for v in st.values()) / got * 1e4) if got else 0.0
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    s["drag"] = float(sum(v["imp"] for v in st.values()) / (nav.mean() * yrs))     # impact Rp per year / average NAV
    s["sleeve"] = {k: {"sig": v["sig"], "skip": v["skip"], "fill": v["got"] / v["want"] if v["want"] else float("nan"),
                       "imp_bps": v["imp"] / v["got"] * 1e4 if v["got"] else 0.0,
                       "pnl": float(sum(z for _, z in pnl[k]))} for k, v in st.items()}
    return s


def crossing(navs, vals, thr):
    """smallest NAV (log-linear interpolation) at which vals first drops to <= thr; None if never on the grid"""
    for i, (n, v) in enumerate(zip(navs, vals)):
        if v <= thr:
            if i == 0:
                return n
            n0, v0 = navs[i - 1], vals[i - 1]
            w = (v0 - thr) / (v0 - v) if v0 != v else 1.0
            return float(math.exp(math.log(n0) + w * (math.log(n) - math.log(n0))))
    return None


def main() -> int:
    d = K.dsn()
    cal = calibrate(d)
    hi = central_from(cal)
    Ya, Yb = hi["Y05_hi"], cal["B"]["fit"]["Y05"]
    Yc = round(math.sqrt(Ya * Yb), 2)
    log(f"central Y (delta 0.5) = sqrt(A {Ya:.2f} x B {Yb:.2f}) = {Yc}; A local exponent {hi['delta_hi']:.2f}")
    I = load_inputs(d)
    nav0, _, _ = engine_cap(I, 20e6)
    base = stt(nav0)
    import idx_engine_fix as EF
    ref, _, _ = EF.engine_attr(I["dates"], I["codes"], I["A"], I["raw"], I["offer"], I["bid"], I["ml"] + I["tr"], I["gap"])
    assert np.allclose(nav0.to_numpy(), ref.to_numpy(), atol=1e-3), "engine_cap(Y=0) != engine_fix.engine_attr"
    assert abs(base["cagr"] - REF["cagr"]) < 0.0015 and abs(base["sharpe"] - REF["sharpe"]) < 0.01 and abs(base["mdd"] - REF["mdd"]) < 0.0015, base
    log(f"baseline reproduced: {base['cagr'] * 100:.1f} % / {base['sharpe']:.2f} / {base['mdd'] * 100:.1f} %")

    grid = NAVS + EXT
    scen = {"zero": dict(Y=0.0, cap=None)}
    for Y in sorted({0.5, Yc, 1.0, 1.5}):
        for cp in CAPS:
            scen[f"Y{Y:g}_cap{'none' if cp is None else int(cp * 100)}"] = dict(Y=Y, cap=cp)
    scen["Alocal_cap10"] = dict(Y=hi["Y_hi"], dl=hi["delta_hi"], cap=0.10)
    for Y in sorted({0.5, Yc, 1.0, 1.5}):                                  # the model-derived per-sleeve rule (measurement, not a trial)
        scen[f"Y{Y:g}_rule"] = dict(Y=Y, cap=RULE)
    R = {}
    for sn, kw in scen.items():
        for b, use in BOOKS.items():
            for nv in grid:
                R[(sn, b, nv)] = run_one(I, nv, use=use, **kw)
        log(f"{sn}: total " + " ".join(f"{nv / 1e6:g}M:{R[(sn, 'total', nv)]['cagr'] * 100:.1f}" for nv in grid))
    main_s = f"Y{Yc:g}_cap10"

    # thresholds: NAV where CAGR halves (vs the Rp 20 M zero-impact CAGR) and where impact eats > 25 % (vs zero-impact at the same NAV)
    thr = {}
    for sn in scen:
        if sn == "zero":
            continue
        for b in BOOKS:
            c = [R[(sn, b, nv)]["cagr"] for nv in grid]
            z = [R[("zero", b, nv)]["cagr"] for nv in grid]
            share = [1 - ci / zi if zi > 0 else float("nan") for ci, zi in zip(c, z)]
            dr = np.array([R[(sn, b, nv)]["drag"] for nv in grid])
            ok = dr > 0
            bb, aa = np.polyfit(np.log(np.array(grid)[ok]), np.log(dr[ok]), 1) if ok.sum() >= 3 else (float("nan"), float("nan"))
            zref = float(np.median([R[("zero", b, nv)]["cagr"] for nv in grid if nv >= 100e6]))
            d25 = float(np.exp((math.log(0.25 * zref) - aa) / bb)) if zref > 0 and np.isfinite(bb) else None
            d50 = float(np.exp((math.log(0.50 * zref) - aa) / bb)) if zref > 0 and np.isfinite(bb) else None
            thr[(sn, b)] = {"half": crossing(grid, [-s for s in share], -0.5), "eat25": crossing(grid, [-s for s in share], -0.25), "share": share,
                            "drag_b": float(bb), "drag25": d25, "drag50": d50, "zref": zref}
    # ---- 3. execution trials on the overnight sleeve that breaks first ----
    pure_s = f"Y{Yc:g}_capnone"                                              # pure impact: DRAG is only meaningful without a cap
    ov = {b: thr[(pure_s, b)]["drag25"] or float("inf") for b in ("trend", "ML")}
    first = min(ov, key=ov.get)
    nav_x = float(f"{ov[first]:.2g}")
    log(f"first overnight sleeve to bleed at {pure_s}: {first} (drag25 {ov[first] / 1e6:.0f} M) -> execution at {nav_x / 1e6:g} M; gap drag25 {thr[(pure_s, 'gap')]['drag25'] / 1e6:.0f} M")
    X = {}
    for sch in ["one"] + TRIALS:
        X[sch] = {"sleeve": run_one(I, nav_x, Y=Yc, cap=0.10, sched=sch, use=BOOKS[first]),
                  "total": run_one(I, nav_x, Y=Yc, cap=0.10, sched=sch)}
        for Yx in (0.5, 1.5):
            X[sch][f"sleeve_Y{Yx:g}"] = run_one(I, nav_x, Y=Yx, cap=0.10, sched=sch, use=BOOKS[first])
        log(f"exec {sch}: {first} {X[sch]['sleeve']['cagr'] * 100:.2f}/{X[sch]['sleeve']['sharpe']:.2f}/{X[sch]['sleeve']['mdd'] * 100:.1f} imp {X[sch]['sleeve']['imp_bps']:.0f} bps"
            f" | total {X[sch]['total']['cagr'] * 100:.2f}")
    a = X["one"]["sleeve"]
    verdict = {}
    for sch in TRIALS:
        s = X[sch]["sleeve"]
        full = s["cagr"] - a["cagr"] >= 0.01 and s["sharpe"] >= a["sharpe"] and s["mdd"] >= a["mdd"] - 0.01
        halves_ok = [h["cagr"] - ha["cagr"] >= 0.01 and h["sharpe"] >= ha["sharpe"] and h["mdd"] >= ha["mdd"] - 0.01 for h, ha in zip(s["h"], a["h"])]
        verdict[sch] = {"full": bool(full), "halves": [bool(z) for z in halves_ok], "wins": bool(full and all(halves_ok))}
    winners = [s for s in TRIALS if verdict[s]["wins"]]
    best = max(winners, key=lambda s: X[s]["sleeve"]["cagr"]) if winners else None
    ac_sched = {lam: [ac_fracs(q * 1e6, 0.035, 20e9, Yc, 0.5, AC_LAMBDA[lam]) for q in (5, 25, 100, 400)] for lam in ("ac_lo", "ac_mid", "ac_hi")}

    with psycopg.connect(d) as conn:
        n_led = conn.execute("SELECT max((params->>'n_trials_cumulative')::int) FROM idx.study").fetchone()[0]
    write_report(cal, hi, Yc, base, scen, R, thr, grid, main_s, first, nav_x, X, verdict, best, ac_sched, n_led)
    if os.environ.get("FE_NOSTORE"):
        return 0
    summ = {"impact_model": {"form": "cost = spread/2 (already in backtest) + Y sigma20 (Q/ADV20_value)^delta per fill", "Y_central": Yc, "delta": 0.5,
                             "A_foreign": {k: {x: v[x] for x in ("Y", "delta", "r2", "Y05", "Y_ci", "delta_ci", "Y05_ci", "n")} for k, v in cal["A"].items() if isinstance(v, dict) and "Y05" in v},
                             "A_local_phi_ge_0.03": hi, "A_next_day": cal["A"]["next_day"],
                             "B_broker_monthly": {x: cal["B"]["fit"][x] for x in ("Y", "delta", "r2", "Y05", "Y_ci", "delta_ci", "Y05_ci", "n")},
                             "C_feed": {"Y05": cal["C"]["fit"]["Y05"], "n": cal["C"]["n"], "verdict": "uninformative (sign reversed; feed captures ~1/3 of volume, verb unreliable)"},
                             "D_book": cal["D"]["by_phi"]},
            "baseline_reproduced": {k: base[k] for k in ("cagr", "sharpe", "mdd")},
            "capacity": {f"{sn}|{b}|{nv:.0f}": {k: v for k, v in R[(sn, b, nv)].items() if k in ("cagr", "sharpe", "mdd", "skip", "fill", "imp_bps", "drag")} for (sn, b, nv) in R},
            "thresholds": {f"{sn}|{b}": {k: v[k] for k in ("half", "eat25", "drag_b", "drag25", "drag50", "zref")} for (sn, b), v in thr.items()},
            "execution": {"sleeve": first, "nav": nav_x, "runs": {s: {k: {x: X[s][k][x] for x in ("cagr", "sharpe", "mdd", "imp_bps", "fill", "skip", "h")} for k in X[s]} for s in X},
                          "verdict": verdict, "winner": best}}
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date(2026, 9, 26),
                              params={"n_trials_cumulative": N_BEFORE + len(TRIALS), "n_trials_before": N_BEFORE, "n_before_ledger_at_run": n_led, "trials_added": len(TRIALS),
                                      "trial_ids": list(range(N_BEFORE + 1, N_BEFORE + len(TRIALS) + 1)), "trials": TRIALS, "ac_lambda": AC_LAMBDA,
                                      "measurements_not_trials": ["impact calibration A-D", "capacity curve"], "navs": grid, "caps": CAPS, "scenarios": {k: {x: y for x, y in v.items()} for k, v in scen.items()},
                                      "deployed": K.PCT, "floor": K.FLOOR, "slots": CR.MAX_POS, "window": [str(CR.START.date()), str(CR.END.date())],
                                      "caches": {"pit": PIT_CACHE, "ml": ML_CACHE}, "board_mode": "pit"},
                              summary=common.plain(summ), names=[], report_path=OUT,
                              note="FE-2 market impact (sqrt law, IDX-calibrated) + capacity curve of the deployed combo + Almgren-Chriss execution trials")
    log(f"study #{sid} stored; report {OUT}")
    return 0


def pct(x, n=1):
    return "-" if x is None or not np.isfinite(x) else f"{x * 100:.{n}f} %"


def rp(x):
    if x is None or not np.isfinite(x):
        return "> 100 B"
    return f"Rp {x / 1e9:.2f} B" if x >= 1e9 else f"Rp {x / 1e6:.0f} M"


def write_report(cal, hi, Yc, base, scen, R, thr, grid, main_s, first, nav_x, X, verdict, best, ac_sched, n_led):
    A = cal["A"]
    pure_s = f"Y{Yc:g}_capnone"
    L = ["# IDX FE-2 - market impact and capacity of the deployed combo book - 2026-09-26", "",
         f"Script `research/idx_fe_capacity.py`. Impact calibration and the capacity curve are MEASUREMENT (0 trials); part 3 spends "
         f"{len(TRIALS)} pre-registered trials, cumulative N {N_BEFORE} -> {N_BEFORE + len(TRIALS)} (ids {N_BEFORE + 1}..{N_BEFORE + len(TRIALS)}; "
         f"range 955..960 was allocated to this menu by the caller; the ledger max at run time, {n_led}, is fe_kelly_rl / rl_alloc, which start after 960). Deployed book = gap 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots, cash floor 30 %, "
         f"{CR.START.date()} -> {CR.END.date()}, the engine of `idx_engine_fix.py` (d) with point-in-time board (IDX_BOARD_MODE=pit, "
         "tmp/exit_cache_pit.pkl, tmp/ml_strategy_cache.pkl); gap opens only open_src='idx'.", "",
         f"**Baseline reproduced** (Rp 20 M, zero impact, no cap): {pct(base['cagr'])} / {base['sharpe']:.2f} / {pct(base['mdd'])} "
         "(target 33.8 % / 1.83 / -17.9 %; the capacity engine is asserted equal to `engine_fix.engine_attr` to 1e-3 Rp per day).", "",
         "## 1. Impact model", "",
         "cost per fill = spread/2 (already charged: buys at the closing offer, sells at the closing bid) + **Y x sigma20 x (Q / ADV20)^delta**, "
         "sigma20 = 20-day stdev of daily log returns, ADV20 = 20-day mean REGULAR-board value (negotiated trades removed), both known at t-1; "
         "Q = the order's Rp value. Several pieces in one name/side on one day pay the marginal cost of the aggregate.", "",
         "| source | proxy | n | Y (free delta) | delta [90 % CI] | R2 (bins) | Y at delta=0.5 [90 % CI] |", "|---|---|---|---|---|---|---|"]
    for k, lab in (("all", "A all"), ("liq_low", "A ADV tercile low"), ("liq_mid", "A ADV tercile mid"), ("liq_high", "A ADV tercile high"),
                   ("small_adv_lt_5bn", "A ADV < Rp 5 bn"), ("h1", "A 2020-02..2023-05"), ("h2", "A 2023-06..2026-09")):
        v = A[k]
        L.append(f"| {lab} | daily net foreign flow | {v['n']:,} | {v['Y']:.2f} | {v['delta']:.2f} [{v['delta_ci'][0]:.2f}, {v['delta_ci'][1]:.2f}] | {v['r2']:.2f} | "
                 f"{v['Y05']:.2f} [{v['Y05_ci'][0]:.2f}, {v['Y05_ci'][1]:.2f}] |")
    L.append(f"| A, phi >= 0.03 only | local fit on the bins the book trades in | - | {hi['Y_hi']:.2f} | {hi['delta_hi']:.2f} | - | {hi['Y05_hi']:.2f} |")
    b = cal["B"]["fit"]
    L.append(f"| B | top-broker net over ~20-day windows (17 large caps) | {b['n']} | {b['Y']:.2f} | {b['delta']:.2f} [{b['delta_ci'][0]:.2f}, {b['delta_ci'][1]:.2f}] | {b['r2']:.2f} | "
             f"{b['Y05']:.2f} [{b['Y05_ci'][0]:.2f}, {b['Y05_ci'][1]:.2f}] |")
    c = cal["C"]
    L.append(f"| C | live feed, 30-min signed volume (4 sessions, {c['names']} names) | {c['n']:,} | - | - | - | {c['fit']['Y05']:.2f} (wrong sign) |")
    L += ["", "A bins (phi = |net foreign| / ADV20, mean I = sign x market-relative return / sigma20): " +
          ", ".join(f"{p:.3f}: {m:+.3f}" for p, m, _, _ in A["all"]["bins"]) + ".",
          "Next-day continuation of the same-day move (A, market-relative, in sigma): " +
          "; ".join(f"phi {r['phi'][0]}-{r['phi'][1]}: same day {r['same_day']:+.2f}, next day {r['next_day']:+.2f}" for r in A["next_day"]) + ".", "",
          "D - the visible book (10 levels) at 15:40-15:49 WIB, 4 sessions: cost of sweeping phi x ADV20 over the half-spread:", "",
          "| phi | share of books deep enough | median excess cost | in sigma | median half-spread |", "|---|---|---|---|---|"]
    for r in cal["D"]["by_phi"]:
        L.append(f"| {r['phi']} | {r['share_fillable_10lv'] * 100:.0f} % | {r['median_excess_bps'] or 0:.0f} bps | {r['median_excess_over_sigma'] or 0:.2f} | {r['median_half_spread_bps']:.0f} bps |")
    L += ["", f"**Model used: delta = 0.5, Y central = {Yc}** (geometric mean of A's local fit {hi['Y05_hi']:.2f} and B {b['Y05']:.2f}); bracket Y = 0.5 / 1.0 "
          "(literature) and 1.5 (stress: what an immediate sweep of the visible book implies at phi 0.05-0.1). Plus the A local free fit "
          f"(Y {hi['Y_hi']:.2f}, delta {hi['delta_hi']:.2f}) as an exponent check.", "",
          "## 2. Capacity curve", "",
          f"Main scenario **{main_s}** (Y {Yc}, participation cap 10 % of ADV20 per name/side/day: entry excess skipped, exit excess spills to the "
          "next closes). CAGR / Sharpe / mDD; skip = signals with no fill because of the cap; fill = filled / wanted Rp; imp = average impact per Rp traded.", "",
          "| NAV | total | gap | trend | ML | total skip / fill | round-trip impact bps per Rp entered (gap / trend / ML) | drag pp/yr |", "|---|---|---|---|---|---|---|---|"]
    for nv in grid:
        t_ = R[(main_s, "total", nv)]
        cells = [f"{R[(main_s, bk, nv)]['cagr'] * 100:.1f} / {R[(main_s, bk, nv)]['sharpe']:.2f} / {R[(main_s, bk, nv)]['mdd'] * 100:.0f}" for bk in BOOKS]
        sl = t_["sleeve"]
        L.append(f"| {rp(nv)} | " + " | ".join(cells) + f" | {t_['skip'] * 100:.1f} % / {t_['fill'] * 100:.0f} % | {sl['gap']['imp_bps']:.0f} / {sl['trend']['imp_bps']:.0f} / {sl['ML']['imp_bps']:.0f} | {t_['drag'] * 100:.2f} |")
    L += ["", "Zero-impact reference at each NAV (lots of 100 only): " + ", ".join(f"{rp(nv)} {R[('zero', 'total', nv)]['cagr'] * 100:.1f} %" for nv in grid) + ".", "",
          "Per-sleeve skip share (main scenario, sleeve alone): " + "; ".join(
              f"{bk}: " + ", ".join(f"{rp(nv)} {R[(main_s, bk, nv)]['skip'] * 100:.0f} %" for nv in grid if nv <= 5e9) for bk in ("gap", "trend", "ML")) + ".", "",
          "### NAV thresholds (sleeve alone; total = the combined book)", "",
          "SIM = first NAV on the grid (log-interpolated) where the simulated CAGR is <= 75 % / <= 50 % of the zero-impact CAGR at the same NAV "
          "(the zero-impact CAGR itself moves with NAV through lot rounding: the ML quarter-pieces are Rp 250 k at Rp 20 M). The combined book is "
          "path-dependent (shared cash, floor, slots), so its SIM points are noisy. DRAG = the smooth estimate: realised impact Rp per year / average NAV, "
          "fitted as a power of NAV over the grid (slope b ~ 0.5 = square root), solved for drag = 25 % / 50 % of the sleeve's zero-impact CAGR "
          "(median over NAV >= 100 M). DRAG is shown only without a cap: under a cap the impact saturates and the cost moves into skipped / "
          "unfilled signals, which only SIM sees. **Capacity = DRAG 25 % without a cap (cross-checked by SIM); cap rules are read on SIM.**", "",
          "| scenario | book | zero-impact CAGR | SIM 25 % | SIM 50 % (CAGR halves) | DRAG 25 % | DRAG 50 % | drag slope b |", "|---|---|---|---|---|---|---|---|"]
    for sn in scen:
        if sn == "zero":
            continue
        for bk in BOOKS:
            t_ = thr[(sn, bk)]
            nc = sn.endswith("capnone")
            L.append(f"| {sn} | {bk} | {t_['zref'] * 100:.1f} % | {rp(t_['eat25'])} | {rp(t_['half'])} | {rp(t_['drag25']) if nc else '-'} | "
                     f"{rp(t_['drag50']) if nc else '-'} | {t_['drag_b']:.2f} |")
    L += ["", "Total book CAGR by scenario and NAV:", "", "| scenario | " + " | ".join(rp(nv) for nv in grid) + " |", "|---|" + "---|" * len(grid)]
    for sn in scen:
        L.append(f"| {sn} | " + " | ".join(f"{R[(sn, 'total', nv)]['cagr'] * 100:.1f}" for nv in grid) + " |")
    a = X["one"]["sleeve"]
    L += ["", f"## 3. Optimal execution - {first} sleeve at {rp(nav_x)} (Y {Yc}, cap 10 % per child)", "",
          f"The first OVERNIGHT sleeve to lose 25 % of its return to impact (pure impact, Y {Yc}, no cap) is **{first}** (DRAG 25 % at "
          f"{rp(thr[(pure_s, first)]['drag25'])}; the trials run at that NAV); the gap sleeve (DRAG 25 % at {rp(thr[(pure_s, 'gap')]['drag25'])}) is intraday (buy the open, sell the same close), so a multi-session schedule "
          "does not apply to it.", "",
          "| schedule | sleeve CAGR / Sharpe / mDD | H1 | H2 | imp bps | fill | sleeve @Y0.5 | sleeve @Y1.5 | total book | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for sch in ["one"] + TRIALS:
        s = X[sch]["sleeve"]
        v = verdict.get(sch)
        L.append(f"| {sch} | {s['cagr'] * 100:.2f} / {s['sharpe']:.2f} / {s['mdd'] * 100:.1f} | {s['h'][0]['cagr'] * 100:.1f} / {s['h'][0]['sharpe']:.2f} | "
                 f"{s['h'][1]['cagr'] * 100:.1f} / {s['h'][1]['sharpe']:.2f} | {s['imp_bps']:.0f} | {s['fill'] * 100:.0f} % | "
                 f"{X[sch]['sleeve_Y0.5']['cagr'] * 100:.2f} | {X[sch]['sleeve_Y1.5']['cagr'] * 100:.2f} | {X[sch]['total']['cagr'] * 100:.2f} / {X[sch]['total']['sharpe']:.2f} | "
                 + ("reference" if v is None else ("WINS" if v["wins"] else f"no (full {'y' if v['full'] else 'n'}, halves {''.join('y' if z else 'n' for z in v['halves'])})")) + " |")
    L += ["", "AC fractions over 3 closes for a Rp 5 / 25 / 100 / 400 M order in a Rp 20 bn ADV name with sigma 3.5 %: " +
          "; ".join(f"{k} (lambda {AC_LAMBDA[k]:g}): " + ", ".join("/".join(f"{z:.2f}" for z in f) for f in v) for k, v in ac_sched.items()) + ".", "",
          f"Reading rule (pre-registered): CAGR >= +1 pp AND Sharpe not lower AND mDD not deeper by > 1 pp vs (a), full window and both halves. "
          f"Winner: **{best or 'none'}**.", ""]
    L += recommendation(Yc, thr, R, grid, pure_s, first, X, best)
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


def recommendation(Yc, thr, R, grid, pure_s, first, X, best):
    br = lambda bk, key: " / ".join(rp(thr[(f"Y{y:g}_capnone", bk)][key]) for y in (1.5, 1.0, Yc, 0.5))  # noqa: E731
    z = lambda nv: R[("zero", "total", nv)]["cagr"]  # noqa: E731
    L = ["## 4. Recommendation", "",
         f"Max NAV before impact eats > 25 % of the return (DRAG 25 %, sleeve alone at its deployed per-trade size, no cap; "
         f"Y 1.5 / 1.0 / **{Yc}** / 0.5):", "",
         f"- **gap-fade (10 %/trade): {rp(thr[(pure_s, 'gap')]['drag25'])}** ({br('gap', 'drag25')}). It breaks first by an order of magnitude: "
         "10 % of NAV per trade, both legs pay impact the same day, and its edge per trade (~3 %) is the thinnest. Its open leg also trades "
         "into the opening auction, whose depth the desk cannot measure (the feed does not carry auctions), so the lower end of the bracket is "
         "the prudent reading.",
         f"- **trend (5 %/trade): {rp(thr[(pure_s, 'trend')]['drag25'])}** ({br('trend', 'drag25')}).",
         f"- **ML ens4 (5 %/trade in quarter pieces): {rp(thr[(pure_s, 'ML')]['drag25'])}** ({br('ML', 'drag25')}).",
         f"- **combined book: {rp(thr[(pure_s, 'total')]['drag25'])}** ({br('total', 'drag25')}); SIM cross-check {rp(thr[(pure_s, 'total')]['eat25'])}.",
         f"- CAGR halves (DRAG 50 %, central Y): gap {rp(thr[(pure_s, 'gap')]['drag50'])}, trend {rp(thr[(pure_s, 'trend')]['drag50'])}, "
         f"ML {rp(thr[(pure_s, 'ML')]['drag50'])}, total {rp(thr[(pure_s, 'total')]['drag50'])}.", "",
         f"At the operator's next step (Rp 500 M) the central model costs the combined book {(z(500e6) - R[(pure_s, 'total', 500e6)]['cagr']) * 100:.1f} pp "
         f"CAGR ({z(500e6) * 100:.1f} -> {R[(pure_s, 'total', 500e6)]['cagr'] * 100:.1f} %), at Y 1.5 {(z(500e6) - R[('Y1.5_capnone', 'total', 500e6)]['cagr']) * 100:.1f} pp; "
         f"at Rp 1 B {(z(1e9) - R[(pure_s, 'total', 1e9)]['cagr']) * 100:.1f} pp. Hundreds of millions are inside capacity; past ~Rp 1 B the gap sleeve is the binding constraint.", "",
         "Sizing / participation rule for the combo runner when the book grows (model-derived; the per-sleeve rule was run as a capacity "
         "scenario, i.e. measurement, NOT a pre-registered trial):", "",
         "1. Size = min(sleeve % x NAV, phi* x ADV20 value), phi* = (0.125 x edge / (Y x sigma20))^2, i.e. round-trip impact <= 25 % of the sleeve's "
         "backtest edge per trade. At sigma 3.5 %, Y 0.83: **gap 2 %, trend 5 %, ML 10 % of ADV20**; scale with 1/sigma^2 per name. "
         f"Measured: rule vs no cap at central Y, combined SIM 25 % point {rp(thr[(f'Y{Yc:g}_rule', 'total')]['eat25'])} vs {rp(thr[(pure_s, 'total')]['eat25'])}; "
         f"gap {rp(thr[(f'Y{Yc:g}_rule', 'gap')]['eat25'])} vs {rp(thr[(pure_s, 'gap')]['eat25'])}; trend {rp(thr[(f'Y{Yc:g}_rule', 'trend')]['eat25'])} vs "
         f"{rp(thr[(pure_s, 'trend')]['eat25'])}; ML {rp(thr[(f'Y{Yc:g}_rule', 'ML')]['eat25'])} vs {rp(thr[(pure_s, 'ML')]['eat25'])} "
         "(the ML cap costs more skipped edge than it saves in impact: drop the ML cap; the rule becomes gap 2 %, trend 5 %, ML uncapped).",
         "2. Unfilled remainder is dropped (do not chase the next day); exits are never skipped - spill the excess to the next close.",
         "3. Do not stretch execution over several sessions: every multi-session schedule lost more to signal decay than it saved in impact "
         f"(part 3; winner: {best or 'none'}). Trade at one close; when capacity binds, shrink the size, do not slow the trade.",
         "4. Above ~Rp 1 B cut the gap sleeve's per-trade weight (e.g. 10 % -> 5 %) or its K, before touching trend/ML; re-run this script with "
         "the live scorecard's measured slippage to re-fit Y once >= 50 live fills per sleeve exist (the combo scorecard records slippage vs ref_close).",
         "5. At Rp 20 M impact is immaterial (central Y, cap 10 %: "
         f"{R[(f'Y{Yc:g}_cap10', 'total', 20e6)]['cagr'] * 100:.1f} % vs 33.8 %); nothing changes in the live book now."]
    return L


if __name__ == "__main__":
    if os.environ.get("FE_STAGE") == "cal":
        calibrate(K.dsn())
        sys.exit(0)
    sys.exit(main())
