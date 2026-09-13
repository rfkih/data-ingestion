#!/usr/bin/env python3
"""IDX — the cost of executing late (2026-09-13). The desk does not auto-trade: a signal is computed at the close of the
check day, the operator is notified, and the order is worked the next session or later. This measures what that delay
costs the rules the operator has chosen, on the strict book 2021-2026, four calendars.

Arms (references, not new trials): none (hold to the rebalance), index (regime filter), asym_rsi (the asymmetric rule),
asym_rsi_regime (both). Execution lag k in {0, 1, 2, 5} trading days: the signal is still computed at the check close
(day 0), the trade happens at the close of day k. Costs, dividends, cash as in the other studies.

READ: per arm and lag, the CAGR / Sharpe / max drawdown, and the average across calendars; the cost of lag k is the
CAGR difference against lag 0. No adoption decision here: the numbers go into the catalog notes and the app's guidance.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_execution_delay.py
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
import idx_asymmetric as AS  # noqa: E402
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

OUT = os.path.join(VQ.OUTDIR, "execution_delay_results.json")
LAGS = (0, 1, 2, 5)
ARMS = ("none", "index", "asym_rsi", "asym_rsi_regime")


def lagged(plan: dict, index: pd.DatetimeIndex, k: int) -> dict:
    """Signals stay as computed at their check date; the trade moves to the close k bars later."""
    if k == 0:
        return plan
    out = {}
    for m, entry in plan.items():
        pos = index.get_loc(m)
        j = min(pos + k, len(index) - 1)
        out[index[j]] = entry
    return out


def main():
    conn = VQ.connect()
    close, vol, delisted, div, ix = VQ.load(conn)
    end = close.index[-1]
    jk = ix["COMPOSITE"].dropna()
    rsi_all = AS.rsi(close)
    mean20 = close.rolling(AS.BB_N, min_periods=AS.BB_N).mean()
    sd20 = close.rolling(AS.BB_N, min_periods=AS.BB_N).std()
    bb_lo_all = mean20 - AS.BB_K * sd20
    results = {"generated": datetime.now(UTC).isoformat(), "months": {}}
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        lists = {D: {r["code"] for r in ST.pick("strict", cand.build(conn, D.date())["all_rows"]) if r["selected"]} for D in rebals}
        checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))
        sig = TO.Signals(close, jk, checks)
        rsi_at = rsi_all.reindex(checks, method="ffill")
        bb_lo = bb_lo_all.reindex(checks, method="ffill")

        def slot(d, lists=lists):
            return 1 / max(1, len(lists[max(a for a in lists if a <= d)]))

        table = {}
        print(f"\n=== month {month}: {[str(r.date()) for r in rebals]}")
        print(f"{'arm':16s} " + "  ".join(f"{'lag ' + str(k) + ' (CAGR·Sh·mDD)':>22s}" for k in LAGS))
        for arm in ARMS:
            if arm in ("none", "index"):
                base_plan = TO.build_plan(arm, lists, sig)
            elif arm == "asym_rsi":
                base_plan = AS.build_asym("asym_rsi", lists, sig, close, rsi_at, bb_lo)
            else:
                inner = AS.build_asym("asym_rsi", lists, sig, close, rsi_at, bb_lo)
                base_plan = {m: (inner[m] if sig.regime(m) else set()) for m in inner}
            row = {}
            for k in LAGS:
                # the stateful asymmetric rule must be rebuilt per lag (its closures carry state across calls)
                if arm == "asym_rsi":
                    base_plan = AS.build_asym("asym_rsi", lists, sig, close, rsi_at, bb_lo)
                elif arm == "asym_rsi_regime":
                    inner = AS.build_asym("asym_rsi", lists, sig, close, rsi_at, bb_lo)
                    base_plan = {m: (inner[m] if sig.regime(m) else set()) for m in inner}
                plan = lagged(base_plan, close.index, k)
                start = min(plan)
                nav = VQ.simulate(plan, close, vol, delisted, div, start, end, True, mode="drift", cap=slot, cash_rate=TO.CASH_RATE)
                st = VQ.stats(nav, [d for d in sorted(plan) if d in nav.index and d in set(lagged({r: 0 for r in rebals}, close.index, k))])
                st.pop("_r")
                row[k] = {"cagr_pct": st["cagr_pct"], "sharpe": st["sharpe"], "mdd_pct": st["mdd_pct"], "total_pct": st["total_pct"]}
            table[arm] = row
            print(f"{arm:16s} " + "  ".join(f"{row[k]['cagr_pct']:6.1f}·{row[k]['sharpe']:4.2f}·{row[k]['mdd_pct']:3.0f}%   " for k in LAGS))
            sys.stdout.flush()
        results["months"][str(month)] = table
    print("\n--- average across the four calendars: CAGR by lag, and the cost of each lag against same-day execution")
    summary = {}
    for arm in ARMS:
        avg = {k: float(np.mean([results["months"][m][arm][k]["cagr_pct"] for m in results["months"]])) for k in LAGS}
        dd = {k: float(np.max([results["months"][m][arm][k]["mdd_pct"] for m in results["months"]])) for k in LAGS}
        summary[arm] = {"cagr": avg, "worst_mdd": dd}
        print(f"    {arm:16s} " + "  ".join(f"lag {k}: {avg[k]:5.1f}% ({avg[k] - avg[0]:+.1f}), worst mDD {dd[k]:.0f}%" for k in LAGS))
    results["summary"] = summary
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
