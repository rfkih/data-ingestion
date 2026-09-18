#!/usr/bin/env python3
"""IDX menu 6 — trend following with trailing exits (operator, 2026-09-17: "tidak masalah 5 hari / 1 bulan / 2 bulan — selama
trend naik dan harga naik, keep"). Menus 1–5 held for a fixed number of days; this one holds while the trend holds and exits on
its break. The analyst-target leg (target >= +40 %) cannot be tested yet (consensus recorded since 2026-09-14 only) and is
NOT part of this menu; the technical leg alone is.

PRE-REGISTERED MENU (10 trials; cumulative 267 + 10 = 277). Declared before the run; nothing tuned afterwards.
  Universe BLUE (menu 2): Utama/Pengembangan, 60-day value >= Rp 20 bn, close >= Rp 1,000. One arm on LIQ (value >= Rp 5 bn, close >= 100).
  Book: up to K = 10 concurrent positions, each 1/K of capital, cash otherwise; one position per name; free slots filled by the
  day's entry signals in rank order. Entry signal at close t -> buy at close t+1 (closing offer); exit signal at close t -> sell at
  close t+1 (closing bid); Stockbit fees 0.10/0.20 %. No fixed horizon. Adjusted closes for signals and returns.
  Entries:
    hi60      close = 60-day high, close > MA200, volume >= 1.5x its 20-day median            (ranked by volume ratio)
    cross     MA20 crossed above MA50 today, close > MA200                                    (ranked by MA20/MA50 - 1)
    momq      3-month return in the top quintile of the universe and close > MA20 > MA50      (ranked by 3-month return)
  Exits (checked every close while held):
    ma20      close < 20-day average
    ma50      close < 50-day average
    trail10   close <= 90 % of the highest close since entry
  Arms: hi60|ma20, hi60|ma50, hi60|trail10, cross|ma20, cross|ma50, cross|trail10, momq|ma20, momq|ma50, momq|trail10 on BLUE;
        hi60|trail10 on LIQ. A name that leaves the universe (no bar) is sold at the last close.
  References (not trials): random entries on the same dates with the same slot logic and the ma20 / trail10 exit; COMPOSITE buy and hold.
READING RULE (declared before the run): candidate only if ALL hold after costs: >= 150 closed trades; mean net return per trade
  > 0 with t >= 2.5 across trades; annualised Sharpe of the daily book >= 1.0 (the book is invested, so Sharpe means something
  here); max drawdown <= 25 %; net positive in >= 5 of 7 calendar years; Sharpe >= the random reference with the same exit + 0.5.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_trend.py
"""
from __future__ import annotations

import math
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import equity_screen as ES  # noqa: E402
import idx_swing2 as S  # noqa: E402

N_BEFORE = 267
K = 10
ARMS = [f"{e}|{x}|BLUE" for e in ("hi60", "cross", "momq") for x in ("ma20", "ma50", "trail10")] + ["hi60|trail10|LIQ"]
assert len(ARMS) == 10
SEED = 20260917


def run_book(A, C, c_in, c_out, entry_mask, entry_score, exit_rule, uni, k=K, rng=None):
    """Event-driven book. A/C adjusted/raw closes (T x N); entry_mask/score (T x N) evaluated at close t, executed at close t+1;
    exit_rule(pos) -> bool evaluated at close t for held names, executed at close t+1. Returns daily returns, closed trades."""
    T, N = A.shape
    ret = np.full((T, N), np.nan)
    ret[1:] = A[1:] / A[:-1] - 1
    R = np.zeros(T)
    held: dict[int, dict] = {}                 # j -> {e, peak, pe}
    pending_exit: set[int] = set()
    pending_entry: list[int] = []
    trades = []
    w = 1.0 / k
    for t in range(1, T):
        # 1. returns of what we hold over t-1 -> t
        day = 0.0
        for j, p in held.items():
            r = ret[t, j]
            day += w * (0.0 if np.isnan(r) else r)
        # 2. execute at close t what was signalled at close t-1
        for j in list(pending_exit):
            if j in held and not np.isnan(A[t, j]) and np.isfinite(c_out[t, j]):
                p = held.pop(j)
                gross = A[t, j] / p["a0"] - 1
                net = gross - p["ci"] - c_out[t, j]
                day -= w * c_out[t, j]
                trades.append((p["e"], j, gross, net, t - p["e"]))
        pending_exit.clear()
        for j in pending_entry:
            if len(held) >= k or j in held or np.isnan(A[t, j]) or not np.isfinite(c_in[t, j]):
                continue
            held[j] = {"e": t, "a0": A[t, j], "peak": A[t, j], "ci": c_in[t, j]}
            day -= w * c_in[t, j]
        pending_entry = []
        R[t] = day
        # 3. signals at close t for execution at t+1
        for j, p in held.items():
            if not np.isnan(A[t, j]):
                p["peak"] = max(p["peak"], A[t, j])
            if np.isnan(A[t, j]) or exit_rule(t, j, p):
                pending_exit.add(j)
        free = k - (len(held) - len(pending_exit))
        if free > 0:
            if rng is not None:
                cand = np.flatnonzero(uni[t] & ~np.isnan(A[t]))
                cand = [j for j in cand if j not in held]
                pick = list(rng.choice(cand, size=min(free, len(cand)), replace=False)) if cand else []
            else:
                cand = np.flatnonzero(entry_mask[t] & uni[t])
                cand = [j for j in cand if j not in held]
                sc = np.nan_to_num(entry_score[t, cand], nan=-np.inf) if cand else np.array([])
                pick = [cand[i] for i in np.argsort(-sc, kind="stable")[:free]] if cand else []
            pending_entry = list(pick)
    # close what is still open at the last bar (marked, not a trade)
    return pd.Series(R), trades, held


def stats(R: pd.Series, trades, dates, n_trials):
    R.index = dates
    eq = (1 + R).cumprod()
    years = R.groupby(R.index.year).apply(lambda s: (1 + s).prod() - 1)
    vol = R.std() * math.sqrt(250)
    sharpe = (R.mean() * 250 / vol) if vol > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    n = len(trades)
    nets = np.array([t[3] for t in trades]) if n else np.array([])
    holds = np.array([t[4] for t in trades]) if n else np.array([])
    tstat = (nets.mean() / nets.std(ddof=1) * math.sqrt(n)) if n > 2 and nets.std(ddof=1) > 0 else 0.0
    wins, losses = nets[nets > 0], nets[nets <= 0]
    return {"n": n, "hold": float(holds.mean()) if n else 0.0, "hit": float((nets > 0).mean()) if n else 0.0, "avg_net": float(nets.mean()) if n else 0.0,
            "med_net": float(np.median(nets)) if n else 0.0, "payoff": float(wins.mean() / -losses.mean()) if len(wins) and len(losses) and losses.mean() != 0 else 0.0,
            "tstat": float(tstat), "total": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (250 / len(R)) - 1), "sharpe": float(sharpe), "mdd": float(dd),
            "dsr": float(ES.deflated_sharpe(list(R[R != 0].values), n_trials)) if (R != 0).sum() > 10 else 0.0,
            "years": {int(y): float(v) for y, v in years.items()}}


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
    P = S.panels(bars, listing)
    _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
    c_in, c_out = S.costs(P)
    adj, close, vol = P["adj"], P["close"], P["volume"]
    dates = adj.index
    A, C = adj.to_numpy(float), close.to_numpy(float)
    ma20, ma50, ma200 = (adj.rolling(n, min_periods=n).mean() for n in (20, 50, 200))
    hi60 = adj.rolling(60, min_periods=60).max()
    vr = vol / vol.rolling(20, min_periods=20).median()
    r3 = adj / adj.shift(63) - 1
    M20, M50 = ma20.to_numpy(float), ma50.to_numpy(float)
    entries = {
        "hi60": ((adj >= hi60) & (adj > ma200) & (vr >= 1.5), vr),
        "cross": ((ma20 > ma50) & (ma20.shift(1) <= ma50.shift(1)) & (adj > ma200), ma20 / ma50 - 1),
    }
    top_q = r3.where(unis["BLUE"]).rank(axis=1, ascending=False, pct=True) <= 0.20
    entries["momq"] = (top_q & (adj > ma20) & (ma20 > ma50), r3)
    exits = {
        "ma20": lambda t, j, p: A[t, j] < M20[t, j],
        "ma50": lambda t, j, p: A[t, j] < M50[t, j],
        "trail10": lambda t, j, p: A[t, j] <= 0.90 * p["peak"],
    }
    n_trials = N_BEFORE + len(ARMS)
    rng = np.random.default_rng(SEED)
    refs, res, verd = {}, {}, {}
    for x in ("ma20", "trail10"):
        R, tr, _ = run_book(A, C, c_in, c_out, None, None, exits[x], unis["BLUE"].to_numpy(bool), rng=rng)
        refs[x] = stats(R, tr, dates, n_trials)
    for arm in ARMS:
        e, x, u = arm.split("|")
        m, sc = entries[e]
        R, tr, open_ = run_book(A, C, c_in, c_out, m.to_numpy(bool), sc.to_numpy(float), exits[x], unis[u].to_numpy(bool))
        s = stats(R, tr, dates, n_trials)
        s["open"] = len(open_)
        res[arm] = s
        ref = refs[x if x in refs else "ma20"]
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
        if s["sharpe"] < ref["sharpe"] + 0.5:
            why.append("vs random")
        verd[arm] = "CANDIDATE" if not why else "tested: " + ",".join(why)
    cc = comp.dropna()
    comp_total = cc.iloc[-1] / cc.iloc[0] - 1
    comp_years = cc.groupby(cc.index.year).apply(lambda s: s.iloc[-1] / s.iloc[0] - 1)

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, s, verdict):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['med_net'] * 100:+.2f} % | {s['payoff']:.2f} | "
                f"{s['tstat']:.1f} | {s['total'] * 100:+.0f} % | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {verdict} |")
    lines = [f"# IDX menu 6 — trend following with trailing exits — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             f"Book of K = {K} slots, entry close t+1 @offer, exit close t+1 @bid, fees {S.FEE_BUY * 100:.2f}/{S.FEE_SELL * 100:.2f} %; "
             f"{dates[0].date()} -> {dates[-1].date()}. COMPOSITE buy-and-hold {comp_total * 100:+.1f} % | {yrs(comp_years.to_dict())}", "",
             "| arm (entry|exit|universe) | trades | avg hold d | hit | avg net | median | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for x, s in refs.items():
        lines.append(row(f"random entries | {x} | BLUE", s, "reference"))
    for arm in ARMS:
        lines.append(row(arm.replace("|", " | "), res[arm], verd[arm]))
    n_c = sum(1 for v in verd.values() if v == "CANDIDATE")
    lines += ["", f"Reading rule applied as declared: {n_c} candidate(s) of {len(ARMS)}.", "",
              "Limits: current listing board (not PIT); signals and exits one day late (close-to-close); no quality gate beyond liquidity; dividends",
              "ignored; costs = quoted closing spread + fees, no extra slippage; positions still open at the last bar are marked, not counted as trades."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_TREND_FOLLOW_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "trend_follow", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "K": K},
                              summary={"results": res, "random": refs, "verdicts": verd, "candidates": n_c, "composite_total": float(comp_total)},
                              names=[], report_path=out, note=f"{n_c} candidates of {len(ARMS)}")
        print("study", sid)


if __name__ == "__main__":
    main()
