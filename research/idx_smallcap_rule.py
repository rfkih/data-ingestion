#!/usr/bin/env python3
"""IDX menu 12 — the two robust small-cap fundamental signals as costed trading rules (operator "iya boleh", 2026-09-17).

Menus 10–11 (event studies) found two point-in-time fundamental filters that survive their neighbours on liquid small caps:
sideways 60 days + net profit growth >= +20 % (sleeper_np) and revenue growth >= +20 % with positive profit (rev20_profit). Here
they are run through the desk's book with real costs, as a rule would be traded.

PRE-REGISTERED MENU (4 trials; cumulative 309 + 4 = 313). Declared before the run; nothing tuned afterwards.
  Universe: liquid small caps (Utama/Pengembangan, 60-day value >= Rp 5 bn, close >= Rp 100, market cap <= Rp 5 T).
  Signals on the first trading day of each month from the latest PUBLISHED report; entry at the next close (closing offer);
  exit at the close after the exit signal (closing bid); Stockbit fees 0.10/0.20 %. Book of K = 10 slots, 1/K each, one position
  per name, free slots filled by rank (profit growth for sleeper_np, revenue growth for rev20_profit).
  Exits: trail20 = close <= 80 % of the highest close since entry OR 250 trading days; hold250 = 250 trading days, no stop.
  Arms: sleeper_np|trail20, sleeper_np|hold250, rev20_profit|trail20, rev20_profit|hold250.
  References (not trials): random small caps entered on the same monthly dates with each exit; COMPOSITE buy and hold.
READING RULE (declared before the run; the hold is ~1 year, so the trade count is bounded by 10 slots x 6.7 years): candidate
  for a paper book if ALL hold after costs: >= 60 closed trades; mean net per trade > 0 with t >= 2.5; annualised Sharpe of the
  book >= 1.0; max drawdown <= 25 %; >= 5 of 7 calendar years positive; Sharpe >= random with the same exit + 0.5.
  A near miss (all but one criterion, Sharpe >= 0.8) is reported as such - it is still not a rule for money.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_smallcap_rule.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import idx_smallcap_fund as F  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_trend as T  # noqa: E402

N_BEFORE = 309
ARMS = ["sleeper_np|trail20", "sleeper_np|hold250", "rev20_profit|trail20", "rev20_profit|hold250"]


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        P = S.panels(bars, listing)
        _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
        adj = P["adj"]
        dates = adj.index
        mc = pd.read_sql("SELECT code, trade_date, mcap FROM idx.feature_daily WHERE trade_date >= %s", conn, params=(date(2020, 1, 1),))
        G, first = F.growth_panels(conn, dates, adj.columns)
    c_in, c_out = S.costs(P)
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    mcap = mc.pivot(index="trade_date", columns="code", values="mcap").reindex(index=dates, columns=adj.columns)
    mcap.index = pd.to_datetime(mcap.index)
    small = unis["LIQ"] & (mcap <= 5e12)
    fm = first.to_numpy()[:, None]
    r60 = adj / adj.shift(60) - 1
    rng60 = adj.rolling(60, min_periods=60).max() / adj.rolling(60, min_periods=60).min() - 1
    sideways = small & (r60.abs() <= 0.10) & (rng60 <= 0.25)
    npg = (G["np_yoy"] >= 0.20) & (G["np_pos"] > 0)
    revg = (G["rev_yoy"] >= 0.20) & (G["np_pos"] > 0)
    entries = {"sleeper_np": ((sideways & fm & npg).to_numpy(bool), G["np_yoy"].to_numpy(float)),
               "rev20_profit": ((small & fm & revg).to_numpy(bool), G["rev_yoy"].to_numpy(float))}
    A, C = adj.to_numpy(float), P["close"].to_numpy(float)
    exits = {"trail20": lambda t, j, p: A[t, j] <= 0.80 * p["peak"] or (t - p["e"]) >= 250, "hold250": lambda t, j, p: (t - p["e"]) >= 250}
    n_trials = N_BEFORE + len(ARMS)
    rng = np.random.default_rng(T.SEED)
    uni_monthly = (small & fm).to_numpy(bool)
    refs, res, verd = {}, {}, {}
    for x, rule in exits.items():
        R, tr, _ = T.run_book(A, C, c_in, c_out, None, None, rule, uni_monthly, rng=rng)
        refs[x] = T.stats(R, tr, dates, n_trials)
    for arm in ARMS:
        e, x = arm.split("|")
        m, sc = entries[e]
        R, tr, open_ = T.run_book(A, C, c_in, c_out, m, sc, exits[x], small.to_numpy(bool))
        s = T.stats(R, tr, dates, n_trials)
        s["open"] = len(open_)
        res[arm] = s
        why = []
        if s["n"] < 60:
            why.append("n<60")
        if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
            why.append("t<2.5")
        if s["sharpe"] < 1.0:
            why.append("sharpe<1")
        if s["mdd"] < -0.25:
            why.append("mdd>25%")
        if sum(1 for v in s["years"].values() if v > 0) < 5:
            why.append("years<5/7")
        if s["sharpe"] < refs[x]["sharpe"] + 0.5:
            why.append("vs random")
        verd[arm] = "CANDIDATE" if not why else ("NEAR MISS: " if (len(why) == 1 and s["sharpe"] >= 0.8) else "tested: ") + ",".join(why)
    cc = comp.dropna()
    comp_total = cc.iloc[-1] / cc.iloc[0] - 1
    comp_years = cc.groupby(cc.index.year).apply(lambda s: s.iloc[-1] / s.iloc[0] - 1)

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, s, v):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | {s['total'] * 100:+.0f} % | "
                f"{s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {v} |")
    lines = [f"# IDX menu 12 — small-cap fundamental signals as costed rules — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             f"Book K = 10, monthly entries at the next close @offer, exits @bid, fees {S.FEE_BUY * 100:.2f}/{S.FEE_SELL * 100:.2f} %; {dates[0].date()} -> {dates[-1].date()}. "
             f"COMPOSITE buy-and-hold {comp_total * 100:+.1f} % | {yrs(comp_years.to_dict())}", "",
             "| arm | trades | hold d | hit | avg net | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for x, s in refs.items():
        lines.append(row(f"random small caps | {x}", s, "reference"))
    for arm in ARMS:
        lines.append(row(arm.replace("|", " | "), res[arm], verd[arm]))
    n_c = sum(1 for v in verd.values() if v == "CANDIDATE")
    lines += ["", f"Reading rule applied as declared: {n_c} candidate(s) of {len(ARMS)}; near misses: {sum(1 for v in verd.values() if v.startswith('NEAR'))}.", "",
              "Limits: as menus 10-11 (current listing board; growth from published YTD figures); ~1-year holds mean few trades per year and",
              "positions open at the last bar are marked, not counted; costs = quoted closing spread + fees, no extra slippage."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_SMALLCAP_RULE_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "smallcap_rule", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "K": T.K},
                              summary={"results": res, "random": refs, "verdicts": verd, "candidates": n_c, "composite_total": float(comp_total)},
                              names=[], report_path=out, note=f"{n_c} candidates of {len(ARMS)}")
        print("study", sid)


if __name__ == "__main__":
    main()
