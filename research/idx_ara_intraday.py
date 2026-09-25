#!/usr/bin/env python3
"""IDX menu 45b - does a 3-6 % stop rescue the ARA open-entry rule? Answered from the FEED's minute bars (operator
2026-09-26: "test on the daily feed data").

Menu 45 (#200) CLOSED the operator's rule on daily bars: buy the model's top buyable ARA pick at the open (+1 tick), sell at
the lower of +20 % / the ARA price, else at the close -> -74 bps a trade. Adding a stop gave -72..-121 bps if the stop was hit
first and +124..+239 bps if the take-profit was hit first: 41-59 % of the winners also touched the stop the same day, so the
answer depends on the intraday ORDER, which daily bars do not have. From 2026-09-26 the scheduler subscribes the top 5 picks
by calibrated p_lock to the feed every evening (scheduler._ara_feed_subscribe, reason 'ara_paper'), so idx.feed_bar_1m
records their next session minute by minute. This script replays the rule on those minutes. PAPER only.

PRE-REGISTERED (written 2026-09-26, before any feed session of the picks exists):
  Pick: for each session S, the picks = idx.ara_watch run on the previous trading day, ordered by p_lock; take the first
    whose first minute bar's open is below its ara_px (buyable at the open) and has minute bars that session.
  Entry: first minute bar's open + 1 tick. Take-profit TP = min(entry x 1.20, ara_px). Stop = entry x (1 - s), fill at the
    stop - 1 tick. Walk the minutes in order: a minute whose low <= stop exits at the stop (checked BEFORE the take-profit
    inside the same minute - the conservative reading; the count of such same-minute conflicts is reported); else a high
    >= TP exits at TP; else the last minute's close. Fees 0.15 % buy / 0.25 % sell.
  Arms: s in {none, 3 %, 4 %, 5 %, 6 %} - 5 counted trials when judged (cumulative N at judgement).
  JUDGEMENT only when >= 30 sessions with a traded pick exist (not before - early numbers are anecdotes):
    an arm PASSES if mean net per trade > 0 with t >= 2, net positive in >= 55 % of calendar weeks with a trade, and it
    beats the no-stop arm on the same sessions. Otherwise the stop idea is CLOSED and the ARA freeze stays as it is.
  Until then it prints the running tally, clearly labelled NOT A RESULT.
READ-ONLY. Env INGEST_DB_DSN (idx-local.env). Usage: python research/idx_ara_intraday.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import psycopg

STOPS = [None, 0.03, 0.04, 0.05, 0.06]
MIN_SESSIONS = 30
FB, FS = 0.0015, 0.0025
N_PICKS = 5


def tick(p: float) -> float:
    return 1.0 if p < 200 else 2.0 if p < 500 else 5.0 if p < 2000 else 10.0 if p < 5000 else 25.0


def floor_tick(p: float) -> float:
    t = tick(p)
    return np.floor(p / t) * t


def replay(bars: pd.DataFrame, entry: float, tp: float, s: float | None) -> tuple[float, str, bool]:
    stop = floor_tick(entry * (1 - s)) if s else None
    conflict = False
    for b in bars.itertuples():
        hit_s = stop is not None and b.low <= stop
        hit_t = b.high >= tp
        if hit_s and hit_t:
            conflict = True
        if hit_s:
            return stop - tick(stop), "stop", conflict
        if hit_t:
            return tp, "tp", conflict
    return float(bars["close"].iloc[-1]), "close", conflict


def main() -> int:
    conn = psycopg.connect(os.environ["INGEST_DB_DSN"])
    conn.read_only = True
    q = lambda sql, p=(): pd.DataFrame(*(lambda c: (c.fetchall(), [d.name for d in c.description]))(conn.execute(sql, p)))  # noqa: E731
    fb = q("""SELECT (minute AT TIME ZONE 'Asia/Jakarta') AS m, code, open, high, low, close FROM idx.feed_bar_1m
               WHERE minute >= '2026-09-28' ORDER BY code, minute""")
    if fb.empty:
        print("no feed minute bars since the ARA paper subscription started (2026-09-28) - nothing to replay yet")
        return 0
    for c in ("open", "high", "low", "close"):
        fb[c] = fb[c].astype(float)
    fb["d"] = pd.to_datetime(fb["m"]).dt.date
    sessions = sorted(fb["d"].unique())
    runs = q("SELECT run_date, code, p_lock, ara_px FROM idx.ara_watch WHERE run_date >= '2026-09-25' AND p_lock IS NOT NULL")
    rows = []
    for S in sessions:
        prev = runs[runs["run_date"] < S]
        if prev.empty:
            continue
        r = prev[prev["run_date"] == prev["run_date"].max()].sort_values("p_lock", ascending=False).head(N_PICKS)
        for pick in r.itertuples():
            bars = fb[(fb["d"] == S) & (fb["code"] == pick.code)]
            if bars.empty:
                continue
            o, ara = float(bars["open"].iloc[0]), float(pick.ara_px)
            if o >= ara:
                continue                                                   # locked at the open: no fill, next pick
            entry = o + tick(o)
            tp = min(floor_tick(entry * 1.20), ara)
            rec = {"d": S, "code": pick.code, "p_lock": float(pick.p_lock), "entry": entry}
            for s in STOPS:
                x, how, conf = replay(bars, entry, tp, s)
                k = "none" if s is None else f"{int(s * 100)}%"
                rec[k] = x * (1 - FS) / (entry * (1 + FB)) - 1
                rec[k + "_how"], rec[k + "_conflict"] = how, conf
            rows.append(rec)
            break
    T = pd.DataFrame(rows)
    n = len(T)
    label = "JUDGEMENT" if n >= MIN_SESSIONS else f"RUNNING TALLY - NOT A RESULT ({n} of {MIN_SESSIONS} sessions)"
    print(f"menu 45b ARA stop on feed minutes: {label}")
    if not n:
        return 0
    T["week"] = pd.to_datetime(T["d"]).dt.to_period("W")
    for k in ("none", "3%", "4%", "5%", "6%"):
        x = T[k]
        t = x.mean() / x.std() * np.sqrt(n) if n > 1 and x.std() > 0 else float("nan")
        wk = (x.groupby(T["week"]).mean() > 0).mean()
        conf = int(T.get(k + "_conflict", pd.Series(dtype=bool)).sum()) if k != "none" else 0
        verdict = ""
        if n >= MIN_SESSIONS and k != "none":
            ok = x.mean() > 0 and t >= 2 and wk >= 0.55 and x.mean() > T["none"].mean()
            verdict = "PASS" if ok else "fail"
        print(f"  stop {k:>4}: mean {x.mean() * 1e4:+6.0f} bps  t {t:5.2f}  win {(x > 0).mean():4.0%}  weeks+ {wk:4.0%}  "
              f"exits {T[k + '_how'].value_counts().to_dict()}  same-minute conflicts {conf}  {verdict}")
    print(T[["d", "code", "p_lock", "entry", "none", "3%", "5%"]].tail(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
