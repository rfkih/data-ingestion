#!/usr/bin/env python3
"""IDX — trend overlays for entry and exit (2026-09-13). The operator's ask: enter only when the trend is up (no falling
knives) and do not let a pandemic-sized crash take the book. Does a technical layer on top of the fundamental book protect
it in a crisis, and what does it cost in calm years?

Two parts, PRE-REGISTERED before the run.

PART A — 2008-2026, price only. Yahoo adjusted closes cached in research-scratch/idx: the 450 names alive today + ^JKSE.
  Survivorship: only names alive in 2026 are in that cache, so the basket's own drawdowns are flattered; every overlay is
  measured against the SAME basket, so the comparison is fair even if the level is not. Price returns, no dividends, in
  every arm. Cash earns 4 %/yr (a net rupiah deposit over the period; the first run paid it 0 and is kept in the report).
  Basket: each May (first weekday >= 2 May), the 100 most traded names (60-day median value) with a year of history,
  equal weight, "drift" mode (exits sold, entrants bought from cash, no re-weighting). Overlays are checked on the first
  trading day of each month and trade at that close:
    A0 basket, no overlay
    A1 index regime       all to cash while JKSE < its 200-day average; back in when above
    A2 index regime, band exit below 0.97 x SMA200, re-enter above 1.03 x SMA200 (hysteresis against whipsaw)
    A3 name trend         hold a name only while it is above its own 200-day average; below -> cash; re-entrants capped
    A4 name momentum      hold a name only while its 12-1 month return is positive (absolute momentum)
    A5 trailing stop      sell a name 20 % below its highest close since entry; re-enter when back above its SMA200
    JKSE itself with A1 and A2 (pure index timing) as reference lines.
  Read: total, CAGR, Sharpe, max drawdown, days fully in cash, switches, and the drawdown inside each episode:
    2008 (Jan 08-Mar 09), 2011 (Jul-Oct), 2013 taper (May-Aug), 2015 (Apr-Sep), 2018 (Jan-Oct), 2020 COVID (Jan-Mar),
    2022 (full year), 2025 (Jan-Apr).

PART B — 2021-2026, the real book: the strict composite (PIT lists, real costs, dividends net of tax) with the same
  overlays, four rebalance calendars. B5 isolates the operator's entry idea: buy a listed name only when it is above its
  SMA200 (at the rebalance, or at the first monthly check where it crosses), but never sell on trend.
    B0 strict (reference) | B1 index regime | B2 index regime, band | B3 name trend | B4 trailing stop | B5 entry-only gate
  Per-name entrants are capped at one equal-weight slot of the current list (1/N); the rest of the cash waits. Cash
  earns 4 %/yr here too.

ADOPTION CRITERION (declared before the run). An overlay goes on the book only if
  (i)  in Part A it cuts the basket's 2008 AND 2020 episode drawdowns by at least 10 points each, and
  (ii) in Part B its total return is within 20 % (relative) of plain strict in at least 3 of 4 calendars and its
       worst-calendar max drawdown is not deeper than strict's.
Trials: 7 (Part A) + 5 (Part B) = 12; cumulative this session 71 + 12 = 83.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_trend_overlay.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import equity_screen as ES  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

N_TRIALS = 83
OUT = os.path.join(VQ.OUTDIR, "trend_overlay_results.json")
YAHOO = os.path.join(VQ.ROOT, "research-scratch", "idx")
SMA, BAND, STOP, BASKET_N, HISTORY = 200, 0.03, 0.20, 100, 250
CASH_RATE = 0.04
EPISODES = {"2008": ("2008-01-01", "2009-03-31"), "2011": ("2011-07-01", "2011-10-31"), "2013": ("2013-05-20", "2013-08-31"),
            "2015": ("2015-04-01", "2015-09-30"), "2018": ("2018-01-01", "2018-10-31"), "2020": ("2020-01-01", "2020-03-31"),
            "2022": ("2022-01-01", "2022-12-31"), "2025": ("2025-01-01", "2025-04-30")}
OVERLAYS = ("none", "index", "index_band", "name_trend", "name_mom", "stop")
EMPTY_DIV = pd.DataFrame(columns=["code", "ex", "dps"])


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def load_yahoo() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    closes, vols = {}, {}
    for f in sorted(glob.glob(os.path.join(YAHOO, "*.JK.csv"))):
        code = os.path.basename(f).split(".")[0]
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        closes[code], vols[code] = df["close"].astype(float), df["volume"].astype(float)
    close = pd.DataFrame(closes).sort_index()
    vol = pd.DataFrame(vols).sort_index().reindex(close.index)
    jk = pd.read_csv(os.path.join(YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    jk = jk[~jk.index.duplicated(keep="last")]
    return close, vol, jk


def month_starts(index: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    idx = index[(index >= start) & (index <= end)]
    s = pd.Series(idx, index=idx)
    return list(s.groupby([idx.year, idx.month]).first())


def baskets(close: pd.DataFrame, vol: pd.DataFrame, dates: list[pd.Timestamp]) -> dict[pd.Timestamp, set[str]]:
    value = (close * vol).rolling(60, min_periods=40).median()
    hist = close.notna().rolling(HISTORY, min_periods=1).sum()
    out = {}
    for D in dates:
        ok = (hist.loc[D] >= HISTORY) & close.loc[D].notna() & (vol.loc[D] > 0)
        v = value.loc[D][ok].dropna().sort_values(ascending=False)
        out[D] = set(v.index[:BASKET_N])
    return out


# ---------------------------------------------------------------------------
# overlays -> simulate() plans
# ---------------------------------------------------------------------------
class Signals:
    """Everything an overlay reads, aligned to the check dates: index regime, per-name SMA200 and 12-1 momentum."""

    def __init__(self, close: pd.DataFrame, jk: pd.Series, checks: list[pd.Timestamp]):
        self.checks = checks
        jk_sma = jk.rolling(SMA, min_periods=SMA).mean()
        self.jk = jk.reindex(checks, method="ffill")
        self.jk_sma = jk_sma.reindex(checks, method="ffill")
        self.px = close.reindex(checks, method="ffill")
        self.sma = close.rolling(SMA, min_periods=SMA).mean().reindex(checks, method="ffill")
        self.mom = (close.shift(21) / close.shift(252) - 1).reindex(checks, method="ffill")
        self.close = close

    def regime(self, m: pd.Timestamp) -> bool:
        return bool(self.jk.loc[m] > self.jk_sma.loc[m]) if not np.isnan(self.jk_sma.loc[m]) else True

    def above_sma(self, m: pd.Timestamp, codes: set[str]) -> set[str]:
        row, sma = self.px.loc[m], self.sma.loc[m]
        return {c for c in codes if c in row.index and not np.isnan(sma.get(c, np.nan)) and row[c] > sma[c]}

    def mom_pos(self, m: pd.Timestamp, codes: set[str]) -> set[str]:
        mom = self.mom.loc[m]
        return {c for c in codes if c in mom.index and not np.isnan(mom[c]) and mom[c] > 0}


def build_plan(kind: str, lists: dict[pd.Timestamp, set[str]], sig: Signals) -> dict:
    """The plan for one overlay: at every check date (annual list dates included) what the book should hold."""
    annual = sorted(lists)
    checks = sorted(set(sig.checks) | set(annual))

    def current(m):
        return lists[max(a for a in annual if a <= m)]

    plan: dict = {}
    state = {"on": None, "entry": {}, "prev_held": set(), "prev_date": None}
    for m in checks:
        L = current(m)
        if kind == "none":
            plan[m] = set(L)
        elif kind == "index":
            plan[m] = set(L) if sig.regime(m) else set()
        elif kind == "index_band":
            jk, sma = sig.jk.loc[m], sig.jk_sma.loc[m]
            if np.isnan(sma):
                on = True
            else:
                on = state["on"] if state["on"] is not None else jk > sma
                if on and jk < (1 - BAND) * sma:
                    on = False
                elif not on and jk > (1 + BAND) * sma:
                    on = True
            state["on"] = on
            plan[m] = set(L) if on else set()
        elif kind == "name_trend":
            plan[m] = sig.above_sma(m, L)
        elif kind == "name_mom":
            plan[m] = sig.mom_pos(m, L)
        elif kind == "entry_only":
            def rule(held, m=m, L=L):
                return (held & L) | sig.above_sma(m, L - held)
            plan[m] = rule
        elif kind == "stop":
            def rule(held, m=m, L=L):
                entry, prev = state["entry"], state["prev_held"]
                for c in held - prev:                                          # bought at the previous check
                    entry[c] = state["prev_date"] if state["prev_date"] is not None else m
                for c in prev - held:
                    entry.pop(c, None)
                keep = set()
                for c in held & L:
                    since = entry.get(c, m)
                    peak = sig.close[c].loc[since:m].max()
                    if not (np.isnan(peak) or sig.px.loc[m].get(c, np.nan) < (1 - STOP) * peak):
                        keep.add(c)
                    else:
                        entry.pop(c, None)
                out = keep | sig.above_sma(m, L - held)
                state["prev_held"], state["prev_date"] = set(held), m
                return out
            plan[m] = rule
        else:
            raise ValueError(kind)
    return plan


# ---------------------------------------------------------------------------
# reading a NAV
# ---------------------------------------------------------------------------
def episode_dd(nav: pd.Series) -> dict[str, float | None]:
    out = {}
    for k, (a, b) in EPISODES.items():
        seg = nav.loc[a:b]
        out[k] = round(100 * float((seg / seg.cummax() - 1).min()), 1) if len(seg) > 5 else None
    return out


def read(nav: pd.Series, rebals: list[pd.Timestamp]) -> dict:
    st = VQ.stats(nav, rebals)
    r = st.pop("_r")
    st["dsr"] = round(ES.deflated_sharpe(list(r), N_TRIALS), 3)
    st["psr"] = round(ES.deflated_sharpe(list(r), 1), 3)
    st["episodes"] = episode_dd(nav)
    st["cash_days_pct"] = round(100 * float((r == 0).mean()), 1)
    return st


def line(label: str, v: dict, eps: tuple[str, ...]) -> str:
    e = " ".join(f"{k}:{(v['episodes'][k] if v['episodes'][k] is not None else float('nan')):+.0f}" for k in eps)
    return (f"{label:14s} {v['total_pct']:8.0f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v['cash_days_pct']:5.0f} "
            f"{v['dsr']:5.2f} | {e}")


# ---------------------------------------------------------------------------
def part_a(results: dict) -> None:
    close, vol, jk = load_yahoo()
    end = close.index[-1]
    annual = []
    for y in range(2008, end.year + 1):
        pos = close.index.searchsorted(pd.Timestamp(f"{y}-05-02"))
        if pos < len(close.index):
            annual.append(close.index[pos])
    lists = baskets(close, vol, annual)
    checks = sorted(set(month_starts(close.index, annual[0], end)) | set(annual))
    sig = Signals(close, jk, checks)
    eps = tuple(EPISODES)
    print(f"\n=== PART A: {len(close.columns)} names (Yahoo, survivors), basket of {BASKET_N} from {annual[0].date()} to {end.date()}, "
          f"monthly checks, price returns, cash {100 * CASH_RATE:.0f} %/yr  (DSR at N_trials = {N_TRIALS})")
    print(f"{'arm':14s} {'total%':>8} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'cash%':>5} {'DSR':>5} | episode drawdowns %")
    table = {}
    for kind in OVERLAYS:
        plan = build_plan(kind, lists, sig)
        nav = VQ.simulate(plan, close, vol, {}, EMPTY_DIV, annual[0], end, True, mode="drift", cap=1 / BASKET_N, cash_rate=CASH_RATE)
        table[f"basket/{kind}"] = read(nav, annual)
        print(line(f"basket/{kind}", table[f"basket/{kind}"], eps))
        sys.stdout.flush()
    # the index itself, timed
    jk_close = pd.DataFrame({"JKSE": jk}).reindex(close.index).ffill()
    jk_vol = pd.DataFrame({"JKSE": 1.0}, index=close.index)
    jk_lists = {annual[0]: {"JKSE"}}
    for kind in ("none", "index", "index_band"):
        plan = build_plan(kind, jk_lists, Signals(jk_close, jk, checks))
        nav = VQ.simulate(plan, jk_close, jk_vol, {}, EMPTY_DIV, annual[0], end, False, mode="drift", cash_rate=CASH_RATE)
        table[f"JKSE/{kind}"] = read(nav, annual)
        print(line(f"JKSE/{kind}", table[f"JKSE/{kind}"], eps))
    results["part_a"] = {"start": str(annual[0].date()), "end": str(end.date()), "names": len(close.columns), "table": table}


def part_b(results: dict) -> None:
    conn = VQ.connect()
    close, vol, delisted, div, ix = VQ.load(conn)
    end = close.index[-1]
    jk = ix["COMPOSITE"].dropna()
    eps = ("2022", "2025")
    results["part_b"] = {}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        rows_at = {D: cand.build(conn, D.date())["all_rows"] for D in rebals}
        lists = {D: {r["code"] for r in ST.pick("strict", rows_at[D]) if r["selected"]} for D in rebals}
        checks = sorted(set(month_starts(close.index, rebals[0], end)) | set(rebals))
        sig = Signals(close, jk, checks)
        print(f"\n=== PART B month {month}: strict composite {[str(r.date()) for r in rebals]}, monthly checks, real costs and dividends")
        print(f"{'arm':14s} {'total%':>8} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'cash%':>5} {'DSR':>5} | episode drawdowns %")
        table = {}
        def slot(d, lists=lists):
            return 1 / max(1, len(lists[max(a for a in lists if a <= d)]))

        for kind in ("none", "index", "index_band", "name_trend", "stop", "entry_only"):
            plan = build_plan(kind, lists, sig)
            nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="drift", cap=slot, cash_rate=CASH_RATE)
            table[kind] = read(nav, rebals)
            print(line(kind, table[kind], eps))
            sys.stdout.flush()
        results["part_b"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}


def verdict(results: dict) -> None:
    a = results["part_a"]["table"]
    base = a["basket/none"]["episodes"]
    print("\n--- adoption criterion (declared before the run)")
    out = {}
    for kind in ("index", "index_band", "name_trend", "name_mom", "stop"):
        e = a[f"basket/{kind}"]["episodes"]
        cut08 = (base["2008"] or 0) - (e["2008"] or 0)
        cut20 = (base["2020"] or 0) - (e["2020"] or 0)
        i_ok = cut08 <= -10 and cut20 <= -10                                 # drawdowns are negative numbers: cut = less negative
        b_ok, wins, dd_ok = None, None, None
        if kind in ("index", "index_band", "name_trend", "stop") and results.get("part_b"):
            wins = sum(results["part_b"][m]["table"][kind]["total_pct"] >= 0.8 * results["part_b"][m]["table"]["none"]["total_pct"]
                       for m in results["part_b"])
            dd_ok = max(results["part_b"][m]["table"][kind]["mdd_pct"] for m in results["part_b"]) <= \
                max(results["part_b"][m]["table"]["none"]["mdd_pct"] for m in results["part_b"])
            b_ok = wins >= 3 and dd_ok
        out[kind] = {"cut_2008_pts": round(-cut08, 1), "cut_2020_pts": round(-cut20, 1), "part_a_ok": bool(i_ok),
                     "part_b_wins": wins, "part_b_dd_ok": dd_ok, "adopt": bool(i_ok and b_ok)}
        print(f"    {kind:12s} 2008 dd cut {-cut08:+5.1f} pts, 2020 dd cut {-cut20:+5.1f} pts -> part A {'ok' if i_ok else 'no'}; "
              f"part B within 20 % in {wins}/4, drawdown ok {dd_ok} -> {'ADOPT' if out[kind]['adopt'] else 'not adopted'}")
    if results.get("part_b"):
        e = "entry_only"
        wins = sum(results["part_b"][m]["table"][e]["total_pct"] >= 0.8 * results["part_b"][m]["table"]["none"]["total_pct"] for m in results["part_b"])
        print(f"    {e:12s} (no part A arm) part B within 20 % in {wins}/4")
    results["verdict"] = out


def main():
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS}
    part_a(results)
    part_b(results)
    verdict(results)
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
