#!/usr/bin/env python3
"""IDX menu DT-2 - day-trading rules from the published literature, tested on IDX intraday bars (operator 2026-09-27:
"cari di internet cara day trade / scalping, dapatkan ilmunya, implement di data day trading kita").

WHY A NEW STUDY. Menu 29 (#?, IDX_DAYTRADE_2026-09-22) tested open->close rules on DAILY bars only; menus 28-33 used the tick
feed, which holds 4 sessions. Neither could test the rules the literature actually proposes, which need the minute path
(opening range, VWAP, noise band, last half-hour). New data: Yahoo .JK intraday history, verified 2026-09-27 against the desk's
own tick feed (research-scratch/idx/daytrade2/validate.py): 5-minute closes identical on 99.2 % of 30,148 overlapping bars
(highs/lows 98.9 %, opens 98.1 %, all within 1 %); the 16:00 bar = the closing auction (= daily_summary.close on 99.8 %);
1-hour bars equal the 5-minute aggregate on 100 % of 73,300 bars. Samples: A = 5-minute, 58 sessions 2026-07-06 .. 09-25;
B = 1-hour, 716 sessions 2023-09-13 .. 2026-09-25. Universe = the tick collector's subscription list (~190 liquid names).

LITERATURE (web sweep 2026-09-27, report in IDX_DAYTRADE2_2026-09-27.md): ORB on stocks in play (Zarattini, Barbon, Aziz 2024),
market intraday momentum (Gao, Han, Li, Zhou 2018; IDX: Hamidi et al. 2024), noise-area momentum with VWAP trail (Zarattini,
Aziz, Barbon 2024), overnight-intraday reversal / gap fade (Lou, Polk, Skouras 2019; Akbas et al. 2022), practitioner VWAP
pullback. Adapted to IDX: LONG ONLY, no entry within reach of the upper auto-rejection band, stops at the opening-range low
(10 % ATR is below one tick on most IDX names).

COSTS. Fees 0.15 % buy + 0.25 % sell (Stockbit/Ajaib). Continuous-market fills pay half the name's median quoted spread
(idx.feed_book_1m, best level, continuous-session minutes only; floor half a tick); the closing auction pays fees only. Stops fill at min(bar open, stop - 1
tick) less half spread; when an entry bar also touches the stop, the stop is assumed hit (order inside a bar is unknown).
A close locked at the lower band exits at the next official open instead. Stress: every cost x 1.5.

UNIVERSE on day d: 20-session average traded value (daily_summary, ending d-1) >= Rp 5 bn, previous close >= Rp 100.

PRE-REGISTERED (11 trials + 4 void re-specified = cumulative 1042 + 15 = 1057).
  DATA DEFECT found on the first run: Yahoo leaves the volume of the FIRST bar empty (09:00 5-min bar 98 %, 09:00 hour 80 %),
  so RV on the opening range was void (A1/A2 made 6 and 5 trades; B1/B2 ranked on noise). A reconstruction (daily volume -
  negotiated - other bars) agreed with the tick feed at Spearman 0.59 only - rejected. Re-specified BEFORE the re-run, and the
  four void runs counted as trials: A1/A2 RV = the 09:05 bar's volume vs its 14-session mean, entries from 09:10; A3 RV =
  09:05-09:15; B1/B2 RV = yesterday's daily volume / its 14-day mean ("in play since yesterday"). K = 5 slots a day, 1/K of the book each.
  A1 ORB5_RV     09:00 5-min bar up; RV = its volume / mean of the prior 14 sessions' first bar (>= 10 needed) >= 1; top K
                 by RV; buy-stop at ORH + 1 tick until 15:00; stop ORL; exit closing auction.
  A2 ORB5_RV5    A1 with RV >= 5 (the "in play" tail).
  A3 ORB15_RV    A1 on the 09:00-09:15 range.
  A4 NOISE       top 40 names by 20-day value; sigma(t) = mean |c(t)/open - 1| over 14 prior sessions at the same minute;
                 upper = max(open, prev close) x (1 + sigma); at each HH:00 / HH:30 (until 15:00) buy if close > upper and >
                 VWAP; exit at a later HH:00/HH:30 close below max(upper, VWAP), else the closing auction.
  A5 IMOM        r1 = prev close -> 09:30; at 15:20 buy the top K by r1 (r1 > 0); exit closing auction.
  A6 GAP_CONF    official gap <= -3 % (> -14 %), 09:00 5-min bar closes above its open; buy its close; stop = its low;
                 exit closing auction; K most negative gaps.
  A7 VWAP_PB     up >= 2 % at 10:00 and above VWAP; top K; from 10:00 to 14:30 buy the first bar that dips to the prior VWAP
                 and closes above VWAP; exit on a close below 0.99 x VWAP, else the closing auction.
  B1 ORB60_RV    A1 on the 09:00 hour (sample B).       B2 ORB60_RV5  B1 with RV >= 5.
  B3 IMOM_H      r1 = prev close -> 10:00; buy the top K at the 15:00 open; exit closing auction.
  B4 GAP_CONF_H  gap as A6, 09:00 hour bar closes above its open; buy the 10:00 open; stop = the 09:00 low.
  References (not trials): GAP_HOST / GAP_HOST_H = buy the official open (auction, no spread), sell the close, same gaps.
READING RULE: CANDIDATE if ALL: >= 100 trades; mean net > 0; t on daily means >= 2; placebo percentile >= 95 (200 draws:
random eligible names, same day, same entry minute, same stop distance, same exit); positive in both halves of the sample
(B also in >= 3 of its 4 calendar years); mean net > 0 at costs x 1.5. An A-only candidate (58 sessions) is at most a
forward-paper watch. READ-ONLY on the DB except one idx.study row (--no-store to skip).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
DATA = os.path.join(ROOT, "research-scratch", "idx", "daytrade2")
STUDY = "daytrade2"
N_BEFORE, N_VOID, TRIALS = 1042, 4, ["A1_ORB5_RV", "A2_ORB5_RV5", "A3_ORB15_RV", "A4_NOISE", "A5_IMOM", "A6_GAP_CONF", "A7_VWAP_PB",
                          "B1_ORB60_RV", "B2_ORB60_RV5", "B3_IMOM_H", "B4_GAP_CONF_H"]
K, FEE_B, FEE_S, MIN_VAL, MIN_PX, N_PLACEBO = 5, 0.0015, 0.0025, 5e9, 100, 200
AUCTION, CONT_END, LOCK = 960, 950, -0.069               # minutes of day; lower-band lock threshold
RNG = np.random.default_rng(20260927)


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    return [ln.split("=", 1)[1].strip() for ln in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"))
            if ln.startswith("INGEST_DB_DSN=")][0]


def tick(p: float) -> float:
    return 1 if p < 200 else 2 if p < 500 else 5 if p < 2000 else 10 if p < 5000 else 25


def ara(p: float) -> float:
    return 0.35 if p < 200 else 0.25 if p < 5000 else 0.20


# ---- data -------------------------------------------------------------------------------------------------------------

def load(conn):
    ds = pd.DataFrame(conn.execute("""select trade_date, code, previous, open, close, value, volume from idx.daily_summary
                                      where trade_date >= '2023-07-01'""").fetchall(),
                      columns=["d", "code", "prev", "dopen", "dclose", "dval", "dvol"])
    for k in ("prev", "dopen", "dclose", "dval", "dvol"):
        ds[k] = ds[k].astype(float)
    ds = ds.sort_values(["code", "d"])
    ds["v20"] = ds.groupby("code").dval.transform(lambda s: s.shift(1).rolling(20, min_periods=15).mean())
    ds["next_open"] = ds.groupby("code").dopen.shift(-1)
    ds["rv_prev"] = ds.groupby("code").dvol.shift(1) / ds.groupby("code").dvol.transform(lambda s: s.shift(2).rolling(14, min_periods=10).mean())
    ds["elig"] = (ds.v20 >= MIN_VAL) & (ds.prev >= MIN_PX)
    daily = {(r.code, r.d): r for r in ds.itertuples(index=False)}
    sp = dict(conn.execute("""select code, percentile_cont(0.5) within group (order by
                                (off_px[1]-bid_px[1])::float / ((off_px[1]+bid_px[1])/2.0))
                              from idx.feed_book_1m where off_px[1] > 0 and bid_px[1] > 0 and off_px[1] > bid_px[1]
                                and ((minute at time zone 'Asia/Jakarta')::time between '09:01' and '11:59'
                                  or (minute at time zone 'Asia/Jakarta')::time between '13:31' and '15:49')
                              group by code""").fetchall())
    return daily, sp


def sessions(path: str) -> dict:
    y = pd.read_parquet(path).dropna(subset=["close"]).reset_index(drop=True)
    y = y[y.code != "IHSG"]
    t = y.ts.dt.tz_convert("Asia/Jakarta")
    y["d"] = t.dt.date
    y["tm"] = t.dt.hour * 60 + t.dt.minute
    y["volume"] = y.volume.fillna(0.0)
    y = y.sort_values(["code", "d", "tm"])
    out = {}
    for (code, d), g in y.groupby(["code", "d"], sort=False):
        a = {k: g[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume")}
        a["tm"] = g.tm.to_numpy()
        cont = a["tm"] < CONT_END
        if cont.sum() < 3:
            continue
        auc = a["close"][a["tm"] >= AUCTION]
        a["auction"] = float(auc[-1]) if len(auc) else float(a["close"][cont][-1])
        for k in ("open", "high", "low", "close", "volume", "tm"):
            a[k] = a[k][cont]
        tp = (a["high"] + a["low"] + a["close"]) / 3
        cv = np.cumsum(a["volume"])
        a["vwap"] = np.where(cv > 0, np.cumsum(tp * a["volume"]) / np.maximum(cv, 1e-9), a["close"])
        out[(code, d)] = a
    # previous close on the Yahoo basis (the prior session of the same name)
    by_code = defaultdict(list)
    for (code, d) in out:
        by_code[code].append(d)
    for code, ds_ in by_code.items():
        ds_.sort()
        for i, d in enumerate(ds_):
            out[(code, d)]["prevc"] = out[(code, ds_[i - 1])]["auction"] if i else np.nan
            out[(code, d)]["hist"] = ds_[max(0, i - 14):i]
    return out


# ---- execution --------------------------------------------------------------------------------------------------------

class Ctx:
    def __init__(self, S, daily, sp):
        self.S, self.daily, self.sp = S, daily, sp
        self.days = sorted({d for (_, d) in S})
        self.by_day = defaultdict(list)
        for (code, d) in S:
            r = daily.get((code, d))
            if r is not None and r.elig and not np.isnan(S[(code, d)]["prevc"]):
                self.by_day[d].append(code)

    def hs(self, code, p):
        s = self.sp.get(code)
        s = 2 * tick(p) / p if s is None or not np.isfinite(s) else s
        return max(s, tick(p) / p) / 2


def trade(ctx, code, d, i, px, stop, trial, exit_fn=None):
    """Enter at raw price px on bar i (inside the bar); run the stop / exit rule; closing auction otherwise."""
    a = ctx.S[(code, d)]
    if px >= a["prevc"] * (1 + ara(ctx.daily[(code, d)].prev)) - tick(px):
        return None                                                    # at / near the upper band: no fill
    hs_e, sell, hs_x, kind = ctx.hs(code, px), None, 0.0, "close"
    for j in range(i, len(a["tm"])):
        if stop is not None and a["low"][j] < stop:
            sell = min(a["open"][j], stop - tick(stop)) if j > i else stop - tick(stop)
            kind = "stop"
            break
        if exit_fn is not None and j > i:
            x = exit_fn(a, j)
            if x is not None:
                sell, kind = x, "rule"
                break
    if sell is not None:
        hs_x = ctx.hs(code, sell)
    else:
        sell = a["auction"]
        r = ctx.daily[(code, d)]
        if sell / a["prevc"] - 1 <= LOCK and sell <= a["low"].min() and np.isfinite(r.next_open) and r.dclose:
            sell, kind = sell * r.next_open / r.dclose, "locked"      # cannot sell at the band: next official open
    return dict(trial=trial, d=d, code=code, tm=int(a["tm"][i]), buy=px, sell=sell, hs_e=hs_e, hs_x=hs_x, kind=kind,
                stop_pct=(1 - stop / px) if stop is not None else None)


def net(t, m=1.0):
    return t["sell"] * (1 - m * t["hs_x"]) * (1 - m * FEE_S) / (t["buy"] * (1 + m * t["hs_e"]) * (1 + m * FEE_B)) - 1


# ---- rules ------------------------------------------------------------------------------------------------------------

def orb(ctx, trial, nbars, rv_min, last_entry=900, rv_bars=None, first_entry=None):
    """rv_bars = (i0, i1): RV on those bars' volume (Yahoo leaves the 09:00 bar's volume empty); None = yesterday's daily
    volume / its 14-day mean (sample B). first_entry = first bar index allowed (after the RV bars are known)."""
    out = []
    for d in ctx.days:
        cands = []
        for code in ctx.by_day[d]:
            a = ctx.S[(code, d)]
            if len(a["tm"]) <= nbars or a["tm"][0] != 540:
                continue
            o, c = a["open"][0], a["close"][nbars - 1]
            hist = [ctx.S[(code, h)] for h in a["hist"]]
            if c <= o:
                continue
            if rv_bars is None:
                rv = ctx.daily[(code, d)].rv_prev
                if not np.isfinite(rv):
                    continue
            else:
                i0, i1 = rv_bars
                hv = [h["volume"][i0:i1].sum() for h in hist if h["tm"][0] == 540 and len(h["tm"]) > i1]
                if len(hv) < 10 or np.mean(hv) <= 0 or len(a["tm"]) <= i1:
                    continue
                rv = a["volume"][i0:i1].sum() / np.mean(hv)
            if rv >= rv_min:
                cands.append((rv, code))
        for rv, code in sorted(cands, reverse=True)[:K]:
            a = ctx.S[(code, d)]
            orh, orl = a["high"][:nbars].max(), a["low"][:nbars].min()
            trig = orh + tick(orh)
            for j in range(first_entry or nbars, len(a["tm"])):
                if a["tm"][j] > last_entry:
                    break
                if a["high"][j] >= trig:
                    t = trade(ctx, code, d, j, max(trig, a["open"][j]), orl, trial)
                    if t:
                        t["rv"] = rv
                        out.append(t)
                    break
    return out


def noise(ctx, trial):
    marks = {565, 595, 625, 655, 685, 835, 865, 895, 925}               # bars ending HH:00 / HH:30
    out = []
    for d in ctx.days:
        names = sorted(ctx.by_day[d], key=lambda c: -ctx.daily[(c, d)].v20)[:40]
        for code in names:
            a = ctx.S[(code, d)]
            if a["tm"][0] != 540:
                continue
            hist = [ctx.S[(code, h)] for h in a["hist"] if ctx.S[(code, h)]["tm"][0] == 540]
            if len(hist) < 10:
                continue
            op = a["open"][0]
            upper = np.full(len(a["tm"]), np.nan)
            for j, tm in enumerate(a["tm"]):
                mv = [abs(h["close"][k] / h["open"][0] - 1) for h in hist for k in np.nonzero(h["tm"] == tm)[0][:1]]
                if len(mv) >= 10:
                    upper[j] = max(op, a["prevc"]) * (1 + np.mean(mv))

            def ex(a_, j, upper=upper):
                if a_["tm"][j] in marks and np.isfinite(upper[j]) and a_["close"][j] < max(upper[j], a_["vwap"][j]):
                    return a_["close"][j]
                return None
            for j, tm in enumerate(a["tm"]):
                if tm in marks and tm <= 895 and np.isfinite(upper[j]) and a["close"][j] > upper[j] and a["close"][j] > a["vwap"][j]:
                    t = trade(ctx, code, d, j, a["close"][j], None, trial, ex)
                    if t:
                        t["stop_pct"] = 1 - max(upper[j], a["vwap"][j]) / a["close"][j]
                        out.append(t)
                    break
    return out


def imom(ctx, trial, r1_bar_tm, entry_tm, at_open):
    out = []
    for d in ctx.days:
        cands = []
        for code in ctx.by_day[d]:
            a = ctx.S[(code, d)]
            i1, ie = np.nonzero(a["tm"] == r1_bar_tm)[0], np.nonzero(a["tm"] == entry_tm)[0]
            if len(i1) and len(ie):
                r1 = a["close"][i1[0]] / a["prevc"] - 1
                if r1 > 0:
                    cands.append((r1, code, ie[0]))
        for r1, code, j in sorted(cands, reverse=True)[:K]:
            a = ctx.S[(code, d)]
            t = trade(ctx, code, d, j, a["open"][j] if at_open else a["close"][j], None, trial)
            if t:
                out.append(t)
    return out


def gap(ctx, trial, conf_bar_tm, entry_next_open):
    out, host = [], []
    for d in ctx.days:
        cands = []
        for code in ctx.by_day[d]:
            r = ctx.daily[(code, d)]
            if not r.dopen or not r.prev:
                continue
            g = r.dopen / r.prev - 1
            if -0.14 < g <= -0.03:
                cands.append((g, code))
        cands.sort()
        for g, code in cands[:K]:                                        # host: official open -> close, no spread
            a = ctx.S[(code, d)]
            host.append(dict(trial=trial + "_HOST", d=d, code=code, tm=540, buy=a["prevc"] * (1 + g), sell=a["auction"],
                             hs_e=0.0, hs_x=0.0, kind="close", stop_pct=None))
        n = 0
        for g, code in cands:
            a = ctx.S[(code, d)]
            ic = np.nonzero(a["tm"] == conf_bar_tm)[0]
            if not len(ic) or ic[0] + 1 >= len(a["tm"]) or a["close"][ic[0]] <= a["open"][ic[0]]:
                continue
            i = ic[0]
            if entry_next_open:
                t = trade(ctx, code, d, i + 1, a["open"][i + 1], a["low"][i], trial)
            else:
                t = trade(ctx, code, d, i + 1, a["close"][i], a["low"][i], trial)     # the confirming bar's close
            if t:
                t["gap"] = g
                out.append(t)
                n += 1
            if n >= K:
                break
    return out, host


def vwap_pb(ctx, trial):
    out = []
    for d in ctx.days:
        cands = []
        for code in ctx.by_day[d]:
            a = ctx.S[(code, d)]
            i = np.nonzero(a["tm"] == 595)[0]
            if len(i):
                r = a["close"][i[0]] / a["prevc"] - 1
                if r >= 0.02 and a["close"][i[0]] > a["vwap"][i[0]]:
                    cands.append((r, code))
        for r, code in sorted(cands, reverse=True)[:K]:
            a = ctx.S[(code, d)]

            def ex(a_, j):
                return a_["close"][j] if a_["close"][j] < 0.99 * a_["vwap"][j] else None
            for j in range(1, len(a["tm"])):
                if a["tm"][j] < 600:
                    continue
                if a["tm"][j] > 870:
                    break
                if a["low"][j] <= a["vwap"][j - 1] and a["close"][j] > a["vwap"][j]:
                    t = trade(ctx, code, d, j, a["close"][j], None, trial, ex)
                    if t:
                        t["stop_pct"] = 1 - 0.99 * a["vwap"][j] / a["close"][j]
                        out.append(t)
                    break
    return out


# ---- evaluation -------------------------------------------------------------------------------------------------------

def placebo(ctx, trades):
    """Random eligible names, same day and entry minute, same stop distance, exit at the stop or the closing auction."""
    means = []
    slots = []
    for t in trades:
        pool = [c for c in ctx.by_day[t["d"]] if np.any(ctx.S[(c, t["d"])]["tm"] == t["tm"])]
        slots.append((t, pool))
    for _ in range(N_PLACEBO):
        vals = []
        for t, pool in slots:
            if not pool:
                continue
            code = pool[RNG.integers(len(pool))]
            a = ctx.S[(code, t["d"])]
            j = int(np.nonzero(a["tm"] == t["tm"])[0][0])
            px = a["close"][j]
            sp = t["stop_pct"]
            p = trade(ctx, code, t["d"], min(j + 1, len(a["tm"]) - 1), px,
                      px * (1 - sp) if sp is not None and sp > 0 else None, "placebo")
            if p:
                vals.append(net(p))
        if vals:
            means.append(np.mean(vals))
    return np.array(means)


def evaluate(ctx, trades, kind, do_placebo=True):
    if not trades:
        return dict(n=0)
    df = pd.DataFrame(trades)
    df["net"] = [net(t) for t in trades]
    df["net15"] = [net(t, 1.5) for t in trades]
    df["gross"] = df.sell / df.buy - 1
    daily = df.groupby("d").net.mean()
    t_day = daily.mean() / daily.std(ddof=1) * np.sqrt(len(daily)) if len(daily) > 2 else np.nan
    book = (df.groupby("d").net.sum() / K).reindex(ctx.days, fill_value=0.0)
    eq = (1 + book).cumprod()
    yrs = len(ctx.days) / 244
    mid = ctx.days[len(ctx.days) // 2]
    h1, h2 = df[df.d < mid].net.mean(), df[df.d >= mid].net.mean()
    by_year = df.groupby(df.d.map(lambda x: x.year)).net.mean()
    res = dict(n=len(df), days=int(daily.size), hit=float((df.net > 0).mean()), gross_bps=df.gross.mean() * 1e4,
               net_bps=df.net.mean() * 1e4, median_bps=df.net.median() * 1e4, net15_bps=df.net15.mean() * 1e4,
               cost_bps=(df.gross - df.net).mean() * 1e4, t_day=float(t_day), h1_bps=h1 * 1e4, h2_bps=h2 * 1e4,
               by_year={int(k): round(v * 1e4, 1) for k, v in by_year.items()},
               exits=df.kind.value_counts().to_dict(),
               cagr=float(eq.iloc[-1] ** (1 / yrs) - 1), sharpe=float(book.mean() / book.std() * np.sqrt(244)) if book.std() > 0 else 0.0,
               mdd=float((eq / eq.cummax() - 1).min()), total=float(eq.iloc[-1] - 1))
    if do_placebo:
        pl = placebo(ctx, trades)
        res["placebo_bps"] = float(pl.mean() * 1e4) if len(pl) else np.nan
        res["placebo_pct"] = float((pl < df.net.mean()).mean() * 100) if len(pl) else np.nan
    yrs_pos = sum(v > 0 for v in by_year.values)
    checks = dict(n100=res["n"] >= 100, net_pos=res["net_bps"] > 0, t2=res["t_day"] >= 2,
                  placebo=res.get("placebo_pct", 0) >= 95, halves=h1 > 0 and h2 > 0, cost15=res["net15_bps"] > 0)
    if kind == "B":
        checks["years"] = yrs_pos >= 3
    res["checks"] = checks
    res["verdict"] = "CANDIDATE" if all(checks.values()) else "no"
    return res


def hour_profile(ctx):
    """Informative: the equal-weight mean return of each hourly bar (sample B), overnight and the closing auction."""
    rows = defaultdict(list)
    for (code, d), a in ctx.S.items():
        if code not in ctx.by_day.get(d, []):
            continue
        if a["tm"][0] == 540 and np.isfinite(a["prevc"]):
            rows["overnight (prev close -> 09:00 open)"].append(a["open"][0] / a["prevc"] - 1)
        for j, tm in enumerate(a["tm"]):
            rows[f"{tm // 60:02d}:{tm % 60:02d} bar"].append(a["close"][j] / a["open"][j] - 1)
        rows["closing auction (15:50 last -> close)"].append(a["auction"] / a["close"][-1] - 1)
    return {k: dict(n=len(v), mean_bps=float(np.mean(v) * 1e4), t=float(np.mean(v) / np.std(v) * np.sqrt(len(v))))
            for k, v in rows.items()}


# ---- report -----------------------------------------------------------------------------------------------------------

def fmt_row(name, r):
    if not r.get("n"):
        return f"| {name} | 0 | | | | | | | | | | | | | | no trades |"
    fails = ",".join(k for k, v in r.get("checks", {}).items() if not v) or "-"
    yrs = " ".join(f"{str(k)[2:]}:{v:+.0f}" for k, v in r["by_year"].items())
    return (f"| {name} | {r['n']:,} | {r['days']} | {r['hit']:.0%} | {r['gross_bps']:+.0f} | {r['cost_bps']:.0f} | "
            f"**{r['net_bps']:+.0f}** | {r['median_bps']:+.0f} | {r['t_day']:.2f} | {r['net15_bps']:+.0f} | "
            f"{r['h1_bps']:+.0f} / {r['h2_bps']:+.0f} | {yrs} | {r.get('placebo_bps', float('nan')):+.0f} ({r.get('placebo_pct', float('nan')):.0f}) | "
            f"{r['cagr']:+.0%} / {r['sharpe']:.2f} / {r['mdd']:.0%} | {r['verdict']}{'' if r['verdict'] == 'CANDIDATE' else ' (' + fails + ')'} |")


HDR = ("| arm | trades | days | hit | gross bps | cost bps | net bps | median | t (daily) | net @1.5x cost | halves | by year | "
       "placebo bps (pct) | book CAGR / Sharpe / mDD | verdict (failed checks) |\n|" + "---|" * 15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "IDX_DAYTRADE2_2026-09-27.json"))
    args = ap.parse_args()
    with psycopg.connect(dsn()) as conn:
        daily, sp = load(conn)
    res, meta = {}, {}
    for tag, path in (("A", "yahoo_5m.parquet"), ("B", "yahoo_1h.parquet")):
        S = sessions(os.path.join(DATA, path))
        ctx = Ctx(S, daily, sp)
        meta[tag] = dict(sessions=len(ctx.days), first=str(ctx.days[0]), last=str(ctx.days[-1]),
                         names=len({c for (c, _) in S}), eligible_name_days=sum(len(v) for v in ctx.by_day.values()),
                         median_half_spread_bps=float(np.median([ctx.hs(c, 1000) for c in {c for (c, _) in S}]) * 1e4))
        print(tag, meta[tag], flush=True)
        if tag == "A":
            arms = {"A1_ORB5_RV": orb(ctx, "A1", 1, 1.0, rv_bars=(1, 2), first_entry=2),
                    "A2_ORB5_RV5": orb(ctx, "A2", 1, 5.0, rv_bars=(1, 2), first_entry=2),
                    "A3_ORB15_RV": orb(ctx, "A3", 3, 1.0, rv_bars=(1, 3)), "A4_NOISE": noise(ctx, "A4"),
                    "A5_IMOM": imom(ctx, "A5", 565, 915, False)}
            g, host = gap(ctx, "A6", 540, False)
            arms.update({"A6_GAP_CONF": g, "A6_GAP_HOST (ref)": host, "A7_VWAP_PB": vwap_pb(ctx, "A7")})
        else:
            arms = {"B1_ORB60_RV": orb(ctx, "B1", 1, 1.0, 840), "B2_ORB60_RV5": orb(ctx, "B2", 1, 5.0, 840),
                    "B3_IMOM_H": imom(ctx, "B3", 540, 900, True)}
            g, host = gap(ctx, "B4", 540, True)
            arms.update({"B4_GAP_CONF_H": g, "B4_GAP_HOST_H (ref)": host})
            meta["hour_profile"] = hour_profile(ctx)
        for name, tr in arms.items():
            res[name] = evaluate(ctx, tr, tag, do_placebo="ref" not in name)
            print(name, {k: res[name].get(k) for k in ("n", "net_bps", "t_day", "placebo_pct", "verdict")}, flush=True)
    json.dump(dict(meta=meta, results=res), open(args.out, "w"), indent=1, default=str)
    if not args.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(),
                                  params={"trials": TRIALS, "n_trials_cumulative": N_BEFORE + N_VOID + len(TRIALS), "k": K,
                                          "fees": [FEE_B, FEE_S], "data": "yahoo 5m/1h verified vs tick feed"},
                                  summary={k: {kk: v.get(kk) for kk in ("n", "net_bps", "t_day", "placebo_pct", "verdict")}
                                           for k, v in res.items()},
                                  names=[], report_path="research/IDX_DAYTRADE2_2026-09-27.md")
            print("study id", sid)
    print("\n" + HDR)
    for name, r in res.items():
        print(fmt_row(name, r))


if __name__ == "__main__":
    main()
