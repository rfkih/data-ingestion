#!/usr/bin/env python3
"""IDX — do macro signals add to the stress detector? (2026-09-14)

The cash-buffer detector (IDX_CASH_BUFFER) reads prices and breadth. The operator asked for macro inputs: the BI rate,
growth, the rupiah, and whatever else moves stocks. The desk now stores those series (idx.macro). This tests, with the
same set-up as the cash-buffer study (30 % cash normally, 50 % while a signal is on), whether any macro signal, alone or
added to the price signals, improves the trade-off. Read at the monthly check from data up to that day; series with a
publication lag (GDP, CPI) are excluded because their point-in-time dates are not known.

PRE-REGISTERED MENU (7 trials; cumulative 162 + 7 = 169):
    idr_3m      USD/IDR up more than 5 % over three months (the rupiah weakening)
    vix_hi      VIX above 25
    us10y_3m    the US 10-year yield up more than 0.75 points over three months
    bi_hike     the BI policy rate above its level six months earlier (tightening)
    brent_3m    Brent down more than 20 % over three months (a commodity bust; IDX is commodity-heavy)
    macro_any2  at least two of the five macro signals
    all_any2    at least two of the nine (four price + five macro)
References recomputed: full, cash30, ma (30 -> 50), any2 (price only).
READING RULE (declared before the run): a macro arm earns a place in the detector only if it passes the cash-buffer
rule (Sharpe > full in 3/4 calendars, worst mDD >= 5 pts shallower, CAGR >= 75 % of full, 2008 basket mDD <= 40 % with
2008 and 2020 >= -30 %) AND beats the price-only any2 arm on the 2008 basket max drawdown by at least 3 points.
Otherwise it is a number in the report and the app shows the macro board for reading, not for trading.

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_macro_stress.py
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
import idx_cash_buffer as CB  # noqa: E402
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

OUT = os.path.join(VQ.OUTDIR, "macro_stress_results.json")
TRIALS = 169
MACRO = ("idr_3m", "vix_hi", "us10y_3m", "bi_hike", "brent_3m")
ARMS = ("full", "cash30", "ma", "any2", *MACRO, "macro_any2", "all_any2")


def load_macro(conn) -> pd.DataFrame:
    df = VQ.frame(conn, "SELECT series, obs_date, value FROM idx.macro WHERE series = ANY(%s) ORDER BY obs_date",
                  (["usdidr", "vix", "us10y", "brent", "bi_rate", "bi_rate_hist"],), ["series", "obs_date", "value"])
    df["value"] = df["value"].astype(float)
    wide = df.pivot(index="obs_date", columns="series", values="value")
    wide.index = pd.to_datetime(wide.index)
    bi = wide["bi_rate_hist"].copy()
    if "bi_rate" in wide:
        bi = bi.combine_first(wide["bi_rate"])                              # OECD to 2023-12, then the BI page
        bi.loc[wide["bi_rate"].dropna().index] = wide["bi_rate"].dropna()
    wide["bi"] = bi
    return wide.sort_index().ffill()


class MacroStress(CB.Stress):
    def __init__(self, jk, close, checks, macro: pd.DataFrame):
        super().__init__(jk, close, checks)
        m = macro.reindex(macro.index.union(checks)).ffill()
        for c in checks:
            row = m.loc[:c].iloc[-1] if len(m.loc[:c]) else None
            past = lambda days: m.loc[:c - pd.Timedelta(days=days)].iloc[-1] if len(m.loc[:c - pd.Timedelta(days=days)]) else None  # noqa: E731
            m3, m6 = past(91), past(182)
            s = {}
            s["idr_3m"] = bool(row is not None and m3 is not None and not np.isnan(row["usdidr"]) and not np.isnan(m3["usdidr"]) and row["usdidr"] / m3["usdidr"] - 1 > 0.05)
            s["vix_hi"] = bool(row is not None and not np.isnan(row["vix"]) and row["vix"] > 25)
            s["us10y_3m"] = bool(row is not None and m3 is not None and not np.isnan(row["us10y"]) and not np.isnan(m3["us10y"]) and row["us10y"] - m3["us10y"] > 0.75)
            s["bi_hike"] = bool(row is not None and m6 is not None and not np.isnan(row["bi"]) and not np.isnan(m6["bi"]) and row["bi"] > m6["bi"])
            s["brent_3m"] = bool(row is not None and m3 is not None and not np.isnan(row["brent"]) and not np.isnan(m3["brent"]) and row["brent"] / m3["brent"] - 1 < -0.20)
            n_macro = sum(s.values())
            s["macro_any2"] = n_macro >= 2
            s["all_any2"] = (n_macro + sum(self.s[c][k] for k in ("ma", "vol", "dd", "breadth"))) >= 2
            self.s[c].update(s)


def exposure_fn(arm: str, stress: MacroStress):
    if arm in ("full", "cash30", "ma", "any2"):
        return CB.exposure_fn(arm, stress)
    return lambda d: 0.5 if stress.on(d, arm) else 0.7


def main():
    conn = VQ.connect()
    macro = load_macro(conn)
    print("macro series:", {c: (str(macro[c].dropna().index[0].date()), str(macro[c].dropna().index[-1].date())) for c in ("usdidr", "vix", "us10y", "brent", "bi")})
    results = {"generated": datetime.now(UTC).isoformat(), "n_trials": TRIALS, "part_a": {}, "part_b": {}}
    close, vol, delisted, div, ix = VQ.load(conn)
    end = close.index[-1]
    jk = ix["COMPOSITE"].dropna()
    for month in (5, 2, 8, 11):
        rebals = VQ.rebalance_dates(close.index, month)
        lists = {D: {r["code"] for r in ST.pick("strict", cand.build(conn, D.date())["all_rows"]) if r["selected"]} for D in rebals}
        checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))
        stress = MacroStress(jk, close, checks, macro)
        plan = CB.monthly_plan(lists, checks)
        print(f"\n=== strict book, month {month}   on-time: " + ", ".join(f"{k} {CB.stress_share(stress, checks, k):.0f}%" for k in (*MACRO, "macro_any2", "all_any2")))
        print(f"{'arm':12s} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'2025 dip':>8}")
        table = {}
        for arm in ARMS:
            nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="reset", cash_rate=CB.CASH_RATE, exposure=exposure_fn(arm, stress))
            st = VQ.stats(nav, rebals); st.pop("_r")
            seg = nav.loc["2025-01-01":"2025-04-30"]
            st["dip_2025"] = round(100 * (seg.min() / seg.cummax().max() - 1), 1) if len(seg) else None
            table[arm] = st
            print(f"{arm:12s} {st['cagr_pct']:6.1f} {st['sharpe']:6.2f} {st['mdd_pct']:5.0f} {st['dip_2025'] if st['dip_2025'] is not None else float('nan'):8.0f}")
            sys.stdout.flush()
        results["part_a"][str(month)] = table
    # 2008 basket
    closeY, volY, jkY = TO.load_yahoo()
    endY = closeY.index[-1]
    annual = []
    for y in range(2008, endY.year + 1):
        pos = closeY.index.searchsorted(pd.Timestamp(f"{y}-05-02"))
        if pos < len(closeY.index):
            annual.append(closeY.index[pos])
    lists = TO.baskets(closeY, volY, annual)
    checks = sorted(set(TO.month_starts(closeY.index, annual[0], endY)) | set(annual))
    stress = MacroStress(jkY, closeY, checks, macro)
    plan = CB.monthly_plan(lists, checks)
    eps = tuple(TO.EPISODES)
    TO.N_TRIALS = TRIALS
    print(f"\n=== 2008-2026 basket   on-time: " + ", ".join(f"{k} {CB.stress_share(stress, checks, k):.0f}%" for k in (*MACRO, "macro_any2", "all_any2")))
    print(f"{'arm':14s} {'total%':>8} {'CAGR%':>6} {'Sharpe':>6} {'mDD%':>5} {'cash%':>5} {'DSR':>5} | episode drawdowns %")
    tableB = {}
    for arm in ARMS:
        nav = VQ.simulate(plan, closeY, volY, {}, TO.EMPTY_DIV, annual[0], endY, True, mode="reset", cash_rate=CB.CASH_RATE, exposure=exposure_fn(arm, stress))
        v = TO.read(nav, annual)
        tableB[arm] = v
        print(TO.line(arm, v, eps))
        sys.stdout.flush()
    results["part_b"] = tableB
    A, B = results["part_a"], results["part_b"]
    print("\n--- reading rule: the cash-buffer rule AND 2008-basket mDD at least 3 pts shallower than price-only any2")
    full_dd = max(A[m]["full"]["mdd_pct"] for m in A)
    full_avg = float(np.mean([A[m]["full"]["cagr_pct"] for m in A]))
    any2_dd = B["any2"]["mdd_pct"]
    verdicts = {}
    for arm in ARMS:
        if arm == "full":
            continue
        sh = sum(A[m][arm]["sharpe"] > A[m]["full"]["sharpe"] for m in A)
        dd = max(A[m][arm]["mdd_pct"] for m in A)
        avg = float(np.mean([A[m][arm]["cagr_pct"] for m in A]))
        b = B[arm]
        e08, e20 = b["episodes"].get("2008"), b["episodes"].get("2020")
        base_ok = sh >= 3 and dd <= full_dd - 5 and avg >= 0.75 * full_avg and b["mdd_pct"] <= 40 and (e08 or 0) >= -30 and (e20 or 0) >= -30
        better = b["mdd_pct"] <= any2_dd - 3
        ok = base_ok and better and arm in (*MACRO, "macro_any2", "all_any2")
        verdicts[arm] = {"avg_cagr": avg, "sharpe_wins": sh, "worst_mdd": dd, "basket_cagr": b["cagr_pct"], "basket_mdd": b["mdd_pct"], "ep_2008": e08, "ep_2020": e20,
                         "passes_buffer_rule": base_ok, "beats_price_any2": better, "candidate": ok}
        print(f"  {arm:12s} strict avg CAGR {avg:5.1f} ({100*avg/full_avg:3.0f}%)  Sharpe wins {sh}/4  worst mDD {dd:3.0f}% | basket CAGR {b['cagr_pct']:5.1f} mDD {b['mdd_pct']:3.0f}% "
              f"2008 {e08:+.0f} 2020 {e20:+.0f} | buffer rule {'ok' if base_ok else 'no'}, beats price any2 {'yes' if better else 'no'} -> {'CANDIDATE' if ok else 'tested'}")
    results["verdicts"] = verdicts
    with open(OUT, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nresults ->", OUT)


if __name__ == "__main__":
    main()
