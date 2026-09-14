#!/usr/bin/env python3
"""IDX — three names with the "highest upside" out of the strict list (2026-09-14).

The operator's idea: keep the strict composite as the universe, but hold only the three names with the most upside, and
re-pick them as the picture changes. "Upside" has to be a rule, so several definitions are pre-registered and each is one
trial (cumulative trial count continues from 137). Top 3 by:

  composite   the strict composite's own rank (the three cheapest on E/P + B/P + DY together)
  ep          earnings yield (the deepest discount on profit)
  vgap        value gap: ROE x B/P, i.e. ROE / (P/B) — the residual-income fair-P/B gap at a fixed cost of equity
  recovery    the deepest drawdown from the 52-week high (the most beaten-down; "room to recover")
  momentum    the highest 12-month return (upside continuing)
  growth      the highest net-profit growth (earnings upside)

Cadence: annual (pick at the rebalance, hold a year) for all six; plus a monthly re-pick within the annual list for the
three price-driven ones (ep_m, vgap_m, recovery_m: fundamentals fixed at the rebalance, prices as of each month start),
which is the operator's "keep rebalancing toward the highest upside". Nine trials -> cumulative 146.

Same simulator, costs and calendars as the strict record (reset mode, equal weight, four rebalance calendars 2021-2026).
Reference: the strict list in full, equal weight.

READING RULE, written before the run: a top-3 variant is a candidate only if
  (a) its CAGR beats the full strict list in at least three of four calendars,
  (b) its worst-calendar drawdown is not more than 8 points deeper than the full list's (a concentration allowance),
  (c) with its single best-contributing name excluded from every pick (re-picked without it), (a) still holds.
Anything else is "tested": a number in the catalog, not a plan.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_top3_upside.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

OUT = os.path.join(VQ.OUTDIR, "top3_upside_results.json")
N = 3
ANNUAL = ("composite", "ep", "vgap", "recovery", "momentum", "growth")
MONTHLY = ("ep_m", "vgap_m", "recovery_m")
TRIALS_BEFORE = 137


def f(v) -> float:
    try:
        return float(v) if v is not None else np.nan
    except (TypeError, ValueError):
        return np.nan


def drawdown_from_high(close: pd.DataFrame, code: str, D: pd.Timestamp) -> float:
    s = close[code].loc[:D].dropna()
    s = s.iloc[-250:]
    if len(s) < 120 or s.iloc[-1] <= 0:
        return np.nan
    return s.iloc[-1] / s.max() - 1                                   # negative; most negative = most beaten down


def score(kind: str, r: dict, close: pd.DataFrame, D: pd.Timestamp, px_now: float | None = None) -> float:
    """Higher = more upside. NaN = not rankable (drops to the bottom)."""
    if kind == "composite":
        return -f(r["rank"])
    p0 = f(r["price"])
    if kind in ("ep", "ep_m"):
        ep = f(r["ep"])
        return ep if kind == "ep" or px_now is None else ep * p0 / px_now
    if kind in ("vgap", "vgap_m"):
        roe, bp = f(r["roe"]), f(r["bp"])
        if kind == "vgap" or px_now is None:
            return roe * bp
        return roe * bp * p0 / px_now
    if kind in ("recovery", "recovery_m"):
        return -drawdown_from_high(close, r["code"], D)
    if kind == "momentum":
        return f(r["mom"])
    if kind == "growth":
        return f(r["np_yoy"])
    raise ValueError(kind)


def pick(kind: str, rows: list[dict], close: pd.DataFrame, D: pd.Timestamp, exclude: set[str], px_now: dict | None = None) -> set[str]:
    scored = []
    for r in rows:
        if r["code"] in exclude:
            continue
        s = score(kind, r, close, D, None if px_now is None else px_now.get(r["code"]))
        if not np.isnan(s):
            scored.append((s, r["code"]))
    scored.sort(reverse=True)
    return {c for _, c in scored[:N]}


def best_contributor(sel_by_date: dict, close, div, end) -> str:
    dates = sorted(sel_by_date)
    total: dict[str, float] = {}
    for a, b in zip(dates, [*dates[1:], end], strict=True):
        for code, ret in VQ.contributions(sel_by_date[a], close, div, a, b):
            total[code] = total.get(code, 0.0) + ret
    return max(total, key=total.get) if total else ""


def main():
    conn = VQ.connect()
    close, vol, delisted, div, ix = VQ.load(conn)
    end = close.index[-1]
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": TRIALS_BEFORE + len(ANNUAL) + len(MONTHLY), "months": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        lists = {}
        for D in rebals:
            rows = cand.build(conn, D.date())["all_rows"]
            lists[D] = [r for r in ST.pick("strict", rows) if r["selected"]]
        month_starts = [d for d in close.index if d >= rebals[0] and d == close.index[close.index.searchsorted(d.replace(day=1))]]
        table = {}
        print(f"\n=== month {month}: {[str(r.date()) for r in rebals]}")

        def run(kind: str, exclude: set[str]) -> tuple[dict, dict]:
            sel = {}
            if kind in ANNUAL:
                for D in rebals:
                    sel[D] = pick(kind, lists[D], close, D, exclude)
            else:
                for m in sorted(set(month_starts) | set(rebals)):
                    D = max(a for a in rebals if a <= m)
                    px_now = {r["code"]: close[r["code"]].loc[:m].dropna().iloc[-1] if r["code"] in close.columns and len(close[r["code"]].loc[:m].dropna()) else np.nan
                              for r in lists[D]}
                    sel[m] = pick(kind, lists[D], close, m, exclude, px_now)
            nav = VQ.simulate(sel, close, vol, delisted, div, rebals[0], end, True, mode="reset")
            st = VQ.stats(nav, rebals)
            st.pop("_r")
            return st, sel

        full = {D: {r["code"] for r in lists[D]} for D in rebals}
        nav = VQ.simulate(full, close, vol, delisted, div, rebals[0], end, True, mode="reset")
        ref = VQ.stats(nav, rebals); ref.pop("_r")
        table["strict_full"] = {"stats": ref}
        print(f"{'strict (full list)':22s} {ref['cagr_pct']:6.1f}·{ref['sharpe']:4.2f}·{ref['mdd_pct']:3.0f}%   names/yr {[len(full[D]) for D in rebals]}")
        for kind in (*ANNUAL, *MONTHLY):
            st, sel = run(kind, set())
            best = best_contributor({d: s for d, s in sel.items() if d in rebals} or sel, close, div, end)
            st_ex, _ = run(kind, {best}) if best else (st, sel)
            held = {str(d.date()): sorted(s) for d, s in sel.items() if d in rebals}
            table[kind] = {"stats": st, "picks": held, "best_name": best, "stats_ex_best": st_ex}
            print(f"{kind:22s} {st['cagr_pct']:6.1f}·{st['sharpe']:4.2f}·{st['mdd_pct']:3.0f}%   ex-{best or '-':5s} {st_ex['cagr_pct']:6.1f}·{st_ex['mdd_pct']:3.0f}%   picks {[held[k] for k in sorted(held)]}")
            sys.stdout.flush()
        results["months"][str(month)] = table

    print("\n--- reading rule: beats strict in >=3/4 calendars on CAGR, worst mDD not >8 pts deeper, and still >=3/4 without the best name")
    verdicts = {}
    months = results["months"]
    ref_dd = max(months[m]["strict_full"]["stats"]["mdd_pct"] for m in months)
    for kind in (*ANNUAL, *MONTHLY):
        wins = sum(months[m][kind]["stats"]["cagr_pct"] > months[m]["strict_full"]["stats"]["cagr_pct"] for m in months)
        wins_ex = sum(months[m][kind]["stats_ex_best"]["cagr_pct"] > months[m]["strict_full"]["stats"]["cagr_pct"] for m in months)
        dd = max(months[m][kind]["stats"]["mdd_pct"] for m in months)
        avg = float(np.mean([months[m][kind]["stats"]["cagr_pct"] for m in months]))
        avg_ex = float(np.mean([months[m][kind]["stats_ex_best"]["cagr_pct"] for m in months]))
        ok = wins >= 3 and dd <= ref_dd + 8 and wins_ex >= 3
        verdicts[kind] = {"avg_cagr": avg, "avg_cagr_ex_best": avg_ex, "wins": wins, "wins_ex_best": wins_ex, "worst_mdd": dd, "candidate": ok}
        print(f"  {kind:12s} avg CAGR {avg:5.1f} (ex-best {avg_ex:5.1f})  wins {wins}/4 (ex-best {wins_ex}/4)  worst mDD {dd:3.0f}% (strict {ref_dd:.0f}%)  -> {'CANDIDATE' if ok else 'tested'}")
    ref_avg = float(np.mean([months[m]["strict_full"]["stats"]["cagr_pct"] for m in months]))
    print(f"  {'strict_full':12s} avg CAGR {ref_avg:5.1f}  worst mDD {ref_dd:3.0f}%")
    results["verdicts"] = verdicts
    results["strict_full_avg_cagr"] = ref_avg
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
