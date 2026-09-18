#!/usr/bin/env python3
"""IDX menu 8 — "saham tidur": sideways names under continuous accumulation — how much do they rise afterwards? (operator, 2026-09-17)

The question has two parts, answered in order: (1) an EVENT STUDY — after a name has gone sideways for 60 days while being
accumulated continuously, what are its returns over the next 20 / 60 / 120 days, and how big is the best excursion (the
"breakout"), against a control of sideways names WITHOUT accumulation; (2) a TRADE READ — the same signal run through the
desk's book (10 slots, real costs, exit on a 10 % trailing stop or after 120 days).

PRE-REGISTERED MENU (5 trials; cumulative 287 + 5 = 292). Declared before the run; nothing tuned afterwards.
  Universe SMALL (operator, added before the run: "fokus di saham market cap kecil"): LIQ (Utama/Pengembangan, 60-day value
  >= Rp 5 bn, close >= Rp 100) AND market cap <= Rp 5 trillion on the day. LIQ as a whole is shown as a reference row only.
  Signal at close t, entry close t+1 (offer), exit at
  close t+1 after the exit signal (bid), Stockbit fees. Adjusted closes.
  SIDEWAYS (all arms): over the trailing 60 trading days |return| <= 10 % AND (60-day high / 60-day low - 1) <= 25 %.
  ACCUMULATION, four definitions (the desk's data, 2020-2026 unless stated):
    fflow      the 20-day foreign net share of volume > 0 in each of the last three 20-day blocks (60 days of net foreign buying)
    obv        on-balance volume (cumulative sign(daily change) x volume) up over the last 60 AND the last 20 days while price flat
    broker2    broker feed, 20-day windows (46 names, 2023-09 ->): the API's label "Acc" in >= 2 of the last 3 windows ending at t
    broker5    broker feed, 5-day windows (46 names, last 12 months): top-5 net buyers' share of value > 0 in >= 5 of the last 6 windows
  Fifth trial: fflow_obv = fflow AND obv (both flows agree).
  Control (not a trial): sideways names on the same dates that fail the arm's accumulation test.
  Event outcomes (gross, no costs): forward 20/60/120-day returns from the entry close; MFE120 = best close within 120 days vs entry;
    P(+20 % within 120 days). Trade read: the book as menu 6 with exit = trailing 10 % from the peak OR 120 trading days, K = 10.
READING RULES (declared before the run):
  Informative: an arm's median 60-day forward return beats its control by >= +3 pp with n >= 100 signals (>= 40 for the broker arms).
  Candidate for money: the menu-6 rule unchanged (>= 150 trades, t >= 2.5, Sharpe >= 1.0, mDD <= 25 %, >= 5 of 7 years, >= random + 0.5).
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_sleeper.py
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
import idx_trend as T  # noqa: E402

N_BEFORE = 287
ARMS = ["fflow", "obv", "broker2", "broker5", "fflow_obv"]
MIN_N = {"fflow": 100, "obv": 100, "fflow_obv": 100, "broker2": 40, "broker5": 40}
HS = (20, 60, 120)


def broker_masks(conn, dates, cols):
    det = pd.read_sql("""SELECT code, date_from, date_to, broker_accdist, top5_pct FROM idx.broker_detector WHERE code <> 'TEST'""", conn)
    det["date_to"] = pd.to_datetime(det["date_to"])
    det["span"] = (det["date_to"] - pd.to_datetime(det["date_from"])).dt.days
    det["top5_pct"] = pd.to_numeric(det["top5_pct"], errors="coerce")
    b20 = det[det["span"] >= 20].sort_values(["code", "date_to"])
    b5 = det[(det["span"] <= 9) & (det["date_to"] >= pd.Timestamp("2025-09-16"))].sort_values(["code", "date_to"])
    m2 = pd.DataFrame(False, index=dates, columns=cols)
    m5 = pd.DataFrame(False, index=dates, columns=cols)
    for code, g in b20.groupby("code"):
        if code not in cols:
            continue
        acc = (g["broker_accdist"] == "Acc").astype(int).rolling(3, min_periods=3).sum()
        for d, k in zip(g["date_to"], acc):
            if k >= 2 and d in m2.index:
                m2.at[d, code] = True
    for code, g in b5.groupby("code"):
        if code not in cols:
            continue
        pos = (g["top5_pct"] > 0).astype(int).rolling(6, min_periods=6).sum()
        for d, k in zip(g["date_to"], pos):
            if k >= 5 and d in m5.index:
                m5.at[d, code] = True
    return m2, m5, set(b20["code"].unique())


def event_stats(A, mask, H_list=HS):
    """Gross forward returns from close t+1 for every (t, name) with mask True; MFE within 120 days."""
    T_, N = A.shape
    out = {f"r{H}": [] for H in H_list}
    out["mfe"] = []
    ts, js = np.nonzero(mask)
    for t, j in zip(ts, js):
        e = t + 1
        if e + 120 >= T_ or np.isnan(A[e, j]):
            continue
        ok = True
        for H in H_list:
            if np.isnan(A[e + H, j]):
                ok = False
        if not ok:
            continue
        for H in H_list:
            out[f"r{H}"].append(A[e + H, j] / A[e, j] - 1)
        path = A[e + 1:e + 121, j]
        out["mfe"].append(np.nanmax(path) / A[e, j] - 1)
    return {k: np.array(v) for k, v in out.items()}


def fmt_event(ev):
    n = len(ev["r60"])
    if n == 0:
        return "| 0 | - | - | - | - | - | - | - |"
    return (f"| {n} | {(ev['r20'] > 0).mean() * 100:.0f} % | {np.median(ev['r20']) * 100:+.1f} % | {(ev['r60'] > 0).mean() * 100:.0f} % | {np.median(ev['r60']) * 100:+.1f} % "
            f"| {ev['r60'].mean() * 100:+.1f} % | {np.median(ev['r120']) * 100:+.1f} % | {np.median(ev['mfe']) * 100:+.1f} % / {(ev['mfe'] >= 0.20).mean() * 100:.0f} % |")


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        P = S.panels(bars, listing)
        _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
        adj = P["adj"]
        m2, m5, fed = broker_masks(conn, adj.index, adj.columns)
    c_in, c_out = S.costs(P)
    close, vol = P["close"], P["volume"]
    dates = adj.index
    A, C = adj.to_numpy(float), close.to_numpy(float)
    liq = unis["LIQ"]
    with psycopg.connect(dsn) as conn:
        mc = pd.read_sql("SELECT code, trade_date, mcap FROM idx.feature_daily WHERE trade_date >= %s", conn, params=(date(2020, 1, 1),))
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    mcap = mc.pivot(index="trade_date", columns="code", values="mcap").reindex(index=dates, columns=adj.columns)
    mcap.index = pd.to_datetime(mcap.index)
    small = liq & (mcap <= 5e12)
    r60 = adj / adj.shift(60) - 1
    rng60 = adj.rolling(60, min_periods=60).max() / adj.rolling(60, min_periods=60).min() - 1
    sideways_liq = liq & (r60.abs() <= 0.10) & (rng60 <= 0.25)
    sideways = small & (r60.abs() <= 0.10) & (rng60 <= 0.25)
    f20 = P["f20"]
    fflow = (f20 > 0) & (f20.shift(20) > 0) & (f20.shift(40) > 0)
    obv = (np.sign(adj.diff()).fillna(0) * vol.fillna(0)).cumsum()
    obv_up = (obv - obv.shift(60) > 0) & (obv - obv.shift(20) > 0)
    fed_cols = pd.Series([c in fed for c in adj.columns], index=adj.columns)
    fed_mask = pd.DataFrame(np.tile(fed_cols.to_numpy()[None, :], (len(dates), 1)), index=dates, columns=adj.columns)
    accum = {"fflow": fflow, "obv": obv_up, "broker2": m2, "broker5": m5, "fflow_obv": fflow & obv_up}
    base = {"fflow": sideways, "obv": sideways, "fflow_obv": sideways, "broker2": sideways & fed_mask, "broker5": sideways & fed_mask & (pd.Series(dates >= pd.Timestamp("2025-10-23"), index=dates).to_numpy()[:, None])}
    # windowed signals: broker arms only fire on window ends (their masks are True only there)
    n_trials = N_BEFORE + len(ARMS)
    events, controls, trades, verd, informative = {}, {}, {}, {}, {}

    def exit_rule(t, j, p):
        return A[t, j] <= 0.90 * p["peak"] or (t - p["e"]) >= 120
    rng = np.random.default_rng(T.SEED)
    R, tr, _ = T.run_book(A, C, c_in, c_out, sideways.to_numpy(bool), (-rng60).to_numpy(float), exit_rule, small.to_numpy(bool))
    ref_side = T.stats(R, tr, dates, n_trials)                       # sideways small caps without any accumulation test
    R, tr, _ = T.run_book(A, C, c_in, c_out, None, None, exit_rule, small.to_numpy(bool), rng=rng)
    ref_rand = T.stats(R, tr, dates, n_trials)
    ref_liq_event = event_stats(A, (sideways_liq & fflow).to_numpy(bool))
    for arm in ARMS:
        sig = base[arm] & accum[arm]
        ctl = base[arm] & ~accum[arm]
        if arm.startswith("broker"):                                  # control on the same window-end dates only
            win_dates = accum[arm].any(axis=1) | (accum[arm] != accum[arm])  # placeholder to keep dtype
            ends = (m2 if arm == "broker2" else m5).index[(m2 if arm == "broker2" else m5).any(axis=1)]
            ctl = ctl & pd.Series(dates.isin(ends), index=dates).to_numpy()[:, None]
        events[arm] = event_stats(A, sig.to_numpy(bool))
        controls[arm] = event_stats(A, ctl.to_numpy(bool))
        n = len(events[arm]["r60"])
        gap = (np.median(events[arm]["r60"]) - np.median(controls[arm]["r60"])) * 100 if n and len(controls[arm]["r60"]) else float("nan")
        informative[arm] = bool(n >= MIN_N[arm] and gap >= 3.0)
        R, tr, _ = T.run_book(A, C, c_in, c_out, sig.to_numpy(bool), (-rng60).to_numpy(float), exit_rule, small.to_numpy(bool))
        s = T.stats(R, tr, dates, n_trials)
        trades[arm] = s
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
        if s["sharpe"] < ref_rand["sharpe"] + 0.5:
            why.append("vs random")
        verd[arm] = "CANDIDATE" if not why else "tested: " + ",".join(why)

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))
    lines = [f"# IDX menu 8 — sleeping small caps under continuous accumulation — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             "## Event study (gross, every signal, equal weight): what happens after a sideways name has been accumulated", "",
             "| arm | n | P(up 20d) | med 20d | P(up 60d) | med 60d | avg 60d | med 120d | med MFE120 / P(>= +20 % within 120d) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for arm in ARMS:
        lines.append(f"| **{arm}** (sideways small cap + accumulation) " + fmt_event(events[arm]))
        lines.append(f"| control (sideways small cap, no {arm}) " + fmt_event(controls[arm]))
    lines.append("| reference: fflow on ALL liquid caps " + fmt_event(ref_liq_event))
    lines += ["", "| arm | n | median 60d gap vs control | informative? |", "|---|---|---|---|"]
    for arm in ARMS:
        n = len(events[arm]["r60"])
        gap = (np.median(events[arm]["r60"]) - np.median(controls[arm]["r60"])) * 100 if n and len(controls[arm]["r60"]) else float("nan")
        lines.append(f"| {arm} | {n} | {gap:+.1f} pp | {'YES' if informative[arm] else 'no'} |")
    lines += ["", "## Trade read (book of 10 slots, entry close t+1 @offer, exit trailing 10 % or 120 days @bid, Stockbit fees)", "",
              "| arm | trades | hold d | hit | avg net | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def row(label, s, v):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | {s['total'] * 100:+.0f} % | "
                f"{s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {v} |")
    lines.append(row("random entries + same exit", ref_rand, "reference"))
    lines.append(row("sideways only (no accumulation test)", ref_side, "reference"))
    for arm in ARMS:
        lines.append(row(arm, trades[arm], verd[arm]))
    n_c = sum(1 for v in verd.values() if v == "CANDIDATE")
    n_i = sum(1 for v in informative.values() if v)
    lines += ["", f"Reading rules applied as declared: informative {n_i} of {len(ARMS)}; candidates for money {n_c} of {len(ARMS)}.", "",
              "Limits: current listing board (not PIT); broker arms cover 46 names (20-day windows since 2023-09, 5-day windows since 2025-09);",
              "signals one day late (close-to-close); costs = quoted closing spread + fees; dividends ignored."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_SLEEPER_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        summ = {"events": {a: {k: {"n": int(len(v)), "median": float(np.median(v)) if len(v) else None, "mean": float(v.mean()) if len(v) else None,
                                   "p_up": float((v > 0).mean()) if len(v) else None} for k, v in e.items()} for a, e in events.items()},
                "controls": {a: {k: {"n": int(len(v)), "median": float(np.median(v)) if len(v) else None} for k, v in e.items()} for a, e in controls.items()},
                "trades": trades, "ref_random": ref_rand, "ref_sideways": ref_side, "verdicts": verd, "informative": informative, "candidates": n_c}
        sid = rs.record_study(conn, "sleeper", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials}, summary=summ, names=[],
                              report_path=out, note=f"informative {n_i}/{len(ARMS)}; candidates {n_c}/{len(ARMS)}")
        print("study", sid)


if __name__ == "__main__":
    main()
