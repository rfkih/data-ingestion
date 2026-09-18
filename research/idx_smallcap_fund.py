#!/usr/bin/env python3
"""IDX menu 10 — small caps with a fundamental filter: does sales / profit growth (point-in-time, from the quarterly reports)
pick the small caps that rise? (operator, 2026-09-17: "tambah filter fundamental dan laporan keuangan, seperti potensi penjualan")

Event study on the liquid small-cap universe (menus 8–9), signals on the first trading day of each month, forward 60 / 250 / 500
trading days on forward-filled closes, against the small caps that fail the filter on the same dates, the small-cap base rate and
the COMPOSITE. Growth is read from the latest report PUBLISHED by the signal date (idx.fundamental.published_at): year-on-year
growth of year-to-date revenue and net profit versus the same period a year earlier.

PRE-REGISTERED MENU (6 trials; cumulative 295 + 6 = 301). Declared before the run; nothing tuned afterwards.
  rev_g          revenue YTD +20 % y/y or better
  np_g           net profit YTD +20 % y/y or better, and positive
  rev_np_g       both
  accel          revenue growth accelerating: this report's y/y at least 10 pp above the previous report's
  sleeper_rev    sideways 60 days (menu 8 definition) AND rev_g
  sleeper_np     sideways 60 days AND np_g
  Controls (not trials): small caps on the same dates failing the arm's filter; base rate = all small caps; COMPOSITE same windows.
READING RULE: informative if the arm's median 250-day return beats its control by >= +5 pp with n >= 100 signals AND beats the
  small-cap base rate. An informative arm earns a rule test (costs, book) in a later menu; nothing here is a trading rule yet.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_smallcap_fund.py
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
import idx_swing2 as S  # noqa: E402

N_BEFORE = 295
ARMS = ["rev_g", "np_g", "rev_np_g", "accel", "sleeper_rev", "sleeper_np"]


def growth_panels(conn, dates, cols):
    """Monthly (first trading day) point-in-time panels: rev_yoy, np_yoy, np_pos, rev_accel from the latest report published by then."""
    f = pd.read_sql("""SELECT code, period_end, months, published_at::date AS pub, revenue, net_profit FROM idx.fundamental
                       WHERE published_at IS NOT NULL AND months IN (3, 6, 9, 12) ORDER BY code, period_end""", conn)
    for c in ("revenue", "net_profit"):
        f[c] = pd.to_numeric(f[c], errors="coerce")
    f["period_end"] = pd.to_datetime(f["period_end"])
    f["pub"] = pd.to_datetime(f["pub"])
    prev = f.copy()
    prev["period_end"] = prev["period_end"] + pd.DateOffset(years=1)
    m = f.merge(prev[["code", "period_end", "months", "revenue", "net_profit"]], on=["code", "period_end", "months"], how="left", suffixes=("", "_prev"))
    m["rev_yoy"] = np.where((m["revenue_prev"] > 0), m["revenue"] / m["revenue_prev"] - 1, np.nan)
    m["np_yoy"] = np.where((m["net_profit_prev"] > 0) & (m["net_profit"].notna()), m["net_profit"] / m["net_profit_prev"] - 1, np.nan)
    m = m.sort_values(["code", "pub", "period_end"])
    m["rev_yoy_prev_report"] = m.groupby("code")["rev_yoy"].shift(1)
    m["rev_accel"] = m["rev_yoy"] - m["rev_yoy_prev_report"]
    firsts = [d for i, d in enumerate(dates) if i == 0 or d.month != dates[i - 1].month]
    panels = {k: pd.DataFrame(np.nan, index=dates, columns=cols) for k in ("rev_yoy", "np_yoy", "np_pos", "rev_accel")}
    m = m[m["code"].isin(cols)]
    for d in firsts:
        latest = m[m["pub"] <= d].groupby("code").tail(1).set_index("code")
        for k in ("rev_yoy", "np_yoy", "rev_accel"):
            panels[k].loc[d, latest.index] = latest[k].to_numpy()
        panels["np_pos"].loc[d, latest.index] = (latest["net_profit"] > 0).astype(float).to_numpy()
    first_mask = pd.Series(dates.isin(firsts), index=dates)
    return panels, first_mask


def events(A_ff, mask, comp):
    T_, N = A_ff.shape
    out = {"r60": [], "r250": [], "r500": [], "c250": []}
    ts, js = np.nonzero(mask)
    for t, j in zip(ts, js):
        e = t + 1
        if e + 500 >= T_ or np.isnan(A_ff[e, j]):
            continue
        out["r60"].append(A_ff[e + 60, j] / A_ff[e, j] - 1)
        out["r250"].append(A_ff[e + 250, j] / A_ff[e, j] - 1)
        out["r500"].append(A_ff[e + 500, j] / A_ff[e, j] - 1)
        out["c250"].append(comp[e + 250] / comp[e] - 1)
    return {k: np.array(v) for k, v in out.items()}


def fmt(ev):
    n = len(ev["r250"])
    if n == 0:
        return "| 0 | - | - | - | - | - | - | - |"
    r60, r1, r2 = ev["r60"], ev["r250"], ev["r500"]
    return (f"| {n} | {(r60 > 0).mean() * 100:.0f} % / {np.median(r60) * 100:+.1f} % | {(r1 > 0).mean() * 100:.0f} % | {np.median(r1) * 100:+.1f} % | {r1.mean() * 100:+.1f} % | "
            f"{(r1 >= 0.5).mean() * 100:.0f} % / {(r1 <= -0.3).mean() * 100:.0f} % | {(r2 > 0).mean() * 100:.0f} % | {np.median(r2) * 100:+.1f} % |")


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        P = S.panels(bars, listing)
        _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
        adj = P["adj"]
        dates = adj.index
        mc = pd.read_sql("SELECT code, trade_date, mcap FROM idx.feature_daily WHERE trade_date >= %s", conn, params=(date(2020, 1, 1),))
        G, first = growth_panels(conn, dates, adj.columns)
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    mcap = mc.pivot(index="trade_date", columns="code", values="mcap").reindex(index=dates, columns=adj.columns)
    mcap.index = pd.to_datetime(mcap.index)
    small = unis["LIQ"] & (mcap <= 5e12)
    r60 = adj / adj.shift(60) - 1
    rng60 = adj.rolling(60, min_periods=60).max() / adj.rolling(60, min_periods=60).min() - 1
    sideways = small & (r60.abs() <= 0.10) & (rng60 <= 0.25)
    monthly = small & first.to_numpy()[:, None]
    rev_g = G["rev_yoy"] >= 0.20
    np_g = (G["np_yoy"] >= 0.20) & (G["np_pos"] > 0)
    known = G["rev_yoy"].notna()
    arms = {"rev_g": (monthly & known, rev_g), "np_g": (monthly & G["np_yoy"].notna(), np_g), "rev_np_g": (monthly & known & G["np_yoy"].notna(), rev_g & np_g),
            "accel": (monthly & G["rev_accel"].notna(), G["rev_accel"] >= 0.10),
            "sleeper_rev": (sideways & first.to_numpy()[:, None] & known, rev_g), "sleeper_np": (sideways & first.to_numpy()[:, None] & G["np_yoy"].notna(), np_g)}
    A_ff = adj.ffill().to_numpy(float)
    C = comp.ffill().to_numpy(float)
    base = events(A_ff, monthly.to_numpy(bool), C)
    res, ctl = {}, {}
    for arm, (base_m, cond) in arms.items():
        res[arm] = events(A_ff, (base_m & cond).to_numpy(bool), C)
        ctl[arm] = events(A_ff, (base_m & ~cond).to_numpy(bool), C)
    n_trials = N_BEFORE + len(ARMS)
    lines = [f"# IDX menu 10 — small caps with a fundamental growth filter (point-in-time) — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             "Monthly signals (first trading day), liquid small caps (value >= Rp 5 bn/day, close >= Rp 100, market cap <= Rp 5 T); growth from the latest",
             "report published by the signal date; returns on forward-filled closes; windows must fit inside the data (signals to ~2024-09).", "",
             "| set | n | P(up) / med 60d | P(up 1y) | med 1y | avg 1y | P(>= +50 % 1y) / P(<= −30 %) | P(up 2y) | med 2y |", "|---|---|---|---|---|---|---|---|---|",
             "| all small caps (base rate) " + fmt(base)]
    for arm in ARMS:
        lines.append(f"| **{arm}** " + fmt(res[arm]))
        lines.append(f"| control: fails {arm} " + fmt(ctl[arm]))
    lines += ["", f"COMPOSITE over the same windows (median 1y): {np.median(base['c250']) * 100:+.1f} %.", "",
              "| arm | n | med 1y gap vs control | vs small-cap base | informative? |", "|---|---|---|---|---|"]
    n_i = 0
    for arm in ARMS:
        n = len(res[arm]["r250"])
        gap = (np.median(res[arm]["r250"]) - np.median(ctl[arm]["r250"])) * 100 if n and len(ctl[arm]["r250"]) else float("nan")
        vsb = (np.median(res[arm]["r250"]) - np.median(base["r250"])) * 100 if n else float("nan")
        ok = n >= 100 and gap >= 5 and vsb > 0
        n_i += ok
        lines.append(f"| {arm} | {n} | {gap:+.1f} pp | {vsb:+.1f} pp | {'YES' if ok else 'no'} |")
    lines += ["", f"Reading rule applied as declared: informative {n_i} of {len(ARMS)}.", "",
              "Limits: current listing board (not PIT); growth uses year-to-date figures vs the same period a year earlier (reports with a prior-year",
              "comparative only); overlapping windows — descriptive, not significance; no costs (event study)."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_SMALLCAP_FUND_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs

    def pack(ev):
        return {k: {"n": int(len(v)), "median": float(np.median(v)) if len(v) else None, "mean": float(v.mean()) if len(v) else None,
                    "p_up": float((v > 0).mean()) if len(v) else None} for k, v in ev.items()}
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "smallcap_fund", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials},
                              summary={"arms": {a: pack(v) for a, v in res.items()}, "controls": {a: pack(v) for a, v in ctl.items()}, "base": pack(base), "informative": n_i},
                              names=[], report_path=out, note=f"informative {n_i}/{len(ARMS)}")
        print("study", sid)


if __name__ == "__main__":
    main()
