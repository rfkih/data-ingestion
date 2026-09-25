#!/usr/bin/env python3
"""IDX menu 37 (Track B2) - CALENDAR effects on IDX, long-only: turn-of-month, Ramadan / Lebaran, year-end + January,
pre-holiday, day-of-week. Does a calendar window beat simply HOLDING the same exposure, net of IDX costs, and is it
useful as a SLEEVE or as a TIMING OVERLAY for the existing books?

DATA
  JKSE     Yahoo ^JKSE daily close (research-scratch/idx/_JKSE.csv), 2006-01 -> 2026-09 (primary: 20 years, 3 blocks)
  COMP     idx.index_daily index_code 'COMPOSITE', 2020-01 -> 2026-09 (the desk's own index; cross-check of JKSE)
  LIQ      equal-weight basket of the LIQ universe (board Utama/Pengembangan, 60-day value >= Rp 5 bn, close >= Rp 100),
           membership as of the prior close, adjusted closes from idx.bar (tmp/exit_cache.pkl = idx_exit.load_all), 2020-26
  SMALL    the same basket on `small` = LIQ minus BLUE (the trend book's universe; "small caps" of the tradeable desk)
  Calendar: trading days = union of JKSE and COMPOSITE dates; a HOLIDAY = a weekday that is not a trading day.
  Lebaran: Indonesian government 1 Syawal dates 2006-2026 (list LEBARAN below). The market closure block is the run of
  non-trading days containing the date (or the nearest block within 3 calendar days; asserted), so a +/-1-day dispute on
  the date itself cannot move the windows.

PRE-REGISTERED (written before any result was computed; 12 trials, ids 861..872 -> cumulative N = 872).
  Windows (in-window days = the days whose close-to-close return the position earns; entered at the prior close):
   1 tom13        turn-of-month: last trading day of the month + first 3 of the next (Lakonishok-Smidt -1..+3)   sign +
   2 tom33        last 3 + first 3                                                                             sign +
   3 preleb5      the 5 trading days before the Lebaran closure                                                sign +
   4 ramadan20    the 20 trading days before the Lebaran closure (Ramadan run-up)                              sign +
   5 postleb5     the first 5 trading days after the Lebaran closure                                           sign - (expected weak)
   6 declast10    the last 10 trading days of December (window dressing / Santa)                               sign +
   7 janfirst10   the first 10 trading days of January (January effect; the SMALL basket is the one that matters) sign +
   8 preholiday   the trading day immediately before any weekday market holiday                                 sign +
   9 monday       Mondays                                                                                      sign -
  10 friday       Fridays                                                                                      sign +
  11 combo-sleeve best survivor as a 20 % sleeve next to the combined book (#168 engine), correlations      (only if a survivor)
  12 combo-overlay best survivor as a timing overlay on the combined book: sign + window -> trend/ML EXITS that fall
                  inside the window are deferred to the window's last day; sign - window -> ENTRIES inside it are
                  deferred to the first day after it                                                    (only if a survivor)
  Statistic: per EPISODE (a contiguous run of in-window days), excess = sum of in-window daily returns minus
  (episode length x the mean daily return of the SAME calendar year) = "beats holding the same exposure".
  Net excess = excess - round trip. Round trip: JKSE / COMP 80 bps (the midpoint of the desk's 70-91 bps incl. fees);
  baskets: measured - the mean over members of the closing-offer entry cost + closing-bid exit cost + Stockbit fees
  (idx_swing2.costs, the helper behind idx_combo_rupiah's FEE_BUY/FEE_SELL/tick). Costs x 1.5 = 120 bps / 1.5 x measured.
  Battery on JKSE 2006-26 (primary):
    T   t-stat of the per-episode gross excess (sign as hypothesised)
    B   the mean excess has the hypothesised sign in each block 2006-12, 2013-19, 2020-26 (3/3), and in >= 60 % of years
    P   placebo: 500 circular shifts of the window mask (offset >= 10 days, overlap with the real mask <= 50 %); the real
        mean gross excess must sit at percentile >= 95 (sign-adjusted)
    N   neighbours, window +/- 1 day on each edge (listed per window): all must keep the sign and >= half the gross excess
    C   costs x 1.5: net excess still > 0 (sleeve bar only)
    X   tradeable: the same window on COMP, LIQ and SMALL 2020-26 keeps the sign (gross); sleeve bar: SMALL or LIQ net > 0
    M   DSR of the sleeve's daily net return series at N = 872 (reported; the placebo, not DSR, is the gate)
  BARS
    SLEEVE (long-only, only sign + windows): net excess > 0 with t_net >= 2.0, B, P, N, C, X(net).
    OVERLAY (costless re-timing of trades the books already make): gross t >= 2.0, B (blocks 3/3), P, N, X(gross sign).
  VERDICT per window: ROBUST = passes the overlay bar (and the sleeve bar, reported separately);
    PARTIAL = |t| >= 2 and P pass, but exactly one of B / N / X fails; FRAGILE = P fails, or two of B / N / X fail
    while |t| >= 2; CLOSED = |t| < 2 (no effect distinguishable from holding) or the sign is opposite to the hypothesis.
    Day-of-week needs 50+ round trips a year, so it is judged as an overlay only.
READ-ONLY; one idx.study row ('calendar'). INGEST_DB_DSN (or blackheart-ingest/idx-local.env), IDX_EXIT_CACHE (tmp/exit_cache.pkl),
IDX_ML_CACHE (tmp/ml_strategy_cache.pkl, only for trials 11-12).
"""
from __future__ import annotations

import json
import math
import os
import pickle
import re
import sys
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
os.environ.setdefault("IDX_EXIT_CACHE", os.path.join(ROOT, "tmp", "exit_cache.pkl"))
os.environ.setdefault("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))

N_BEFORE = 861
N_TRIALS = 12
N_CUM = N_BEFORE + N_TRIALS - 1          # trial ids 861..872
STUDY = "calendar"
RT_INDEX = 0.0080
BLOCKS = [(2006, 2012), (2013, 2019), (2020, 2026)]
N_PLACEBO = 500
RNG = np.random.default_rng(37)

LEBARAN = ["2006-10-24", "2007-10-13", "2008-10-01", "2009-09-20", "2010-09-10", "2011-08-31", "2012-08-19", "2013-08-08",
           "2014-07-28", "2015-07-17", "2016-07-06", "2017-06-25", "2018-06-15", "2019-06-05", "2020-05-24", "2021-05-13",
           "2022-05-02", "2023-04-22", "2024-04-10", "2025-03-31", "2026-03-20"]

# window name -> (spec, sign); neighbours are specs too
WINDOWS = {
    "tom13": (("tom", 1, 3), +1),
    "tom33": (("tom", 3, 3), +1),
    "preleb5": (("preleb", 5, 0), +1),
    "ramadan20": (("preleb", 20, 0), +1),
    "postleb5": (("postleb", 5, 0), -1),
    "declast10": (("declast", 10, 0), +1),
    "janfirst10": (("janfirst", 10, 0), +1),
    "preholiday": (("prehol", 1, 0), +1),
    "monday": (("dow", 0, 0), -1),
    "friday": (("dow", 4, 0), +1),
}
NEIGH = {
    "tom13": [("tom", 2, 3), ("tom", 0, 3), ("tom", 1, 2), ("tom", 1, 4)],
    "tom33": [("tom", 4, 3), ("tom", 2, 3), ("tom", 3, 2), ("tom", 3, 4)],
    "preleb5": [("preleb", 4, 0), ("preleb", 6, 0), ("preleb", 5, 1)],          # (n, skip): skip = the last `skip` days dropped
    "ramadan20": [("preleb", 19, 0), ("preleb", 21, 0), ("preleb", 20, 1)],
    "postleb5": [("postleb", 4, 0), ("postleb", 6, 0), ("postleb", 5, 1)],
    "declast10": [("declast", 9, 0), ("declast", 11, 0)],
    "janfirst10": [("janfirst", 9, 0), ("janfirst", 11, 0)],
    "preholiday": [("prehol", 2, 0), ("prehol", 2, 1)],                        # 2 days before; the day 2 before only
    "monday": [("dow_nohol", 0, 0), ("postweekend", 0, 0)],                     # Mondays not after a holiday; first day after any closure
    "friday": [("dow_nohol", 4, 0), ("preweekend", 0, 0)],                      # Fridays not before a holiday; last day before any closure
}


READING = """## Reading (written after the run)

1. **No calendar sleeve exists on IDX.** Not one window clears its own round trip: the best gross excess over holding is
   +74 bps per episode (last 10 days of December) against an 80 bps round trip, and every window is net NEGATIVE on JKSE
   and on the tradeable LIQ / SMALL baskets 2020-26 (measured round trip 86 / 97 bps). The only window net-positive anywhere
   is the first 10 days of January on the 2020-26 baskets (+146..+159 bps, t ~1.0, 6 Januaries) - on 20 years of JKSE it is
   +30 bps gross, 45 % of years, placebo pct 61: noise.
2. **Turn-of-month was real in 2006-12 and is gone.** tom33 (last 3 + first 3): +96 bps/episode in 2006-12, +30 in 2013-19,
   -14 in 2020-26; placebo pct 99 over the full span but t 1.85, and the desk's own 2020-26 series are flat (COMP -5, LIQ -8,
   SMALL -11). The classic -1..+3 window is weaker still (t 1.1). A decayed anomaly: holding trend/value entries "through the
   turn of the month" is worth nothing measurable today.
3. **Ramadan / Lebaran.** The Ramadan run-up (20 days) is a myth on this data (-6 bps, t -0.05; 2020-26 -97). Pre-Lebaran
   5 days +50 bps, t 1.15, negative in 2020-26. **Post-Lebaran is the one consistent pattern**: -140 bps vs holding over the
   first 5 days after the holiday, negative in 3/3 blocks and 71 % of years, placebo pct 98, all neighbours and COMP / LIQ /
   SMALL negative - but 21 episodes, t -1.45, so CLOSED by the letter. It cannot be a sleeve (long-only, negative sign); as an
   overlay it says at most "no need to hurry new buys in the first week after Lebaran" - a free, low-evidence preference, not
   a rule. Worth a re-test when it has more episodes.
4. **Year-end.** December window dressing +74 bps, t 1.26, 2020-26 block negative (-58; baskets -169..-214): no evidence for
   "delay buys to after window dressing", and none for a small-cap January effect (SMALL minus LIQ over the first 10 days of
   January: 3 of 6 years negative).
5. **Pre-holiday and Friday: nothing** (+0.8 and +1.4 bps/day, t 0.1 / 0.4).
6. **Monday is the only effect that passes the statistics - and it lives in the index, not in what the desk trades.** JKSE
   Monday -13 bps vs the same year's mean day, t -2.9, 3/3 blocks (-16 / -12 / -11), 76 % of years, placebo pct 100, neighbours
   hold (Mondays not after a holiday -15, t -3.4); COMPOSITE 2020-26 agrees (-11). But the equal-weight LIQ and SMALL baskets are
   +3 / +5 on Mondays in 2020-26: the weakness sits in the cap-weighted large names. Verdict PARTIAL (tradeable check fails). As
   an overlay on the combined book (defer trend/ML entries that land on a Monday to Tuesday, 80 trades moved) CAGR 32.7 -> 32.3 %,
   Sharpe 1.75 -> 1.74, mDD unchanged: nothing to adopt. Day-of-week can never be a sleeve (50+ round trips a year at ~80 bps).
7. **Verdict for menu 37: CLOSED as a family** (9 CLOSED, 1 PARTIAL with no economic use). Calendar timing adds nothing to the
   trend / value / gap-fade / ML books; the DSR of every calendar sleeve at N = 872 is 0.00. Nothing to deploy.
"""


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    v = env["INGEST_DB_DSN"].strip().strip('"')
    os.environ["INGEST_DB_DSN"] = v
    return v


def log(msg: str) -> None:
    print(msg, flush=True)


# ---- calendar -------------------------------------------------------------------------------------------------------------------
class Cal:
    def __init__(self, days: pd.DatetimeIndex):
        self.days = pd.DatetimeIndex(sorted(set(days)))
        wk = pd.bdate_range(self.days[0], self.days[-1])
        self.holidays = wk.difference(self.days)
        s = pd.Series(np.arange(len(self.days)), index=self.days)
        ym = self.days.year * 100 + self.days.month
        self.pos_start = s.groupby(ym).cumcount().to_numpy() + 1
        self.pos_end = s.groupby(ym).cumcount(ascending=False).to_numpy() + 1
        nxt = list(self.days[1:]) + [self.days[-1] + pd.Timedelta(days=1)]
        prv = [self.days[0] - pd.Timedelta(days=1)] + list(self.days[:-1])
        hol = set(self.holidays)
        # a weekday holiday strictly between this day and the next trading day
        self.before_hol = np.array([any(d in hol for d in pd.bdate_range(a + pd.Timedelta(days=1), b - pd.Timedelta(days=1))) for a, b in zip(self.days, nxt)])
        self.after_hol = np.array([any(d in hol for d in pd.bdate_range(b + pd.Timedelta(days=1), a - pd.Timedelta(days=1))) for a, b in zip(self.days, prv)])
        self.gap_after = np.array([(b - a).days > 1 for a, b in zip(self.days, nxt)])      # any closure (weekend or holiday) follows
        self.gap_before = np.array([(a - b).days > 1 for a, b in zip(self.days, prv)])
        # Lebaran closure: index of the last trading day before, first trading day after
        self.leb = []
        for L in LEBARAN:
            d = pd.Timestamp(L)
            if d < self.days[0] or d > self.days[-1]:
                continue
            i_after = int(self.days.searchsorted(d))           # first trading day >= d
            i_before = i_after - 1
            if self.days[i_after] == d:                         # traded on the date itself -> snap to the nearest multi-day block
                gaps = [(i, (self.days[i + 1] - self.days[i]).days) for i in range(max(0, i_after - 5), min(len(self.days) - 1, i_after + 5))]
                i_before = max(gaps, key=lambda z: z[1])[0]
                i_after = i_before + 1
            blk = (self.days[i_after] - self.days[i_before]).days
            assert blk >= 3 and abs((d - self.days[i_before]).days) <= 10, (L, self.days[i_before], self.days[i_after])
            self.leb.append((i_before, i_after, L, str(self.days[i_before].date()), str(self.days[i_after].date()), blk))

    def mask(self, spec) -> np.ndarray:
        kind, a, b = spec
        T = len(self.days)
        m = np.zeros(T, bool)
        dow = self.days.dayofweek.to_numpy()
        mon = self.days.month.to_numpy()
        if kind == "tom":
            m = (self.pos_end <= a) | (self.pos_start <= b)
        elif kind == "preleb":
            for ib, ia, *_ in self.leb:
                lo, hi = ib - a + 1, ib - b
                m[max(0, lo):hi + 1] = True
        elif kind == "postleb":
            for ib, ia, *_ in self.leb:
                lo, hi = ia + b, ia + a - 1
                m[lo:min(T, hi + 1)] = True
        elif kind == "declast":
            m = (mon == 12) & (self.pos_end <= a)
        elif kind == "janfirst":
            m = (mon == 1) & (self.pos_start <= a)
        elif kind == "prehol":
            idx = np.where(self.before_hol)[0]
            for i in idx:
                m[max(0, i - a + 1):i - b + 1] = True
        elif kind == "dow":
            m = dow == a
        elif kind == "dow_nohol":
            m = (dow == a) & ~(self.after_hol if a == 0 else self.before_hol)
        elif kind == "postweekend":
            m = self.gap_before.copy()
        elif kind == "preweekend":
            m = self.gap_after.copy()
        return np.asarray(m, bool)


# ---- episode statistics ---------------------------------------------------------------------------------------------------------
def episodes(mask: np.ndarray) -> list[tuple[int, int]]:
    out, i, T = [], 0, len(mask)
    while i < T:
        if mask[i]:
            j = i
            while j + 1 < T and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def ep_table(r: pd.Series, mask: np.ndarray, rt=None) -> pd.DataFrame:
    """r: daily simple returns on the calendar (NaN = no data). rt: scalar round trip or per-episode callable(i0, i1)."""
    ymean = r.groupby(r.index.year).transform("mean").to_numpy()
    rv = r.to_numpy()
    rows = []
    for i0, i1 in episodes(mask):
        seg = rv[i0:i1 + 1]
        if np.isnan(seg).all() or i0 == 0:
            continue
        seg = np.nan_to_num(seg)
        L = i1 - i0 + 1
        gross_ret = float(np.prod(1 + seg) - 1)
        bench = float(np.nanmean(ymean[i0:i1 + 1]) * L)
        c = rt(i0, i1) if callable(rt) else (rt or 0.0)
        rows.append({"i0": i0, "i1": i1, "year": int(r.index[i0].year), "L": L, "ret": gross_ret, "excess": gross_ret - bench, "rt": c})
    return pd.DataFrame(rows)


def tstat(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def placebo_pct(r: pd.Series, mask: np.ndarray, real: float, sign: int) -> float:
    T = len(mask)
    n = int(mask.sum())
    vals = []
    tries = 0
    while len(vals) < N_PLACEBO and tries < N_PLACEBO * 20:
        tries += 1
        k = int(RNG.integers(10, T - 10))
        m2 = np.roll(mask, k)
        if (m2 & mask).sum() > 0.5 * n:
            continue
        e = ep_table(r, m2)
        if len(e):
            vals.append(e["excess"].mean())
    vals = np.array(vals) * sign
    return float((vals < real * sign).mean() * 100)


def deflated_sharpe(s, n_trials):
    s = [x for x in s if np.isfinite(x)]
    n = len(s)
    if n < 3:
        return 0.0
    mu = sum(s) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in s) / n)
    if sd == 0:
        return 0.0
    sr = mu / sd
    sk = (sum((x - mu) ** 3 for x in s) / n) / sd ** 3
    ku = (sum((x - mu) ** 4 for x in s) / n) / sd ** 4
    Z = NormalDist()
    e = 0.5772156649015329
    v = (1 - sk * sr + (ku - 1) / 4.0 * sr ** 2) / (n - 1)
    if v <= 0:
        return 0.0
    se = math.sqrt(v)
    emax = Z.inv_cdf(1 - 1.0 / n_trials) * (1 - e) + Z.inv_cdf(1 - 1.0 / (n_trials * math.e)) * e
    return Z.cdf((sr - se * emax) / se)


def sleeve_daily(r: pd.Series, mask: np.ndarray, E: pd.DataFrame) -> pd.Series:
    """Daily net returns of the long-only sleeve: in-window returns, the round trip charged on the episode's first day."""
    out = np.where(mask, np.nan_to_num(r.to_numpy()), 0.0)
    for x in E.itertuples():
        out[x.i0] -= x.rt
    return pd.Series(out, index=r.index)


def ann(s: pd.Series) -> dict:
    eq = (1 + s).cumprod()
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1), "sharpe": float(s.mean() / s.std() * np.sqrt(252)) if s.std() > 0 else float("nan"),
            "mdd": float((eq / eq.cummax() - 1).min())}


# ---- data -----------------------------------------------------------------------------------------------------------------------
def load():
    jk = pd.read_csv(os.path.join(ROOT, "research-scratch", "idx", "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    jk = jk[(jk.index >= "2005-10-01")]
    jk = jk[jk.diff().ne(0) | jk.index.isin(jk.index[:1])]                  # drop stale repeated closes (Yahoo holiday fills)
    with psycopg.connect(dsn()) as conn:
        comp = pd.read_sql("select trade_date, close from idx.index_daily where index_code='COMPOSITE' order by trade_date", conn,
                           parse_dates=["trade_date"]).set_index("trade_date")["close"].astype(float)
    P, unis, _comp, _H, _L = pickle.load(open(os.environ["IDX_EXIT_CACHE"], "rb"))
    return jk, comp, P, unis


def basket(P, uni: pd.DataFrame, c_in, c_out):
    adj = P["adj"]
    ret = (adj / adj.shift(1) - 1).clip(-0.5, 1.0)
    mem = uni.shift(1).fillna(False).astype(bool) & ret.notna()
    r = ret.where(mem).mean(axis=1)
    cin = pd.DataFrame(c_in, index=adj.index, columns=adj.columns).where(uni.astype(bool)).mean(axis=1)
    cout = pd.DataFrame(c_out, index=adj.index, columns=adj.columns).where(uni.astype(bool)).mean(axis=1)
    return r, cin, cout


def evaluate(name, spec, sign, series: dict, cal: dict, rts: dict, primary="JKSE", placebo=True):
    res = {"spec": spec, "sign": sign}
    for sname, r in series.items():
        C = cal[sname]
        m = C.mask(spec)
        E = ep_table(r, m, rts[sname])
        if not len(E):
            res[sname] = None
            continue
        net = E["excess"] - E["rt"]
        d = {"n_ep": len(E), "days_share": float(m.mean()), "mean_len": float(E["L"].mean()),
             "gross_bps": float(E["excess"].mean() * 1e4), "t_gross": tstat(E["excess"]), "net_bps": float(net.mean() * 1e4), "t_net": tstat(net),
             "rt_bps": float(E["rt"].mean() * 1e4), "net15_bps": float((E["excess"] - 1.5 * E["rt"]).mean() * 1e4),
             "hit": float((E["excess"] * sign > 0).mean()),
             "by_year": {int(y): float(v * 1e4) for y, v in E.groupby("year")["excess"].mean().items()}}
        yrs = d["by_year"]
        d["years_ok"] = float(np.mean([v * sign > 0 for v in yrs.values()]))
        d["blocks"] = {f"{a}-{b % 100:02d}": (float(np.mean([v for y, v in yrs.items() if a <= y <= b])) if any(a <= y <= b for y in yrs) else None) for a, b in BLOCKS}
        sl = sleeve_daily(r, m, E)
        d["sleeve"] = ann(sl.loc[r.first_valid_index():])
        d["dsr"] = deflated_sharpe(sl.to_numpy().tolist(), N_CUM)
        if sname == primary:
            d["placebo_pct"] = placebo_pct(r, m, float(E["excess"].mean()), sign) if placebo else None
            d["neigh"] = {}
            for nspec in NEIGH[name]:
                En = ep_table(r, C.mask(nspec), rts[sname])
                d["neigh"][str(nspec)] = {"gross_bps": float(En["excess"].mean() * 1e4), "net_bps": float((En["excess"] - En["rt"]).mean() * 1e4), "t": tstat(En["excess"])}
            res["_sleeve_series"] = sl
            res["_mask"] = m
        res[sname] = d
    return res


def judge(res, sign) -> dict:
    p = res["JKSE"]
    g = p["gross_bps"] * sign
    t = p["t_gross"] * sign
    B = all(v is not None and v * sign > 0 for v in p["blocks"].values()) and p["years_ok"] >= 0.6
    P = (p["placebo_pct"] or 0) >= 95
    N = all(v["gross_bps"] * sign > 0 and v["gross_bps"] * sign >= 0.5 * g for v in p["neigh"].values())
    X = all(res[s] is not None and res[s]["gross_bps"] * sign > 0 for s in ("COMP", "LIQ", "SMALL"))
    overlay = t >= 2.0 and B and P and N and X
    sleeve = None
    if sign > 0:
        Xn = any(res[s] is not None and res[s]["net_bps"] > 0 for s in ("LIQ", "SMALL"))
        Nn = all(v["net_bps"] > 0 for v in p["neigh"].values())
        sleeve = bool(p["net_bps"] > 0 and p["t_net"] >= 2.0 and B and P and N and Nn and p["net15_bps"] > 0 and Xn)
    fails = [k for k, ok in (("B", B), ("N", N), ("X", X)) if not ok]
    if not (t >= 2.0):
        verdict = "CLOSED"
    elif overlay:
        verdict = "ROBUST"
    elif P and len(fails) == 1:
        verdict = "PARTIAL"
    else:
        verdict = "FRAGILE"
    return {"T": t >= 2.0, "B": B, "P": P, "N": N, "X": X, "overlay_bar": overlay, "sleeve_bar": sleeve, "verdict": verdict}


# ---- combo trials (11-12) -------------------------------------------------------------------------------------------------------
def combo_trials(best: str, sign: int, sleeve_series: pd.Series, cal_small: Cal) -> dict:
    import idx_combo_rupiah as CR
    import idx_ml_strategy as M
    d = dsn()
    Pm = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    Pm = Pm[(Pm["d"] >= "2021-06-01") & (Pm["d"] <= CR.END)].copy()
    dates = M.wide(Pm, "close").index
    codes = M.wide(Pm, "close").columns
    g = lambda c: M.wide(Pm, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = CR.ml_trades(Pm, dates, codes, A, raw, offer, bid, liq)
    tr = CR.trend_trades(d, dates)
    gap = CR.gap_events(d, dates)
    out = {}
    navs = {}
    for nm, use in {"combined": {"gap", "trend", "ML"}, "gap": {"gap"}, "trend": {"trend"}, "ML": {"ML"}}.items():
        nav, _, _ = CR.engine(dates, codes, A, raw, offer, bid, ml, tr, gap, use)
        navs[nm] = nav
    rets = {k: v.pct_change().fillna(0.0) for k, v in navs.items()}
    sl = sleeve_series.reindex(rets["combined"].index).fillna(0.0)
    out["corr"] = {k: float(np.corrcoef(v, sl)[0, 1]) for k, v in rets.items()}
    base = ann(rets["combined"])
    blend = ann(0.8 * rets["combined"] + 0.2 * sl)
    out["sleeve20"] = {"combined": base, "blend_80_20": blend, "sleeve_alone": ann(sl)}
    # overlay: re-time trend/ML trades around the window (calendar = the ML panel's dates)
    cal = Cal(pd.DatetimeIndex(dates))
    spec = WINDOWS[best][0]
    m = cal.mask(spec)
    eps = episodes(m)
    last_of = np.full(len(dates), -1)
    for i0, i1 in eps:
        last_of[i0:i1 + 1] = i1
    moved = 0

    def shift(x):
        nonlocal moved
        y = dict(x)
        if sign > 0 and last_of[y["t_out"]] >= 0 and y["t_out"] < last_of[y["t_out"]]:
            y["t_out"] = int(last_of[y["t_out"]])
            moved += 1
        if sign < 0 and last_of[y["t_in"]] >= 0:
            new = int(last_of[y["t_in"]]) + 1
            if new < y["t_out"] and new < len(dates):
                y["t_in"] = new
                moved += 1
        return y
    tr2 = [shift(x) for x in tr]
    ml2 = [shift(x) for x in ml]
    nav2, _, _ = CR.engine(dates, codes, A, raw, offer, bid, ml2, tr2, gap, {"gap", "trend", "ML"})
    out["overlay"] = {"combined": base, "overlay": ann(nav2.pct_change().fillna(0.0)), "trades_moved": moved,
                      "rule": "defer exits to window end" if sign > 0 else "defer entries past window"}
    return out


# ---- main -----------------------------------------------------------------------------------------------------------------------
def main() -> int:
    import idx_swing2 as S
    jk, comp, P, unis = load()
    master = Cal(jk.index.union(comp.index))
    log(f"calendar {master.days[0].date()} -> {master.days[-1].date()}, {len(master.days)} days, {len(master.holidays)} weekday holidays; "
        f"Lebaran closures {len(master.leb)}")
    for x in master.leb:
        log(f"  Lebaran {x[2]}: last day {x[3]}, reopen {x[4]} ({x[5]} calendar days)")
    # series on their own calendar (the master restricted to their span); returns reindexed to it
    series, cal, rts = {}, {}, {}
    jk_r = jk.reindex(master.days).pct_change(fill_method=None)
    jk_r = jk_r[jk_r.index >= "2006-01-01"]
    comp_r = comp.reindex(master.days[master.days >= comp.index[0]]).pct_change(fill_method=None)
    c_in, c_out = S.costs(P)
    liq = unis["LIQ"].astype(bool)
    small = (unis["LIQ"] & ~unis["BLUE"]).astype(bool)
    r_liq, cin_l, cout_l = basket(P, liq, c_in, c_out)
    r_sm, cin_s, cout_s = basket(P, small, c_in, c_out)
    days_b = master.days[(master.days >= P["adj"].index[0]) & (master.days <= P["adj"].index[-1])]
    for nm, r in (("JKSE", jk_r), ("COMP", comp_r)):
        series[nm] = r
        cal[nm] = Cal(r.index) if nm == "JKSE" else Cal(r.index)
        rts[nm] = RT_INDEX
    for nm, r, ci, co in (("LIQ", r_liq, cin_l, cout_l), ("SMALL", r_sm, cin_s, cout_s)):
        rr = r.reindex(days_b)
        series[nm] = rr
        cal[nm] = Cal(days_b)
        ci_v, co_v = ci.reindex(days_b).ffill().to_numpy(), co.reindex(days_b).ffill().to_numpy()
        rts[nm] = (lambda ci_v, co_v: (lambda i0, i1: float(np.nan_to_num(ci_v[i0 - 1], nan=0.008) + np.nan_to_num(co_v[i1], nan=0.008))))(ci_v, co_v)
    # the sub-calendars recompute holidays inside their span only: rebuild with the master's holiday knowledge
    for nm in series:
        c = cal[nm]
        c.holidays = master.holidays[(master.holidays >= c.days[0]) & (master.holidays <= c.days[-1])]
        sel = master.days.isin(c.days)
        c.before_hol, c.after_hol = master.before_hol[sel], master.after_hol[sel]
        c.gap_after, c.gap_before = master.gap_after[sel], master.gap_before[sel]
        c.leb = [(int(c.days.searchsorted(master.days[ib])), int(c.days.searchsorted(master.days[ia])), *rest)
                 for ib, ia, *rest in master.leb if master.days[ib] >= c.days[0] and master.days[ia] <= c.days[-1]]
    log(f"mean measured round trip: LIQ {np.nanmean(cin_l + cout_l) * 1e4:.0f} bps, SMALL {np.nanmean(cin_s + cout_s) * 1e4:.0f} bps; index {RT_INDEX * 1e4:.0f} bps")

    results = {}
    for name, (spec, sign) in WINDOWS.items():
        res = evaluate(name, spec, sign, series, cal, rts)
        res["judge"] = judge(res, sign)
        results[name] = res
        p = res["JKSE"]
        log(f"{name:<11} JKSE n {p['n_ep']:4d} gross {p['gross_bps']:+7.1f} bps t {p['t_gross']:+5.2f} net {p['net_bps']:+7.1f} (t {p['t_net']:+5.2f}) "
            f"blocks {', '.join(f'{k}:{v:+.0f}' for k, v in p['blocks'].items())} yrs {p['years_ok'] * 100:.0f}% plc {p['placebo_pct']:.0f} | "
            + " ".join(f"{s}:{res[s]['gross_bps']:+.0f}/{res[s]['net_bps']:+.0f}" for s in ("COMP", "LIQ", "SMALL") if res[s]) + f" -> {res['judge']}")
    # January small-minus-large spread (descriptive)
    jan = cal["SMALL"].mask(("janfirst", 10, 0))
    Es = ep_table(series["SMALL"], jan)
    El = ep_table(series["LIQ"], jan)
    jan_spread = {int(a.year): float((a.ret - b.ret) * 1e4) for a, b in zip(Es.itertuples(), El.itertuples())}

    used = 10
    combo = None
    surv = [n for n, r in results.items() if r["judge"]["verdict"] in ("ROBUST", "PARTIAL")]
    if surv:
        best = max(surv, key=lambda n: abs(results[n]["JKSE"]["t_gross"]))
        sign = WINDOWS[best][1]
        sm = results[best]
        sl_small = sleeve_daily(series["SMALL"], cal["SMALL"].mask(WINDOWS[best][0]), ep_table(series["SMALL"], cal["SMALL"].mask(WINDOWS[best][0]), rts["SMALL"]))
        combo = {"best": best, **combo_trials(best, sign, sl_small, cal["SMALL"])}
        used = 12
        log(f"combo ({best}): {json.dumps(combo, default=str)[:1500]}")
    n_cum = N_BEFORE + used - 1

    # ---- report ----
    def f(x, k="gross_bps"):
        return "-" if x is None else f"{x[k]:+.0f}"
    L = [f"# IDX menu 37 (Track B2) - calendar effects, long-only - {date.today()} - {used} trials (ids {N_BEFORE}..{n_cum}), cumulative N = {n_cum}", "",
         "Question: does holding only inside a calendar window beat HOLDING the same exposure, net of IDX costs - as a sleeve, or as a timing overlay "
         "for the books? Per episode: excess = window return - (days x the same year's mean daily return). JKSE (Yahoo ^JKSE) 2006-01 -> 2026-09 is the "
         "primary series; COMPOSITE (idx.index_daily), LIQ and SMALL equal-weight baskets (idx.bar, membership at the prior close) 2020-26 are the tradeable checks. "
         f"Round trip: index 80 bps; baskets measured at closing offer/bid + fees (mean LIQ {np.nanmean(cin_l + cout_l) * 1e4:.0f} bps, SMALL {np.nanmean(cin_s + cout_s) * 1e4:.0f} bps per day-pair).", "",
         "## Pre-registered bar (from the script docstring, written before the run)", "",
         "- OVERLAY: gross t >= 2 (sign as hypothesised), mean excess of that sign in all 3 blocks (2006-12, 2013-19, 2020-26) and >= 60 % of years, "
         "placebo (500 circular shifts of the window) percentile >= 95, every +/-1-day neighbour keeps the sign and >= half the excess, same sign on COMP, LIQ, SMALL.",
         "- SLEEVE (sign + only): the overlay bar AND net excess > 0 with t_net >= 2, neighbours net > 0, costs x1.5 net > 0, LIQ or SMALL net > 0.",
         "- ROBUST = overlay bar; PARTIAL = t and placebo pass, one of blocks / neighbours / tradeable fails; FRAGILE = placebo fails or two fail; CLOSED = |t| < 2 or wrong sign.", "",
         "## JKSE 2006-26 (primary)", "",
         "| window | sign | episodes | days % | gross excess bps/ep | t | net bps (80) | t net | net x1.5 | 2006-12 | 2013-19 | 2020-26 | years ok | placebo pct | DSR sleeve | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, res in results.items():
        p, j = res["JKSE"], res["judge"]
        b = p["blocks"]
        L.append(f"| {name} | {'+' if res['sign'] > 0 else '-'} | {p['n_ep']} | {p['days_share'] * 100:.0f} % | {p['gross_bps']:+.1f} | {p['t_gross']:+.2f} | {p['net_bps']:+.1f} | {p['t_net']:+.2f} | "
                 f"{p['net15_bps']:+.1f} | " + " | ".join("-" if v is None else f"{v:+.0f}" for v in b.values()) + f" | {p['years_ok'] * 100:.0f} % | {p['placebo_pct']:.0f} | {p['dsr']:.2f} | **{j['verdict']}** |")
    L += ["", "## Tradeable checks 2020-26 (gross / net excess, bps per episode; t gross)", "",
          "| window | COMP gross | COMP net | LIQ gross | LIQ net | LIQ t | SMALL gross | SMALL net | SMALL t | SMALL sleeve CAGR / Sharpe / mDD |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, res in results.items():
        c, l, s = res["COMP"], res["LIQ"], res["SMALL"]
        L.append(f"| {name} | {f(c)} | {f(c, 'net_bps')} | {f(l)} | {f(l, 'net_bps')} | {l['t_gross']:+.2f} | {f(s)} | {f(s, 'net_bps')} | {s['t_gross']:+.2f} | "
                 f"{s['sleeve']['cagr'] * 100:+.1f} % / {s['sleeve']['sharpe']:.2f} / {s['sleeve']['mdd'] * 100:.0f} % |")
    L += ["", "## Neighbours (JKSE, window +/- 1 day) and battery", "", "| window | neighbours: gross / net bps (t) | T | B | P | N | X | overlay bar | sleeve bar |", "|---|---|---|---|---|---|---|---|---|"]
    for name, res in results.items():
        p, j = res["JKSE"], res["judge"]
        nb = "; ".join(f"{k}: {v['gross_bps']:+.0f} / {v['net_bps']:+.0f} ({v['t']:+.1f})" for k, v in p["neigh"].items())
        yn = lambda z: "-" if z is None else ("pass" if z else "fail")  # noqa: E731
        L.append(f"| {name} | {nb} | {yn(j['T'])} | {yn(j['B'])} | {yn(j['P'])} | {yn(j['N'])} | {yn(j['X'])} | {yn(j['overlay_bar'])} | {yn(j['sleeve_bar'])} |")
    L += ["", "## Per year, JKSE gross excess (bps per episode)", "", "| window | " + " | ".join(str(y)[2:] for y in range(2006, 2027)) + " |", "|---|" + "---|" * 21]
    for name, res in results.items():
        by = res["JKSE"]["by_year"]
        L.append(f"| {name} | " + " | ".join(f"{by[y]:+.0f}" if y in by else "" for y in range(2006, 2027)) + " |")
    L += ["", "January, SMALL minus LIQ over the first 10 trading days (bps): " + ", ".join(f"{y}: {v:+.0f}" for y, v in jan_spread.items()), "",
          "Lebaran closures used (last trading day -> reopen): " + "; ".join(f"{x[2]}: {x[3]} -> {x[4]}" for x in master.leb)]
    if combo:
        s20, ov = combo["sleeve20"], combo["overlay"]
        L += ["", f"## Survivor on the combined book ({combo['best']}; trials 11-12)", "",
              "Correlation of the SMALL sleeve's daily net returns with: " + ", ".join(f"{k} {v:+.2f}" for k, v in combo["corr"].items()), "",
              "| book | CAGR | Sharpe | mDD |", "|---|---|---|---|"]
        if WINDOWS[combo["best"]][1] < 0:
            L.insert(len(L) - 2, "The survivor's sign is negative, so trial 11 (a long-only sleeve INSIDE the window) is by construction a long-Mondays "
                                 "sleeve - shown for completeness, not a candidate. Trial 12 (the overlay) is the real test.\n")
        for k, v in list(s20.items()) + [("overlay: " + ov["rule"] + f" ({ov['trades_moved']} trades)", ov["overlay"])]:
            L.append(f"| {k} | {v['cagr'] * 100:.1f} % | {v['sharpe']:.2f} | {v['mdd'] * 100:.0f} % |")
    L += ["", READING]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_CALENDAR_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    slim = {n: {k: v for k, v in r.items() if not k.startswith("_")} for n, r in results.items()}
    json.dump({"results": slim, "jan_spread": jan_spread, "lebaran": master.leb, "combo": combo}, open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    if os.environ.get("IDX_CAL_NOSTORE"):
        return 0
    from blackheart_ingest.idx import research_store as rs
    from blackheart_ingest.idx.ml import common
    with psycopg.connect(dsn()) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(WINDOWS) + (["combo_sleeve", "combo_overlay"] if combo else []), "n_trials_cumulative": n_cum,
                                                                 "n_before": N_BEFORE, "rt_index": RT_INDEX, "placebo": N_PLACEBO, "blocks": BLOCKS, "lebaran": LEBARAN},
                              summary={"verdicts": {n: r["judge"] for n, r in results.items()}, "jkse": common.plain({n: r["JKSE"] for n, r in slim.items()}),
                                       "tradeable": common.plain({n: {s: r[s] for s in ("COMP", "LIQ", "SMALL")} for n, r in slim.items()}),
                                       "jan_spread": jan_spread, "combo": common.plain(combo) if combo else None},
                              names=[], report_path=out, note="menu 37 (Track B2): calendar effects - TOM, Lebaran, year-end/January, pre-holiday, day-of-week")
        conn.commit()
    log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
