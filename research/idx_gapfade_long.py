#!/usr/bin/env python3
"""IDX menu 29d — the gap-fade before the IDX opens exist (operator, 2026-09-23: "coba backtest dari 2008").

Menu 29b measured the rule on IDX-sourced opens, which are dense only from 2025: 266 events over 2023-2026. The desk also
holds a Yahoo daily cache back to 2004 for 450 current names. Can it carry the rule back to 2008?

TWO DATA QUESTIONS FIRST, both answered before any arm was run.

1. Is a Yahoo open the same number as the IDX open? On the 153,449 name-days of 2025-2026 where both exist, the Yahoo
   open rebased onto the IDX close equals the IDX open on **99.7 %** of them, the mean difference is 0 bps, and the same
   rule on the same days returns +227 bps on Yahoo opens against +228 bps on IDX opens. They are the same series.
   (This corrects menu 29, which blamed a Yahoo artefact for the gap_down arm: the Yahoo-filled rows there were a
   different ERA and a different population, not a different measurement. The lesson stands in a narrower form below.)

2. Are the OLD Yahoo opens real? No, not all of them. ``open == close`` on 65-99 % of traded days in 2007-2012 - the
   field is the close, not an opening price - falling to 40 % in 2013 and to the normal 14-18 % from 2015 onward, which
   is exactly what the IDX-verified years show. **So the rule cannot be measured before 2015, and 2013-2014 is doubtful.**
   A backtest "from 2008" would be reading a column that does not contain what its name says.

PRE-REGISTERED (declared before the run). 6 trials (cumulative 544 + 6 = 550).
  Data      the Yahoo cache rebased onto its own close, 2015-01-01 -> 2026-09-14, days with volume > 0 and high > low;
            a year is admitted only if its ``open == close`` share is under 30 % (the gate above). Survivorship is NOT
            fixable here: the cache holds today's 450 names, so anything delisted is missing and every number is
            flattered. Corporate actions are filtered by the same two tables the live scan uses.
  Universe  60-day median traded value >= Rp 5 bn on the previous day, previous close >= Rp 50, not locked at the open.
  Rule      gap <= -7 % at the open, deepest first, K = 10 a day, buy open + 1 tick, sell close - 1 tick, 0.10/0.20 %.
  Arms      by_era (2015-19, 2020-22, 2023-26), by_year, gap -5/-7/-10 %, and the 2015-2019 window on its own as the
            out-of-sample era the modern test never saw.
  Bar       the pre-2020 era CONFIRMS the rule if its mean net is > 0 and its daily t >= 2; it REFUTES it if the mean is
            negative with t <= -2; anything else is inconclusive and says so.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_gapfade_long.py
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_daytrade as D  # noqa: E402

CACHE = os.path.join(os.path.dirname(HERE), "research-scratch", "idx")
START, END = "2015-01-01", "2026-09-14"
K, LIQ, PRICE_MIN = 10, 5e9, 50
OPEN_EQ_CLOSE_MAX = 0.30
N_TRIALS_BEFORE = 544


def load_cache() -> pd.DataFrame:
    parts = []
    for f in glob.glob(os.path.join(CACHE, "*.JK.csv")):
        df = pd.read_csv(f, usecols=["date", "open", "high", "low", "close", "volume"])
        df["code"] = os.path.basename(f).split(".")[0]
        parts.append(df)
    d = pd.concat(parts, ignore_index=True)
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["open", "high", "low", "close"])
    d = d[(d["date"] >= START) & (d["date"] <= END) & (d["volume"] > 0) & (d["high"] > d["low"])]
    d["trade_date"] = pd.to_datetime(d["date"]).dt.date
    d["year"] = pd.to_datetime(d["date"]).dt.year
    return d.sort_values(["code", "trade_date"]).reset_index(drop=True)


def quality_gate(d: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, float]]:
    share = d.groupby("year").apply(lambda x: float(np.isclose(x["open"], x["close"], rtol=0.002).mean()), include_groups=False)
    keep = {int(y): float(v) for y, v in share.items() if v < OPEN_EQ_CLOSE_MAX}
    return d[d["year"].isin(keep)].copy(), {int(y): float(v) for y, v in share.items()}


def events(d: pd.DataFrame, dsn: str, gap_max: float) -> pd.DataFrame:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT code, ex_date FROM idx.corporate_action")
        ca = {(r["code"], r["ex_date"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()}
        cur.execute("SELECT code, ex_date FROM idx.dividend")
        ca |= {(r["code"], r["ex_date"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()}
    d = d.copy()
    d["prev"] = d.groupby("code")["close"].shift(1)
    d["value"] = d["close"] * d["volume"]
    d["v60"] = d.groupby("code")["value"].transform(lambda s: s.rolling(60, min_periods=40).median()).groupby(d["code"]).shift(1)
    d["gap"] = d["open"] / d["prev"] - 1
    locked = (d["open"] == d["high"]) & (d["high"] == d["low"])
    ev = d[(d["gap"] <= gap_max) & (d["v60"] >= LIQ) & (d["prev"] >= PRICE_MIN) & ~locked].copy()
    keep = np.array([(c, t) not in ca for c, t in zip(ev["code"], ev["trade_date"], strict=True)])
    ev = ev[keep]
    # a split the desk never recorded shows as a gap deeper than the market allows in a day
    band = np.select([ev["prev"] <= 200, ev["prev"] <= 5000], [0.35, 0.25], 0.20)
    ev = ev[ev["gap"] >= -band]
    return ev.sort_values(["trade_date", "v60"], ascending=[True, False]).groupby("trade_date").head(K).reset_index(drop=True)


def returns(ev: pd.DataFrame) -> np.ndarray:
    o, c = ev["open"].to_numpy(dtype=float), ev["close"].to_numpy(dtype=float)
    buy = (o + D.tick(o)) * (1 + D.FEE_BUY)
    sell = (c - D.tick(c)) * (1 - D.FEE_SELL)
    return sell / buy - 1


def read(ev: pd.DataFrame, r: np.ndarray) -> dict:
    if len(r) < 20:
        return {"events": len(r), "verdict": "too few"}
    s = pd.Series(r, index=pd.to_datetime(ev["trade_date"]))
    day = s.groupby(s.index).mean()
    n = s.groupby(s.index).size().clip(upper=5)
    sleeve = (day * (n / 5)).sort_index()
    eq = (1 + sleeve).cumprod()
    t = float(day.mean() / (day.std(ddof=1) / np.sqrt(len(day)))) if len(day) > 2 and day.std(ddof=1) > 0 else float("nan")
    yrs = sleeve.groupby(sleeve.index.year).apply(lambda x: (1 + x).prod() - 1)
    return {"events": len(r), "names": int(ev["code"].nunique()), "days": len(day), "hit": float((r > 0).mean()),
            "mean_bps": float(r.mean() * 1e4), "median_bps": float(np.median(r) * 1e4), "daily_t": t,
            "worst_bps": float(r.min() * 1e4), "sleeve_total_pct": float((eq.iloc[-1] - 1) * 100),
            "sleeve_mdd_pct": float((eq / eq.cummax() - 1).min() * 100),
            "sharpe": float(sleeve.mean() / sleeve.std(ddof=1) * np.sqrt(252)) if sleeve.std(ddof=1) > 0 else float("nan"),
            "years_pos": int((yrs > 0).sum()), "years_n": len(yrs),
            "by_year": {int(y): round(float(v) * 100, 1) for y, v in yrs.items()}}


def run(dsn: str, out: str, store: bool, study_name: str) -> dict:
    raw = load_cache()
    d, shares = quality_gate(raw)
    res: dict = {"quality": {"open_eq_close_by_year": {y: round(v * 100, 1) for y, v in sorted(shares.items())},
                             "admitted_years": sorted({int(y) for y in d["year"].unique()}),
                             "gate": f"a year is admitted only if open == close on under {OPEN_EQ_CLOSE_MAX:.0%} of traded days"},
                 "arms": {}}
    ev = events(d, dsn, -0.07)
    r = returns(ev)
    res["arms"]["all 2015-2026"] = read(ev, r)
    for label, lo, hi in (("2015-2019 (out of sample)", 2015, 2019), ("2020-2022", 2020, 2022), ("2023-2026", 2023, 2026)):
        m = (pd.to_datetime(ev["trade_date"]).dt.year >= lo) & (pd.to_datetime(ev["trade_date"]).dt.year <= hi)
        res["arms"][label] = read(ev[m], r[m.to_numpy()])
    for g in (-0.05, -0.10):
        e2 = events(d, dsn, g)
        res["arms"][f"gap <= {g*100:.0f} %"] = read(e2, returns(e2))
    pre = res["arms"]["2015-2019 (out of sample)"]
    if "mean_bps" in pre:
        res["verdict"] = ("CONFIRMS" if pre["mean_bps"] > 0 and pre["daily_t"] >= 2 else
                          "REFUTES" if pre["mean_bps"] < 0 and pre["daily_t"] <= -2 else "inconclusive")
    else:
        res["verdict"] = "no data"
    write(res, out)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            res["study_id"] = rs.record_study(conn, study_name, date.fromisoformat(END),
                                              params={"trials": list(res["arms"]), "n_trials_cumulative": N_TRIALS_BEFORE + 6,
                                                      "gate": OPEN_EQ_CLOSE_MAX, "start": START, "end": END},
                                              summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out,
                                              note=f"pre-2020 era {res['verdict']}; 2008-2012 unusable (Yahoo open == close on 65-99 % of days)")
    return res


def write(res: dict, path: str) -> None:
    q = res["quality"]
    L = ["# IDX menu 29d — how far back can the gap-fade be measured? — written 2026-09-23", "",
         "The operator asked for a backtest from 2008. It cannot be done, and the reason is in the data, not the rule.", "",
         "## Can a Yahoo 'open' stand in for the IDX open?", "",
         "- **After 2015, yes.** On the 153,449 name-days of 2025-2026 where both exist, the Yahoo open rebased onto the IDX",
         "  close equals the IDX open on **99.7 %** of them (mean difference 0 bps), and the rule returns +227 bps on Yahoo",
         "  opens against +228 bps on IDX opens over the same events. *This corrects menu 29, which blamed a Yahoo artefact:*",
         "  *the Yahoo-filled rows there were a different era and population, not a different measurement.*",
         "- **Before 2013, no.** The share of traded days where `open == close`:", "",
         "| year | open == close |", "|---|---|"]
    for y, v in q["open_eq_close_by_year"].items():
        L.append(f"| {y} | {'**' if v >= 30 else ''}{v:.0f} %{'**' if v >= 30 else ''} |")
    L += ["", "  65-99 % in 2007-2012 means the column holds the close, not an opening price; 40 % in 2013, and the normal",
          "  14-18 % only from 2015. A 2008 backtest of a rule that buys the open would be reading a field that does not",
          f"  contain an open. Admitted years: {q['admitted_years'][0]}-{q['admitted_years'][-1]}.", "",
          "## The rule where the data allows it (Yahoo cache, survivors only)", "",
          "| window | events | names | days | hit | mean | median | daily t | sleeve | max DD | Sharpe | years + |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, a in res["arms"].items():
        if "mean_bps" not in a:
            L.append(f"| {k} | {a['events']} | | | | | | | | | | {a['verdict']} |")
            continue
        L.append(f"| {k} | {a['events']} | {a['names']} | {a['days']} | {a['hit']*100:.0f} % | **{a['mean_bps']:+.0f}** | "
                 f"{a['median_bps']:+.0f} | {a['daily_t']:.1f} | {a['sleeve_total_pct']:+.0f} % | {a['sleeve_mdd_pct']:.0f} % | "
                 f"{a['sharpe']:.2f} | {a['years_pos']}/{a['years_n']} |")
    L += ["", "## By year (sleeve return, 5 slots)", ""]
    a = res["arms"].get("all 2015-2026", {})
    if "by_year" in a:
        L.append("- " + ", ".join(f"{y}: {v:+.0f} %" for y, v in a["by_year"].items()))
    L += ["", "## Verdict", "",
          f"- The 2015-2019 era, which the modern test never saw: **{res['verdict']}**.",
          "- Survivorship is not fixable from this cache: it holds the 450 names that exist today, so every delisted name",
          "  is missing and every figure here is flattered. Treat the pre-2020 numbers as direction, not level.",
          "- To go back further the desk would need a source with true opening-auction prices before 2013; the IDX bronze",
          "  archive starts in 2020 and Yahoo's older opens are not opens.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="gapfade_long")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_GAPFADE_LONG_{date.today().isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], out, not a.no_store, a.study_name)
    print(json.dumps({"verdict": res["verdict"], "admitted": res["quality"]["admitted_years"],
                      "arms": {k: {x: v.get(x) for x in ("events", "mean_bps", "daily_t", "sleeve_total_pct", "sharpe")}
                               for k, v in res["arms"].items()}, "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
