#!/usr/bin/env python3
"""IDX menu RB-2 - the C0 radar signal as a WIDE sleeve (operator 2026-09-27 "okay lanjutkan", after the RB-1 diagnosis).

RB-1 diagnosis (research-scratch/idx/daytrade2/radar_diag.py): the K-10 book took 11 % of the radar's trades (1 % in 2025), so its
result was a lottery on which rockets landed in a slot; taking EVERY flag (calendar-time, equal weight) the C0 signal with a
-15 % stop / 25 % trail earned Sharpe 1.23 from 2022-01 (20.9 %/yr, mDD -36 % fully invested) and was stable across start dates,
while the deployed trend rule gains nothing from breadth (0.88 vs 0.95). The remedy tested here: many small positions (breadth)
and a capped total exposure (drawdown by allocation, not by exits).

MACHINERY: PIT panels tmp/exit_cache_pit.pkl; trades = every C0 flag in U1 (20-day value >= Rp 1 bn, close >= Rp 50, board on the
day), one position per name, fill at the close after the flag (no fill on a >= 18 % day), exit at the close after the first close
<= 85 % of the entry (stop) or <= 75 % of the peak (trail). Rupiah replay: 1.25 % of NAV per position, at most 40 open (= <= 50 %
exposure), lots of 100, entry at the closing offer, exit at the closing bid, fees 0.10 / 0.20 %, no sale on a <= -6.5 % day
without a bid; on a crowded day the higher attention ratio goes first. REF = the deployed trend sleeve's book exactly as TR-2
(K-10 run_book trades, 5 % of NAV) at the SAME capital.

PRE-REGISTERED (2 trials; cumulative 1091 + 2 = 1093):
  W1  capital Rp 20 m          W2  capital Rp 200 m (the lot constraint relaxed; same percentages)
READING RULE - a trial is BETTER only if ALL: (a) Sharpe > REF's (same capital) at EACH start 2022-01-03, 2022-07-01, 2023-01-02,
2023-07-03 (the check RB-1 failed); (b) mDD no more than 10 points deeper than REF's at each start; (c) >= 3 of 4 exit neighbours
(stop 10/20 % x trail 20/30 %) Sharpe > REF from 2022-01; (d) costs x 2 Sharpe > REF's at x 2 from 2022-01. A BETTER arm is a
proposal for a PAPER sleeve, not a change to the live book. READ-ONLY on the DB except one idx.study row (--no-store to skip).
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
import idx_radar_book as RB  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_trend_c0 as T  # noqa: E402

STUDY, N_BEFORE = "c0_wide", 1091
STARTS = ["2022-01-03", "2022-07-01", "2023-01-02", "2023-07-03"]
PCT_W, MAXPOS_W = 0.0125, 40


def all_trades(A, raw, c_in, flag, strength, stop=0.15, trail=0.25, t0=0):
    out = []
    Tn, N = A.shape
    for j in range(N):
        i = t0
        while i < Tn - 2:
            if not flag[i, j]:
                i += 1
                continue
            e = i + 1
            if np.isnan(A[e, j]) or (raw[e - 1, j] > 0 and raw[e, j] / raw[e - 1, j] - 1 >= T.UPCAP) or not np.isfinite(c_in[e, j]):
                i += 1
                continue
            peak, x = A[e, j], None
            for k in range(e + 1, Tn):
                if np.isnan(A[k, j]):
                    continue
                peak = max(peak, A[k, j])
                if (stop is not None and A[k, j] <= (1 - stop) * A[e, j]) or A[k, j] <= (1 - trail) * peak:
                    x = k + 1
                    break
            if x is None or x >= Tn:
                x = Tn - 1
            s = strength[i, j]
            out.append((e, j, x, float(s) if np.isfinite(s) else 0.0))
            i = x + 1
    return out


def replay(trades, P, start, capital, pct, maxpos, cost_mult=1.0):
    adj, raw, off, bid = (P[k].to_numpy(float) for k in ("adj", "close", "offer", "bid"))
    dates = P["adj"].index
    Tn = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(start))))
    fb, fs = T.FEE_BUY * cost_mult, T.FEE_SELL * cost_mult
    entries = {}
    for e, j, x, s in trades:
        if e >= t0:
            entries.setdefault(e, []).append((j, x, s))
    cash, held, nav, n_in, skip_lot, skip_cap = capital, {}, np.full(Tn, np.nan), 0, 0, 0
    for t in range(t0, Tn):
        for j in [j for j, p in held.items() if p["x"] <= t]:
            p = held[j]
            r = raw[t, j] / raw[t - 1, j] - 1 if raw[t - 1, j] > 0 else 0.0
            if np.isnan(adj[t, j]) or (r <= T.DNLOCK and not (bid[t, j] > 0) and t - p["x"] < 10):
                continue
            px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - T.tick(raw[t, j])
            cash += p["units"] * (adj[t, j] / p["a_in"]) * (1 - cost_mult * (1 - px / raw[t, j])) * (1 - fs)
            held.pop(j)
        mv = sum(p["units"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav_now = cash + mv
        for j, x, s in sorted(entries.get(t, []), key=lambda z: -z[2]):
            if j in held or np.isnan(adj[t, j]) or not raw[t, j] > 0:
                continue
            if len(held) >= maxpos:
                skip_cap += 1
                continue
            px = off[t, j] if off[t, j] > 0 and off[t, j] >= raw[t, j] else raw[t, j] + T.tick(raw[t, j])
            px = raw[t, j] * (1 + cost_mult * (px / raw[t, j] - 1))
            lots = int((pct * nav_now) // (px * T.LOT * (1 + fb)))
            cost = lots * T.LOT * px * (1 + fb)
            if lots < 1:
                skip_lot += 1
                continue
            if cost > cash:
                continue
            cash -= cost
            held[j] = {"a_in": adj[t, j], "units": lots * T.LOT * raw[t, j], "x": x}
            n_in += 1
        mv = sum(p["units"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav[t] = cash + mv
    s = pd.Series(nav[t0:], index=dates[t0:]).ffill()
    r = s.pct_change().fillna(0)
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    by = s.groupby(s.index.year).agg(["first", "last"])
    return dict(cagr=float((s.iloc[-1] / capital) ** (1 / yrs) - 1), sharpe=float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0,
                mdd=float((s / s.cummax() - 1).min()), trades=n_in, skip_lot=skip_lot, skip_cap=skip_cap,
                by_year={int(y): round(float(v["last"] / v["first"] - 1) * 100, 1) for y, v in by.iterrows()}, _nav=s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    P, unis, comp, Hp, Lp = E.load_all(T.dsn(), T.CACHE, board="pit")
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L = P["adj"].to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    raw = P["close"].to_numpy(float)
    arms, vr, c0_entry, u1, tier = RB.masks(P, unis, comp)
    value = P["close"] * P["volume"]
    attn = (value.rolling(20, min_periods=15).mean() / value.rolling(250, min_periods=200).mean()).to_numpy(float)
    t_first = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(STARTS[0])))) - 1
    flag = c0_entry & u1
    base_tr = all_trades(A, raw, c_in, flag, attn, t0=t_first)
    # REF: the deployed trend sleeve's own K-10 trades, 5 % each (TR-2)
    vr_np = vr.to_numpy(float) if hasattr(vr, "to_numpy") else vr
    ok = np.asarray(dates >= pd.Timestamp(STARTS[0]) - pd.Timedelta(days=5))[:, None]
    _, trs, _ = E.run_book(A, H, L, c_in, c_out, arms["REF"][0] & ok, vr_np, T.rules(A, 0.10), arms["REF"][1])
    ref_tr = [(t[0], t[1], t[0] + t[4], 0.0) for t in trs]
    res = {}
    for name, cap in (("W1", 20e6), ("W2", 200e6)):
        rows = {}
        for st in STARTS:
            w = replay(base_tr, P, st, cap, PCT_W, MAXPOS_W)
            rf = replay(ref_tr, P, st, cap, 0.05, 20)
            rows[st] = dict(w=w, ref=rf)
            print(f"{name} from {st}: W CAGR {w['cagr'] * 100:5.1f}% Sh {w['sharpe']:.2f} mDD {w['mdd'] * 100:4.0f}% trades {w['trades']} "
                  f"skip_lot {w['skip_lot']} skip_cap {w['skip_cap']} | REF CAGR {rf['cagr'] * 100:5.1f}% Sh {rf['sharpe']:.2f} mDD {rf['mdd'] * 100:4.0f}%", flush=True)
        nb = {}
        for stp in (0.10, 0.20):
            for tl in (0.20, 0.30):
                w = replay(all_trades(A, raw, c_in, flag, attn, stp, tl, t_first), P, STARTS[0], cap, PCT_W, MAXPOS_W)
                nb[f"{stp}/{tl}"] = dict(cagr=w["cagr"], sharpe=w["sharpe"], mdd=w["mdd"])
        w2 = replay(base_tr, P, STARTS[0], cap, PCT_W, MAXPOS_W, cost_mult=2.0)
        r2 = replay(ref_tr, P, STARTS[0], cap, 0.05, 20, cost_mult=2.0)
        checks = dict(sharpe_all_starts=all(v["w"]["sharpe"] > v["ref"]["sharpe"] for v in rows.values()),
                      mdd_all_starts=all(v["w"]["mdd"] >= v["ref"]["mdd"] - 0.10 for v in rows.values()),
                      neighbours=sum(v["sharpe"] > rows[STARTS[0]]["ref"]["sharpe"] for v in nb.values()) >= 3,
                      cost2=w2["sharpe"] > r2["sharpe"])
        res[name] = dict(capital=cap, starts=rows, neighbours=nb, cost2=dict(w=w2["sharpe"], ref=r2["sharpe"]), checks=checks, better=all(checks.values()))
        print(name, "neighbours", {k: round(v["sharpe"], 2) for k, v in nb.items()}, "cost x2", round(w2["sharpe"], 2), "vs", round(r2["sharpe"], 2))
        print(name, "checks", checks, "BETTER" if all(checks.values()) else "no", flush=True)
        print(name, "by year from 2022-01:", rows[STARTS[0]]["w"]["by_year"], "| REF", rows[STARTS[0]]["ref"]["by_year"], flush=True)
    for v in res.values():
        for row in v["starts"].values():
            row["w"].pop("_nav", None); row["ref"].pop("_nav", None)
    json.dump(res, open(os.path.join(HERE, "IDX_C0_WIDE_2026-09-27.json"), "w"), indent=1, default=str)
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(T.dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["W1", "W2"], "n_trials_cumulative": N_BEFORE + 2},
                                  summary=res, names=[], report_path="research/IDX_C0_WIDE_2026-09-27.md")
            print("study id", sid)


if __name__ == "__main__":
    main()
