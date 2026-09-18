#!/usr/bin/env python3
"""IDX menu 11 — robustness of the two menu-10 signals before they are believed: revenue growth (rev_g, informative by the rule) and
sideways + profit growth (sleeper_np, +28 pp over its control but n = 61, below the rule's 100).

PRE-REGISTERED MENU (8 trials; cumulative 301 + 8 = 309). Declared before the run; nothing tuned afterwards. Neighbours only — one
parameter moved at a time; same universe, dates, horizons, controls and reading as menu 10.
  rev_g neighbours:      rev10 (revenue YTD >= +10 %), rev30 (>= +30 %), rev20_mcap2 (>= +20 % and market cap <= Rp 2 T),
                         rev20_profit (>= +20 % and net profit > 0)
  sleeper_np neighbours: side40_np20 (sideways over 40 days, range <= 20 %), side90_np20 (90 days, range <= 30 %),
                         side60_np10 (profit growth >= +10 %), side60_np30 (>= +30 %)
ROBUSTNESS RULE: a signal is ROBUST if >= 3 of its 4 neighbours keep a median 1-year gap over their control of >= +5 pp (and
  n >= 40 each); a robust signal earns a costed rule test in a later menu. Otherwise it is recorded as fragile.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_smallcap_fund2.py
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

N_BEFORE = 301
ARMS = ["rev10", "rev30", "rev20_mcap2", "rev20_profit", "side40_np20", "side90_np20", "side60_np10", "side60_np30"]


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
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    mcap = mc.pivot(index="trade_date", columns="code", values="mcap").reindex(index=dates, columns=adj.columns)
    mcap.index = pd.to_datetime(mcap.index)
    small = unis["LIQ"] & (mcap <= 5e12)
    fm = first.to_numpy()[:, None]
    monthly = small & fm

    def sideways(n, cap):
        r = adj / adj.shift(n) - 1
        rng = adj.rolling(n, min_periods=n).max() / adj.rolling(n, min_periods=n).min() - 1
        return small & (r.abs() <= 0.10) & (rng <= cap)
    known_r, known_p = G["rev_yoy"].notna(), G["np_yoy"].notna()
    npg = lambda x: (G["np_yoy"] >= x) & (G["np_pos"] > 0)  # noqa: E731
    arms = {
        "rev10": (monthly & known_r, G["rev_yoy"] >= 0.10), "rev30": (monthly & known_r, G["rev_yoy"] >= 0.30),
        "rev20_mcap2": (monthly & known_r & (mcap <= 2e12), G["rev_yoy"] >= 0.20), "rev20_profit": (monthly & known_r, (G["rev_yoy"] >= 0.20) & (G["np_pos"] > 0)),
        "side40_np20": (sideways(40, 0.20) & fm & known_p, npg(0.20)), "side90_np20": (sideways(90, 0.30) & fm & known_p, npg(0.20)),
        "side60_np10": (sideways(60, 0.25) & fm & known_p, npg(0.10)), "side60_np30": (sideways(60, 0.25) & fm & known_p, npg(0.30)),
    }
    A_ff = adj.ffill().to_numpy(float)
    C = comp.ffill().to_numpy(float)
    base = F.events(A_ff, monthly.to_numpy(bool), C)
    res, ctl, gaps = {}, {}, {}
    for arm, (b, cond) in arms.items():
        res[arm] = F.events(A_ff, (b & cond).to_numpy(bool), C)
        ctl[arm] = F.events(A_ff, (b & ~cond).to_numpy(bool), C)
        n = len(res[arm]["r250"])
        gaps[arm] = (np.median(res[arm]["r250"]) - np.median(ctl[arm]["r250"])) * 100 if n and len(ctl[arm]["r250"]) else float("nan")
    n_trials = N_BEFORE + len(ARMS)
    robust = {}
    for sig, members in (("rev_g", ARMS[:4]), ("sleeper_np", ARMS[4:])):
        ok = sum(1 for a in members if len(res[a]["r250"]) >= 40 and gaps[a] >= 5)
        robust[sig] = (ok, ok >= 3)
    lines = [f"# IDX menu 11 — robustness of revenue growth and sideways+profit growth in small caps — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             "| set | n | P(up) / med 60d | P(up 1y) | med 1y | avg 1y | P(>= +50 % 1y) / P(<= −30 %) | P(up 2y) | med 2y |", "|---|---|---|---|---|---|---|---|---|",
             "| all small caps (base rate) " + F.fmt(base)]
    for arm in ARMS:
        lines.append(f"| **{arm}** " + F.fmt(res[arm]))
        lines.append(f"| control: fails {arm} " + F.fmt(ctl[arm]))
    lines += ["", "| arm | n | med 1y gap vs control | keeps >= +5 pp? |", "|---|---|---|---|"]
    for arm in ARMS:
        lines.append(f"| {arm} | {len(res[arm]['r250'])} | {gaps[arm]:+.1f} pp | {'yes' if (len(res[arm]['r250']) >= 40 and gaps[arm] >= 5) else 'no'} |")
    lines += ["", f"Robustness read (declared): rev_g {robust['rev_g'][0]}/4 neighbours -> **{'ROBUST' if robust['rev_g'][1] else 'FRAGILE'}**; "
              f"sleeper_np {robust['sleeper_np'][0]}/4 -> **{'ROBUST' if robust['sleeper_np'][1] else 'FRAGILE'}**.", "",
              "Limits: as menu 10 (event study, no costs; overlapping windows; current listing board)."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_SMALLCAP_FUND2_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "smallcap_fund_robust", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials},
                              summary={"gaps": gaps, "n": {a: int(len(res[a]["r250"])) for a in ARMS}, "robust": {k: {"ok": v[0], "robust": v[1]} for k, v in robust.items()}},
                              names=[], report_path=out, note=f"rev_g {'ROBUST' if robust['rev_g'][1] else 'FRAGILE'}; sleeper_np {'ROBUST' if robust['sleeper_np'][1] else 'FRAGILE'}")
        print("study", sid)


if __name__ == "__main__":
    main()
