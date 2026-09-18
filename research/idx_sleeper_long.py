#!/usr/bin/env python3
"""IDX menu 9 — the sleeper question at 1–2 years (operator, 2026-09-17: "kalau timeline-nya 1–2 tahun ke depan").

Same signals as menu 8 (sideways small cap for 60 days + continuous accumulation: foreign flow / OBV / both), read 250 and 500
trading days ahead — the annual-book horizon and twice that. Event study only (no book): the question is "how much do they rise",
against (a) sideways small caps without accumulation, (b) every small cap on the same dates, (c) the COMPOSITE over the same windows.

PRE-REGISTERED (3 trials: fflow, obv, fflow_obv at the long horizon; cumulative 292 + 3 = 295). Declared before the run.
  Survivorship: a name that stops trading before the horizon is carried at its last close (forward-filled), and the share of
  such signals is reported. Windows must fit inside the data (signals up to ~2024-09 for the 2-year read).
READING RULE: informative if the arm's median 250-day return beats its control by >= +5 pp with n >= 100 AND beats the small-cap
  base rate on the same dates; the same at 500 days is reported. Anything else: not informative.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_sleeper_long.py
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

N_BEFORE = 292
ARMS = ["fflow", "obv", "fflow_obv"]
HS = (250, 500)


def events(A_ff, A_raw, mask, comp):
    """Forward returns from close t+1 on forward-filled closes; MFE within 500 days; COMPOSITE over the same window; stopped-trading share."""
    T_, N = A_ff.shape
    out = {"r250": [], "r500": [], "mfe500": [], "c250": [], "c500": [], "stopped": []}
    ts, js = np.nonzero(mask)
    for t, j in zip(ts, js):
        e = t + 1
        if e + 500 >= T_ or np.isnan(A_ff[e, j]):
            continue
        out["r250"].append(A_ff[e + 250, j] / A_ff[e, j] - 1)
        out["r500"].append(A_ff[e + 500, j] / A_ff[e, j] - 1)
        out["mfe500"].append(np.nanmax(A_ff[e + 1:e + 501, j]) / A_ff[e, j] - 1)
        out["c250"].append(comp[e + 250] / comp[e] - 1)
        out["c500"].append(comp[e + 500] / comp[e] - 1)
        out["stopped"].append(np.isnan(A_raw[e + 500, j]))
    return {k: np.array(v) for k, v in out.items()}


def fmt(ev):
    n = len(ev["r250"])
    if n == 0:
        return "| 0 | - | - | - | - | - | - | - | - |"
    r1, r2, m = ev["r250"], ev["r500"], ev["mfe500"]
    return (f"| {n} | {(r1 > 0).mean() * 100:.0f} % | {np.median(r1) * 100:+.1f} % | {r1.mean() * 100:+.1f} % | {(r2 > 0).mean() * 100:.0f} % | {np.median(r2) * 100:+.1f} % | "
            f"{(r2 >= 0.5).mean() * 100:.0f} % / {(r2 <= -0.3).mean() * 100:.0f} % | {np.median(m) * 100:+.1f} % | {ev['stopped'].mean() * 100:.0f} % |")


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        P = S.panels(bars, listing)
        _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
        adj = P["adj"]
        mc = pd.read_sql("SELECT code, trade_date, mcap FROM idx.feature_daily WHERE trade_date >= %s", conn, params=(date(2020, 1, 1),))
    dates = adj.index
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    mcap = mc.pivot(index="trade_date", columns="code", values="mcap").reindex(index=dates, columns=adj.columns)
    mcap.index = pd.to_datetime(mcap.index)
    vol = P["volume"]
    liq = unis["LIQ"]
    small = liq & (mcap <= 5e12)
    r60 = adj / adj.shift(60) - 1
    rng60 = adj.rolling(60, min_periods=60).max() / adj.rolling(60, min_periods=60).min() - 1
    sideways = small & (r60.abs() <= 0.10) & (rng60 <= 0.25)
    f20 = P["f20"]
    fflow = (f20 > 0) & (f20.shift(20) > 0) & (f20.shift(40) > 0)
    obv = (np.sign(adj.diff()).fillna(0) * vol.fillna(0)).cumsum()
    obv_up = (obv - obv.shift(60) > 0) & (obv - obv.shift(20) > 0)
    accum = {"fflow": fflow, "obv": obv_up, "fflow_obv": fflow & obv_up}
    A_raw = adj.to_numpy(float)
    A_ff = adj.ffill().to_numpy(float)
    C = comp.ffill().to_numpy(float)
    # thin the signal set to one observation per name per 20 trading days (consecutive sideways days are the same event)
    thin = pd.Series(np.arange(len(dates)) % 20 == 0, index=dates).to_numpy()[:, None]
    res, ctl = {}, {}
    for arm in ARMS:
        res[arm] = events(A_ff, A_raw, (sideways & accum[arm] & thin).to_numpy(bool), C)
        ctl[arm] = events(A_ff, A_raw, (sideways & ~accum[arm] & thin).to_numpy(bool), C)
    base_small = events(A_ff, A_raw, (small & thin).to_numpy(bool), C)
    base_side = events(A_ff, A_raw, (sideways & thin).to_numpy(bool), C)
    n_trials = N_BEFORE + len(ARMS)
    lines = [f"# IDX menu 9 — sleeping small caps + accumulation, 1–2 years ahead — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             "Signals thinned to one per name per 20 trading days; returns on forward-filled closes (a name that stops trading is carried at its last price);",
             "windows must fit inside 2020-01 .. 2026-09, so signals run to about 2024-09.", "",
             "| set | n | P(up 1y) | med 1y | avg 1y | P(up 2y) | med 2y | P(>= +50 % 2y) / P(<= −30 % 2y) | med best point in 2y | stopped trading |",
             "|---|---|---|---|---|---|---|---|---|---|",
             "| all small caps (base rate) " + fmt(base_small), "| sideways small caps, any flow " + fmt(base_side)]
    for arm in ARMS:
        lines.append(f"| **{arm}**: sideways + accumulation " + fmt(res[arm]))
        lines.append(f"| control: sideways, no {arm} " + fmt(ctl[arm]))
    c1 = np.median(base_small["c250"]) * 100 if len(base_small["c250"]) else float("nan")
    c2 = np.median(base_small["c500"]) * 100 if len(base_small["c500"]) else float("nan")
    lines += ["", f"COMPOSITE over the same windows (median): 1y {c1:+.1f} %, 2y {c2:+.1f} %.", "", "| arm | n | med 1y gap vs control | vs small-cap base | informative? |", "|---|---|---|---|---|"]
    n_i = 0
    for arm in ARMS:
        n = len(res[arm]["r250"])
        gap = (np.median(res[arm]["r250"]) - np.median(ctl[arm]["r250"])) * 100 if n and len(ctl[arm]["r250"]) else float("nan")
        vsb = (np.median(res[arm]["r250"]) - np.median(base_small["r250"])) * 100 if n else float("nan")
        ok = n >= 100 and gap >= 5 and vsb > 0
        n_i += ok
        lines.append(f"| {arm} | {n} | {gap:+.1f} pp | {vsb:+.1f} pp | {'YES' if ok else 'no'} |")
    lines += ["", f"Reading rule applied as declared: informative {n_i} of {len(ARMS)}.", "",
              "Limits: current listing board (not PIT); market cap from feature_daily on the day; signals thinned; the 2-year read has fewer independent",
              "windows than it has rows (overlapping calendar time), so treat P(up) and medians as descriptive, not as significance."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_SLEEPER_LONG_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs

    def pack(ev):
        return {k: {"n": int(len(v)), "median": float(np.median(v)) if len(v) else None, "mean": float(v.mean()) if len(v) else None} for k, v in ev.items() if k != "stopped"}
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "sleeper_long", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "horizons": list(HS)},
                              summary={"arms": {a: pack(v) for a, v in res.items()}, "controls": {a: pack(v) for a, v in ctl.items()}, "base_small": pack(base_small),
                                       "base_sideways": pack(base_side), "informative": n_i}, names=[], report_path=out, note=f"informative {n_i}/{len(ARMS)}")
        print("study", sid)


if __name__ == "__main__":
    main()
