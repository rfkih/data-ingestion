#!/usr/bin/env python3
"""IDX — momentum and profit growth combined, inside the strict list (2026-09-14).

Both orderings had some power to name the eventual winners of the strict list (IDX_TOP3_UPSIDE: 41 % and 38 % of their
picks landed in the ex-post best three, against 25 % for chance). This tests them combined, as a cut and as a tilt.

Combined score = the average of two ranks inside the list: 12-1 momentum (higher first) and audited net-profit growth
(higher first); a name without growth data ranks last on that input.

PRE-REGISTERED MENU (4 trials; cumulative 151 + 4 = 155):
    mg3        the three names with the best combined score, equal weight
    mg5        the five best, equal weight
    mg_tilt    the whole list, weights linear from 2 (best score) to 1 (worst), renormalised
    mom_tilt   the whole list, the same tilt on momentum alone (to see what growth adds)
Reference: the strict list in full, equal weight. Windows: 2021-2026 on four calendars (the record), and 2020-2026 on
May/Aug/Nov (FY2019 audits) as a direction check. Same simulator, costs and calendars as the strict record.

READING RULE, written before the run: a variant is a candidate only if
  (a) its CAGR beats the full list in at least three of four calendars (2021 start),
  (b) its worst drawdown is not more than 5 points deeper (tilts) or 8 points deeper (cuts),
  (c) with its single best-contributing name excluded from every pick (re-picked / re-weighted without it), (a) holds,
  (d) it beats the full list in at least two of the three 2020-start calendars.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_mom_growth.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

OUT = os.path.join(VQ.OUTDIR, "mom_growth_results.json")
ARMS = ("mg3", "mg5", "mg_tilt", "mom_tilt")
TRIALS = 155


def f(v) -> float:
    try:
        return float(v) if v is not None else np.nan
    except (TypeError, ValueError):
        return np.nan


def ranks(values: dict[str, float]) -> dict[str, float]:
    """1 = highest; NaN last."""
    order = sorted(values, key=lambda c: (np.isnan(values[c]), -(values[c] if not np.isnan(values[c]) else 0), c))
    return {c: i + 1 for i, c in enumerate(order)}


def scores(rows: list[dict], kind: str, exclude: set[str]) -> list[str]:
    """Codes ordered best first by the arm's score."""
    rows = [r for r in rows if r["code"] not in exclude]
    mom = ranks({r["code"]: f(r.get("mom")) for r in rows})
    if kind == "mom_tilt":
        comb = mom
    else:
        gro = ranks({r["code"]: f(r.get("np_yoy")) for r in rows})
        comb = {c: (mom[c] + gro[c]) / 2 for c in mom}
    return sorted(comb, key=lambda c: (comb[c], c))


def selection(kind: str, rows: list[dict], exclude: set[str]):
    ordered = scores(rows, kind, exclude)
    if kind == "mg3":
        return set(ordered[:3])
    if kind == "mg5":
        return set(ordered[:5])
    n = len(ordered)
    if n <= 1:
        return set(ordered)
    return {c: 2.0 - (i / (n - 1)) for i, c in enumerate(ordered)}        # 2 .. 1


def best_contributor(sel_by_date: dict, close, div, end) -> str:
    dates = sorted(sel_by_date)
    total: dict[str, float] = {}
    for a, b in zip(dates, [*dates[1:], end], strict=True):
        names = set(sel_by_date[a]) if not isinstance(sel_by_date[a], dict) else set(sel_by_date[a])
        for code, ret in VQ.contributions(names, close, div, a, b):
            total[code] = total.get(code, 0.0) + ret
    return max(total, key=total.get) if total else ""


def run_window(conn, close, vol, delisted, div, first_year: int, months: tuple[int, ...]) -> dict:
    VQ.FIRST_YEAR = first_year
    end = close.index[-1]
    out = {}
    for month in months:
        rebals = VQ.rebalance_dates(close.index, month)
        lists = {D: [r for r in ST.pick("strict", cand.build(conn, D.date())["all_rows"]) if r["selected"]] for D in rebals}
        table = {}
        full = {D: {r["code"] for r in lists[D]} for D in rebals}
        nav = VQ.simulate(full, close, vol, delisted, div, rebals[0], end, True, mode="reset")
        ref = VQ.stats(nav, rebals); ref.pop("_r")
        table["strict_full"] = {"stats": ref}
        print(f"\n=== start {first_year}, month {month}: {[str(r.date()) for r in rebals]}")
        print(f"{'strict (full list)':20s} {ref['cagr_pct']:6.1f}·{ref['sharpe']:4.2f}·{ref['mdd_pct']:3.0f}%")
        for kind in ARMS:
            sel = {D: selection(kind, lists[D], set()) for D in rebals}
            nav = VQ.simulate(sel, close, vol, delisted, div, rebals[0], end, True, mode="reset")
            st = VQ.stats(nav, rebals); st.pop("_r")
            best = best_contributor(sel, close, div, end)
            sel_ex = {D: selection(kind, lists[D], {best}) for D in rebals}
            nav_ex = VQ.simulate(sel_ex, close, vol, delisted, div, rebals[0], end, True, mode="reset")
            st_ex = VQ.stats(nav_ex, rebals); st_ex.pop("_r")
            picks = {str(D.date()): (sorted(sel[D]) if not isinstance(sel[D], dict) else {c: round(w, 2) for c, w in sorted(sel[D].items())}) for D in rebals}
            table[kind] = {"stats": st, "best_name": best, "stats_ex_best": st_ex, "picks": picks}
            print(f"{kind:20s} {st['cagr_pct']:6.1f}·{st['sharpe']:4.2f}·{st['mdd_pct']:3.0f}%   ex-{best or '-':5s} {st_ex['cagr_pct']:6.1f}·{st_ex['mdd_pct']:3.0f}%")
            sys.stdout.flush()
        out[str(month)] = table
    return out


def main():
    conn = VQ.connect()
    close, vol, delisted, div, ix = VQ.load(conn)
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": TRIALS,
               "months": run_window(conn, close, vol, delisted, div, 2021, (5, 2, 8, 11)),
               "months_2020": run_window(conn, close, vol, delisted, div, 2020, (5, 8, 11))}
    m21, m20 = results["months"], results["months_2020"]
    ref_dd = max(m21[m]["strict_full"]["stats"]["mdd_pct"] for m in m21)
    print("\n--- reading rule: >=3/4 wins (2021 start), worst mDD not >5 (tilt) / >8 (cut) pts deeper, >=3/4 ex-best, >=2/3 wins from 2020")
    verdicts = {}
    for kind in ARMS:
        wins = sum(m21[m][kind]["stats"]["cagr_pct"] > m21[m]["strict_full"]["stats"]["cagr_pct"] for m in m21)
        wins_ex = sum(m21[m][kind]["stats_ex_best"]["cagr_pct"] > m21[m]["strict_full"]["stats"]["cagr_pct"] for m in m21)
        wins20 = sum(m20[m][kind]["stats"]["cagr_pct"] > m20[m]["strict_full"]["stats"]["cagr_pct"] for m in m20)
        dd = max(m21[m][kind]["stats"]["mdd_pct"] for m in m21)
        allow = 5 if kind.endswith("tilt") else 8
        avg = float(np.mean([m21[m][kind]["stats"]["cagr_pct"] for m in m21]))
        avg_ex = float(np.mean([m21[m][kind]["stats_ex_best"]["cagr_pct"] for m in m21]))
        avg20 = float(np.mean([m20[m][kind]["stats"]["cagr_pct"] for m in m20]))
        ok = wins >= 3 and dd <= ref_dd + allow and wins_ex >= 3 and wins20 >= 2
        verdicts[kind] = {"avg_cagr": avg, "avg_ex_best": avg_ex, "avg_2020": avg20, "wins": wins, "wins_ex_best": wins_ex, "wins_2020": wins20, "worst_mdd": dd, "candidate": ok}
        print(f"  {kind:9s} avg {avg:5.1f} (ex-best {avg_ex:5.1f}; 2020-start {avg20:5.1f})  wins {wins}/4, ex-best {wins_ex}/4, 2020 {wins20}/3  worst mDD {dd:3.0f}% (strict {ref_dd:.0f}%)  -> {'CANDIDATE' if ok else 'tested'}")
    ref_avg = float(np.mean([m21[m]["strict_full"]["stats"]["cagr_pct"] for m in m21]))
    ref_avg20 = float(np.mean([m20[m]["strict_full"]["stats"]["cagr_pct"] for m in m20]))
    print(f"  {'strict':9s} avg {ref_avg:5.1f} (2020-start {ref_avg20:5.1f})  worst mDD {ref_dd:.0f}%")
    results["verdicts"] = verdicts
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
