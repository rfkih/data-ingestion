#!/usr/bin/env python3
"""IDX — normal: the strict list with a momentum tilt; after a crash: the most undervalued names (2026-09-14).

The operator's idea. In a normal market hold the strict composite tilted to momentum; once the market has crashed,
shift to the most undervalued names, which lead the rebound; return to the strict list when the market has recovered.

Definitions, fixed before the run:
  crash on     at a monthly check the COMPOSITE closes 20 % or more under its 252-day high
  crash off    at a monthly check the COMPOSITE closes above its 200-day average
  normal list  the strict composite, weights linear 2:1 from the highest 12-1 momentum to the lowest (IDX_MOM_GROWTH)
  deep value   built at the check that turns the crash on (and at annual rebalances while it stays on):
    dv_strict_ep   strict gate, the cheapest fifth by earnings yield alone
    dv_loose_ep    loose gate (profit, ROE >= 5 %), the cheapest fifth by earnings yield: lower quality, harder bounce
    dv_beaten      strict gate pool, the fifth that fell furthest from its 252-day high (price only)
  Deep-value lists are equal weight. When the crash turns off, the book returns to the current annual normal list.

PRE-REGISTERED MENU (3 trials; cumulative 170 + 3 = 173). References: strict (equal weight, annual), tilt (the normal
list without any switch). Windows: 2021-2026 on four calendars; 2020-2026 on May/Aug/Nov (the COVID rebound);
2008-2026 on the 100-name basket, May calendar, price only, dv_beaten only (fundamentals do not exist before 2020).

READING RULE, written before the run: a switch variant is a candidate only if its CAGR beats tilt in three of four
2021-start calendars AND two of three 2020-start calendars, its worst drawdown is not more than 5 points deeper than
tilt's, and with its single best-contributing deep-value name excluded it still beats tilt in three of four; on the
2008 basket dv_beaten must beat the basket's CAGR with a drawdown no more than 5 points deeper.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_crash_switch.py
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
import idx_mom_growth as MG  # noqa: E402
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

OUT = os.path.join(VQ.OUTDIR, "crash_switch_results.json")
TRIALS = 173
DV = ("dv_strict_ep", "dv_loose_ep", "dv_beaten")
CRASH_DD = -0.20


def crash_states(jk: pd.Series, checks: list[pd.Timestamp]) -> dict[pd.Timestamp, bool]:
    jk = jk.dropna()
    hi = jk.rolling(252, min_periods=120).max()
    ma = jk.rolling(200, min_periods=200).mean()
    on = False
    out = {}
    for m in checks:
        j = jk.loc[:m]
        if not len(j):
            out[m] = False
            continue
        d = j.index[-1]
        dd = j.iloc[-1] / hi.loc[d] - 1 if not np.isnan(hi.loc[d]) else 0.0
        above = j.iloc[-1] > ma.loc[d] if not np.isnan(ma.loc[d]) else True
        if not on and dd <= CRASH_DD:
            on = True
        elif on and above:
            on = False
        out[m] = on
    return out


def deep_value(kind: str, rows: list[dict], close: pd.DataFrame, D: pd.Timestamp, exclude: set[str]) -> set[str]:
    rows = [r for r in rows if r["code"] not in exclude]
    if kind == "dv_strict_ep":
        pool = cand.rank_pool([dict(r) for r in rows], gate="strict", keys=("ep",))
        return {r["code"] for r in pool if r["selected"]}
    if kind == "dv_loose_ep":
        pool = cand.rank_pool([dict(r) for r in rows], gate="loose", keys=("ep",))
        return {r["code"] for r in pool if r["selected"]}
    gate = [r["code"] for r in rows if r.get("tradable") and r.get("gate_strict") and r["code"] in close.columns]
    dd = {}
    for c in gate:
        s = close[c].loc[:D].dropna().iloc[-252:]
        if len(s) >= 120 and s.iloc[-1] > 0:
            dd[c] = s.iloc[-1] / s.max() - 1
    order = sorted(dd, key=lambda c: dd[c])
    k = max(5, len(order) // 5) if len(order) >= 20 else 0
    return set(order[:k])


def build_plans(conn, close, jk, rebals, end, exclude_by_kind: dict[str, set[str]] | None = None) -> tuple[dict[str, dict], dict]:
    exclude_by_kind = exclude_by_kind or {}
    checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))
    state = crash_states(jk, checks)
    rows_at: dict[pd.Timestamp, list[dict]] = {}

    def rows(D):
        if D not in rows_at:
            rows_at[D] = cand.build(conn, D.date())["all_rows"]
        return rows_at[D]

    strict_lists = {D: [r for r in ST.pick("strict", rows(D)) if r["selected"]] for D in rebals}
    plans: dict[str, dict] = {"strict": {D: {r["code"] for r in strict_lists[D]} for D in rebals},
                              "tilt": {D: MG.selection("mom_tilt", strict_lists[D], set()) for D in rebals}}
    for kind in DV:
        plan = {}
        prev_on = False
        for m in checks:
            D = max(a for a in rebals if a <= m)
            on = state[m]
            if on and (not prev_on or m in rebals):
                plan[m] = deep_value(kind, rows(m), close, m, exclude_by_kind.get(kind, set()))
            elif not on and (prev_on or m in rebals):
                plan[m] = plans["tilt"][D]
            prev_on = on
        plans[kind] = plan
    return plans, {"checks": checks, "state": state, "n_builds": len(rows_at)}


def best_dv_name(plan: dict, state: dict, close, div, end) -> str:
    dates = sorted(plan)
    total: dict[str, float] = {}
    for a, b in zip(dates, [*dates[1:], end], strict=True):
        if state.get(a):
            for code, ret in VQ.contributions(set(plan[a]), close, div, a, b):
                total[code] = total.get(code, 0.0) + ret
    return max(total, key=total.get) if total else ""


def run_window(conn, close, vol, delisted, div, jk, first_year: int, months: tuple[int, ...], results: dict, label: str) -> None:
    VQ.FIRST_YEAR = first_year
    end = close.index[-1]
    results[label] = {}
    for month in months:
        rebals = VQ.rebalance_dates(close.index, month)
        plans, info = build_plans(conn, close, jk, rebals, end)
        crash_months = [str(m.date()) for m in info["checks"] if info["state"][m]]
        table = {}
        print(f"\n=== {label}, month {month}: {[str(r.date()) for r in rebals]}   crash-on months: {len(crash_months)} "
              f"({crash_months[0] if crash_months else '-'} .. {crash_months[-1] if crash_months else '-'})")
        for arm in ("strict", "tilt", *DV):
            st = VQ.stats(VQ.simulate(plans[arm], close, vol, delisted, div, rebals[0], end, True, mode="reset"), rebals); st.pop("_r")
            table[arm] = {"stats": st}
            line = f"{arm:14s} {st['cagr_pct']:6.1f}·{st['sharpe']:4.2f}·{st['mdd_pct']:3.0f}%"
            if arm in DV:
                best = best_dv_name(plans[arm], info["state"], close, div, end)
                plans_ex, _ = build_plans(conn, close, jk, rebals, end, {arm: {best}})
                st_ex = VQ.stats(VQ.simulate(plans_ex[arm], close, vol, delisted, div, rebals[0], end, True, mode="reset"), rebals); st_ex.pop("_r")
                table[arm].update({"best_name": best, "stats_ex_best": st_ex,
                                   "dv_lists": {str(m.date()): sorted(v) for m, v in plans[arm].items() if info["state"].get(m) and not isinstance(v, dict)}})
                line += f"   ex-{best or '-':5s} {st_ex['cagr_pct']:6.1f}·{st_ex['mdd_pct']:3.0f}%"
            print(line)
            sys.stdout.flush()
        table["crash_months"] = crash_months
        results[label][str(month)] = table


def part_b(results: dict) -> None:
    close, vol, jk = TO.load_yahoo()
    end = close.index[-1]
    annual = []
    for y in range(2008, end.year + 1):
        pos = close.index.searchsorted(pd.Timestamp(f"{y}-05-02"))
        if pos < len(close.index):
            annual.append(close.index[pos])
    lists = TO.baskets(close, vol, annual)
    checks = sorted(set(TO.month_starts(close.index, annual[0], end)) | set(annual))
    state = crash_states(jk, checks)
    dd_all = close / close.rolling(252, min_periods=120).max() - 1

    def beaten(m, L, exclude=set()):
        d = dd_all.loc[:m].iloc[-1].reindex([c for c in L if c not in exclude]).dropna().sort_values()
        return set(d.index[: max(5, len(d) // 5)])

    def plan_for(exclude=set()):
        plan, prev = {}, False
        for m in checks:
            D = max(a for a in annual if a <= m)
            on = state[m]
            if on and (not prev or m in annual):
                plan[m] = beaten(m, lists[D], exclude)
            elif not on and (prev or m in annual):
                plan[m] = set(lists[D])
            prev = on
        return plan

    eps = tuple(TO.EPISODES)
    TO.N_TRIALS = TRIALS
    crash_months = [str(m.date()) for m in checks if state[m]]
    print(f"\n=== 2008-2026 basket, May calendar   crash-on months: {len(crash_months)}: {', '.join(crash_months[:3])} ... {', '.join(crash_months[-3:])}")
    print(f"{'arm':14s} {'total%':>8} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'cash%':>5} {'DSR':>5} | episode drawdowns %")
    table = {}
    base = VQ.simulate({D: set(lists[D]) for D in annual}, close, vol, {}, TO.EMPTY_DIV, annual[0], end, True, mode="reset")
    table["basket"] = TO.read(base, annual); print(TO.line("basket", table["basket"], eps))
    nav = VQ.simulate(plan_for(), close, vol, {}, TO.EMPTY_DIV, annual[0], end, True, mode="reset")
    table["dv_beaten"] = TO.read(nav, annual); print(TO.line("dv_beaten", table["dv_beaten"], eps))
    total: dict[str, float] = {}
    p = plan_for(); dates = sorted(p)
    for a, b in zip(dates, [*dates[1:], end], strict=True):
        if state.get(a):
            for code, ret in VQ.contributions(p[a], close, TO.EMPTY_DIV, a, b):
                total[code] = total.get(code, 0.0) + ret
    best = max(total, key=total.get) if total else ""
    nav_ex = VQ.simulate(plan_for({best}), close, vol, {}, TO.EMPTY_DIV, annual[0], end, True, mode="reset")
    table["dv_beaten_ex_best"] = TO.read(nav_ex, annual); table["best_name"] = best
    print(TO.line(f"dv ex-{best}", table["dv_beaten_ex_best"], eps))
    table["crash_months"] = crash_months
    results["part_b"] = table


def main():
    conn = VQ.connect()
    close, vol, delisted, div, ix = VQ.load(conn)
    jk = ix["COMPOSITE"].dropna()
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": TRIALS}
    run_window(conn, close, vol, delisted, div, jk, 2021, (5, 2, 8, 11), results, "from_2021")
    run_window(conn, close, vol, delisted, div, jk, 2020, (5, 8, 11), results, "from_2020")
    part_b(results)
    A, A20, B = results["from_2021"], results["from_2020"], results["part_b"]
    print("\n--- reading rule: beats tilt in 3/4 (2021) and 2/3 (2020), mDD not >5 pts deeper, ex-best 3/4; 2008: beats the basket, mDD not >5 deeper")
    tilt_dd = max(A[m]["tilt"]["stats"]["mdd_pct"] for m in A)
    verdicts = {}
    for kind in DV:
        wins = sum(A[m][kind]["stats"]["cagr_pct"] > A[m]["tilt"]["stats"]["cagr_pct"] for m in A)
        wins20 = sum(A20[m][kind]["stats"]["cagr_pct"] > A20[m]["tilt"]["stats"]["cagr_pct"] for m in A20)
        wins_ex = sum(A[m][kind]["stats_ex_best"]["cagr_pct"] > A[m]["tilt"]["stats"]["cagr_pct"] for m in A)
        dd = max(A[m][kind]["stats"]["mdd_pct"] for m in A)
        avg = float(np.mean([A[m][kind]["stats"]["cagr_pct"] for m in A]))
        avg20 = float(np.mean([A20[m][kind]["stats"]["cagr_pct"] for m in A20]))
        ok = wins >= 3 and wins20 >= 2 and dd <= tilt_dd + 5 and wins_ex >= 3
        if kind == "dv_beaten":
            ok = ok and B["dv_beaten"]["cagr_pct"] > B["basket"]["cagr_pct"] and B["dv_beaten"]["mdd_pct"] <= B["basket"]["mdd_pct"] + 5
        verdicts[kind] = {"avg_cagr": avg, "avg_cagr_2020": avg20, "wins": wins, "wins_2020": wins20, "wins_ex_best": wins_ex, "worst_mdd": dd, "candidate": ok}
        print(f"  {kind:13s} avg {avg:5.1f} (2020-start {avg20:5.1f})  wins {wins}/4, 2020 {wins20}/3, ex-best {wins_ex}/4  worst mDD {dd:3.0f}% (tilt {tilt_dd:.0f}%) -> {'CANDIDATE' if ok else 'tested'}")
    for ref in ("strict", "tilt"):
        print(f"  {ref:13s} avg {float(np.mean([A[m][ref]['stats']['cagr_pct'] for m in A])):5.1f} (2020-start {float(np.mean([A20[m][ref]['stats']['cagr_pct'] for m in A20])):5.1f})")
    print(f"  2008 basket: basket {B['basket']['cagr_pct']:.1f} mDD {B['basket']['mdd_pct']:.0f}% | dv_beaten {B['dv_beaten']['cagr_pct']:.1f} mDD {B['dv_beaten']['mdd_pct']:.0f}% (ex-{B['best_name']} {B['dv_beaten_ex_best']['cagr_pct']:.1f})")
    results["verdicts"] = verdicts
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
