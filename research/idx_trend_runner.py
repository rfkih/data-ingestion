#!/usr/bin/env python3
"""IDX menu TR-3 - two fixes for the multibaggers the deployed trend sleeve lets go (operator 2026-09-27 "iya jalankan").

Diagnostic (research-scratch/idx/daytrade2/diag_trend5.py, no trial): of ANTM / BRIS / PANI / AMMN / HRTA the sleeve bought only
PANI once (2024-08 -> 10, +94 %, cut by the 10 % trail before the next leg) and HRTA once (2025-08, -13 %, stopped just before a
+370 % run). ANTM / BRIS / AMMN are BLUE (excluded on purpose, LIQ-wide trend tested worse in IDX_BEYOND). Two leaks remain:
  the exit (a 10 % trail cuts the runners; a full 25 % trail, TR-2's T1, loses the many small wins), and
  the lot size (Rp 20 m x 5 % = Rp 1 m < one lot of a Rp 10,000+ name: PANI 329 days, AMMN 92 days above Rp 10,000).

Same machinery as TR-2 (research/idx_trend_c0.py): PIT panels tmp/exit_cache_pit.pkl, K-10 simulator idx_exit.run_book,
rupiah replay (Rp 20 m, 5 % of NAV, 20 max, lots of 100, offer / bid, band realism), deployed entry / universe / regime gate.
PRE-REGISTERED (2 trials; cumulative 1077 + 2 = 1079).
  T5 RUNNER   sell HALF the position at the close after the first close <= 90 % of the peak (the deployed trail), the rest after
              the first close <= 75 % of the peak (partial exits in both the K-10 simulator and the rupiah replay)
  T6 MIN_LOT  REF, but when 5 % of NAV buys less than one lot, buy ONE lot if it costs <= 10 % of NAV (rupiah replay only; the
              K-10 simulator has no lots, so its check is n/a)
READING RULE = TR-2's: BETTER than REF only if ALL on the rupiah book 2022-01 -> cache end: Sharpe > REF; CAGR >= REF; mDD no
more than 10 points deeper; CAGR > 0 in both halves (2022-01..2024-06, 2024-07..end); costs x 2 Sharpe > REF's at x 2; K-10
simulator Sharpe > REF's (T5). Sanity: REF here must equal TR-2's REF. Reported: trades on the five names.
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
import idx_swing2 as S  # noqa: E402
import idx_trend_c0 as T  # noqa: E402

STUDY, N_BEFORE = "trend_runner", 1077
TRIALS = ["T5", "T6"]
FIVE = ["ANTM", "BRIS", "PANI", "AMMN", "HRTA"]


def runner_rule(A):
    def f(t, j, p):
        st = p["state"]
        if A[t, j] <= 0.75 * p["peak"]:
            return 1.0
        if not st.get("half") and A[t, j] <= 0.90 * p["peak"]:
            st["half"] = True
            return 0.5
        return 0
    return f


def legs_for(A, e, j, final, runner):
    """[(day, fraction of the original)] - executed at the close of `day`."""
    if not runner:
        return [(final, 1.0)]
    peak = A[e, j]
    for k in range(e, final):
        if np.isnan(A[k, j]):
            continue
        peak = max(peak, A[k, j])
        if A[k, j] <= 0.90 * peak and k + 1 < final:
            return [(k + 1, 0.5), (final, 0.5)]
    return [(final, 1.0)]


def replay(trades, P, cost_mult=1.0, min_lot=False):
    adj, raw, off, bid = (P[k].to_numpy(float) for k in ("adj", "close", "offer", "bid"))
    dates = P["adj"].index
    Tn = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(T.START)))
    fb, fs = T.FEE_BUY * cost_mult, T.FEE_SELL * cost_mult
    entries = {}
    for e, j, legs in trades:
        entries.setdefault(e, []).append((j, legs))
    cash, held, nav, n_in, minlot_used = T.CAPITAL, {}, np.full(Tn, np.nan), 0, 0
    fills = []
    for t in range(t0, Tn):
        for j in list(held):
            p = held[j]
            due = [lg for lg in p["legs"] if lg[0] <= t]
            if not due:
                continue
            r = raw[t, j] / raw[t - 1, j] - 1 if raw[t - 1, j] > 0 else 0.0
            if np.isnan(adj[t, j]) or (r <= T.DNLOCK and not (bid[t, j] > 0) and t - due[0][0] < 10):
                continue
            px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - T.tick(raw[t, j])
            frac = sum(lg[1] for lg in due)
            value = p["units0"] * frac * (adj[t, j] / p["a_in"]) * (1 - cost_mult * (1 - px / raw[t, j]))
            cash += value * (1 - fs)
            p["left"] -= frac
            p["legs"] = [lg for lg in p["legs"] if lg[0] > t]
            p["got"] += value * (1 - fs)
            if p["left"] <= 1e-9 or not p["legs"]:
                fills.append(dict(code=P["adj"].columns[j], d_in=dates[p["t"]].date(), d_out=dates[t].date(), ret=p["got"] / p["cost"] - 1))
                held.pop(j)
        mv = sum(p["units0"] * p["left"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav_now = cash + mv
        for j, legs in entries.get(t, []):
            if j in held or len(held) >= T.MAX_POS or np.isnan(adj[t, j]) or not raw[t, j] > 0:
                continue
            r = raw[t, j] / raw[t - 1, j] - 1 if raw[t - 1, j] > 0 else 0.0
            if r >= T.UPCAP:
                continue
            px = off[t, j] if off[t, j] > 0 and off[t, j] >= raw[t, j] else raw[t, j] + T.tick(raw[t, j])
            px = raw[t, j] * (1 + cost_mult * (px / raw[t, j] - 1))
            lots = int((T.PCT * nav_now) // (px * T.LOT * (1 + fb)))
            if lots < 1 and min_lot and T.LOT * px * (1 + fb) <= 0.10 * nav_now:
                lots, minlot_used = 1, minlot_used + 1
            cost = lots * T.LOT * px * (1 + fb)
            if lots < 1 or cost > cash:
                continue
            cash -= cost
            held[j] = {"t": t, "a_in": adj[t, j], "units0": lots * T.LOT * raw[t, j], "legs": list(legs), "left": 1.0, "cost": cost, "got": 0.0}
            n_in += 1
        mv = sum(p["units0"] * p["left"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav[t] = cash + mv
    s = pd.Series(nav[t0:], index=dates[t0:]).ffill()
    r = s.pct_change().fillna(0)
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    half = s.index.searchsorted(pd.Timestamp("2024-07-01"))
    cg = lambda x: float((x.iloc[-1] / x.iloc[0]) ** (365.25 / max(1, (x.index[-1] - x.index[0]).days)) - 1)
    by = s.groupby(s.index.year).agg(["first", "last"])
    return dict(cagr=float((s.iloc[-1] / T.CAPITAL) ** (1 / yrs) - 1), sharpe=float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0,
                mdd=float((s / s.cummax() - 1).min()), h1=cg(s.iloc[:half]), h2=cg(s.iloc[half - 1:]), trades=n_in, minlot_used=minlot_used,
                by_year={int(y): round(float(v["last"] / v["first"] - 1) * 100, 1) for y, v in by.iterrows()},
                five=[f"{x['code']} {x['d_in']}->{x['d_out']} {x['ret'] * 100:+.0f}%" for x in fills if x["code"] in FIVE])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    P, unis, comp, Hp, Lp = E.load_all(T.dsn(), T.CACHE, board="pit")
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L = P["adj"].to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    arms, score, v20 = T.arms_masks(P, unis, comp)
    entry, uni, _ = arms["REF"]
    sim_ok = np.asarray(dates >= T.SIM_START)[:, None]
    res = {}
    for name, rule, runner, min_lot in (("REF", T.rules(A, 0.10), False, False), ("T5", runner_rule(A), True, False),
                                        ("T6", T.rules(A, 0.10), False, True)):
        R, trs, _ = E.run_book(A, H, L, c_in, c_out, entry & sim_ok, score, rule, uni)
        tr = [(t[0], t[1], legs_for(A, t[0], t[1], t[0] + t[4], runner)) for t in trs]
        sim = T.sim_stats(R.to_numpy(), dates, T.SIM_START)
        b1 = replay(tr, P, min_lot=min_lot)
        b2 = replay(tr, P, cost_mult=2.0, min_lot=min_lot)
        res[name] = dict(sim=sim, book=b1, book_cost2=dict(cagr=b2["cagr"], sharpe=b2["sharpe"], mdd=b2["mdd"]))
        print(name, "sim", {k: round(v, 3) for k, v in sim.items()}, "book", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in b1.items()},
              "x2", round(b2["sharpe"], 2), flush=True)
    ref = res["REF"]
    ver = {}
    for name in TRIALS:
        b, s = res[name]["book"], res[name]
        checks = dict(sharpe=b["sharpe"] > ref["book"]["sharpe"], cagr=b["cagr"] >= ref["book"]["cagr"], mdd=b["mdd"] >= ref["book"]["mdd"] - 0.10,
                      halves=b["h1"] > 0 and b["h2"] > 0, cost2=s["book_cost2"]["sharpe"] > ref["book_cost2"]["sharpe"],
                      sim=(s["sim"]["sharpe"] > ref["sim"]["sharpe"]) if name == "T5" else True)
        ver[name] = dict(checks=checks, better=all(checks.values()))
    res["verdicts"] = ver
    print(json.dumps(ver, indent=1))
    json.dump(res, open(os.path.join(HERE, "IDX_TREND_RUNNER_2026-09-27.json"), "w"), indent=1, default=str)
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(T.dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": TRIALS, "n_trials_cumulative": N_BEFORE + len(TRIALS)},
                                  summary=res, names=[], report_path="research/IDX_TREND_RUNNER_2026-09-27.md")
            print("study id", sid)


if __name__ == "__main__":
    main()
