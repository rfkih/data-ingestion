#!/usr/bin/env python3
"""IDX — cheap and expensive relative to the industry and to growth (2026-09-13). The operator's correction: a P/E of 5
can be a value trap and a P/E of 30 can be fair for a fast grower; "expensive" must be judged against the sector and the
growth, not against an absolute multiple.

PRE-REGISTERED MENU (5 trials; cumulative 104 + 5 = 109). Strict-gate pool unless stated, 2021-2026, four calendars, the
rev. 3 simulator (drift, one-slot cap, cash 4 %/yr).

  selection (annual, top fifth of the gated pool, equal weight)
    sector_rel/loose   each of E/P, B/P, DY as a percentile WITHIN THE SECTOR (sectors with fewer than 5 gated names fall
                       back to the whole pool); score = mean percentile; light gate
    sector_rel/strict  the same on the strict gate
    growth_adj/loose   composite of ranks E/P, B/P, DY and audited profit growth (cheap AND growing); light gate
    growth_adj/strict  the same on the strict gate
  sell rule (monthly, strict composite, the sold name waits in cash until the next rebalance)
    sell_sector        sell a held name when its E/P falls under the median E/P of its sector's gated names that day
                       ("expensive against its industry")
  references (not trials): strict (the deployed rule), value-trap check = the strict gate itself.

READING RULE (declared before the run): a selection variant is adopted over the strict composite only if its total
return is higher in at least three of four calendars with no deeper worst drawdown; the sell rule replaces "hold to the
rebalance" on the same bar.

Consensus targets: no point-in-time history exists in the data we have, so a "price above consensus" rule cannot be
backtested here; it can only be a judgment input on the card (see the note in the report).

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_sector_relative.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402
from blackheart_ingest.idx.candidates import KEYS, rank_pool  # noqa: E402

N_TRIALS = 109
TO.N_TRIALS = N_TRIALS
OUT = os.path.join(VQ.OUTDIR, "sector_relative_results.json")
MIN_SECTOR = 5


def _pool(rows, gate):
    key = "gate_strict" if gate == "strict" else "gate_loose"
    return [r for r in rows if r.get(key) and r.get("ep") is not None and r["ep"] > 0 and r.get("tradable", True)]


def sector_percentiles(pool, keys=KEYS):
    """Per row, the mean over ``keys`` of its percentile within its sector (or the whole pool for thin sectors)."""
    by = defaultdict(list)
    for r in pool:
        by[r.get("sector") or "?"].append(r)
    score = {}
    for key in keys:
        for sec, rs in by.items():
            group = rs if len(rs) >= MIN_SECTOR else pool
            vals = sorted((float(x[key]) if x.get(key) is not None else float("-inf")) for x in group)
            n = len(vals)
            for r in rs:
                v = float(r[key]) if r.get(key) is not None else float("-inf")
                below = sum(1 for x in vals if x < v)
                equal = sum(1 for x in vals if x == v)
                score[r["code"]] = score.get(r["code"], 0.0) + ((below + 0.5 * equal) / n if n else 0.0)
    return {c: s / len(keys) for c, s in score.items()}


def select_sector_rel(rows, gate):
    pool = _pool(rows, gate)
    if len(pool) < 20:
        return set()
    sc = sector_percentiles(pool)
    ordered = sorted(pool, key=lambda r: (-sc[r["code"]], r["code"]))
    k = max(10, len(pool) // 5)
    return {r["code"] for r in ordered[:k]}


def select_growth_adj(rows, gate):
    pool = rank_pool([dict(r) for r in rows], gate=gate, keys=tuple(KEYS) + ("np_yoy",))
    return {r["code"] for r in pool if r["selected"]}


def sector_medians(rows, gate="loose"):
    by = defaultdict(list)
    for r in _pool(rows, gate):
        by[r.get("sector") or "?"].append(Decimal(r["ep"]))
    allv = sorted(v for vs in by.values() for v in vs)
    med_all = allv[len(allv) // 2] if allv else None
    out = {}
    for sec, vs in by.items():
        vs = sorted(vs)
        out[sec] = vs[len(vs) // 2] if len(vs) >= MIN_SECTOR else med_all
    return out, med_all


def main():
    conn = VQ.connect()
    close, vol, delisted, div, _ix = VQ.load(conn)
    end = close.index[-1]
    rows_cache: dict = {}

    def rows_at(D):
        if D not in rows_cache:
            rows_cache[D] = cand.build(conn, D.date())["all_rows"]
        return rows_cache[D]

    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": N_TRIALS, "months": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))
        strict = {D: {r["code"] for r in ST.pick("strict", rows_at(D)) if r["selected"]} for D in rebals}
        arms = {
            "strict": strict,
            "sector_rel/loose": {D: select_sector_rel(rows_at(D), "loose") for D in rebals},
            "sector_rel/strict": {D: select_sector_rel(rows_at(D), "strict") for D in rebals},
            "growth_adj/loose": {D: select_growth_adj(rows_at(D), "loose") for D in rebals},
            "growth_adj/strict": {D: select_growth_adj(rows_at(D), "strict") for D in rebals},
        }
        table = {}
        print(f"\n=== month {month}: {[str(r.date()) for r in rebals]}   (DSR at N_trials = {N_TRIALS})")
        print(f"{'arm':18s} {'total%':>7} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'DSR':>5} | names | rebalance-period returns %")
        for label, lists in arms.items():
            def slot(d, lists=lists):
                return 1 / max(1, len(lists[max(a for a in lists if a <= d)]))
            plan = TO.build_plan("none", lists, TO.Signals(close, _ix["COMPOSITE"].dropna(), checks))
            nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="drift", cap=slot, cash_rate=TO.CASH_RATE)
            v = TO.read(nav, rebals)
            v["n"] = [len(lists[D]) for D in rebals]
            v["overlap_with_strict"] = [round(len(lists[D] & strict[D]) / max(1, len(strict[D])), 2) for D in rebals]
            table[label] = v
            per = " ".join(f"{d[:4]}:{x:+.0f}" for d, x in v["periods"].items())
            print(f"{label:18s} {v['total_pct']:7.1f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v['dsr']:5.2f} | {v['n']} | {per}")
            sys.stdout.flush()
        # the sector-relative sell rule on the strict book
        annual = sorted(strict)
        state = {"sold": set(), "list_date": None}
        plan = {}
        for m in checks:
            list_date = max(a for a in annual if a <= m)
            L = strict[list_date]

            def rule(held, m=m, L=L, list_date=list_date):
                if state["list_date"] != list_date:
                    state["sold"], state["list_date"] = set(), list_date
                rows = rows_at(m)
                meds, med_all = sector_medians(rows, "loose")
                info = {r["code"]: r for r in rows}
                keep = set()
                for c in held & L:
                    r = info.get(c)
                    e = Decimal(r["ep"]) if r and r.get("ep") is not None else None
                    med = meds.get((r or {}).get("sector") or "?", med_all) if r else None
                    if e is not None and med is not None and e < med:
                        state["sold"].add(c)
                    else:
                        keep.add(c)
                return keep | {c for c in L if c not in held and c not in state["sold"]}
            plan[m] = rule

        def slot_s(d, lists=strict):
            return 1 / max(1, len(lists[max(a for a in lists if a <= d)]))
        nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="drift", cap=slot_s, cash_rate=TO.CASH_RATE)
        v = TO.read(nav, rebals)
        table["sell_sector"] = v
        per = " ".join(f"{d[:4]}:{x:+.0f}" for d, x in v["periods"].items())
        print(f"{'sell_sector':18s} {v['total_pct']:7.1f} {v['cagr_pct']:6.1f} {v['sharpe']:6.2f} {v['mdd_pct']:5.0f} {v['dsr']:5.2f} | strict list, monthly | {per}")
        sys.stdout.flush()
        results["months"][str(month)] = {"rebalances": [str(r.date()) for r in rebals], "table": table}

    print("\n--- reading rule: adopt over strict only if ahead in >= 3 of 4 calendars with no deeper worst drawdown")
    verdict = {}
    base_dd = max(results["months"][m]["table"]["strict"]["mdd_pct"] for m in results["months"])
    for arm in ("sector_rel/loose", "sector_rel/strict", "growth_adj/loose", "growth_adj/strict", "sell_sector"):
        wins = sum(results["months"][m]["table"][arm]["total_pct"] > results["months"][m]["table"]["strict"]["total_pct"] for m in results["months"])
        dd_ok = max(results["months"][m]["table"][arm]["mdd_pct"] for m in results["months"]) <= base_dd
        verdict[arm] = {"wins": int(wins), "dd_ok": bool(dd_ok), "adopt": bool(wins >= 3 and dd_ok)}
        print(f"    {arm:18s} ahead of strict in {wins}/4, drawdown ok {dd_ok} -> {'ADOPT' if verdict[arm]['adopt'] else 'keep strict'}")
    results["verdict"] = verdict
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
