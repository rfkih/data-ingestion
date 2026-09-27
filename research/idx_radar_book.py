#!/usr/bin/env python3
"""IDX menu RB-1 - a trading book built on the multibagger radar (operator 2026-09-27: "berdasarkan radar ini bikin strategi
trading-nya, cara optimize profit dan minimize drawdown").

MB-1 (#403): as a RADAR the momentum flag works every year (C0 touches 2x within 12 m 30 % vs 18 % random), and it works better
with context: C0 + an exchange-query (UMA) reply in the prior 20 sessions 42 %, C0 + a change-of-control / restructuring
announcement in the prior 120 sessions 45 %. Its price: about half the flagged names are at some point 30 % under the flag
price. SX-1 / TR-2 / TR-3 showed that plain C0 with a 25 % trail is no better than the deployed trend sleeve on the desk engine.
Three levers aimed at those two facts, none tested before on this desk:
  precision  enter only the radar's high tiers;
  the -30 % tail  an INITIAL stop at -15 % from entry (cut the duds before they fall far; Han, Zhou & Zhu 2016: a 10-15 % loss
                  stop on momentum winners roughly doubled their Sharpe) + the 25 % trail from the peak for the rockets;
  drawdown   size by tier and scale NEW entries down when the book's own 60-session volatility is high (vol targeting, the
             form of risk management that survived out of sample for momentum - Barroso & Santa-Clara 2015, Cederburg et al. 2020).

MACHINERY = TR-2's (research/idx_trend_c0.py): PIT panels tmp/exit_cache_pit.pkl, K-10 event simulator idx_exit.run_book
(signal close t, fill close t+1 at the offer, exits at the bid), then a rupiah replay: Rp 20 m, lots of 100, <= 20 positions,
fees 0.10 / 0.20 %, no fill on a >= 18 % day, no sale on a <= -6.5 % day without a bid. Universe U1 (20-day value >= Rp 1 bn,
close >= Rp 50, board on the day). Tier flags as MB-1 (announcements from 2023-07-03).
WINDOW: 2023-07-03 -> cache end (the announcement archive); every arm and reference on the same window.

PRE-REGISTERED (4 trials; cumulative 1087 + 4 = 1091):
  R1 TOP       entry = C0 + (UMA in 20 sessions OR control/restructuring in 120); 10 % of NAV each; exit stop -15 % / trail 25 %
  R2 ATTN      entry = C0 + attention (20-day value >= 3x its 250-day mean); 5 % of NAV; same exit
  R3 TIERED    entry = any C0; size by tier: top 10 %, attention 7.5 %, plain C0 5 %; same exit; higher tier first
  R4 TIERED_VT R3 with new-entry size x min(1, 20 % / the book's annualised 60-session volatility)
  References (not trials): REF = the deployed trend sleeve; C0 = plain C0, 5 %, trail 25 % only (TR-2's T3) - same window.
READING RULE - a trial is BETTER only if ALL on the rupiah book: Sharpe > max(REF, C0); CAGR >= REF's; mDD no deeper than REF's
mDD - 10 points; CAGR > 0 in both halves (2023-07..2024-12, 2025-01..end); with costs x 2 Sharpe still > REF's at x 2. Also
reported: exits by kind, the share of trades stopped at -15 %, the five names. A BETTER arm is a PAPER book proposal only.
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
sys.path.insert(0, HERE)
import idx_exit as E  # noqa: E402
import idx_mb_radar as MB  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_trend_c0 as T  # noqa: E402

STUDY, N_BEFORE = "radar_book", 1087
TRIALS = ["R1", "R2", "R3", "R4"]
START = pd.Timestamp("2023-07-03")
HALF = pd.Timestamp("2025-01-01")
FIVE = ["ANTM", "BRIS", "PANI", "AMMN", "HRTA"]
VT_TARGET = 0.20


def masks(P, unis, comp):
    arms, score, v20 = T.arms_masks(P, unis, comp)
    adj, vol, close = P["adj"], P["volume"], P["close"]
    idx, cols = adj.index, adj.columns
    c0_entry, u1 = arms["T3"][0], arms["T3"][1]
    value = close * vol
    attn = ((value.rolling(20, min_periods=15).mean() / value.rolling(250, min_periods=200).mean()) >= 3).to_numpy(bool)
    with psycopg.connect(T.dsn()) as conn:
        _, ev = MB.load(conn)
    ctl = MB.event_mask(ev, idx, cols, lambda r: r.kind == "control_change" or any(w in r.title for w in ("pengambilalihan", "pengendali", "tender wajib"))
                        and "persidangan" not in r.title and "pkpu" not in r.title)
    rst = MB.event_mask(ev, idx, cols, lambda r: any(w in r.title for w in ("penggabungan usaha", "merger", "peleburan", "perubahan kegiatan usaha", "transaksi material")))
    uma = MB.event_mask(ev, idx, cols, lambda r: r.kind == "exchange_query")
    top = (MB.recent(uma, 20) | MB.recent(ctl | rst, 120)).to_numpy(bool)
    tier = np.where(c0_entry & top, 3, np.where(c0_entry & attn, 2, np.where(c0_entry, 1, 0))).astype(float)
    return arms, score, c0_entry, u1, tier


def stop_trail(A, stop=0.15, trail=0.25):
    def f(t, j, p):
        if stop is not None and A[t, j] <= (1 - stop) * p["a0"]:
            p["state"]["why"] = "stop"
            return 1.0
        if A[t, j] <= (1 - trail) * p["peak"]:
            p["state"]["why"] = "trail"
            return 1.0
        return 0
    return f


def replay(trades, P, start, cost_mult=1.0, vt=False):
    """trades: (e, j, x, pct). Rupiah book as TR-2's replay, with a per-trade size and optional vol targeting."""
    adj, raw, off, bid = (P[k].to_numpy(float) for k in ("adj", "close", "offer", "bid"))
    dates = P["adj"].index
    Tn = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(start)))
    fb, fs = T.FEE_BUY * cost_mult, T.FEE_SELL * cost_mult
    entries = {}
    for e, j, x, pct in trades:
        entries.setdefault(e, []).append((j, x, pct))
    cash, held, nav, n_in = T.CAPITAL, {}, np.full(Tn, np.nan), 0
    fills = []
    for t in range(t0, Tn):
        for j in [j for j, p in held.items() if p["x"] <= t]:
            p = held[j]
            r = raw[t, j] / raw[t - 1, j] - 1 if raw[t - 1, j] > 0 else 0.0
            if np.isnan(adj[t, j]) or (r <= T.DNLOCK and not (bid[t, j] > 0) and t - p["x"] < 10):
                continue
            px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - T.tick(raw[t, j])
            value = p["units"] * (adj[t, j] / p["a_in"]) * (1 - cost_mult * (1 - px / raw[t, j]))
            cash += value * (1 - fs)
            fills.append(dict(code=P["adj"].columns[j], d_in=dates[p["t"]].date(), ret=value * (1 - fs) / p["cost"] - 1))
            held.pop(j)
        mv = sum(p["units"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav_now = cash + mv
        scale = 1.0
        if vt and t - t0 > 60:
            rr = np.diff(nav[t - 61:t]) / nav[t - 61:t - 1]
            v = np.nanstd(rr) * np.sqrt(252)
            scale = min(1.0, VT_TARGET / v) if v > 0 else 1.0
        for j, x, pct in sorted(entries.get(t, []), key=lambda z: -z[2]):
            if j in held or len(held) >= T.MAX_POS or np.isnan(adj[t, j]) or not raw[t, j] > 0:
                continue
            r = raw[t, j] / raw[t - 1, j] - 1 if raw[t - 1, j] > 0 else 0.0
            if r >= T.UPCAP:
                continue
            px = off[t, j] if off[t, j] > 0 and off[t, j] >= raw[t, j] else raw[t, j] + T.tick(raw[t, j])
            px = raw[t, j] * (1 + cost_mult * (px / raw[t, j] - 1))
            lots = int((pct * scale * nav_now) // (px * T.LOT * (1 + fb)))
            cost = lots * T.LOT * px * (1 + fb)
            if lots < 1 or cost > cash:
                continue
            cash -= cost
            held[j] = {"t": t, "a_in": adj[t, j], "units": lots * T.LOT * raw[t, j], "x": x, "cost": cost}
            n_in += 1
        mv = sum(p["units"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav[t] = cash + mv
    s = pd.Series(nav[t0:], index=dates[t0:]).ffill()
    r = s.pct_change().fillna(0)
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    h = s.index.searchsorted(HALF)
    cg = lambda x: float((x.iloc[-1] / x.iloc[0]) ** (365.25 / max(1, (x.index[-1] - x.index[0]).days)) - 1)
    by = s.groupby(s.index.year).agg(["first", "last"])
    return dict(cagr=float((s.iloc[-1] / T.CAPITAL) ** (1 / yrs) - 1), sharpe=float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0,
                mdd=float((s / s.cummax() - 1).min()), h1=cg(s.iloc[:h]), h2=cg(s.iloc[h - 1:]), trades=n_in, final=float(s.iloc[-1]),
                by_year={int(y): round(float(v["last"] / v["first"] - 1) * 100, 1) for y, v in by.iterrows()},
                five=[f"{f['code']} {f['d_in']} {f['ret'] * 100:+.0f}%" for f in fills if f["code"] in FIVE])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    P, unis, comp, Hp, Lp = E.load_all(T.dsn(), T.CACHE, board="pit")
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L = P["adj"].to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    arms, vr, c0_entry, u1, tier = masks(P, unis, comp)
    ok = np.asarray(dates >= START - pd.Timedelta(days=5))[:, None]
    size_of = {3: 0.10, 2: 0.075, 1: 0.05}
    cfg = {  # name: (entry mask, universe, rule, score, sizing(tier)->pct, vt)
        "REF": (arms["REF"][0], arms["REF"][1], T.rules(A, 0.10), vr.to_numpy(float) if hasattr(vr, "to_numpy") else vr, lambda k: 0.05, False),
        "C0": (c0_entry, u1, T.rules(A, 0.25), tier, lambda k: 0.05, False),
        "R1": (c0_entry & (tier == 3), u1, stop_trail(A), tier, lambda k: 0.10, False),
        "R2": (c0_entry & (tier >= 2), u1, stop_trail(A), tier, lambda k: 0.05, False),
        "R3": (c0_entry, u1, stop_trail(A), tier, lambda k: size_of[k], False),
        "R4": (c0_entry, u1, stop_trail(A), tier, lambda k: size_of[k], True),
    }
    res = {}
    for name, (entry, uni, rule, score, sizing, vt) in cfg.items():
        R, trs, _ = E.run_book(A, H, L, c_in, c_out, entry & ok, score, rule, uni)
        tr = [(t[0], t[1], t[0] + t[4], sizing(int(tier[t[0] - 1, t[1]]) or 1)) for t in trs]
        b1, b2 = replay(tr, P, START, vt=vt), replay(tr, P, START, cost_mult=2.0, vt=vt)
        stopped = float(np.mean([t[3] <= -0.14 for t in trs])) if trs else 0.0
        res[name] = dict(book=b1, book_cost2=dict(cagr=b2["cagr"], sharpe=b2["sharpe"], mdd=b2["mdd"]), sim_trades=len(trs),
                         share_near_stop=stopped)
        print(name, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in b1.items() if k not in ("five",)}, "x2", round(b2["sharpe"], 2),
              "| five", b1["five"], flush=True)
    ref, c0 = res["REF"]["book"], res["C0"]["book"]
    ver = {}
    for name in TRIALS:
        b = res[name]["book"]
        checks = dict(sharpe=b["sharpe"] > max(ref["sharpe"], c0["sharpe"]), cagr=b["cagr"] >= ref["cagr"], mdd=b["mdd"] >= ref["mdd"] - 0.10,
                      halves=b["h1"] > 0 and b["h2"] > 0, cost2=res[name]["book_cost2"]["sharpe"] > res["REF"]["book_cost2"]["sharpe"])
        ver[name] = dict(checks=checks, better=all(checks.values()))
    res["verdicts"] = ver
    print(json.dumps(ver, indent=1))
    json.dump(res, open(os.path.join(HERE, "IDX_RADAR_BOOK_2026-09-27.json"), "w"), indent=1, default=str)
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(T.dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": TRIALS, "n_trials_cumulative": N_BEFORE + len(TRIALS)},
                                  summary=res, names=[], report_path="research/IDX_RADAR_BOOK_2026-09-27.md")
            print("study id", sid)


if __name__ == "__main__":
    main()
