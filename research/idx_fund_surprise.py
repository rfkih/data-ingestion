#!/usr/bin/env python3
"""IDX menu 38 (Track B3) - FUNDAMENTAL earnings surprise / post-earnings drift from the actual reported numbers.

Not a repeat of the price-reaction PEAD proxy (IDX_SWING 09-17, 0/22): the signal here is the reported quarter itself,
from idx.fundamental (the parsed idx.financial_report workbooks; net_profit = profit attributable to the parent entity,
already converted to IDR for USD reporters), dated by published_at.

DATA SNAPSHOT: reports parsed by CUTOFF (2026-09-25 16:00 UTC). A backlog drain is running; ~half of the 2020-2023 quarterly
workbooks are still pending (liquid names >= Rp 5 bn/day: 75-87 % parsed in 2021-23, 95-100 % in 2024-26). Every verdict in
this menu is therefore labelled PRELIM; the re-run on the drained data is the real one.

POINT IN TIME. IDX reports are year-to-date. The DISCRETE quarter = YTD minus the previous YTD report of the same fiscal year
(TW1 = its own YTD); the same-quarter-last-year figure = the report's own prior-year comparative minus the previous report's
comparative. A report whose previous report of the year is not parsed is dropped (no fallback to YTD - the YTD change
contains what the previous quarter already told the market). Signal day = published_at in WIB. Entry = the first session
whose open (09:00 WIB) is after publication; IDX opens are not stored before 2025, so entry is at THAT session's CLOSE at the
closing offer (the earliest executable price the data holds; next-open entry is reported for 2025-26 as a diagnostic).
Exit at the closing bid H sessions later. Fees 0.10 % / 0.20 %; missing/crossed quotes cost one tick. Events published more
than 150 days after period_end are dropped (late filers / restatements).
Universe at the close before entry: 60-day median value >= Rp 5 bn, close >= Rp 100 (no board filter: the stored board is
today's, not point-in-time).

SIGNALS (3, fixed before any result was looked at):
  E_mc   standardised unexpected earnings = (NP_q - NP_q,last year) / market cap at the last close before publication
  E_sue  same change / std of the name's previous >= 4 (up to 8) discrete-quarter changes (published before this one)
  R      revenue surprise = (Rev_q - Rev_q,last year) / |Rev_q,last year|  (requires last year's quarter revenue > 0)
  Quality filter: accruals = (NP_ytd - CFO_ytd) / total assets; the filter drops the highest-accrual tercile.
"Top bucket vs the universe": each event's score is ranked against every universe event published in the previous 365 days
(point-in-time percentile; needs >= 100 events in the window). Top quintile = percentile >= 0.80. Entries 2021-01 onward
(2020 = warm-up for the percentile).

PRE-REGISTERED TRIALS (N_BEFORE = 873; at most 10 counted, cumulative printed):
  T1 E_mc top quintile H=20       T2 E_mc top quintile H=40       T3 E_mc top quintile H=60
  T4 E_sue top quintile H=40      T5 R top quintile H=40          T6 E_mc top quintile + accrual filter H=40
  Best arm = the H=40 arm (T2, T4, T5, T6) with the highest month-clustered t. Battery on it (counted as trials):
  T7/T8 bucket neighbours (top decile, top tercile); H neighbours 20/60 (= T1/T3 when the best arm is T2, else 2 more trials).
MEASURES per arm: net return per trade (offer in, bid out, fees), EXCESS = net minus the equal-weight gross return of the
universe names in the same market-cap quintile (quintiles of the universe that day) over the identical window; t-stat
clustered by entry month (mean of monthly means / its standard error); per entry year; a standalone book (Rp 20 M, 5 % of
NAV per trade, 20 slots, lots of 100) -> CAGR / Sharpe / mDD; placebo = the same names at 200 random entry dates.
BAR (CANDIDATE, all three): (a) mean net excess > 0 with month-clustered t >= 2.5; (b) net excess > 0 in >= 4 of the 6 entry
years 2021-2026; (c) standalone book Sharpe >= 0.8 with mDD no deeper than -25 %.
VERDICT on the best arm: CLOSED if no arm meets (a). If the best arm is a CANDIDATE: ROBUST when placebo pct >= 95, >= 3 of 4
neighbours keep mean excess > 0 with t >= 2, costs x1.5 keep mean excess > 0 and a 1-day delay keeps it > 0 with t >= 2;
PARTIAL when exactly one of those fails; FRAGILE when the placebo fails or two or more fail. An arm with (a) but not (b)/(c):
FRAGILE. Every verdict carries PRELIM (coverage). DSR reported on the best arm's daily book returns at the cumulative N.
If a candidate exists: correlation with the gap-fade / trend / ML sleeves and the effect of adding it to the combined book
(idx_combo_rupiah engine), and whether it works as a filter on the ML / trend entries.
READ-ONLY; one idx.study row ('fund_surprise').
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import warnings
from datetime import date, datetime, timedelta, timezone
from statistics import NormalDist

import numpy as np
import pandas as pd
import psycopg

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))

N_BEFORE = 873
STUDY = "fund_surprise"
CUTOFF = datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc)
START, WARM = pd.Timestamp("2021-01-01"), pd.Timestamp("2020-01-01")
LIQ, MIN_PX, MAX_LAG = 5e9, 100.0, 150
FEE_BUY, FEE_SELL = 0.0010, 0.0020
CAPITAL, PCT, MAX_POS, LOT = 20_000_000.0, 0.05, 20, 100
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
N_PLACEBO, SEED = 200, 20260925
ARMS = {"T1": ("E_mc", 0.8, 20, False), "T2": ("E_mc", 0.8, 40, False), "T3": ("E_mc", 0.8, 60, False),
        "T4": ("E_sue", 0.8, 40, False), "T5": ("R", 0.8, 40, False), "T6": ("E_mc", 0.8, 40, True)}
BAR = {"t": 2.5, "years_pos": 4, "sharpe": 0.8, "mdd": -0.25, "placebo_pct": 95.0, "nb_t": 2.0}
PREV = {"TW2": "TW1", "TW3": "TW2", "TAHUNAN": "TW3"}
MONTHS = {"TW1": 3, "TW2": 6, "TW3": 9, "TAHUNAN": 12}
WIB = timezone(timedelta(hours=7))


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    return env["INGEST_DB_DSN"].strip().strip('"')


def tick(px):
    px = np.asarray(px, float)
    return np.select([px < 200, px < 500, px < 2000, px < 5000], [1.0, 2.0, 5.0, 10.0], 25.0)


# ---------------------------------------------------------------- data
def load(conn):
    q = lambda s, p=(): pd.read_sql(s, conn, params=p)  # noqa: E731
    # opens back-filled from Yahoo (open_src='yahoo') are chart data, not IDX opening prints: keep them out
    bars = q("""SELECT b.code, b.trade_date, CASE WHEN b.open_src = 'idx' THEN b.open END AS open, b.close, b.adj_factor, s.bid, s.offer, f.value_60d_median AS v60, f.mcap
                  FROM idx.bar b LEFT JOIN idx.daily_summary s USING (code, trade_date) LEFT JOIN idx.feature_daily f USING (code, trade_date)
                 WHERE b.source = 'idx' AND b.trade_date >= '2019-10-01'""")
    fund = q("""SELECT f.code, f.period_end, f.published_at, f.months, f.net_profit, f.net_profit_prior, f.revenue, f.revenue_prior, f.cfo,
                       f.total_assets, r.fiscal_year, r.period
                  FROM idx.fundamental f JOIN idx.financial_report r ON r.id = f.report_id
                 WHERE r.parse_status = 'parsed' AND r.parsed_at <= %s AND r.report_type = 'rdf'""", (CUTOFF,))
    rep = q("""SELECT fiscal_year, period, parse_status, code, published_at FROM idx.financial_report WHERE report_type = 'rdf' AND fiscal_year >= 2019""")
    return bars, fund, rep


def panels(bars):
    for c in ("open", "close", "adj_factor", "bid", "offer", "v60", "mcap"):
        bars[c] = pd.to_numeric(bars[c], errors="coerce")
    bars["adj"] = bars["close"] * bars["adj_factor"].fillna(1.0)
    bars["trade_date"] = pd.to_datetime(bars["trade_date"])
    W = {c: bars.pivot(index="trade_date", columns="code", values=c).sort_index() for c in ("adj", "close", "open", "bid", "offer", "v60", "mcap")}
    dates, codes = W["close"].index, W["close"].columns
    for k in W:
        W[k] = W[k].reindex(index=dates, columns=codes)
    return W, dates, codes


def discrete(fund: pd.DataFrame) -> pd.DataFrame:
    f = fund.copy()
    for c in ("net_profit", "net_profit_prior", "revenue", "revenue_prior", "cfo", "total_assets", "months"):
        f[c] = pd.to_numeric(f[c], errors="coerce")
    f = f[f["period"].isin(MONTHS) & (f["months"] == f["period"].map(MONTHS))]
    f = f.sort_values("published_at").drop_duplicates(["code", "fiscal_year", "period"], keep="first")
    key = f.set_index(["code", "fiscal_year", "period"])
    rows = []
    for r in f.itertuples(index=False):
        if r.period == "TW1":
            p_np = p_npp = p_rev = p_revp = 0.0
        else:
            k = (r.code, r.fiscal_year, PREV[r.period])
            if k not in key.index:
                continue
            p = key.loc[k]
            if p["published_at"] > r.published_at:
                continue
            p_np, p_npp, p_rev, p_revp = p["net_profit"], p["net_profit_prior"], p["revenue"], p["revenue_prior"]
        rows.append({"code": r.code, "fy": r.fiscal_year, "period": r.period, "period_end": pd.Timestamp(r.period_end), "pub": r.published_at,
                     "np_q": r.net_profit - p_np, "np_q_py": r.net_profit_prior - p_npp, "rev_q": r.revenue - p_rev, "rev_q_py": r.revenue_prior - p_revp,
                     "accr": (r.net_profit - r.cfo) / r.total_assets if r.total_assets and r.total_assets > 0 else np.nan})
    E = pd.DataFrame(rows)
    E["pub"] = pd.to_datetime(E["pub"], utc=True)
    E = E[(E["pub"].dt.tz_convert(WIB).dt.tz_localize(None) - E["period_end"]).dt.days <= MAX_LAG]
    E["d_np"] = E["np_q"] - E["np_q_py"]
    # E_sue: std of the name's previous discrete changes (published strictly before)
    E = E.sort_values(["code", "pub"]).reset_index(drop=True)
    sue = np.full(len(E), np.nan)
    for _, g in E.groupby("code"):
        vals = g["d_np"].to_numpy(float)
        for i, ix in enumerate(g.index):
            hist = vals[max(0, i - 8):i]
            hist = hist[np.isfinite(hist)]
            if len(hist) >= 4 and np.std(hist, ddof=1) > 0:
                sue[ix] = vals[i] / np.std(hist, ddof=1)
    E["E_sue"] = sue
    E["R"] = np.where(E["rev_q_py"] > 0, (E["rev_q"] - E["rev_q_py"]) / E["rev_q_py"].abs(), np.nan)
    return E


def place(E, W, dates, codes):
    """Entry index (first session whose 09:00 WIB open is after publication), market cap before publication, universe."""
    cix = {c: i for i, c in enumerate(codes)}
    pub_wib = E["pub"].dt.tz_convert(WIB).dt.tz_localize(None)
    D = dates.values
    te, jj, mc = [], [], []
    mcap = W["mcap"].ffill(limit=5).to_numpy(float)
    for pw, code in zip(pub_wib, E["code"]):
        j = cix.get(code, -1)
        day = pd.Timestamp(pw.date())
        i = int(np.searchsorted(D, np.datetime64(day)))                      # first session on/after the publication date
        if i < len(D) and D[i] == np.datetime64(day) and pw.hour >= 9:     # published during/after that session -> next one
            i += 1
        ib = int(np.searchsorted(D, np.datetime64(day))) - 1                # last close strictly before the publication date
        te.append(i if i < len(D) else -1)
        jj.append(j)
        mc.append(mcap[ib, j] if (j >= 0 and ib >= 0) else np.nan)
    E = E.assign(t=te, j=jj, mcap=mc)
    E = E[(E["t"] > 0) & (E["j"] >= 0)].copy()
    E["E_mc"] = E["d_np"] / E["mcap"]
    close = W["close"].to_numpy(float)
    v60 = W["v60"].ffill(limit=5).to_numpy(float)
    tb = E["t"].to_numpy() - 1
    E["uni"] = (v60[tb, E["j"]] >= LIQ) & (close[tb, E["j"]] >= MIN_PX)
    E["entry"] = dates[E["t"].to_numpy()]
    return E


def pit_pct(E: pd.DataFrame, col: str) -> np.ndarray:
    """Percentile of each event's score among universe events with the score published in the previous 365 days."""
    U = E[E["uni"] & E[col].notna()].sort_values("pub")
    t = U["pub"].to_numpy()
    v = U[col].to_numpy(float)
    out = pd.Series(np.nan, index=E.index)
    for k, (ix, p, x) in enumerate(zip(U.index, t, v)):
        lo = np.searchsorted(t, p - np.timedelta64(365, "D"))
        w = v[lo:k]
        if len(w) >= 100:
            out[ix] = float((w < x).mean())
    return out.to_numpy()


# ---------------------------------------------------------------- returns
class Mkt:
    def __init__(self, W, dates):
        self.dates = dates
        self.A = W["adj"].ffill(limit=5).to_numpy(float)
        self.C = W["close"].to_numpy(float)
        C = np.nan_to_num(self.C, nan=1.0)
        off, bid = np.nan_to_num(W["offer"].to_numpy(float)), np.nan_to_num(W["bid"].to_numpy(float))
        tk = tick(C)
        self.c_in = np.where((off > 0) & (off >= C), off / C - 1, tk / C) + FEE_BUY
        self.c_out = np.where((bid > 0) & (bid <= C), 1 - bid / C, tk / C) + FEE_SELL
        self.c_in = np.minimum(self.c_in, 0.10)
        self.c_out = np.minimum(self.c_out, 0.10)
        self.O = W["open"].to_numpy(float)
        v60 = W["v60"].ffill(limit=5).to_numpy(float)
        self.uni = (v60 >= LIQ) & (self.C >= MIN_PX)
        mc = W["mcap"].ffill(limit=5).to_numpy(float)
        mcu = np.where(self.uni, mc, np.nan)
        self.q = np.full(mc.shape, -1)
        for t in range(len(dates)):
            row = mcu[t]
            ok = np.isfinite(row)
            if ok.sum() >= 25:
                r = pd.Series(row[ok]).rank(pct=True).to_numpy()
                self.q[t, ok] = np.minimum((r * 5).astype(int), 4)
        self._ctrl = {}

    def fwd(self, H):
        A = self.A
        F = np.full(A.shape, np.nan)
        F[:-H] = A[H:] / A[:-H] - 1
        return F

    def ctrl(self, H):
        """Equal-weight gross return of universe names in the same mcap quintile, entry close t -> close t+H (universe at t-1)."""
        if H not in self._ctrl:
            F = self.fwd(H)
            T = len(self.dates)
            M = np.full((T, 5), np.nan)
            for t in range(1, T):
                ok = self.uni[t - 1] & np.isfinite(F[t])
                for qq in range(5):
                    m = ok & (self.q[t - 1] == qq)
                    if m.sum() >= 5:
                        M[t, qq] = F[t, m].mean()
            self._ctrl[H] = M
        return self._ctrl[H]

    def trade(self, t, j, H, cost_mult=1.0, delay=0):
        t = np.asarray(t) + delay
        j = np.asarray(j)
        T = len(self.dates)
        ok = t + H < T
        x = np.where(ok, t + H, 0)
        te = np.where(ok, t, 0)
        gross = self.A[x, j] / self.A[te, j] - 1
        net = gross - cost_mult * (self.c_in[te, j] + self.c_out[x, j])
        qq = self.q[np.maximum(te - 1, 0), j]
        cm = self.ctrl(H)[te, np.maximum(qq, 0)]
        cm = np.where(qq >= 0, cm, np.nan)
        exc = net - cm
        bad = ~ok | ~np.isfinite(net) | ~np.isfinite(cm)
        return np.where(bad, np.nan, net), np.where(bad, np.nan, exc)


def summarize(ev: pd.DataFrame, net, exc) -> dict:
    d = ev.assign(net=net, exc=exc).dropna(subset=["net", "exc"])
    if len(d) < 10:
        return {"n": len(d), "t": float("nan"), "mean_exc": float("nan"), "mean_net": float("nan"), "years": {}, "years_pos": 0}
    mm = d.groupby(d["entry"].dt.to_period("M"))["exc"].mean()
    t = float(mm.mean() / (mm.std(ddof=1) / math.sqrt(len(mm)))) if len(mm) > 2 and mm.std() > 0 else float("nan")
    yrs = {int(y): {"n": int(len(g)), "exc": float(g["exc"].mean()), "net": float(g["net"].mean())} for y, g in d.groupby(d["entry"].dt.year)}
    return {"n": int(len(d)), "months": int(len(mm)), "mean_net": float(d["net"].mean()), "median_net": float(d["net"].median()),
            "mean_exc": float(d["exc"].mean()), "median_exc": float(d["exc"].median()), "hit": float((d["net"] > 0).mean()), "t": t,
            "years": yrs, "years_pos": int(sum(1 for y in YEARS if y in yrs and yrs[y]["exc"] > 0))}


# ---------------------------------------------------------------- book
def book(mk: Mkt, trades: list[dict], t0: int):
    """Rp 20 M, 5 % of NAV per trade, 20 slots, lots of 100, closing offer in / closing bid out, fees."""
    A, C, T = mk.A, mk.C, len(mk.dates)
    ent, ext = {}, {}
    for x in trades:
        ent.setdefault(x["t_in"], []).append(x)
    cash, held, nav = CAPITAL, {}, np.full(T, np.nan)
    for t in range(t0, T):
        for key in [k for k, p in held.items() if p["t_out"] == t]:
            p = held.pop(key)
            j = p["j"]
            value = p["units"] * (A[t, j] / p["a_in"]) * (1 - (mk.c_out[t, j] - FEE_SELL))
            cash += value * (1 - FEE_SELL)
        mv = sum(p["units"] * A[t, p["j"]] / p["a_in"] for p in held.values() if np.isfinite(A[t, p["j"]]))
        nav_now = cash + mv
        for x in ent.get(t, []):
            j = x["j"]
            if x["code"] in held or len(held) >= MAX_POS or not np.isfinite(A[t, j]) or not np.isfinite(C[t, j]) or C[t, j] <= 0:
                continue
            px = C[t, j] * (1 + mk.c_in[t, j] - FEE_BUY)
            lots = int((PCT * nav_now) // (px * LOT))
            cost = lots * LOT * px * (1 + FEE_BUY)
            if lots < 1 or cost > cash:
                continue
            cash -= cost
            held[x["code"]] = {"j": j, "a_in": A[t, j], "units": lots * LOT * C[t, j], "t_out": min(x["t_out"], T - 1)}
        mv = sum(p["units"] * A[t, p["j"]] / p["a_in"] for p in held.values() if np.isfinite(A[t, p["j"]]))
        nav[t] = cash + mv
    return pd.Series(nav[t0:], index=mk.dates[t0:])


def bstats(nav: pd.Series) -> dict:
    r = nav.pct_change().fillna(0.0)
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    eq = nav / nav.iloc[0]
    by = nav.groupby(nav.index.year).agg(["first", "last"])
    return {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1), "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else float("nan"),
            "mdd": float((eq / eq.cummax() - 1).min()), "total": float(eq.iloc[-1] - 1),
            "by_year": {int(y): float(v["last"] / v["first"] - 1) for y, v in by.iterrows()}}


def deflated_sharpe(s, n_trials):
    s = [float(x) for x in s]
    n = len(s)
    mu = sum(s) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in s) / n)
    if sd == 0:
        return 0.0
    sr = mu / sd
    sk = (sum((x - mu) ** 3 for x in s) / n) / sd ** 3
    ku = (sum((x - mu) ** 4 for x in s) / n) / sd ** 4
    Z, e = NormalDist(), 0.5772156649015329
    v = (1 - sk * sr + (ku - 1) / 4.0 * sr ** 2) / (n - 1)
    if v <= 0:
        return 0.0
    se = math.sqrt(v)
    emax = Z.inv_cdf(1 - 1.0 / n_trials) * (1 - e) + Z.inv_cdf(1 - 1.0 / (n_trials * math.e)) * e
    return Z.cdf((sr - se * emax) / se)


def select(E, pct_col, thr, accr=False):
    m = E["uni"] & (E["entry"] >= START) & (E[pct_col] >= thr)
    if accr:
        m &= E["accr_pct"] <= 2 / 3
    return E[m]


# ---------------------------------------------------------------- main
def main() -> int:
    d = dsn()
    with psycopg.connect(d) as conn:
        bars, fund, rep = load(conn)
    W, dates, codes = panels(bars)
    log(f"panel {len(dates)} days x {len(codes)} codes; fundamentals {len(fund)} rows (parsed by {CUTOFF:%Y-%m-%d %H:%M} UTC)")
    mk = Mkt(W, dates)
    t0 = int(np.searchsorted(dates, np.datetime64(START)))

    # ---- coverage table (reports by year x period x liquidity bucket, parsed share) ----
    rep["pub"] = pd.to_datetime(rep["published_at"], utc=True).dt.tz_convert(WIB).dt.tz_localize(None).dt.normalize()
    cix = {c: i for i, c in enumerate(codes)}
    v60 = W["v60"].ffill(limit=5).to_numpy(float)
    ii = np.searchsorted(dates.values, rep["pub"].values.astype("datetime64[ns]")) - 1
    rep["v60"] = [v60[i, cix[c]] if (c in cix and 0 <= i < len(dates)) else np.nan for i, c in zip(ii, rep["code"])]
    rep["bucket"] = pd.cut(rep["v60"], [-1, 1e9, 5e9, 50e9, 1e18], labels=["<1bn", "1-5bn", "5-50bn", ">=50bn"]).astype(str)
    rep["parsed"] = rep["parse_status"] == "parsed"
    cov = rep.groupby(["fiscal_year", "period", "bucket"])["parsed"].agg(["sum", "count"]).reset_index()

    E = discrete(fund)
    E = place(E, W, dates, codes)
    for c in ("E_mc", "E_sue", "R"):
        E[c + "_pct"] = pit_pct(E, c)
    E["accr_pct"] = pit_pct(E, "accr")
    E["accr_pct"] = E["accr_pct"].fillna(0.5)
    uni_ev = E[E["uni"] & (E["entry"] >= START)]
    log(f"events: {len(E)} discrete quarters; universe events from 2021: {len(uni_ev)}; with E_mc pct {int(uni_ev['E_mc_pct'].notna().sum())}, "
        f"E_sue {int(uni_ev['E_sue_pct'].notna().sum())}, R {int(uni_ev['R_pct'].notna().sum())}")
    ev_year = uni_ev.groupby(uni_ev["entry"].dt.year).size().to_dict()

    # ---- primary arms ----
    res = {}
    for arm, (sig, thr, H, acc) in ARMS.items():
        S = select(E, sig + "_pct", thr, acc)
        net, exc = mk.trade(S["t"].to_numpy(), S["j"].to_numpy(), H)
        st = summarize(S, net, exc)
        trades = [{"code": codes[j], "j": int(j), "t_in": int(t), "t_out": int(t + H)} for t, j in zip(S["t"], S["j"])]
        nav = book(mk, trades, t0)
        st["book"] = bstats(nav)
        st["cand"] = bool(st["n"] >= 10 and st["mean_exc"] > 0 and st["t"] >= BAR["t"] and st["years_pos"] >= BAR["years_pos"]
                          and st["book"]["sharpe"] >= BAR["sharpe"] and st["book"]["mdd"] >= BAR["mdd"])
        st["a_only"] = bool(st["n"] >= 10 and st["mean_exc"] > 0 and st["t"] >= BAR["t"])
        st.update({"signal": sig, "thr": thr, "H": H, "accr": acc})
        res[arm] = st
        st["_nav"] = nav
        # all-universe reference for the same signal (all events, no bucket)
        log(f"{arm} {sig} top{int((1 - thr) * 100)}% H{H}{' +accr' if acc else ''}: n {st['n']} net {st['mean_net'] * 100:+.2f}% exc {st['mean_exc'] * 100:+.2f}% "
            f"t {st['t']:.2f} yrs+ {st['years_pos']}/6 | book CAGR {st['book']['cagr'] * 100:.1f}% Sh {st['book']['sharpe']:.2f} mDD {st['book']['mdd'] * 100:.0f}%")
    # all universe events (reference, not a trial)
    ref = {}
    for H in (20, 40, 60):
        net, exc = mk.trade(uni_ev["t"].to_numpy(), uni_ev["j"].to_numpy(), H)
        ref[H] = summarize(uni_ev, net, exc)
    # quintile spread diagnostic of E_mc at H40 (monotonicity; not a trial)
    qs = {}
    base = uni_ev[uni_ev["E_mc_pct"].notna()]
    net, exc = mk.trade(base["t"].to_numpy(), base["j"].to_numpy(), 40)
    b = base.assign(exc=exc, net=net, qn=np.minimum((base["E_mc_pct"] * 5).astype(int), 4))
    for qn, g in b.groupby("qn"):
        qs[int(qn) + 1] = {"n": int(g["exc"].notna().sum()), "exc": float(g["exc"].mean()), "net": float(g["net"].mean())}

    # ---- best arm + battery ----
    best = max(["T2", "T4", "T5", "T6"], key=lambda a: res[a]["t"] if np.isfinite(res[a]["t"]) else -99)
    sig, thr, H, acc = ARMS[best]
    B = res[best]
    S = select(E, sig + "_pct", thr, acc)
    battery = {}
    n_trials = 6
    for name, th in (("top_decile", 0.9), ("top_tercile", 2 / 3)):
        S2 = select(E, sig + "_pct", th, acc)
        n2, e2 = mk.trade(S2["t"].to_numpy(), S2["j"].to_numpy(), H)
        battery[name] = summarize(S2, n2, e2)
        n_trials += 1
    for H2 in (20, 60):
        if sig == "E_mc" and not acc:
            battery[f"H{H2}"] = {k: v for k, v in res["T1" if H2 == 20 else "T3"].items() if not k.startswith("_")}
        else:
            n2, e2 = mk.trade(S["t"].to_numpy(), S["j"].to_numpy(), H2)
            battery[f"H{H2}"] = summarize(S, n2, e2)
            n_trials += 1
    n_c, e_c = mk.trade(S["t"].to_numpy(), S["j"].to_numpy(), H, cost_mult=1.5)
    battery["cost1.5"] = summarize(S, n_c, e_c)
    n_d, e_d = mk.trade(S["t"].to_numpy(), S["j"].to_numpy(), H, delay=1)
    battery["delay1"] = summarize(S, n_d, e_d)
    # placebo: same names, random entry dates (universe-eligible), 200 draws
    rng = np.random.default_rng(SEED)
    F = mk.fwd(H)
    CT = mk.ctrl(H)
    T = len(dates)
    Tn = np.arange(T)
    nx = F - mk.c_in - np.vstack([mk.c_out[H:], np.full((H, len(codes)), np.nan)])
    qprev = np.vstack([np.full((1, len(codes)), -1), mk.q[:-1]])
    unip = np.vstack([np.zeros((1, len(codes)), bool), mk.uni[:-1]])
    ctrl_m = np.full(F.shape, np.nan)
    for qq in range(5):
        ctrl_m = np.where(qprev == qq, CT[:, [qq]], ctrl_m)
    NX = nx - ctrl_m
    valid = unip & np.isfinite(NX) & (Tn[:, None] >= t0)
    real = float(np.nanmean(NX[S["t"].to_numpy(), S["j"].to_numpy()]))
    pools = {j: np.flatnonzero(valid[:, j]) for j in set(S["j"])}
    draws = []
    for _ in range(N_PLACEBO):
        vals = [NX[rng.choice(pools[j]), j] for j in S["j"] if len(pools[j])]
        draws.append(float(np.mean(vals)))
    plc_pct = float((np.array(draws) < real).mean() * 100)
    battery["placebo"] = {"real_mean_exc": real, "median": float(np.median(draws)), "p95": float(np.percentile(draws, 95)), "pct": plc_pct}
    # next-open entry diagnostic, 2025-26 (opens stored)
    S25 = S[S["entry"] >= "2025-01-01"]
    tt, jj = S25["t"].to_numpy(), S25["j"].to_numpy()
    ok = (tt + H < T)
    o = mk.O[tt, jj]
    tk = tick(np.nan_to_num(o, nan=1.0))
    x = np.where(ok, tt + H, 0)
    n_open = mk.A[x, jj] / mk.A[tt, jj] * mk.C[tt, jj] / (o + tk) - 1 - FEE_BUY - mk.c_out[x, jj]
    n_close, _ = mk.trade(tt, jj, H)
    good = ok & np.isfinite(n_open) & (o > 0) & np.isfinite(n_close)
    battery["open_2025_26"] = {"n": int(good.sum()), "net_open_entry": float(np.mean(n_open[good])) if good.any() else None,
                               "net_close_entry": float(np.mean(n_close[good])) if good.any() else None}
    n_trials_cum = N_BEFORE + n_trials
    dsr = deflated_sharpe(B["_nav"].pct_change().dropna().to_numpy(), n_trials_cum)
    B["dsr"] = dsr

    # ---- verdict ----
    any_a = [a for a in ARMS if res[a]["a_only"]]
    if not any_a:
        verdict = "CLOSED"
    elif not B["cand"]:
        verdict = "FRAGILE" if B["a_only"] else ("FRAGILE" if any_a else "CLOSED")
    else:
        nb = sum(1 for k in ("top_decile", "top_tercile", "H20", "H60") if battery[k]["mean_exc"] > 0 and battery[k]["t"] >= BAR["nb_t"])
        fails = int(nb < 3) + int(battery["cost1.5"]["mean_exc"] <= 0) + int(not (battery["delay1"]["mean_exc"] > 0 and battery["delay1"]["t"] >= BAR["nb_t"]))
        if plc_pct < BAR["placebo_pct"] or fails >= 2:
            verdict = "FRAGILE"
        elif fails == 1:
            verdict = "PARTIAL"
        else:
            verdict = "ROBUST"
    verdict_full = f"{verdict} (PRELIM)"
    log(f"best arm {best}; placebo pct {plc_pct:.0f}; DSR {dsr:.2f} @ {n_trials_cum}; verdict {verdict_full}")

    # ---- combo effect / filter (only if a candidate exists) ----
    combo = None
    if B["cand"]:
        combo = combo_effect(d, S, H, codes)

    # ---- report ----
    pct = lambda v: "-" if v is None or not np.isfinite(v) else f"{v * 100:+.2f} %"  # noqa: E731
    L = [f"# IDX menu 38 (B3) - fundamental earnings surprise / post-earnings drift - {date.today()} - {n_trials} trials, cumulative N = {n_trials_cum} - PRELIM", "",
         f"Reported numbers from idx.fundamental (parsed by {CUTOFF:%Y-%m-%d %H:%M} UTC; drain still running), discrete quarters, signal day = published_at (WIB), "
         f"entry at the close of the first session after publication (closing offer), exit at the closing bid H sessions later, fees 0.10/0.20 %. "
         f"Universe: 60-day median value >= Rp 5 bn, close >= Rp 100. Excess = net minus the same-window gross return of the universe's same-market-cap quintile. "
         f"Entries 2021-01 -> {dates[-1].date()}. Not the price-reaction PEAD of IDX_SWING (0/22).", "",
         "## Coverage (parsed share of IDX quarterly/annual workbooks, by fiscal year and liquidity at publication)", "",
         "| fiscal year | <1bn | 1-5bn | 5-50bn | >=50bn |", "|---|---|---|---|---|"]
    cy = rep.groupby(["fiscal_year", "bucket"])["parsed"].agg(["sum", "count"])
    for fy in range(2019, 2027):
        cells = []
        for bk in ["<1bn", "1-5bn", "5-50bn", ">=50bn"]:
            if (fy, bk) in cy.index:
                s_, c_ = cy.loc[(fy, bk)]
                cells.append(f"{s_}/{c_} ({s_ / c_ * 100:.0f} %)")
            else:
                cells.append("-")
        L.append(f"| {fy} | " + " | ".join(cells) + " |")
    cp = rep[rep["bucket"].isin(["5-50bn", ">=50bn"])].groupby(["fiscal_year", "period"])["parsed"].mean().unstack()
    L += ["", "Liquid names (>= Rp 5 bn) parsed share by period: " + "; ".join(f"{fy}: " + ", ".join(f"{p} {v * 100:.0f} %" for p, v in r.dropna().items()) for fy, r in cp.iterrows()), "",
          f"Usable events (discrete quarter computable, published <= {MAX_LAG} d after period end, universe, entry >= 2021): {len(uni_ev)} - by entry year "
          + ", ".join(f"{y}: {n}" for y, n in ev_year.items()) + ". "
          "The 2021-23 liquid set is 75-87 % parsed and the discrete quarter needs the previous report of the year as well, so 2021-23 is thinner "
          "than 2024-26; the tilt is towards names the value/quality pipeline fetched first (larger, profitable). Hence PRELIM.", "",
          "## Pre-registered bar", "",
          f"CANDIDATE = (a) mean net excess > 0 with month-clustered t >= {BAR['t']}; (b) excess > 0 in >= {BAR['years_pos']}/6 entry years; "
          f"(c) standalone Rp 20 M book (5 % NAV/trade, 20 slots, lots of 100) Sharpe >= {BAR['sharpe']} and mDD >= {BAR['mdd'] * 100:.0f} %. "
          "ROBUST additionally needs placebo pct >= 95, >= 3/4 neighbours with t >= 2, costs x1.5 still positive, 1-day delay positive with t >= 2.", "",
          "## Results - primary arms", "",
          "| arm | signal | bucket | H | trades | net/trade | median net | hit | excess/trade | median exc | t (month) | years exc>0 | book CAGR | Sharpe | mDD | by year (excess) | pass |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for a, s in res.items():
        L.append(f"| {a} | {s['signal']}{' +accruals' if s['accr'] else ''} | top {int(round((1 - s['thr']) * 100))} % | {s['H']} | {s['n']} | {pct(s['mean_net'])} | {pct(s.get('median_net'))} | "
                 f"{s.get('hit', float('nan')) * 100:.0f} % | {pct(s['mean_exc'])} | {pct(s.get('median_exc'))} | {s['t']:.2f} | {s['years_pos']}/6 | {s['book']['cagr'] * 100:.1f} % | "
                 f"{s['book']['sharpe']:.2f} | {s['book']['mdd'] * 100:.0f} % | " + " ".join(f"{str(y)[2:]}:{v['exc'] * 100:+.1f}({v['n']})" for y, v in s["years"].items())
                 + f" | {'CANDIDATE' if s['cand'] else ('(a) only' if s['a_only'] else 'no')} |")
    L += ["", "Reference (not trials): every universe event, no signal: " + "; ".join(f"H{H_}: n {r['n']}, net {pct(r['mean_net'])}, excess {pct(r['mean_exc'])}, t {r['t']:.2f}" for H_, r in ref.items()), "",
          "E_mc quintiles at H = 40 (diagnostic, monotonicity): " + "; ".join(f"Q{k}: n {v['n']}, net {pct(v['net'])}, excess {pct(v['exc'])}" for k, v in qs.items()), "",
          f"## Battery on the best H = 40 arm ({best}: {sig}{' + accruals' if acc else ''})", "",
          "| check | trades | net/trade | excess/trade | t | years exc>0 |", "|---|---|---|---|---|---|"]
    for k in ("top_decile", "top_tercile", "H20", "H60", "cost1.5", "delay1"):
        s = battery[k]
        L.append(f"| {k} | {s['n']} | {pct(s['mean_net'])} | {pct(s['mean_exc'])} | {s['t']:.2f} | {s['years_pos']}/6 |")
    p = battery["placebo"]
    o = battery["open_2025_26"]
    L += ["", f"Placebo (same names, 200 random entry dates): real mean excess {pct(p['real_mean_exc'])}, placebo median {pct(p['median'])}, 95th {pct(p['p95'])}, "
          f"real at percentile {p['pct']:.0f}.", "",
          f"Next-open entry, 2025-26 events (opens stored): n {o['n']}, net/trade {pct(o['net_open_entry'])} at the open vs {pct(o['net_close_entry'])} at the close.", "",
          f"Standalone book of {best}: CAGR {B['book']['cagr'] * 100:.1f} %, Sharpe {B['book']['sharpe']:.2f}, mDD {B['book']['mdd'] * 100:.0f} %, "
          + " ".join(f"{y}: {v * 100:+.0f} %" for y, v in B["book"]["by_year"].items()) + f"; DSR {dsr:.2f} at N = {n_trials_cum}.", "",
          f"## Verdict: **{verdict_full}**", ""]
    if combo:
        L += ["## Combo effect", "", combo["text"], ""]
    text = "\n".join(L)
    out = os.path.join(HERE, "IDX_FUND_SURPRISE_2026-09-25.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    slim = {a: {k: v for k, v in s.items() if not k.startswith("_")} for a, s in res.items()}
    json.dump({"arms": slim, "battery": battery, "ref": ref, "quintiles": qs, "best": best, "verdict": verdict_full, "dsr": dsr, "combo": combo and {k: v for k, v in combo.items() if k != "text"}},
              open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    if os.environ.get("NO_STORE"):
        return 0
    from blackheart_ingest.idx import research_store as rs
    from blackheart_ingest.idx.ml import common
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date.today(),
                              params={"trials": list(ARMS) + ["top_decile", "top_tercile"] + ([] if n_trials == 8 else ["H20", "H60"]), "n_trials": n_trials,
                                      "n_trials_cumulative": n_trials_cum, "bar": BAR, "cutoff": CUTOFF.isoformat(), "universe": {"v60": LIQ, "min_px": MIN_PX}, "prelim": True},
                              summary=common.plain({"arms": slim, "battery": battery, "best": best, "verdict": verdict_full, "dsr": dsr, "events_by_year": ev_year,
                                                    "combo": combo and {k: v for k, v in combo.items() if k != "text"}}),
                              names=[], report_path=out, note="menu 38 / B3: fundamental SUE / revenue surprise / accruals PEAD, PRELIM (drain running)")
        conn.commit()
    log(f"study #{sid} stored")
    return 0


def combo_effect(d, S, H, codes_fs):
    """Only when a candidate exists: correlation with the three sleeves and the combined book with the new sleeve added."""
    import pickle
    os.environ.setdefault("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
    os.environ.setdefault("IDX_EXIT_CACHE", os.path.join(ROOT, "tmp", "exit_cache.pkl"))
    os.environ["INGEST_DB_DSN"] = d
    import idx_combo_rupiah as CR
    import idx_ml_strategy as M
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = CR.ml_trades(P, dates, codes, A, raw, offer, bid, liq)
    tr = CR.trend_trades(d, dates)
    gap = CR.gap_events(d, dates)
    pos = {dd: i for i, dd in enumerate(dates)}
    cset = set(codes)
    fs = []
    for e, c in zip(S["entry"], S["code"]):
        if e in pos and c in cset and pos[e] + H < len(dates):
            fs.append({"strat": "ML", "code": c, "t_in": pos[e], "t_out": pos[e] + H, "fs": True})
    out = {}
    navs = {}
    for name, (m_, t_, g_, use) in {"combined": (ml, tr, gap, {"gap", "trend", "ML"}), "combined+fund": (ml + fs, tr, gap, {"gap", "trend", "ML"}),
                                     "fund_only": (fs, [], [], {"ML"}), "gap_only": (ml, tr, gap, {"gap"}), "trend_only": (ml, tr, gap, {"trend"}), "ml_only": (ml, tr, gap, {"ML"})}.items():
        nav, _, _ = CR.engine(dates, codes, A, raw, offer, bid, m_, t_, g_, use)
        navs[name] = nav
        out[name] = CR.stats(nav)
    R = pd.DataFrame({k: v.pct_change() for k, v in navs.items()}).dropna()
    corr = {k: float(R["fund_only"].corr(R[k])) for k in ("gap_only", "trend_only", "ml_only")}
    # filter: ML / trend trades whose name had a top-bucket surprise entry in the previous 60 sessions
    flag = {}
    for e, c in zip(S["entry"], S["code"]):
        if e in pos:
            flag.setdefault(c, []).append(pos[e])
    fil = {}
    c_in, c_out = M.costs(raw, offer, bid)
    ix = {c: i for i, c in enumerate(codes)}
    for nm, lst in (("ML", ml), ("trend", tr)):
        w, wo = [], []
        for x in lst:
            j = ix[x["code"]]
            r = A[x["t_out"], j] / A[x["t_in"], j] - 1 - c_in[x["t_in"], j] - c_out[x["t_out"], j]
            if not np.isfinite(r):
                continue
            hit = any(0 <= x["t_in"] - t_ <= 60 for t_ in flag.get(x["code"], []))
            (w if hit else wo).append(r)
        fil[nm] = {"with": (len(w), float(np.mean(w)) if w else None), "without": (len(wo), float(np.mean(wo)) if wo else None)}
    text = ("| book | CAGR | Sharpe | mDD |\n|---|---|---|---|\n" + "\n".join(f"| {k} | {v['cagr'] * 100:.1f} % | {v['sharpe']:.2f} | {v['mdd'] * 100:.0f} % |" for k, v in out.items())
            + "\n\nDaily-return correlation of the fund sleeve with: " + ", ".join(f"{k} {v:+.2f}" for k, v in corr.items())
            + "\n\nAs a filter (trade net return with / without a top-bucket surprise in the prior 60 sessions): "
            + "; ".join(f"{k}: with n {v['with'][0]} {v['with'][1] if v['with'][1] is None else round(v['with'][1] * 100, 2)} %, without n {v['without'][0]} {round(v['without'][1] * 100, 2) if v['without'][1] is not None else None} %" for k, v in fil.items()))
    return {"books": out, "corr": corr, "filter": fil, "text": text}


if __name__ == "__main__":
    sys.exit(main())
