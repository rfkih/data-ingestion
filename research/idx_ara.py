#!/usr/bin/env python3
"""IDX menu 16 — "ARA hunter" (operator, 2026-09-21): buying names that lock at the upper auto-rejection price (ARA), the
retail momentum play, measured on the desk's daily data WITH the fill constraints that define it: a locked ARA close has no
offer (nobody can buy), a locked ARB close has no bid (nobody can sell).

PRE-REGISTERED MENU (24 trials; cumulative 377 + 24 = 401). Declared before the run; nothing tuned afterwards.
  Data: idx.bar (OHLC, volume, value, adj_factor) + idx.daily_summary (previous close, closing bid/offer with volumes, the
  IDX notation string -> board on the day), idx.feature_daily (60-day median value), idx.listing (listing_date),
  idx.index_daily (COMPOSITE). 2020-01-02 -> 2026-09-17.
  ARA on day t: close == the highest tick <= previous * (1 + band); band 35 % (previous <= Rp 200), 25 % (<= Rp 5,000),
  20 % (above) — checked on the data before the menu was written (the mass of >= 18 % days sits exactly on that price).
  ARB band by date: 7 % to 2023-06-04, 15 % to 2023-09-03, symmetric after (rule II-A history).
  Boards on the day (notation digit): Utama + Pengembangan only — Akselerasi and Pemantauan Khusus have 10 % bands.
  previous >= Rp 50, volume > 0. IPO family: listing_date >= 2020-02-01, first 5 trading days, first-day band doubled.
  Universes: ALL (as above, value on t >= Rp 1 bn), LIQ (60-day median value >= Rp 5 bn), SMALL (ALL minus LIQ).
  Entries: O = the next open, filled at open + one tick, only when that open is below the day's ARA price (a gap-locked
  open has no offer -> skipped: the hunter's curse, not a modelling choice); C = the close of the signal day at the closing
  offer, only when an offer is quoted (93 % of ARA closes have none); G = the open of the signal day itself (gap arm).
  Exits: nc = first close after entry at the closing bid; no = next open after entry at open - one tick; c3 = third close
  after entry; ride = hold while the close is ARA, sell at the first non-ARA close (max 10 days). A close without a bid
  (locked ARB) cannot be sold: roll to the next day (max 10, then forced at close - tick). Fees 0.10 / 0.20 % (Stockbit).
  K = 5 names per signal day ranked by value traded on t (unless stated); trade P&L booked on the exit day; one slot =
  1/(K * Hnom), Hnom = 1 (nc, no), 3 (c3, ride). Dividends ignored.
  A. plain ARA, next-open entry (ALL):            ara|O>nc  ara|O>no  ara|O>c3  ara|O>ride
  B. plain ARA, close entry when an offer exists:  ara|C>no  ara|C>nc  ara|C>ride
  C. chains, O>no:                                 ara_fresh (no ARA in the prior 20 days)  ara_2nd (second consecutive)  ara_3plus
  D. near-ARA (close >= 60 % of the band above previous, below the ARA price; entry at the closing offer):
                                                   near|C>nc  near|C>no  near|C>ride
  E. liquidity, O>no:                              ara_liq (LIQ)  ara_big (value on t >= Rp 20 bn)  ara_small (SMALL)
  F. attention, O>no:                              ara_volx (volume >= 5x its 20-day median, ranked by the ratio)  ara_quiet (< 2x)
  G. IPO (first 5 trading days):                   ipo_ara|O>no  ipo_ara|O>ride
  H. regime, O>no:                                 ara_bull (COMPOSITE above its 50-day mean)  ara_mania (>= 8 ARA names on t)
  I. after the lock:                               ara_dip|O>c3 (t+1 closed below the ARA close but above previous(t); entry t+2 open)
                                                   ara_gap|G>nc (t+1 opens >= 5 % above the ARA close and not locked; buy that open)
  References (not trials): random names from the same universe with the same entry/exit mechanics and K; COMPOSITE.
READING RULE (declared before the run): candidate only if ALL hold after costs: >= 300 trades (IPO arms >= 100); mean net
  basket-day return > 0 with t >= 2.5; net return positive in >= 5 of 7 calendar years (IPO: >= 4 of 6); annualised
  Sharpe >= 1.0; max drawdown <= 25 %; Sharpe >= random + 0.5. Candidates go to a paper book for >= 60 trades before money.
  Base rates (what follows an ARA close, by chain length and by whether the next open was locked) are reported as facts,
  outside the trial count, together with the naive close-to-close figure that ignores fills.
AMENDMENT (declared after a dry run showed IDX open prices exist for only ~5 % of rows before 2025 and ~60 % after — the
  first dry run therefore covered 2024-2026 only; no arm was tuned): missing opens are filled from the desk's Yahoo daily cache
  (research-scratch/idx, 450 CURRENT names -> survivor-biased before 2025), scaled by the day's IDX/Yahoo close ratio and
  accepted only inside the IDX day's low..high; the report shows the share of Yahoo-filled entries per arm. The years rule
  counts only calendar years in which the arm traded >= 100 times: positive in >= 5 of 7 when 5+ such years exist, otherwise
  in all but one of them (and at least 2 such years).
READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_ara.py
"""
from __future__ import annotations

import argparse
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
import equity_screen as ES  # noqa: E402

START, END = date(2020, 1, 1), date(2026, 9, 17)
FEE_BUY, FEE_SELL = 0.0010, 0.0020
MIN_VALUE, LIQ, BIG = 1e9, 5e9, 20e9
K = 5
N_TRIALS_BEFORE = 377
SEED = 20260921
MAX_ROLL = 10
# (name, entry, exit, universe)
ARMS = [
    ("ara", "O", "nc", "ALL"), ("ara", "O", "no", "ALL"), ("ara", "O", "c3", "ALL"), ("ara", "O", "ride", "ALL"),
    ("ara", "C", "no", "ALL"), ("ara", "C", "nc", "ALL"), ("ara", "C", "ride", "ALL"),
    ("ara_fresh", "O", "no", "ALL"), ("ara_2nd", "O", "no", "ALL"), ("ara_3plus", "O", "no", "ALL"),
    ("near", "C", "nc", "ALL"), ("near", "C", "no", "ALL"), ("near", "C", "ride", "ALL"),
    ("ara_liq", "O", "no", "LIQ"), ("ara_big", "O", "no", "ALL"), ("ara_small", "O", "no", "SMALL"),
    ("ara_volx", "O", "no", "ALL"), ("ara_quiet", "O", "no", "ALL"),
    ("ipo_ara", "O", "no", "IPO"), ("ipo_ara", "O", "ride", "IPO"),
    ("ara_bull", "O", "no", "ALL"), ("ara_mania", "O", "no", "ALL"),
    ("ara_dip", "O", "c3", "ALL"), ("ara_gap", "G", "nc", "ALL"),
]
assert len(ARMS) == 24
HNOM = {"nc": 1, "no": 1, "c3": 3, "ride": 3}
IPO_ARMS = {"ipo_ara"}


def tick(p):
    p = np.asarray(p, dtype=float)
    return np.select([p < 200, p < 500, p < 2000, p < 5000], [1, 2, 5, 10], 25).astype(float)


def up_band(prev):
    return np.select([prev <= 200, prev <= 5000], [0.35, 0.25], 0.20)


def ara_price(prev, mult=1.0):
    raw = prev * (1 + mult * up_band(prev))
    tk = tick(np.nan_to_num(raw, nan=1.0))
    return np.floor(raw / tk) * tk


def arb_price(prev, dates):
    d = np.asarray(dates)
    lo = np.where(d < np.datetime64("2023-06-05"), 0.07, np.where(d < np.datetime64("2023-09-04"), 0.15, np.nan))
    lo = np.where(np.isnan(lo), up_band(prev), lo)
    raw = np.maximum(prev * (1 - lo), 50.0)
    tk = tick(np.nan_to_num(raw, nan=1.0))
    return np.ceil(raw / tk) * tk


def load(conn):
    q = lambda sql, params=(): pd.read_sql(sql, conn, params=params)  # noqa: E731
    # opens back-filled from Yahoo (open_src='yahoo') are chart data, not IDX opening prints: keep them out
    bars = q("""SELECT b.code, b.trade_date, CASE WHEN b.open_src = 'idx' THEN b.open END AS open, b.high, b.low, b.close, b.volume, b.value, b.adj_factor, s.previous, s.remarks,
                       s.bid, s.bid_volume AS bv, s.offer, s.offer_volume AS ov, f.value_60d_median AS v60
                  FROM idx.bar b JOIN idx.daily_summary s USING (code, trade_date) LEFT JOIN idx.feature_daily f USING (code, trade_date)
                 WHERE b.source = 'idx' AND b.trade_date BETWEEN %s AND %s""", (START, END))
    listing = q("SELECT code, listing_date FROM idx.listing")
    idx = q("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND trade_date BETWEEN %s AND %s ORDER BY 1", (START, END))
    return bars, listing, idx


YAHOO = os.path.join(ROOT, "research-scratch", "idx")


def yahoo_opens():
    """(code, trade_date) -> Yahoo open and close on the split-only basis, from the desk's daily cache (current names only)."""
    import glob
    parts = []
    for f in sorted(glob.glob(os.path.join(YAHOO, "*.JK.csv"))):
        code = os.path.basename(f).split(".")[0]
        df = pd.read_csv(f, usecols=["date", "open", "close"])
        df = df[df["date"] >= str(START)]
        df["code"] = code
        parts.append(df)
    y = pd.concat(parts, ignore_index=True)
    y["trade_date"] = pd.to_datetime(y["date"]).dt.date
    y["y_open"] = pd.to_numeric(y["open"], errors="coerce")
    y["y_close"] = pd.to_numeric(y["close"], errors="coerce")
    y = y[(y["y_open"] > 0) & (y["y_close"] > 0)].drop_duplicates(["code", "trade_date"], keep="last")
    return y[["code", "trade_date", "y_open", "y_close"]]


def panels(bars):
    bars = bars.copy()
    for c in ("open", "high", "low", "close", "volume", "value", "adj_factor", "previous", "bid", "bv", "offer", "ov", "v60"):
        bars[c] = pd.to_numeric(bars[c], errors="coerce")
    bars["main"] = bars["remarks"].fillna("").str[4:5].isin(["1", "2"]).astype(float)
    y = yahoo_opens()
    bars = bars.merge(y, on=["code", "trade_date"], how="left")
    fill = bars["y_open"] * (bars["close"] / bars["y_close"])
    ok = bars["open"].isna() & fill.notna() & (bars["volume"] > 0) & (fill >= bars["low"] - 0.5) & (fill <= bars["high"] + 0.5)
    bars["open_src"] = np.where(bars["open"].notna(), 1.0, np.where(ok, 2.0, 0.0))   # 1 idx, 2 yahoo, 0 none
    bars.loc[ok, "open"] = fill[ok]
    bars = bars.sort_values(["code", "trade_date"])
    bars["dayn"] = bars.groupby("code").cumcount().astype(float)
    P = {c: bars.pivot(index="trade_date", columns="code", values=c).sort_index()
         for c in ("open", "high", "low", "close", "volume", "value", "adj_factor", "previous", "bid", "bv", "offer", "ov", "v60", "main", "dayn", "open_src")}
    for k in P:
        P[k].index = pd.to_datetime(P[k].index)
    return P


class Market:
    """Everything as (T, N) float arrays plus the ARA/ARB prices per day."""

    def __init__(self, P, listing, idx):
        self.dates, self.cols = P["close"].index, P["close"].columns
        g = lambda k: P[k].to_numpy(float)  # noqa: E731
        self.open, self.high, self.low, self.close = g("open"), g("high"), g("low"), g("close")
        self.vol, self.val, self.prev = g("volume"), g("value"), g("previous")
        self.adj = np.nan_to_num(g("adj_factor"), nan=1.0)
        self.bid, self.bv, self.offer, self.ov, self.v60 = g("bid"), g("bv"), g("offer"), g("ov"), g("v60")
        self.main, self.dayn = g("main") == 1.0, g("dayn")
        self.open_src = np.nan_to_num(g("open_src"))
        T, N = self.close.shape
        self.T, self.N = T, N
        dcol = np.repeat(self.dates.to_numpy()[:, None], N, axis=1)
        self.lim = ara_price(self.prev)
        self.lo = arb_price(self.prev, dcol)
        ld = listing.set_index("code")["listing_date"].reindex(self.cols)
        ld = pd.to_datetime(ld, errors="coerce")
        self.ipo_code = (ld >= pd.Timestamp("2020-02-01")).to_numpy()
        lim_ipo = np.where(self.dayn == 0, ara_price(self.prev, 2.0), self.lim)
        self.lim_ipo = lim_ipo
        base = self.main & (self.prev >= 50) & (self.vol > 0) & np.isfinite(self.close)
        self.ara = base & (self.close == self.lim)
        ret = self.close / self.prev - 1
        self.near = base & (ret >= 0.6 * up_band(self.prev)) & (self.close < self.lim)
        self.ipo_ara = base & (self.dayn <= 4) & np.repeat(self.ipo_code[None, :], T, axis=0) & (self.close == lim_ipo)
        idx = idx.copy()
        idx["trade_date"] = pd.to_datetime(idx["trade_date"])
        comp = idx.set_index("trade_date")["close"].astype(float).reindex(self.dates, method="ffill")
        self.comp = comp
        self.bull = (comp > comp.rolling(50, min_periods=50).mean()).to_numpy()
        # chains: consecutive ARA closes ending on t
        chain = np.zeros((T, N), dtype=int)
        for t in range(T):
            chain[t] = np.where(self.ara[t], (chain[t - 1] if t else 0) + 1, 0)
        self.chain = chain
        ara_prior20 = pd.DataFrame(self.ara.astype(float)).rolling(20, min_periods=1).sum().shift(1).fillna(0).to_numpy()
        self.ara_prior20 = ara_prior20
        vmed = pd.DataFrame(self.vol).rolling(20, min_periods=20).median().shift(1).to_numpy()
        self.vratio = self.vol / vmed
        self.n_ara_day = self.ara.sum(axis=1)
        self.locked_close = np.isfinite(self.close) & (self.close == self.lo) & ~(self.bv > 0)

    def universe(self, name):
        u = self.main & (self.prev >= 50) & (self.vol > 0) & (self.val >= MIN_VALUE) & np.isfinite(self.close)
        if name == "LIQ":
            return u & (self.v60 >= LIQ)
        if name == "SMALL":
            return u & ~(self.v60 >= LIQ)
        if name == "IPO":
            return u & (self.dayn <= 4) & np.repeat(self.ipo_code[None, :], self.T, axis=0)
        return u

    # ---- fills -------------------------------------------------------------------------------------------------
    def buy_open(self, d, j):
        o = self.open[d, j]
        if not (np.isfinite(o) and o < self.lim[d, j] and self.vol[d, j] > 0):
            return None
        return o + tick(o)

    def buy_close_offer(self, d, j):
        off = self.offer[d, j]
        if not (self.ov[d, j] > 0 and np.isfinite(off) and off >= self.close[d, j]):
            return None
        return off

    def sell_close(self, d, j):
        """Closing bid on d; a locked ARB (no bid) rolls to the next day; forced after MAX_ROLL."""
        for k in range(MAX_ROLL + 1):
            x = d + k
            if x >= self.T:
                return None, None
            b = self.bid[x, j]
            if self.bv[x, j] > 0 and np.isfinite(b) and b <= self.close[x, j]:
                return x, b
            if not np.isfinite(self.close[x, j]):
                continue
        x = min(d + MAX_ROLL, self.T - 1)
        c = self.close[x, j]
        return (x, c - tick(c)) if np.isfinite(c) else (None, None)

    def sell_open(self, d, j):
        if d >= self.T:
            return None, None
        o = self.open[d, j]
        if np.isfinite(o) and o > self.lo[d, j] and self.vol[d, j] > 0:
            return d, o - tick(o)
        return self.sell_close(d, j)

    def exit(self, mode, entry, e, j, s):
        """Exit day and price for an entry on day e (signal day s)."""
        if entry == "C":
            f = s + 1                      # first close after a close entry
            nxt_open = s + 1
        else:
            f = e
            nxt_open = e + 1
        if mode == "nc":
            return self.sell_close(f, j)
        if mode == "no":
            return self.sell_open(nxt_open, j)
        if mode == "c3":
            return self.sell_close(f + 2, j)
        if mode == "ride":
            d = f
            while d < self.T and d < f + MAX_ROLL and self.ara[d, j]:
                d += 1
            return self.sell_close(d, j)
        raise ValueError(mode)


def signals(M):
    """Signal masks and ranking scores (higher first) keyed by arm name."""
    T, N = M.T, M.N
    val = np.nan_to_num(M.val)
    ara = M.ara & (M.val >= MIN_VALUE)
    bull = np.repeat(M.bull[:, None], N, axis=1)
    mania = np.repeat((M.n_ara_day >= 8)[:, None], N, axis=1)
    # after-the-lock arms: signal on s = t+1
    prev_ara = np.zeros_like(ara)
    prev_ara[1:] = ara[:-1]
    close_t = np.full_like(M.close, np.nan)
    close_t[1:] = M.close[:-1]
    prev_t = np.full_like(M.close, np.nan)
    prev_t[1:] = M.prev[:-1]
    dip = prev_ara & (M.close < close_t) & (M.close > prev_t) & (M.val >= MIN_VALUE)
    gap = prev_ara & (M.open >= 1.05 * close_t) & (M.open < M.lim) & (M.vol > 0)
    return {
        "ara": (ara, val), "near": (M.near & (M.val >= MIN_VALUE), val),
        "ara_fresh": (ara & (M.ara_prior20 == 0), val), "ara_2nd": (ara & (M.chain == 2), val), "ara_3plus": (ara & (M.chain >= 3), val),
        "ara_liq": (ara & (M.v60 >= LIQ), val), "ara_big": (ara & (M.val >= BIG), val), "ara_small": (ara & ~(M.v60 >= LIQ), val),
        "ara_volx": (ara & (M.vratio >= 5), np.nan_to_num(M.vratio)), "ara_quiet": (ara & (M.vratio < 2), val),
        "ipo_ara": (M.ipo_ara & (M.val >= MIN_VALUE), val),
        "ara_bull": (ara & bull, val), "ara_mania": (ara & mania, val),
        "ara_dip": (dip, val), "ara_gap": (gap, val),
    }


def simulate(M, entry, exit_mode, mask, score, k, rng=None, uni=None):
    T, N = M.T, M.N
    slot = 1.0 / (k * HNOM[exit_mode])
    R = np.zeros(T)
    W = np.zeros(T)
    trades = []
    skipped = 0
    for s in range(T - 2):
        base = (uni[s] if rng is not None else mask[s])
        cand = np.flatnonzero(base)
        if len(cand) == 0:
            continue
        if rng is not None:
            pick = rng.choice(cand, size=min(k, len(cand)), replace=False)
        else:
            sc = np.nan_to_num(score[s, cand], nan=-np.inf)
            pick = cand[np.argsort(-sc, kind="stable")[:k]]
        for j in pick:
            if entry == "O":
                e = s + 1
                px_in = M.buy_open(e, j)
            elif entry == "G":
                e = s
                px_in = M.buy_open(e, j)
            else:
                e = s
                px_in = M.buy_close_offer(e, j)
            if px_in is None:
                skipped += 1
                continue
            x, px_out = M.exit(exit_mode, entry, e, j, s)
            if x is None or px_out is None:
                continue
            gross = (px_out * M.adj[x, j]) / (px_in * M.adj[e, j]) - 1
            net = (px_out * M.adj[x, j] * (1 - FEE_SELL)) / (px_in * M.adj[e, j] * (1 + FEE_BUY)) - 1
            R[x] += slot * net
            W[e:x + 1] += slot
            trades.append((s, e, x, j, gross, net, M.open_src[e, j] == 2.0, M.dates[e].year))
    return pd.Series(R, index=M.dates), trades, pd.Series(W, index=M.dates), skipped


def stats(R, trades, exposure, n_trials):
    eq = (1 + R).cumprod()
    years = R.groupby(R.index.year).apply(lambda s: (1 + s).prod() - 1)
    vol = R.std() * math.sqrt(250)
    sharpe = (R.mean() * 250 / vol) if vol > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    n = len(trades)
    g = np.array([t[4] for t in trades]) if n else np.array([])
    nets = np.array([t[5] for t in trades]) if n else np.array([])
    hold = np.array([t[2] - t[1] for t in trades]) if n else np.array([])
    by_day = {}
    for s, _, _, _, _, r, _, _ in trades:
        by_day.setdefault(s, []).append(r)
    bd = np.array([np.mean(v) for v in by_day.values()]) if by_day else np.array([])
    tstat = (bd.mean() / bd.std(ddof=1) * math.sqrt(len(bd))) if len(bd) > 2 and bd.std(ddof=1) > 0 else 0.0
    active = R[R != 0]
    dsr = ES.deflated_sharpe(list(active.values), n_trials) if len(active) > 10 else 0.0
    yah = float(np.mean([t[6] for t in trades])) if n else 0.0
    n_year = {}
    for t in trades:
        n_year[t[7]] = n_year.get(t[7], 0) + 1
    return {"n_trades": n, "n_days": len(bd), "yahoo_share": yah, "n_year": n_year, "hit": float((nets > 0).mean()) if n else 0.0, "avg_gross": float(g.mean()) if n else 0.0,
            "avg_net": float(nets.mean()) if n else 0.0, "med_net": float(np.median(nets)) if n else 0.0, "tstat": float(tstat),
            "total": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (250 / len(R)) - 1), "sharpe": float(sharpe), "mdd": float(dd),
            "dsr": float(dsr), "exposure": float(exposure.mean()), "hold": float(hold.mean()) if n else 0.0,
            "years": {int(y): float(v) for y, v in years.items()}}


def passes(name, s, rnd):
    why = []
    ipo = name in IPO_ARMS
    if s["n_trades"] < (100 if ipo else 300):
        why.append("n")
    if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
        why.append("t<2.5")
    yrs = [y for y, c in s["n_year"].items() if c >= 100]
    pos = sum(1 for y in yrs if s["years"].get(y, 0) > 0)
    need = (4 if ipo else 5) if len(yrs) >= 5 else max(len(yrs) - 1, 0)
    if len(yrs) < 2 or pos < need:
        why.append("years")
    if s["sharpe"] < 1.0:
        why.append("sharpe<1")
    if s["mdd"] < -0.25:
        why.append("mdd")
    if s["sharpe"] < rnd["sharpe"] + 0.5:
        why.append("vs random")
    return not why, why


def base_rates(M):
    """Facts after an ARA close on the ALL universe: what the next days look like, by chain length and by fill status."""
    T = M.T
    ara = M.ara & (M.val >= MIN_VALUE)
    rows = []
    ts, js = np.nonzero(ara[: T - 21])
    ac = M.close * M.adj
    ao = M.open * M.adj
    for t, j in zip(ts, js, strict=True):
        c0 = ac[t, j]
        o1, c1 = ao[t + 1, j], ac[t + 1, j]
        if not (np.isfinite(o1) and np.isfinite(c1)):
            continue
        locked = M.open[t + 1, j] >= M.lim[t + 1, j]
        rows.append({"year": M.dates[t].year, "chain": min(M.chain[t, j], 3), "locked": bool(locked),
                     "again": bool(M.ara[t + 1, j]), "gap": o1 / c0 - 1, "c1": c1 / c0 - 1,
                     "c5": ac[t + 5, j] / c0 - 1, "c20": ac[t + 20, j] / c0 - 1,
                     "o1_c1": c1 / o1 - 1, "o1_o2": ao[t + 2, j] / o1 - 1 if np.isfinite(ao[t + 2, j]) else np.nan,
                     "arb5": bool(M.locked_close[t + 1:t + 6, j].any()), "liq": bool(M.v60[t, j] >= LIQ), "yahoo": M.open_src[t + 1, j] == 2.0})
    df = pd.DataFrame(rows)
    df.attrs["n_events"] = int(len(ts))

    def agg(g):
        return pd.Series({"n": len(g), "locked": g["locked"].mean(), "ARA again": g["again"].mean(), "ARB<=5d": g["arb5"].mean(),
                          "gap med": g["gap"].median(), "gap mean": g["gap"].mean(), "c1 med": g["c1"].median(), "c1 mean": g["c1"].mean(),
                          "c5 med": g["c5"].median(), "c5 mean": g["c5"].mean(), "c20 med": g["c20"].median(), "c20 mean": g["c20"].mean(),
                          "open>close med": g["o1_c1"].median(), "open>open med": g["o1_o2"].median()})

    out = {"all": agg(df), "next open from IDX": agg(df[~df["yahoo"]]), "next open from Yahoo": agg(df[df["yahoo"]])}
    for c in (1, 2, 3):
        out[f"chain {c}{'+' if c == 3 else ''}"] = agg(df[df["chain"] == c])
    out["next open locked"] = agg(df[df["locked"]])
    out["next open fillable"] = agg(df[~df["locked"]])
    out["fillable & LIQ"] = agg(df[~df["locked"] & df["liq"]])
    out["fillable & small"] = agg(df[~df["locked"] & ~df["liq"]])
    for y, g in df.groupby("year"):
        out[str(y)] = agg(g)
    return pd.DataFrame(out).T, df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, f"IDX_ARA_{date.today().isoformat()}.md"))
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx = load(conn)
    P = panels(bars)
    M = Market(P, listing, idx)
    sig = signals(M)
    n_trials = N_TRIALS_BEFORE + len(ARMS)
    rng = np.random.default_rng(SEED)
    refs, results, verdicts, skips = {}, {}, {}, {}
    for name, entry, ex, uni in ARMS:
        key = (uni, entry, ex)
        if key not in refs:
            R, tr, W, _ = simulate(M, entry, ex, None, None, K, rng=rng, uni=M.universe(uni))
            refs[key] = stats(R, tr, W, n_trials)
        m, sc = sig[name]
        R, tr, W, sk = simulate(M, entry, ex, m, sc, K)
        arm = f"{name}|{entry}>{ex}"
        results[arm] = stats(R, tr, W, n_trials)
        skips[arm] = sk
        ok, why = passes(name, results[arm], refs[key])
        verdicts[arm] = "CANDIDATE" if ok else "tested: " + ",".join(why)
    br, brdf = base_rates(M)
    cc = M.comp.dropna()
    comp_total = cc.iloc[-1] / cc.iloc[0] - 1

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, s, verdict, skipped="", dsr=True):
        return (f"| {label} | {s['n_trades']} | {skipped} | {s['yahoo_share'] * 100:.0f} % | {s['hit'] * 100:.0f} % | {s['avg_gross'] * 100:+.2f} % | {s['avg_net'] * 100:+.2f} % | "
                f"{s['med_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['hold']:.1f} | {s['total'] * 100:+.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | "
                f"{(f'{s['dsr']:.2f}' if dsr else '-')} | {s['exposure'] * 100:.0f} % | {yrs(s['years'])} | {verdict} |")

    n_ara = int((M.ara & (M.val >= MIN_VALUE)).sum())
    lines = [f"# IDX menu 16 — ARA hunter — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             f"{M.dates[0].date()} -> {M.dates[-1].date()}, {M.N} names, {M.T} days. ARA closes on the main boards with value >= Rp 1 bn: {n_ara} "
             f"({int(M.ara.sum())} before the value floor; {int(M.near.sum())} near-ARA days; {int(M.ipo_ara.sum())} IPO-window ARA days). "
             f"COMPOSITE buy-and-hold {comp_total * 100:+.1f} %.", "",
             "## Base rates after an ARA close (facts, not trials; close-to-close, no fills, no costs)", "",
             f"ARA events with a next-day open price: {len(brdf)} of {brdf.attrs['n_events']} ({int(brdf['yahoo'].sum())} opens from the Yahoo cache).", "",
             "gap = next open vs the ARA close; c1/c5/c20 = close 1/5/20 days later vs the ARA close; open>close = next close vs next open;",
             "open>open = the open after next vs next open; locked = the next open sits at that day's ARA price (no offer, nothing to buy);",
             "ARB<=5d = a close with no bid within 5 days (cannot sell).", ""]
    fmt = br.copy()
    for c in fmt.columns:
        fmt[c] = fmt[c].map(lambda v, c=c: "-" if pd.isna(v) else f"{int(v)}" if c == "n" else f"{v * 100:+.1f} %" if "med" in c or "mean" in c else f"{v * 100:.0f} %")
    lines += ["| slice | " + " | ".join(fmt.columns) + " |", "|---|" + "---|" * len(fmt.columns)]
    for i, r in fmt.iterrows():
        lines.append(f"| {i} | " + " | ".join(r.values) + " |")
    lines += ["", "## Trials", "",
              f"Fills as declared (open + tick / closing offer; closing bid / open - tick; locked closes roll), fees {FEE_BUY * 100:.2f}/{FEE_SELL * 100:.2f} %. "
              "skipped = signals with no fill (locked open / no closing offer / no open price). yahoo open = share of entries whose open came from the Yahoo cache. hold = trading days from entry to exit.", "",
              "| arm | trades | skipped | yahoo open | hit | gross/trade | net/trade | median net | t(basket) | hold | total | Sharpe | mDD | DSR | expo | years | verdict |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (uni, entry, ex), s in sorted(refs.items()):
        lines.append(row(f"random {uni} {entry}>{ex}", s, "reference", dsr=False))
    for name, entry, ex, uni in ARMS:
        arm = f"{name}|{entry}>{ex}"
        lines.append(row(f"{name} [{uni}] {entry}>{ex}", results[arm], verdicts[arm], str(skips[arm])))
    n_cand = sum(1 for v in verdicts.values() if v == "CANDIDATE")
    lines += ["", f"Reading rule applied as declared: {n_cand} candidate(s) of {len(ARMS)}.", "",
              "Limits: daily bars only (the intraday 'buy before the lock' is approximated by near-ARA closes and by the closing offer);",
              "open fills assume the opening auction price plus a tick; closing bid/offer are the last quotes of the day, not depth;",
              "no shorting; dividends ignored; the notation-digit board is missing on a few early-2020 rows (those days are excluded)."]
    text = "\n".join(lines)
    print(text)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {a.out}")
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            best = max(results, key=lambda t: results[t]["sharpe"])
            sid = rs.record_study(conn, "ara_hunter", M.dates[-1].date(),
                                  params={"trials": [f"{n}|{e}>{x}@{u}" for n, e, x, u in ARMS], "n_trials_cumulative": n_trials, "fees": [FEE_BUY, FEE_SELL],
                                          "K": K, "min_value": MIN_VALUE, "liq": LIQ, "big": BIG, "seed": SEED, "max_roll": MAX_ROLL},
                                  summary={"results": results, "random": {f"{u}|{e}>{x}": v for (u, e, x), v in refs.items()}, "verdicts": verdicts,
                                           "skipped": skips, "base_rates": {str(i): {c: (None if pd.isna(v) else float(v)) for c, v in r.items()} for i, r in br.iterrows()},
                                           "composite_total": float(comp_total), "best_by_sharpe": best, "candidates": n_cand, "n_ara": n_ara},
                                  names=[], report_path=a.out, note=f"{n_cand} candidates of {len(ARMS)}; best by Sharpe {best}")
            print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
