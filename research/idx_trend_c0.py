#!/usr/bin/env python3
"""IDX menu TR-2 - does the SX-1 momentum control beat the DEPLOYED trend sleeve on the desk's own engine? (operator 2026-09-27
"okay lanjutkan" after IDX_SENTIMENT_2026-09-27.md).

SX-1's control C0 (momentum +30 % in 60 sessions at a 1-year high, Rp 1 bn floor, 25 % trailing exit) printed 45.8 %/1.92 on
idx.bar 2020-26 against the deployed trend sleeve's 12.7 %/1.19 (#192). The engines differ, so that gap proves nothing. Here
every arm runs on the SAME machinery as the deployed sleeve: panels from tmp/exit_cache_pit.pkl (point-in-time board), the
K-10 event simulator E.run_book (signal at close t, fill at close t+1 at the offer, exits at the bid), then a RUPIAH replay:
Rp 20 m, 5 % of NAV per trade, at most 20 positions, lots of 100, fees 0.10 / 0.20 %, no fill on a day that closes >= 18 %
up (upper band), no sale on a day that closes <= 6.5 % down with no bid (lower band; the sale slides, up to 10 sessions).

ARMS (the decomposition of the gap). REF is the deployed rule; T1..T4 change one or more pieces.
  REF  universe small (LIQ >= Rp 5 bn and not BLUE), entry 60-day high & > MA200 & volume >= 1.5x its 20-day median,
       exit trail 10 %, regime gate (no entries while COMPOSITE < its 200-day mean)
  T1   REF with the exit trail 25 %                                                    (exit only)
  T2   universe U1 (20-day mean traded value >= Rp 1 bn, close >= Rp 50, on the main/development board that day), REF entry,
       trail 10 %, gate                                                                  (universe only)
  T3   C0 as run in SX-1: U1, entry close >= 1.3 x close 60 sessions ago & close = 250-day high & day return < 18 %,
       trail 25 %, NO gate
  T4   T3 with the regime gate
PRE-REGISTERED (4 trials; cumulative 1073 + 4 = 1077). READING RULE on the RUPIAH book, 2022-01 -> cache end: a trial is BETTER
than REF only if ALL: Sharpe > REF's; CAGR >= REF's; mDD no more than 10 points deeper than REF's; CAGR > 0 in both halves
(2022-01..2024-06, 2024-07..end); with every cost x 2 its Sharpe still > REF's (at x 2 as well); and the K-10 simulator
(2020-07 -> end, the desk's standard metric) agrees: Sharpe > REF's. Also reported: trades, lot-skips, median 20-day value of the
names bought (capacity), the 2026 YTD. A BETTER arm is a proposal for a paper book, not a change to the live sleeve.
READ-ONLY on the DB except one idx.study row (--no-store to skip).
"""
from __future__ import annotations

import argparse
import json
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
import idx_beyond as BY  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402

STUDY, N_BEFORE = "trend_c0", 1073
TRIALS = ["T1", "T2", "T3", "T4"]
CACHE = os.path.join(ROOT, "tmp", "exit_cache_pit.pkl")
CAPITAL, PCT, MAX_POS, LOT = 20_000_000.0, 0.05, 20, 100
FEE_BUY, FEE_SELL = 0.0010, 0.0020
START = pd.Timestamp("2022-01-01")
SIM_START = pd.Timestamp("2020-07-01")
UPCAP, DNLOCK = 0.18, -0.065


def dsn() -> str:
    return os.environ.get("INGEST_DB_DSN") or [ln.split("=", 1)[1].strip() for ln in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"))
                                                if ln.startswith("INGEST_DB_DSN=")][0]


def tick(p):
    return np.where(p < 200, 1, np.where(p < 500, 2, np.where(p < 2000, 5, np.where(p < 5000, 10, 25))))


def arms_masks(P, unis, comp):
    adj, vol, close = P["adj"], P["volume"], P["close"]
    dates = adj.index
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi60 = adj.rolling(60, min_periods=60).max()
    hi250 = adj.rolling(250, min_periods=200).max()
    r1 = adj / adj.shift(1) - 1
    gate = ~BY.regime_off_mask(comp, dates)[:, None]
    ref_entry = ((adj >= hi60) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool)
    c0_entry = ((adj >= 1.3 * adj.shift(60)) & (adj >= hi250) & (r1 < UPCAP)).to_numpy(bool)
    small = (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool)
    v20 = (close * vol).rolling(20, min_periods=15).mean()
    board = P["board_ok"].reindex(index=dates, columns=adj.columns).fillna(False).astype(bool) if "board_ok" in P else True
    u1 = ((v20 >= 1e9) & (close >= 50) & (vol > 0) & adj.notna() & board).to_numpy(bool)
    score = vr.to_numpy(float)
    return {"REF": (ref_entry & gate, small, "trail10"), "T1": (ref_entry & gate, small, "trail25"),
            "T2": (ref_entry & gate, u1, "trail10"), "T3": (c0_entry, u1, "trail25"), "T4": (c0_entry & gate, u1, "trail25")}, score, v20


def rules(A, peak_x):
    return lambda t, j, p: 1.0 if A[t, j] <= (1 - peak_x) * p["peak"] else 0


def sim_stats(R, dates, start):
    r = pd.Series(R, index=dates)
    r = r[r.index >= start]
    eq = (1 + r).cumprod()
    yrs = len(r) / 244
    return dict(cagr=float(eq.iloc[-1] ** (1 / yrs) - 1), sharpe=float(r.mean() / r.std() * np.sqrt(244)) if r.std() > 0 else 0.0,
                mdd=float((eq / eq.cummax() - 1).min()))


def replay(trades, P, cost_mult=1.0):
    """Rupiah book: the K-10 simulator's trades at 5 % of NAV, lots, offer/bid, band realism."""
    adj, raw, off, bid = (P[k].to_numpy(float) for k in ("adj", "close", "offer", "bid"))
    dates = P["adj"].index
    T = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(START)))
    fb, fs = FEE_BUY * cost_mult, FEE_SELL * cost_mult
    entries = {}
    for e, j, hold in trades:
        entries.setdefault(e, []).append((j, e + hold))
    cash, held, nav, skipped_lot, skipped_band, n_in, vals = CAPITAL, {}, np.full(T, np.nan), 0, 0, 0, []
    for t in range(t0, T):
        # exits (sale slides past lower-band days with no bid)
        for j in [j for j, p in held.items() if p["x"] <= t]:
            p = held[j]
            r = raw[t, j] / raw[t - 1, j] - 1 if raw[t - 1, j] > 0 else 0.0
            if np.isnan(adj[t, j]) or (r <= DNLOCK and not (bid[t, j] > 0) and t - p["x"] < 10):
                continue
            px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])
            spread_cost = 1 - px / raw[t, j]
            value = p["units"] * (adj[t, j] / p["a_in"]) * (1 - cost_mult * spread_cost)
            cash += value * (1 - fs)
            held.pop(j)
        mv = sum(p["units"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav_now = cash + mv
        for j, x in entries.get(t, []):
            if j in held or len(held) >= MAX_POS or np.isnan(adj[t, j]) or not raw[t, j] > 0:
                continue
            r = raw[t, j] / raw[t - 1, j] - 1 if raw[t - 1, j] > 0 else 0.0
            if r >= UPCAP:
                skipped_band += 1
                continue
            px = off[t, j] if off[t, j] > 0 and off[t, j] >= raw[t, j] else raw[t, j] + tick(raw[t, j])
            px = raw[t, j] * (1 + cost_mult * (px / raw[t, j] - 1))
            lots = int((PCT * nav_now) // (px * LOT * (1 + fb)))
            cost = lots * LOT * px * (1 + fb)
            if lots < 1 or cost > cash:
                skipped_lot += lots < 1
                continue
            cash -= cost
            held[j] = {"a_in": adj[t, j], "units": lots * LOT * raw[t, j], "x": x}
            n_in += 1
            vals.append(float(P["_v20"][t, j]))
        mv = sum(p["units"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav[t] = cash + mv
    s = pd.Series(nav[t0:], index=dates[t0:]).ffill()
    r = s.pct_change().fillna(0)
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    half = s.index.searchsorted(pd.Timestamp("2024-07-01"))
    h1, h2 = s.iloc[:half], s.iloc[half - 1:]
    cg = lambda x: float((x.iloc[-1] / x.iloc[0]) ** (365.25 / max(1, (x.index[-1] - x.index[0]).days)) - 1)
    by = s.groupby(s.index.year).agg(["first", "last"])
    return dict(cagr=float((s.iloc[-1] / CAPITAL) ** (1 / yrs) - 1), sharpe=float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0,
                mdd=float((s / s.cummax() - 1).min()), h1=cg(h1), h2=cg(h2), trades=n_in, skipped_lot=skipped_lot, skipped_band=skipped_band,
                median_v20_bn=float(np.nanmedian(vals) / 1e9) if vals else None,
                by_year={int(y): round(float(v["last"] / v["first"] - 1) * 100, 1) for y, v in by.iterrows()}, final=float(s.iloc[-1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    P, unis, comp, Hp, Lp = E.load_all(dsn(), CACHE, board="pit")
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L = P["adj"].to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    arms, score, v20 = arms_masks(P, unis, comp)
    P["_v20"] = v20.to_numpy(float)
    sim_ok = np.asarray(dates >= SIM_START)[:, None]
    print("panel", dates[0].date(), dates[-1].date(), A.shape, flush=True)
    res = {}
    for name, (entry, uni, rule) in arms.items():
        x = 0.10 if rule == "trail10" else 0.25
        R, trs, _ = E.run_book(A, H, L, c_in, c_out, entry & sim_ok, score, rules(A, x), uni)
        tr = [(t[0], t[1], t[4]) for t in trs]
        sim = sim_stats(R.to_numpy(), dates, SIM_START)
        b1, b2 = replay(tr, P), replay(tr, P, cost_mult=2.0)
        res[name] = dict(sim=sim, sim_trades=len(trs), book=b1, book_cost2=dict(cagr=b2["cagr"], sharpe=b2["sharpe"], mdd=b2["mdd"]))
        print(name, "sim", {k: round(v, 3) for k, v in sim.items()}, "book", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in b1.items() if k != "by_year"},
              b1["by_year"], "x2", round(b2["sharpe"], 2), flush=True)
    ref = res["REF"]
    ver = {}
    for name in TRIALS:
        b, s = res[name]["book"], res[name]
        checks = dict(sharpe=b["sharpe"] > ref["book"]["sharpe"], cagr=b["cagr"] >= ref["book"]["cagr"], mdd=b["mdd"] >= ref["book"]["mdd"] - 0.10,
                      halves=b["h1"] > 0 and b["h2"] > 0, cost2=s["book_cost2"]["sharpe"] > ref["book_cost2"]["sharpe"],
                      sim=s["sim"]["sharpe"] > ref["sim"]["sharpe"])
        ver[name] = dict(checks=checks, better=all(checks.values()))
    res["verdicts"] = ver
    print(json.dumps(ver, indent=1))
    json.dump(res, open(os.path.join(HERE, "IDX_TREND_C0_2026-09-27.json"), "w"), indent=1, default=str)
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": TRIALS, "n_trials_cumulative": N_BEFORE + len(TRIALS)},
                                  summary={k: {"book": v["book"], "sim": v["sim"]} if k != "verdicts" else v for k, v in res.items()},
                                  names=[], report_path="research/IDX_TREND_C0_2026-09-27.md")
            print("study id", sid)


if __name__ == "__main__":
    main()
