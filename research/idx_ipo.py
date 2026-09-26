#!/usr/bin/env python3
"""IDX menu 46 - IPO patterns on IDX (never studied as a family), 2026-09-26.

Universe: every idx.listing row with listing_date >= 2020-01-01 (317 listings; none delisted; all have bars from the listing day).
IPO price = daily_summary.previous on the listing day (IDX sets it to the offering price). The desk can NOT buy at the IPO price at
size (e-IPO pooled allocation is rationed) -> every entry below is a SECONDARY-market buy at the closing offer of a session AFTER
the signal is public; exits at the closing bid; Stockbit fees 0.15 % buy / 0.25 % sell; spread from the day's closing book (tick
fallback). Board on the day from daily_summary.remarks (5th char; old 2020 notation = last char); entry board must be 1 Utama /
2 Pengembangan / 3 Akselerasi on the signal day (Akselerasi kept - its 10 % limits and thin books are in the prices; a neighbour
drops it). Entry session must be BUYABLE (volume > 0 and a closing offer > 0, i.e. not locked at ARA); otherwise the entry slides
to the next buyable session within 5. An exit day without trading slides to the next traded day (suspensions stay in).

Lock-up rule (verified 2026-09-26, sources in the report): POJK 25/POJK.04/2017 art. 2 - any party that acquired shares BELOW the
IPO price within 6 months before filing the registration statement may not transfer them until 8 MONTHS AFTER THE REGISTRATION
STATEMENT BECOMES EFFECTIVE (effective date, not listing date; government holders exempt). Controllers typically commit to 12
months from the effective date (prospectus / IDX I-A). Effective -> listing is 8-10 calendar days in 2025 prospectuses (e-IPO:
DGNS 30-06 -> 10-07, COIN 30-06 -> 09-07, EMAS 15-09 -> 23-09), so LE = listing_date + 8 months - 9 calendar days.

PRE-REGISTERED (10 counted trials, cumulative 982 -> 992, ids 983..992). Liquidity floor Rp 2 bn = median daily value over the last
60 sessions (min 20 sessions since listing) on the signal day. s = sessions since listing (listing day s = 0).
  983 I1a  slide+stabilise: first session t (20 <= s <= 500) with A_t <= 0.50 x post-listing peak close AND the 20-session low
           was set >= 10 sessions before t AND A_t >= 1.05 x that low (+ floor, board) -> buy close t+1, hold 60 sessions.
  984 I1b  same with the drop >= 35 %.
  985 I2a  lock-up expiry: buy at the close of the first session after LE, hold 20.
  986 I2b  after the dip: buy at the close 10 sessions after the first session after LE, hold 40.
  987 I2c  AVOID filter: hold from 21 sessions before LE to the first session >= LE (20 sessions). Avoiding it is worth it only if
           gross excess + one round trip of costs < 0 (a holder pays a round trip to step aside); judged on that number.
  988 I3a  quality: first idx.fundamental report published after listing (entry = 2nd session after its publication date and
           s >= 21, within 250 sessions of listing); net_profit > 0 AND cfo > 0 -> buy, hold 120.
  989 I3b  same, hold 250.
  990 I3c  every IPO bought at s = 21 (after the first month), hold 120 (the unconditional reference - also a candidate).
  991 I4a  first-month momentum: close at s = 20 >= 1.5 x IPO price -> buy at s = 21 (first buyable within 10), hold 60.
  992 I4b  first-month reversal: close at s = 20 <= IPO price (broke issue) -> same entry, hold 60.
Excess = event NET return - mean GROSS buy-and-hold return of 5 matched seasoned names over the same closes (listed >= 3 years
before the signal, board 1/2 that day, v60 >= Rp 0.5 bn; nearest on z(log market cap), z(log v60) inside the same sector - old
JASICA digits mapped to IDX-IC letters - falling back to all sectors when < 5). The benchmark pays no costs, so a pass must beat a
passive holder after the desk's own round trip.
Battery: t clustered by listing month (also entry month), listing-year cohorts, placebo A = same names at random eligible dates
(500 draws), placebo B = random liquid seasoned names on the same dates vs their own matches (500 draws), neighbours (not counted:
listed per arm), costs x1.5, DSR on per-event excess at N = 992.
READING RULE: an arm PASSES if mean net excess > 0 with clustered t >= 2.5, positive in >= 60 % of listing-year cohorts (n >= 3),
placebo A and B >= 95th pct. A passing arm is then tested as a 4th sleeve on the corrected combo (NAV rebuilt as
idx_fe_drawdown.py does): Sharpe up without deeper mDD, correlation with the combo < 0.5. I2c passes as an AVOID filter if the
avoid number < 0 with t <= -2.5, <= 40 % of cohorts positive and placebo <= 5th pct.
READ-ONLY; one idx.study row ('ipo_patterns') only with --record. Env INGEST_DB_DSN (blackheart-ingest/idx-local.env).
"""
from __future__ import annotations

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
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))

N_BEFORE, N_TRIALS = 982, 10
STUDY = "ipo_patterns"
FB, FS = 0.0015, 0.0025
FLOOR = 2e9
CACHE = os.path.join(ROOT, "tmp", "ipo_panel.pkl")
OUT = os.path.join(HERE, "IDX_IPO_2026-09-26.md")
SECMAP = {"1": "D", "2": "A", "3": "B", "4": "C", "5": "D", "6": "H", "7": "J", "8": "G", "9": "E"}
RNG = np.random.default_rng(46)
NDRAW = 500


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    return env["INGEST_DB_DSN"].strip().strip('"')


def tick(px):
    return np.where(px < 200, 1.0, np.where(px < 500, 2.0, np.where(px < 2000, 5.0, np.where(px < 5000, 10.0, 25.0))))


# ------------------------------------------------------------------ data
def load():
    if os.path.exists(CACHE):
        return pickle.load(open(CACHE, "rb"))
    with psycopg.connect(dsn()) as c:
        L = pd.read_sql("SELECT code, listing_date, sector FROM idx.listing", c)
        B = pd.read_sql("""SELECT b.code, b.trade_date, b.close, b.adj_factor, b.value, b.volume, s.bid, s.offer, s.offer_volume,
                                  s.remarks, s.listed_shares, s.previous
                           FROM idx.bar b LEFT JOIN idx.daily_summary s USING (code, trade_date)
                           WHERE b.trade_date >= '2019-10-01'""", c)
        F = pd.read_sql("""SELECT code, published_at, net_profit, cfo FROM idx.fundamental""", c)
    B = B[B.code.isin(set(L.code))]
    B["trade_date"] = pd.to_datetime(B["trade_date"])
    for k in ("close", "adj_factor", "value", "volume", "bid", "offer", "offer_volume", "listed_shares", "previous"):
        B[k] = pd.to_numeric(B[k], errors="coerce")
    rm = B["remarks"].fillna("")
    d5, old = rm.str[4], rm.str[-1]
    B["board"] = np.where(d5.isin(list("12345")), d5, np.where((rm.str.len() == 8) & old.isin(list("123")), old, None))
    B["board"] = pd.to_numeric(B["board"], errors="coerce")
    B["A"] = B["close"] * B["adj_factor"].fillna(1.0)
    W = {k: B.pivot(index="trade_date", columns="code", values=k) for k in
         ("close", "A", "value", "volume", "bid", "offer", "offer_volume", "board", "listed_shares", "previous")}
    dates = W["close"].index
    codes = W["close"].columns
    W = {k: v.reindex(index=dates, columns=codes) for k, v in W.items()}
    W["board"] = W["board"].ffill()
    W["listed_shares"] = W["listed_shares"].ffill()
    W["value"] = W["value"].fillna(0.0)
    v60 = W["value"].where(W["close"].notna()).rolling(60, min_periods=20).median()
    D = {k: W[k].to_numpy(float) for k in W}
    D["v60"] = v60.to_numpy(float)
    D["dates"], D["codes"] = dates, list(codes)
    D["listing"] = L
    D["fund"] = F
    pickle.dump(D, open(CACHE, "wb"))
    return D


# ------------------------------------------------------------------ engine
class Ctx:
    def __init__(self, D):
        self.D = D
        self.dates = D["dates"]
        self.codes = D["codes"]
        self.j = {c: i for i, c in enumerate(self.codes)}
        self.T, self.N = D["close"].shape
        L = D["listing"].set_index("code")
        ld = pd.to_datetime(L["listing_date"]).reindex(self.codes)
        self.ldate = ld.to_numpy("datetime64[ns]")
        sec = L["sector"].reindex(self.codes).fillna("?").str[0].map(lambda s: SECMAP.get(s, s))
        self.sec = sec.to_numpy()
        close, A = D["close"], D["A"]
        self.close, self.A = close, A
        tk = tick(np.nan_to_num(close, nan=1.0))
        off, bid = D["offer"], D["bid"]
        self.cin = np.where((off > 0) & (off >= close), off / close - 1, tk / close) + FB
        self.cout = np.where((bid > 0) & (bid <= close), 1 - bid / close, tk / close) + FS
        self.traded = (D["volume"] > 0) & np.isfinite(close)
        self.buyable = self.traded & (np.nan_to_num(off) > 0) & (np.nan_to_num(D["offer_volume"]) > 0)
        self.board = D["board"]
        self.v60 = D["v60"]
        mcap = close * D["listed_shares"]
        with np.errstate(divide="ignore", invalid="ignore"):
            self.logm = np.log(np.where(mcap > 0, mcap, np.nan))
            self.logv = np.log(np.where(self.v60 > 0, self.v60, np.nan))
        dts = self.dates.to_numpy("datetime64[ns]")
        seasoned_cut = dts - np.timedelta64(3 * 365, "D")
        self.seasoned = (self.ldate[None, :] <= seasoned_cut[:, None]) & ~np.isnat(self.ldate)[None, :]
        self.ctrl_ok = self.seasoned & np.isin(np.nan_to_num(self.board), [1, 2]) & (np.nan_to_num(self.v60) >= 5e8) & np.isfinite(A)
        # IPOs
        L2 = D["listing"]
        L2 = L2[pd.to_datetime(L2["listing_date"]) >= "2020-01-01"]
        self.ipos = []
        for r in L2.itertuples():
            j = self.j.get(r.code)
            if j is None:
                continue
            col = np.where(np.isfinite(close[:, j]))[0]
            if not len(col):
                continue
            t0 = int(col[0])
            p0 = D["previous"][t0, j]
            self.ipos.append({"code": r.code, "j": j, "t0": t0, "ldate": pd.Timestamp(r.listing_date), "p0": p0})

    def entry_from(self, t, j, slide=5):
        for k in range(t, min(t + slide + 1, self.T)):
            if self.buyable[k, j]:
                return k
        return None

    def exit_at(self, t, j):
        for k in range(t, self.T):
            if self.traded[k, j]:
                return k, True
        k = int(np.where(np.isfinite(self.A[:, j]))[0][-1])
        return k, False

    def eligible_signal(self, t, j, floor=FLOOR, boards=(1, 2, 3)):
        b = self.board[t, j]
        return np.isfinite(b) and int(b) in boards and np.nan_to_num(self.v60[t, j]) >= floor

    def controls(self, ts, te, tx, j, k=5):
        ok = self.ctrl_ok[ts] & np.isfinite(self.A[te]) & np.isfinite(self.A[tx]) & np.isfinite(self.logm[ts]) & np.isfinite(self.logv[ts])
        ok[j] = False
        idx = np.where(ok)[0]
        if len(idx) < k:
            return np.nan
        lm, lv = self.logm[ts, idx], self.logv[ts, idx]
        sm, sv = lm.std() or 1.0, lv.std() or 1.0
        x_m, x_v = self.logm[ts, j], self.logv[ts, j]
        if not np.isfinite(x_m):
            x_m = np.nanmedian(lm)
        if not np.isfinite(x_v):
            x_v = np.nanmedian(lv)
        d = ((lm - x_m) / sm) ** 2 + ((lv - x_v) / sv) ** 2
        same = self.sec[idx] == self.sec[j]
        pool = np.where(same)[0] if same.sum() >= k else np.arange(len(idx))
        pick = idx[pool[np.argsort(d[pool])[:k]]]
        return float(np.mean(self.A[tx, pick] / self.A[te, pick] - 1))

    def trade(self, ts, te, H, j, cost_mult=1.0):
        """-> dict(te, tx, gross, net, cost, bench) or None. te already a buyable session."""
        tx_nom = te + H
        if tx_nom >= self.T:
            return None
        tx, traded = self.exit_at(tx_nom, j)
        if tx <= te:
            return None
        g = self.A[tx, j] / self.A[te, j] - 1
        ci, co = self.cin[te, j], (self.cout[tx, j] if traded else 1.0 - 1.0 / 1.0 + FS)
        net = (1 + g) * (1 - cost_mult * co) / (1 + cost_mult * ci) - 1
        bench = self.controls(ts, te, tx, j)
        return {"te": te, "tx": tx, "gross": g, "net": net, "cost": ci + co, "bench": bench, "stale_exit": not traded,
                "net15": (1 + g) * (1 - 1.5 * co) / (1 + 1.5 * ci) - 1}


# ------------------------------------------------------------------ arm definitions: -> list of (ipo, ts, te)
def ev_slide(C, X, H, floor=FLOOR, boards=(1, 2, 3)):
    out = []
    for ip in C.ipos:
        j, t0 = ip["j"], ip["t0"]
        a = C.A[:, j]
        for t in range(t0 + 20, min(t0 + 501, C.T - 1)):
            if not np.isfinite(a[t]):
                continue
            peak = np.nanmax(a[t0:t + 1])
            if a[t] > (1 - X) * peak:
                continue
            w = a[t - 19:t + 1]
            if np.isnan(w).all():
                continue
            lo_i = int(np.nanargmin(w))
            if lo_i > 9 or a[t] < 1.05 * w[lo_i]:
                continue
            if not C.eligible_signal(t, j, floor, boards):
                continue
            te = C.entry_from(t + 1, j)
            if te is not None:
                out.append((ip, t, te))
            break
    return out


def lockup_session(C, ip, months=8, back_days=9):
    le = ip["ldate"] + pd.DateOffset(months=months) - pd.Timedelta(days=back_days)
    k = int(np.searchsorted(C.dates.values, np.datetime64(le)))
    return k, le


def ev_lock(C, mode, H, months=8, back_days=9, floor=FLOOR, boards=(1, 2, 3)):
    out = []
    for ip in C.ipos:
        j = ip["j"]
        k, le = lockup_session(C, ip, months, back_days)      # first session >= LE
        if k >= C.T:
            continue
        if mode == "after":
            first_after = k if C.dates[k] > le else k + 1
            ts, t_e = first_after - 1, first_after
        elif mode == "dip":
            first_after = k if C.dates[k] > le else k + 1
            ts, t_e = first_after + 9, first_after + 10
        else:                                                  # into: hold from k-21 to k
            ts, t_e = k - 22, k - 21
        if t_e >= C.T or ts < ip["t0"] or not C.eligible_signal(ts, j, floor, boards):
            continue
        te = C.entry_from(t_e, j)
        if te is not None:
            out.append((ip, ts, te))
    return out


def ev_quality(C, H, need_quality=True, profit_only=False, floor=FLOOR, boards=(1, 2, 3)):
    F = C.D["fund"].copy()
    F["pub"] = pd.to_datetime(F["published_at"], utc=True).dt.tz_convert("Asia/Jakarta").dt.tz_localize(None).dt.normalize()
    out = []
    for ip in C.ipos:
        j, t0 = ip["j"], ip["t0"]
        f = F[(F.code == ip["code"]) & (F.pub >= ip["ldate"])].sort_values("pub")
        if not len(f):
            continue
        r = f.iloc[0]
        q = (r.net_profit is not None and r.net_profit > 0) and (profit_only or (pd.notna(r.cfo) and r.cfo > 0))
        if need_quality and not q:
            continue
        kp = int(np.searchsorted(C.dates.values, np.datetime64(r.pub), side="right"))   # first session after publication
        ts = max(kp, t0 + 20)
        if ts - t0 > 250 or ts + 1 >= C.T or not C.eligible_signal(ts, j, floor, boards):
            continue
        te = C.entry_from(ts + 1, j)
        if te is not None:
            out.append((ip, ts, te))
    return out


def ev_all(C, H, s=20, floor=FLOOR, boards=(1, 2, 3)):
    out = []
    for ip in C.ipos:
        j, ts = ip["j"], ip["t0"] + s
        if ts + 1 >= C.T or not C.eligible_signal(ts, j, floor, boards):
            continue
        te = C.entry_from(ts + 1, j)
        if te is not None:
            out.append((ip, ts, te))
    return out


def ev_first_month(C, H, lo=None, hi=None, floor=FLOOR, boards=(1, 2, 3)):
    out = []
    for ip in C.ipos:
        j, ts = ip["j"], ip["t0"] + 20
        if ts + 1 >= C.T or not (ip["p0"] > 0) or not np.isfinite(C.close[ts, j]):
            continue
        r20 = C.close[ts, j] / ip["p0"] - 1
        if (lo is not None and r20 < lo) or (hi is not None and r20 > hi):
            continue
        if not C.eligible_signal(ts, j, floor, boards):
            continue
        te = C.entry_from(ts + 1, j, slide=10)
        if te is not None:
            out.append((ip, ts, te))
    return out


# ------------------------------------------------------------------ stats
def run(C, events, H):
    rows = []
    for ip, ts, te in events:
        x = C.trade(ts, te, H, ip["j"])
        if x is None or not np.isfinite(x["bench"]):
            continue
        x.update(code=ip["code"], ts=ts, lmonth=ip["ldate"].strftime("%Y-%m"), lyear=ip["ldate"].year,
                 emonth=C.dates[te].strftime("%Y-%m"), board=C.board[ts, ip["j"]], edate=C.dates[te].date())
        rows.append(x)
    E = pd.DataFrame(rows)
    if len(E):
        E["excess"] = E["net"] - E["bench"]
        E["excess15"] = E["net15"] - E["bench"]
        E["avoid"] = (E["gross"] - E["bench"]) + E["cost"]
    return E


def ctstat(x, g):
    x, g = np.asarray(x, float), np.asarray(g)
    n = len(x)
    if n < 3:
        return float("nan")
    m = x.mean()
    u = pd.Series(x - m).groupby(g).sum().to_numpy()
    G = len(u)
    if G < 2:
        return float("nan")
    se = math.sqrt((u ** 2).sum() * G / (G - 1)) / n
    return m / se if se > 0 else float("nan")


def dsr(r, n_trials):
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 3 or r.std() == 0:
        return 0.0
    mu, sd = r.mean(), r.std()
    sr = mu / sd
    sk = ((r - mu) ** 3).mean() / sd ** 3
    ku = ((r - mu) ** 4).mean() / sd ** 4
    Z, e = NormalDist(), 0.5772156649015329
    v = (1 - sk * sr + (ku - 1) / 4.0 * sr ** 2) / (n - 1)
    if v <= 0:
        return 0.0
    se = math.sqrt(v)
    emax = Z.inv_cdf(1 - 1.0 / n_trials) * (1 - e) + Z.inv_cdf(1 - 1.0 / (n_trials * math.e)) * e
    return Z.cdf((sr - se * emax) / se)


def summarize(E, col="excess"):
    if not len(E):
        return {"n": 0}
    x = E[col]
    yrs = E.groupby("lyear")[col].agg(["mean", "count"])
    yrs3 = yrs[yrs["count"] >= 3]
    return {"n": len(E), "names": E.code.nunique(), "lmonths": E.lmonth.nunique(), "net": E.net.mean(), "bench": E.bench.mean(),
            "excess": x.mean(), "med": x.median(), "win": (x > 0).mean(), "t_lm": ctstat(x, E.lmonth), "t_em": ctstat(x, E.emonth),
            "coh_pos": int((yrs3["mean"] > 0).sum()), "coh_n": len(yrs3), "coh_neg": int((yrs3["mean"] < 0).sum()),
            "by_year": {int(y): (float(r["mean"]), int(r["count"])) for y, r in yrs.iterrows()},
            "ex15": E.excess15.mean(), "cost": E.cost.mean(), "aks": float((E.board == 3).mean()), "stale": int(E.stale_exit.sum()),
            "dsr": dsr(x.to_numpy(), N_BEFORE + N_TRIALS)}


def placebo_dates(C, E, H, floor=FLOOR, col="excess"):
    """Same names, random eligible signal sessions (s >= 20), same H."""
    pools = {}
    for code in E.code.unique():
        j = C.j[code]
        ip = next(i for i in C.ipos if i["code"] == code)
        ts_ok = [t for t in range(ip["t0"] + 20, C.T - H - 2) if C.eligible_signal(t, j, floor) and C.buyable[t + 1, j]]
        pools[code] = ts_ok
    means = []
    for _ in range(NDRAW):
        v = []
        for r in E.itertuples():
            p = pools[r.code]
            if not p:
                continue
            ts = p[RNG.integers(len(p))]
            x = C.trade(ts, ts + 1, H, C.j[r.code])
            if x is None or not np.isfinite(x["bench"]):
                continue
            v.append(x["net"] - x["bench"] if col == "excess" else x["gross"] - x["bench"] + x["cost"])
        means.append(np.mean(v))
    return np.array(means)


def placebo_names(C, E, H, col="excess"):
    """Random liquid (v60 >= floor) seasoned board-1/2 names on the same signal/entry sessions, vs their own matches."""
    means = []
    for _ in range(NDRAW):
        v = []
        for r in E.itertuples():
            ts, te = int(r.ts), int(r.te)
            ok = np.where(C.ctrl_ok[ts] & (np.nan_to_num(C.v60[ts]) >= FLOOR) & C.buyable[te])[0]
            if not len(ok):
                continue
            j = int(ok[RNG.integers(len(ok))])
            x = C.trade(ts, te, H, j)
            if x is None or not np.isfinite(x["bench"]):
                continue
            v.append(x["net"] - x["bench"] if col == "excess" else x["gross"] - x["bench"] + x["cost"])
        means.append(np.mean(v))
    return np.array(means)


ARMS = {
    983: ("I1a slide>=50 % + stabilise, H60", lambda C, **k: ev_slide(C, 0.50, 60, **k), 60),
    984: ("I1b slide>=35 % + stabilise, H60", lambda C, **k: ev_slide(C, 0.35, 60, **k), 60),
    985: ("I2a buy after lock-up end, H20", lambda C, **k: ev_lock(C, "after", 20, **k), 20),
    986: ("I2b buy 10 sessions after lock-up end, H40", lambda C, **k: ev_lock(C, "dip", 40, **k), 40),
    987: ("I2c AVOID: hold into lock-up end (20 sessions)", lambda C, **k: ev_lock(C, "into", 20, **k), 20),
    988: ("I3a quality (NP>0 & CFO>0), H120", lambda C, **k: ev_quality(C, 120, **k), 120),
    989: ("I3b quality (NP>0 & CFO>0), H250", lambda C, **k: ev_quality(C, 250, **k), 250),
    990: ("I3c every IPO at s=21, H120", lambda C, **k: ev_all(C, 120, **k), 120),
    991: ("I4a first-month momentum (>= +50 % vs IPO px), H60", lambda C, **k: ev_first_month(C, 60, lo=0.5, **k), 60),
    992: ("I4b first-month broke issue (<= IPO px), H60", lambda C, **k: ev_first_month(C, 60, hi=0.0, **k), 60),
}

# neighbours (battery, not counted): (label, events fn, H)
NEIGH = {
    983: [("drop 40 %", lambda C: ev_slide(C, 0.40, 60), 60), ("drop 60 %", lambda C: ev_slide(C, 0.60, 60), 60),
          ("H40", lambda C: ev_slide(C, 0.50, 40), 40), ("H120", lambda C: ev_slide(C, 0.50, 120), 120),
          ("floor 5 bn", lambda C: ev_slide(C, 0.50, 60, floor=5e9), 60), ("no Akselerasi", lambda C: ev_slide(C, 0.50, 60, boards=(1, 2)), 60)],
    984: [("drop 30 %", lambda C: ev_slide(C, 0.30, 60), 60), ("H120", lambda C: ev_slide(C, 0.35, 120), 120),
          ("floor 5 bn", lambda C: ev_slide(C, 0.35, 60, floor=5e9), 60), ("no Akselerasi", lambda C: ev_slide(C, 0.35, 60, boards=(1, 2)), 60)],
    985: [("LE = listing+8m", lambda C: ev_lock(C, "after", 20, back_days=0), 20), ("LE -21d", lambda C: ev_lock(C, "after", 20, back_days=21), 20),
          ("H10", lambda C: ev_lock(C, "after", 10), 10), ("H40", lambda C: ev_lock(C, "after", 40), 40),
          ("controller 12m", lambda C: ev_lock(C, "after", 20, months=12), 20)],
    986: [("LE = listing+8m", lambda C: ev_lock(C, "dip", 40, back_days=0), 40), ("H20", lambda C: ev_lock(C, "dip", 20), 20),
          ("controller 12m", lambda C: ev_lock(C, "dip", 40, months=12), 40), ("floor 5 bn", lambda C: ev_lock(C, "dip", 40, floor=5e9), 40)],
    987: [("LE = listing+8m", lambda C: ev_lock(C, "into", 20, back_days=0), 20), ("LE -21d", lambda C: ev_lock(C, "into", 20, back_days=21), 20),
          ("controller 12m", lambda C: ev_lock(C, "into", 20, months=12), 20), ("floor 0.5 bn", lambda C: ev_lock(C, "into", 20, floor=5e8), 20)],
    988: [("profit only", lambda C: ev_quality(C, 120, profit_only=True), 120), ("H60", lambda C: ev_quality(C, 60), 60),
          ("floor 5 bn", lambda C: ev_quality(C, 120, floor=5e9), 120), ("no Akselerasi", lambda C: ev_quality(C, 120, boards=(1, 2)), 120)],
    989: [("profit only", lambda C: ev_quality(C, 250, profit_only=True), 250), ("floor 5 bn", lambda C: ev_quality(C, 250, floor=5e9), 250)],
    990: [("s=40", lambda C: ev_all(C, 120, s=40), 120), ("H60", lambda C: ev_all(C, 60), 60), ("H250", lambda C: ev_all(C, 250), 250),
          ("floor 5 bn", lambda C: ev_all(C, 120, floor=5e9), 120)],
    991: [(">= +30 %", lambda C: ev_first_month(C, 60, lo=0.3), 60), (">= +100 %", lambda C: ev_first_month(C, 60, lo=1.0), 60),
          ("H20", lambda C: ev_first_month(C, 20, lo=0.5), 20), ("H120", lambda C: ev_first_month(C, 120, lo=0.5), 120)],
    992: [("<= -10 %", lambda C: ev_first_month(C, 60, hi=-0.1), 60), ("<= +10 %", lambda C: ev_first_month(C, 60, hi=0.1), 60),
          ("H20", lambda C: ev_first_month(C, 20, hi=0.0), 20), ("H120", lambda C: ev_first_month(C, 120, hi=0.0), 120)],
}


def main() -> int:
    record = "--record" in sys.argv
    if "--record-only" in sys.argv:          # store the study row from the last run's results (tmp/ipo_results.pkl), no recompute
        R = pickle.load(open(os.path.join(ROOT, "tmp", "ipo_results.pkl"), "rb"))
        rec(R["res"], verdict_all(R["res"]), R["ipo_years"])
        return 0
    D = load()
    C = Ctx(D)
    print(f"panel {C.T} days x {C.N} codes; IPOs {len(C.ipos)}", flush=True)
    res = {}
    for tid, (label, fn, H) in ARMS.items():
        E = run(C, fn(C), H)
        col = "avoid" if tid == 987 else "excess"
        s = summarize(E, col)
        if tid == 987:
            s["gross_ex"] = float((E["gross"] - E["bench"]).mean())
        res[tid] = {"label": label, "H": H, "E": E, "s": s, "col": col}
        print(tid, label, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items() if k != "by_year"}, flush=True)
    # neighbours
    for tid, lst in NEIGH.items():
        col = res[tid]["col"]
        res[tid]["neigh"] = []
        for lab, fn, H in lst:
            s = summarize(run(C, fn(C), H), col)
            res[tid]["neigh"].append((lab, s))
            print("   nb", tid, lab, s.get("n"), round(s.get("excess", np.nan), 4), round(s.get("t_lm", np.nan), 2), flush=True)
    # placebos
    for tid, r in res.items():
        E, H, col = r["E"], r["H"], r["col"]
        if len(E) < 5:
            continue
        pa = placebo_dates(C, E, H, col=col)
        pb = placebo_names(C, E, H, col=col)
        real = E[col].mean()
        r["pA"] = (float((pa < real).mean() * 100), float(np.median(pa)), float(np.percentile(pa, 95)), float(np.percentile(pa, 5)))
        r["pB"] = (float((pb < real).mean() * 100), float(np.median(pb)), float(np.percentile(pb, 95)), float(np.percentile(pb, 5)))
        print("   placebo", tid, r["pA"], r["pB"], flush=True)
    # cohort counts
    ipo_years = pd.Series([ip["ldate"].year for ip in C.ipos]).value_counts().sort_index()
    liq = {}
    for ip in C.ipos:
        t = min(ip["t0"] + 60, C.T - 1)
        liq.setdefault(ip["ldate"].year, []).append(np.nan_to_num(C.v60[t, ip["j"]]) >= FLOOR)
    brd = {}
    for ip in C.ipos:
        brd.setdefault(int(np.nan_to_num(C.board[ip["t0"], ip["j"]])), 0)
        brd[int(np.nan_to_num(C.board[ip["t0"], ip["j"]]))] += 1
    first_day = [C.close[ip["t0"], ip["j"]] / ip["p0"] - 1 for ip in C.ipos if ip["p0"] > 0]
    pickle.dump({"res": {k: {kk: vv for kk, vv in v.items()} for k, v in res.items()}, "ipo_years": ipo_years, "liq": liq, "brd": brd,
                 "first_day": first_day}, open(os.path.join(ROOT, "tmp", "ipo_results.pkl"), "wb"))
    verdicts = verdict_all(res)
    for tid, v in verdicts.items():
        print(tid, v)
    if record:
        rec(res, verdicts, ipo_years)
    return 0


def verdict_all(res):
    out = {}
    for tid, r in res.items():
        s = r["s"]
        if s.get("n", 0) < 5 or "pA" not in r:
            out[tid] = "FAIL (n < 5)"
            continue
        if tid == 987:
            ok = s["excess"] < 0 and s["t_lm"] <= -2.5 and s["coh_pos"] <= 0.4 * s["coh_n"] and r["pA"][0] <= 5 and r["pB"][0] <= 5
        else:
            ok = s["excess"] > 0 and s["t_lm"] >= 2.5 and s["coh_pos"] >= 0.6 * s["coh_n"] and r["pA"][0] >= 95 and r["pB"][0] >= 95
        fails = []
        sign = -1 if tid == 987 else 1
        if not sign * s["excess"] > 0:
            fails.append("sign")
        if not sign * s["t_lm"] >= 2.5:
            fails.append(f"t {s['t_lm']:.2f}")
        if tid == 987:
            if s["coh_pos"] > 0.4 * s["coh_n"]:
                fails.append(f"cohorts {s['coh_neg']}/{s['coh_n']} neg")
            if r["pA"][0] > 5:
                fails.append(f"placeboA pct {r['pA'][0]:.0f}")
            if r["pB"][0] > 5:
                fails.append(f"placeboB pct {r['pB'][0]:.0f}")
        else:
            if s["coh_pos"] < 0.6 * s["coh_n"]:
                fails.append(f"cohorts {s['coh_pos']}/{s['coh_n']}")
            if r["pA"][0] < 95:
                fails.append(f"placeboA pct {r['pA'][0]:.0f}")
            if r["pB"][0] < 95:
                fails.append(f"placeboB pct {r['pB'][0]:.0f}")
        out[tid] = ("PASS" if ok else "FAIL") + ("" if ok else " (" + ", ".join(fails) + ")")
    return out


def rec(res, verdicts, ipo_years):
    from blackheart_ingest.idx import research_store as rs
    summary = {tid: {"label": r["label"], "verdict": verdicts[tid], **{k: v for k, v in r["s"].items() if k != "by_year"},
                     "by_year": r["s"].get("by_year"), "placeboA": r.get("pA"), "placeboB": r.get("pB")} for tid, r in res.items()}
    with psycopg.connect(dsn()) as conn:
        sid = rs.record_study(conn, STUDY, date(2026, 9, 26), params={"trials": list(ARMS), "n_trials_cumulative": N_BEFORE + N_TRIALS,
                              "floor_rp": FLOOR, "fees": [FB, FS], "lockup": "POJK 25/POJK.04/2017 art.2: 8 months after effective; LE = listing + 8m - 9d",
                              "ipo_years": {int(k): int(v) for k, v in ipo_years.items()}}, summary=summary, names=[], report_path=OUT,
                              note="menu 46: IPO patterns (slide+stabilise, lock-up expiry/avoid, quality, first-month mom/reversal)")
    print(f"study #{sid} stored")


if __name__ == "__main__":
    raise SystemExit(main())
