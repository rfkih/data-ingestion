#!/usr/bin/env python3
"""IDX menu DT-3 - raising the GROSS edge of short-horizon trades (operator 2026-09-27: "ada plan buat meningkatkan keuntungan
kotornya?" -> "okay boleh"). Follows DT-2 (#397, 0/15): the literature's signals beat random but paid ~37 bps of spread on a
continuous entry, and entered in the worst hour (09:00 hour -18 bps; overnight +28 bps, t 42 - hour profile 2023-26).

Three levers, one hypothesis each, on DT-2's sample B (Yahoo 1-hour bars, 713 sessions 2023-09-13 .. 2026-09-25, verified vs
the tick feed) plus daily_summary's official auction prints (open / close):
  lever 1  trade in the AUCTIONS (no spread): buy the closing auction, sell the next opening auction;
  lever 2  SELECTIVITY: only the extreme "in play" names and an up-trending market;
  lever 3  TIMING: enter after the 09:00 hour instead of at the open.

COSTS. Auction fills: fees 0.15 % + 0.25 % and 5 bps impact each side. Continuous fills: half the quoted spread (DT-2 recipe).
Stress x 1.5. UNIVERSE / eligibility, K = 5 slots and the evaluation are DT-2's (imported).
IHSG regime on day d: the index's close on d-1 above its 20-session mean (Yahoo ^JKSE 1-hour auction bars).

PRE-REGISTERED (6 trials; cumulative 1057 + 6 = 1063).
  C1 MOM_ON        at 15:49 rank eligible names by prev close -> 15:49 return (> 0, first hour also > 0, close not within
                   1 tick of the upper band); buy the top K in the closing auction; sell the next opening auction.
  C2 LASTHOUR_ON   as C1 but ranked by the 15:00-15:49 return (the last-hour "hedging demand" leg; day return > 0).
  C3 INPLAY_OPEN   yesterday's volume >= 5x its 14-day mean and yesterday up; buy the opening auction, sell the closing auction.
  C4 ORB60_SEL     DT-2's B2 (ORB 60-min) with RV >= 10 and only on IHSG-regime-up days.
  C5 INPLAY_10     C3's names bought at the 10:00 open (continuous, pays the spread), sold in the closing auction.
  C6 MOM_ON_REG    C1 on IHSG-regime-up days only.
  Reference (not a trial): ALL_ON = every eligible name, closing auction -> next opening auction (the overnight premium).
READING RULE: DT-2's (>= 100 trades; net > 0; t on daily means >= 2; placebo pct >= 95 - random eligible names, same day,
same execution; positive both halves and in >= 3 of 4 calendar years; net > 0 at costs x 1.5). A candidate is a paper-watch
only. READ-ONLY on the DB except one idx.study row (--no-store to skip).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("dt2", os.path.join(HERE, "idx_daytrade2.py"))
dt2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dt2)

STUDY, N_BEFORE = "daytrade3", 1057
TRIALS = ["C1_MOM_ON", "C2_LASTHOUR_ON", "C3_INPLAY_OPEN", "C4_ORB60_SEL", "C5_INPLAY_10", "C6_MOM_ON_REG"]
IMPACT = 0.0005
K = dt2.K
RNG = np.random.default_rng(20260928)


def regime_days(path):
    y = pd.read_parquet(path)
    y = y[(y.code == "IHSG")].dropna(subset=["close"]).copy()
    y["d"] = y.ts.dt.tz_convert("Asia/Jakarta").dt.date
    c = y.sort_values("ts").groupby("d").close.last()
    up = (c > c.rolling(20).mean()).shift(1)
    return {d for d, v in up.items() if v is True or v == 1.0}


def auction_on(ctx, code, d, trial):
    """Buy d's closing auction, sell the next session's opening auction (official prints, raw ratio)."""
    r = ctx.daily[(code, d)]
    if not (np.isfinite(r.next_open) and r.next_open > 0 and r.dclose > 0):
        return None
    return dict(trial=trial, d=d, code=code, tm=960, buy=r.dclose, sell=r.next_open, hs_e=IMPACT, hs_x=IMPACT, kind="on",
                stop_pct=None)


def auction_day(ctx, code, d, trial):
    """Buy d's opening auction, sell d's closing auction."""
    r = ctx.daily[(code, d)]
    if not (r.dopen and r.dopen > 0 and r.dclose > 0):
        return None
    return dict(trial=trial, d=d, code=code, tm=540, buy=r.dopen, sell=r.dclose, hs_e=IMPACT, hs_x=IMPACT, kind="day",
                stop_pct=None)


def late_day(ctx, code, d, trial):
    """Buy the 10:00 hour's open (continuous, half spread), sell the closing auction."""
    a = ctx.S[(code, d)]
    i = np.nonzero(a["tm"] == 600)[0]
    if not len(i):
        return None
    t = dt2.trade(ctx, code, d, int(i[0]), a["open"][i[0]], None, trial)
    if t:
        t["tm"] = 600
    return t


def near_ara(ctx, code, d, px):
    return px >= ctx.S[(code, d)]["prevc"] * (1 + dt2.ara(ctx.daily[(code, d)].prev)) - dt2.tick(px)


def picks_mom(ctx, d, key):
    out = []
    for code in ctx.by_day[d]:
        a = ctx.S[(code, d)]
        i9, i15 = np.nonzero(a["tm"] == 540)[0], np.nonzero(a["tm"] == 900)[0]
        if not len(i9) or not len(i15):
            continue
        c15 = a["close"][i15[0]]
        rday, r1 = c15 / a["prevc"] - 1, a["close"][i9[0]] / a["prevc"] - 1
        if rday <= 0 or near_ara(ctx, code, d, c15):
            continue
        if key == "day" and r1 > 0:
            out.append((rday, code))
        elif key == "last":
            out.append((c15 / a["open"][i15[0]] - 1, code))
    return [c for _, c in sorted(out, reverse=True)[:K]]


def picks_inplay(ctx, d):
    out = []
    for code in ctx.by_day[d]:
        r = ctx.daily[(code, d)]
        if np.isfinite(r.rv_prev) and r.rv_prev >= 5 and r.prev > 0:
            prev2 = ctx.S[(code, d)]["hist"]
            if prev2:                                                   # yesterday up: yesterday's close vs its prior close
                a1 = ctx.S[(code, prev2[-1])]
                if np.isfinite(a1["prevc"]) and a1["auction"] > a1["prevc"]:
                    out.append((r.rv_prev, code))
    return [c for _, c in sorted(out, reverse=True)[:K]]


def run_arm(ctx, trial, days, picker, execute):
    trades, pools = [], []
    for d in days:
        codes = picker(ctx, d)
        got = [t for t in (execute(ctx, c, d, trial) for c in codes) if t]
        trades += got
        if got:
            pools.append((d, len(got)))
    return trades, pools


def placebo(ctx, pools, execute, n=dt2.N_PLACEBO):
    means = []
    for _ in range(n):
        vals = []
        for d, m in pools:
            pool = ctx.by_day[d]
            for code in RNG.choice(pool, size=min(m, len(pool)), replace=False):
                t = execute(ctx, code, d, "placebo")
                if t:
                    vals.append(dt2.net(t))
        means.append(np.mean(vals))
    return np.array(means)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    args = ap.parse_args()
    with psycopg.connect(dt2.dsn()) as conn:
        daily, sp = dt2.load(conn)
    path = os.path.join(dt2.DATA, "yahoo_1h.parquet")
    ctx = dt2.Ctx(dt2.sessions(path), daily, sp)
    reg = regime_days(path)
    days, rdays = ctx.days, [d for d in ctx.days if d in reg]
    print("sessions", len(days), "regime-up", len(rdays), flush=True)
    arms = {
        "C1_MOM_ON": (days, lambda c, d: picks_mom(c, d, "day"), auction_on),
        "C2_LASTHOUR_ON": (days, lambda c, d: picks_mom(c, d, "last"), auction_on),
        "C3_INPLAY_OPEN": (days, picks_inplay, auction_day),
        "C5_INPLAY_10": (days, picks_inplay, late_day),
        "C6_MOM_ON_REG": (rdays, lambda c, d: picks_mom(c, d, "day"), auction_on),
    }
    res = {}
    for name, (dd, pick, ex) in arms.items():
        tr, pools = run_arm(ctx, name, dd, pick, ex)
        r = dt2.evaluate(ctx, tr, "B", do_placebo=False)
        pl = placebo(ctx, pools, ex)
        r["placebo_bps"], r["placebo_pct"] = float(pl.mean() * 1e4), float((pl < np.mean([dt2.net(t) for t in tr])).mean() * 100)
        r["checks"]["placebo"] = r["placebo_pct"] >= 95
        r["verdict"] = "CANDIDATE" if all(r["checks"].values()) else "no"
        res[name] = r
        print(name, {k: r.get(k) for k in ("n", "gross_bps", "net_bps", "t_day", "placebo_pct", "verdict")}, flush=True)
    # C4: DT-2's ORB-60 with RV >= 10 on regime-up days (DT-2's own placebo)
    sub = dt2.Ctx.__new__(dt2.Ctx)
    sub.S, sub.daily, sub.sp, sub.days = ctx.S, ctx.daily, ctx.sp, ctx.days
    sub.by_day = defaultdict(list, {d: v for d, v in ctx.by_day.items() if d in reg})
    res["C4_ORB60_SEL"] = dt2.evaluate(sub, dt2.orb(sub, "C4", 1, 10.0, 840), "B")
    print("C4_ORB60_SEL", {k: res["C4_ORB60_SEL"].get(k) for k in ("n", "gross_bps", "net_bps", "t_day", "placebo_pct", "verdict")})
    # reference: every eligible name overnight
    ref = [t for d in days for t in (auction_on(ctx, c, d, "ALL_ON") for c in ctx.by_day[d]) if t]
    df = pd.DataFrame(ref)
    df["net"] = [dt2.net(t) for t in ref]
    df["gross"] = df.sell / df.buy - 1
    res["ALL_ON (ref)"] = dict(n=len(df), gross_bps=df.gross.mean() * 1e4, net_bps=df.net.mean() * 1e4,
                               by_year={int(k): round(v * 1e4, 1) for k, v in df.groupby(df.d.map(lambda x: x.year)).gross.mean().items()})
    print("ALL_ON ref", res["ALL_ON (ref)"])
    out = os.path.join(HERE, "IDX_DAYTRADE3_2026-09-27.json")
    json.dump(dict(results=res, sessions=len(days), regime_days=len(rdays)), open(out, "w"), indent=1, default=str)
    if not args.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dt2.dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(),
                                  params={"trials": TRIALS, "n_trials_cumulative": N_BEFORE + len(TRIALS), "k": K,
                                          "impact": IMPACT, "follows": "daytrade2 #397"},
                                  summary={k: {kk: v.get(kk) for kk in ("n", "gross_bps", "net_bps", "t_day", "placebo_pct", "verdict")}
                                           for k, v in res.items()},
                                  names=[], report_path="research/IDX_DAYTRADE3_2026-09-27.md")
            print("study id", sid)
    print("\n" + dt2.HDR)
    for name in TRIALS:
        print(dt2.fmt_row(name, res[name]))


if __name__ == "__main__":
    main()
