#!/usr/bin/env python3
"""IDX menu 7 — is the menu-6 lead real? Robustness of hi60|trail10 on the wide liquid universe, and the operator's
combination: the same trend entry restricted to names passing the audited fundamental gate, point-in-time.

Menu 6 (research/idx_trend.py) found one arm in ten with a trend-following signature and +18.9 %/yr after costs — hi60 (close at a
60-day high, above the 200-day average, volume >= 1.5x its 20-day median) with a 10 % trailing stop, on liquid names down to Rp 100.
One arm can be a lucky corner. This menu does not tune it; it asks whether its neighbours agree and whether fundamentals steady it.

PRE-REGISTERED MENU (10 trials; cumulative 277 + 10 = 287). Declared before the run; nothing tuned afterwards.
  Same book, costs and execution as menu 6 (K = 10 slots, close-to-close, closing offer/bid, Stockbit fees). Universe LIQ unless stated.
  Neighbours of the lead (one parameter moved at a time from 60-day high / 10 % trail / 1.5x volume):
    trail8, trail12, trail15         trailing stop 8 / 12 / 15 %
    hi40, hi90                       40- / 90-day high
    vol1, vol2                       volume >= 1.0x / 2.0x the 20-day median
  The operator's combination (fundamental gate, point-in-time monthly from metrics.fundamentals_asof, forward-filled):
    loose                            lead entry only for names passing the loose gate (audited profit > 0, ROE >= 5 %) on that day
    strict                           lead entry only for names passing the strict gate (+ ROE >= 10 %, prior-year profit, CFO > 0, D/E <= 1.5)
  Where the edge lives:
    small                            lead entry on LIQ names that are NOT in BLUE (value < Rp 20 bn or price < Rp 1,000)
  References (not trials): the lead itself (60/10/1.5, LIQ) re-run; random entries + trail10 on LIQ; COMPOSITE.
READING RULES (declared before the run):
  Candidate for money: the menu-6 rule unchanged (>= 150 trades; t >= 2.5; Sharpe >= 1.0; max DD <= 25 %; >= 5 of 7 years
    positive; Sharpe >= random + 0.5).
  Robustness read (decides whether the lead deserves an out-of-sample paper track with no money): the lead is ROBUST if at least
    5 of its 7 neighbours show CAGR >= 10 % with t >= 2.0; FRAGILE otherwise. A robust lead goes to a paper book `trend` for
    >= 60 closed trades; a fragile one is recorded as luck. The gated arms are read against the lead: steadier means a shallower
    max drawdown with at least 70 % of the lead's CAGR.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_trend2.py
"""
from __future__ import annotations

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
import idx_swing2 as S  # noqa: E402
import idx_trend as T  # noqa: E402
from blackheart_ingest.idx import metrics  # noqa: E402

N_BEFORE = 277
GRID = {"trail8": (60, 0.08, 1.5), "trail12": (60, 0.12, 1.5), "trail15": (60, 0.15, 1.5), "hi40": (40, 0.10, 1.5), "hi90": (90, 0.10, 1.5),
        "vol1": (60, 0.10, 1.0), "vol2": (60, 0.10, 2.0)}
LEAD = (60, 0.10, 1.5)
ARMS = list(GRID) + ["loose", "strict", "small"]
assert len(ARMS) == 10


def gate_masks(conn, dates, cols):
    """Point-in-time gates: evaluated on the first trading day of each month for every panel name, forward-filled."""
    firsts = [d for i, d in enumerate(dates) if i == 0 or d.month != dates[i - 1].month]
    loose = pd.DataFrame(False, index=dates, columns=cols)
    strict = pd.DataFrame(False, index=dates, columns=cols)
    codes = list(cols)
    for d in firsts:
        f = metrics.fundamentals_asof(conn, d.date(), codes)
        lo = [c for c in codes if f.get(c, {}).get("gate_loose")]
        st = [c for c in codes if f.get(c, {}).get("gate_strict")]
        loose.loc[d, lo] = True
        strict.loc[d, st] = True
    # forward-fill month by month
    idx_first = pd.Series(np.nan, index=dates)
    idx_first[firsts] = range(len(firsts))
    grp = idx_first.ffill()
    loose = loose.groupby(grp.values).transform("max").astype(bool)
    strict = strict.groupby(grp.values).transform("max").astype(bool)
    return loose, strict


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        P = S.panels(bars, listing)
        _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
        adj = P["adj"]
        loose, strict = gate_masks(conn, adj.index, adj.columns)
    c_in, c_out = S.costs(P)
    close, vol = P["close"], P["volume"]
    dates = adj.index
    A, C = adj.to_numpy(float), close.to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    liq, blue = unis["LIQ"], unis["BLUE"]

    def entry(nhi, vmin):
        hi = adj.rolling(nhi, min_periods=nhi).max()
        return ((adj >= hi) & (adj > ma200) & (vr >= vmin)).to_numpy(bool), vr.to_numpy(float)

    def trail(x):
        return lambda t, j, p: A[t, j] <= (1 - x) * p["peak"]
    n_trials = N_BEFORE + len(ARMS)
    rng = np.random.default_rng(T.SEED)
    res = {}
    m, sc = entry(LEAD[0], LEAD[2])
    R, tr, _ = T.run_book(A, C, c_in, c_out, m, sc, trail(LEAD[1]), liq.to_numpy(bool))
    res["lead 60/10/1.5"] = T.stats(R, tr, dates, n_trials)
    R, tr, _ = T.run_book(A, C, c_in, c_out, None, None, trail(LEAD[1]), liq.to_numpy(bool), rng=rng)
    res["random+trail10 LIQ"] = T.stats(R, tr, dates, n_trials)
    rnd = res["random+trail10 LIQ"]
    for name in GRID:
        nhi, x, vmin = GRID[name]
        m, sc = entry(nhi, vmin)
        R, tr, _ = T.run_book(A, C, c_in, c_out, m, sc, trail(x), liq.to_numpy(bool))
        res[name] = T.stats(R, tr, dates, n_trials)
    m, sc = entry(LEAD[0], LEAD[2])
    for name, uni in (("loose", liq & loose), ("strict", liq & strict), ("small", liq & ~blue)):
        R, tr, _ = T.run_book(A, C, c_in, c_out, m, sc, trail(LEAD[1]), uni.to_numpy(bool))
        res[name] = T.stats(R, tr, dates, n_trials)
    verd = {}
    for name in ARMS:
        s = res[name]
        why = []
        if s["n"] < 150:
            why.append("n<150")
        if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
            why.append("t<2.5")
        if s["sharpe"] < 1.0:
            why.append("sharpe<1")
        if s["mdd"] < -0.25:
            why.append("mdd>25%")
        if sum(1 for v in s["years"].values() if v > 0) < 5:
            why.append("years<5/7")
        if s["sharpe"] < rnd["sharpe"] + 0.5:
            why.append("vs random")
        verd[name] = "CANDIDATE" if not why else "tested: " + ",".join(why)
    robust_n = sum(1 for g in GRID if res[g]["cagr"] >= 0.10 and res[g]["tstat"] >= 2.0)
    robust = robust_n >= 5
    lead = res["lead 60/10/1.5"]
    steadier = {g: (res[g]["mdd"] > lead["mdd"] and res[g]["cagr"] >= 0.7 * lead["cagr"]) for g in ("loose", "strict")}

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, s, verdict):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | "
                f"{s['total'] * 100:+.0f} % | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {verdict} |")
    lines = [f"# IDX menu 7 — robustness of the trend lead + fundamental gate — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             "| arm | trades | hold d | hit | avg net | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
             row("lead 60/10/1.5 (LIQ)", lead, "reference (menu 6)"), row("random + trail10 (LIQ)", rnd, "reference")]
    for g in GRID:
        lines.append(row(f"{g} {GRID[g]}", res[g], verd[g]))
    for g in ("loose", "strict", "small"):
        lines.append(row(g, res[g], verd[g] + (" | steadier" if steadier.get(g) else (" | not steadier" if g in steadier else ""))))
    n_c = sum(1 for v in verd.values() if v == "CANDIDATE")
    lines += ["", f"Candidates by the menu-6 rule: {n_c} of {len(ARMS)}.",
              f"Robustness read: {robust_n} of 7 neighbours have CAGR >= 10 % with t >= 2.0 -> the lead is **{'ROBUST' if robust else 'FRAGILE'}** "
              + ("(earns an out-of-sample paper track `trend`, no money)." if robust else "(recorded as luck)."),
              f"Gated arms: loose {'steadier' if steadier['loose'] else 'not steadier'} (mDD {res['loose']['mdd'] * 100:.0f} % vs {lead['mdd'] * 100:.0f} %, CAGR {res['loose']['cagr'] * 100:+.1f} % vs {lead['cagr'] * 100:+.1f} %); "
              f"strict {'steadier' if steadier['strict'] else 'not steadier'} (mDD {res['strict']['mdd'] * 100:.0f} %, CAGR {res['strict']['cagr'] * 100:+.1f} %).",
              "", "Limits: as menu 6; the fundamental gate is point-in-time by publication date, evaluated monthly."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_TREND_ROBUST_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "trend_robust", dates[-1].date(), params={"trials": ARMS, "grid": GRID, "lead": LEAD, "n_trials_cumulative": n_trials},
                              summary={"results": res, "verdicts": verd, "robust_n": robust_n, "robust": robust, "steadier": steadier, "candidates": n_c},
                              names=[], report_path=out, note=f"{n_c} candidates; lead {'ROBUST' if robust else 'FRAGILE'} ({robust_n}/7)")
        print("study", sid)


if __name__ == "__main__":
    main()
