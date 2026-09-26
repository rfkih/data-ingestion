#!/usr/bin/env python3
"""IDX menu ML-9b - does the ML stop of ML-9 (#281) survive inside the combined book as it is LIVE? (operator, 2026-09-26)

#281 measured exits on the ML sleeve's own book (K 10, equal weight). The live book (live-fae554) is different: one Rp 20 M cash
pool with trend 5 % and gap-fade 10 % of NAV per trade, a 30 % cash floor, and the ML sleeve as ens4 - four confirmation rules,
each buying a quarter of the 5 % slot (1.25 % of NAV). The combo backtests so far (#166 -> #256, #177 -> #263) model the ML
sleeve with the SINGLE +5 %/10 d rule, so none of them is the live configuration either.

PRE-REGISTERED 2026-09-26 before any result of this script was seen (2 trials; cumulative 985 + 2 = 987):
  Engine  idx_alloc_frontier.engine (the combo engine with a cash floor), 2022-01 -> 2026-09-16, Rp 20 M, cash floor 0.30,
          gap 10 % / trend 5 % of NAV per trade; ML = the four ens4 rule-books of research/idx_ml_ens4_exits.book, each rule's
          trades sized 1.25 % of NAV and kept as its own position (tags ML1..ML4). A quarter slot below one lot is skipped, as live.
  Arms    none (live today) | stop5 | stop10 - the ML exit applied inside all four rule-books, as in #281.
  Also shown (reference, not a trial): the same book with the single +5 %/10 d ML rule at 5 % (what #256/#263 model).
READING RULE: an ML stop is CONFIRMED in the live book if, against `none`: Sharpe >= none, max drawdown not deeper, CAGR >= 0.9 x
  none, and Sharpe >= none in both halves (2022-01..2024-04, 2024-05..end). Otherwise #281's result does not carry over.
Known difference from live: the engine counts each rule's position against the 20-slot cap separately (live: one slot per name).
READ-ONLY; one idx.study row (combo_ml_exits). Needs IDX_ML_CACHE, IDX_EXIT_CACHE (pit) as the re-run.
"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import date

import numpy as np
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
import idx_combo_rupiah as CR  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_ens4_exits as X  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 985
STUDY = "combo_ml_exits"
FLOOR = 0.30
ARMS = {"none": {}, "stop5": {"stop": 0.05}, "stop10": {"stop": 0.10}}
HALF_SPLIT = date(2024, 5, 1)


def sharpe(r: np.ndarray) -> float:
    return float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 1 and r.std() > 0 else float("nan")


def main() -> int:
    dsn = AF.dsn()
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    c_in, c_out = M.costs(raw, offer, bid)
    S_ = g("s5").to_numpy(float)
    e5 = C.ema(S_ - np.nanmedian(np.where(liq, S_, np.nan), axis=1, keepdims=True), X.SPAN)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    tr = CR.trend_trades(dsn, dates)
    gap = CR.gap_events(dsn, dates)
    ml_single = CR.ml_trades(P, dates, codes, A, raw, offer, bid, liq)

    def ens4_trades(**kw):
        out = []
        for i, rule in enumerate(X.ENS4, start=1):
            _, log = X.book(A, liq, e5, X.K, c_in, c_out, X.MARGIN, wait=rule, t_start=t0, **kw)
            out += [{"strat": f"ML{i}", "code": codes[r.j], "t_in": int(r.t_in), "t_out": int(r.t_out)} for r in log.itertuples()]
        return out

    def run(ml, pct):
        nav, expo = AF.engine(dates, codes, A, raw, offer, bid, ml, tr, gap, pct, cash_floor=FLOOR)
        st = CR.stats(nav)
        r = nav.pct_change().dropna()
        st["sharpe_h1"] = sharpe(r[r.index < str(HALF_SPLIT)].to_numpy())
        st["sharpe_h2"] = sharpe(r[r.index >= str(HALF_SPLIT)].to_numpy())
        st["sharpe_ex2025"] = sharpe(r[r.index.year != 2025].to_numpy())
        st["invested"] = expo
        return st

    base_pct = {"gap": 0.10, "trend": 0.05, **{f"ML{i}": 0.05 / 4 for i in range(1, 5)}}
    res: dict[str, dict] = {}
    for arm, kw in ARMS.items():
        ml = ens4_trades(**kw)
        st = run(ml, base_pct)
        st["ml_trades_offered"] = len(ml)
        res[arm] = st
        M.log(f"{arm:<7} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % h1/h2 {st['sharpe_h1']:.2f}/{st['sharpe_h2']:.2f} "
              f"ex25 {st['sharpe_ex2025']:.2f} ML trades offered {len(ml)}")
    ref = run(ml_single, {"gap": 0.10, "trend": 0.05, "ML": 0.05})
    M.log(f"reference (single +5/10 rule at 5 %, floor 0.30): CAGR {ref['cagr'] * 100:.1f} % Sharpe {ref['sharpe']:.2f} mDD {ref['mdd'] * 100:.1f} %")
    b = res["none"]
    for arm in ("stop5", "stop10"):
        r = res[arm]
        why = []
        if r["sharpe"] < b["sharpe"]:
            why.append(f"sharpe {r['sharpe']:.2f} < none {b['sharpe']:.2f}")
        if r["mdd"] < b["mdd"]:
            why.append("mdd deeper")
        if r["cagr"] < 0.9 * b["cagr"]:
            why.append("cagr < 90 % none")
        if r["sharpe_h1"] < b["sharpe_h1"] or r["sharpe_h2"] < b["sharpe_h2"]:
            why.append("not better in both halves")
        r["confirmed"] = not why
        r["verdict"] = "CONFIRMED" if not why else "no: " + "; ".join(why)
        M.log(f"{arm}: {r['verdict']}")
    n_trials = N_BEFORE + 2
    yrs = list(b["by_year"])
    L = [f"# IDX menu ML-9b - the ML stop inside the live combined book - {date.today()} - 2 trials, cumulative N = {n_trials}", "",
         "Live configuration: Rp 20 M, cash floor 30 %, gap 10 % / trend 5 % per trade, ML ens4 with 1.25 % of NAV per rule. "
         "Pre-registered reading rule in the script's docstring.", "",
         "| book | CAGR | Sharpe | mDD | Sharpe H1 / H2 | Sharpe ex-2025 | invested | " + " | ".join(str(y) for y in yrs) + " | verdict |",
         "|---|---|---|---|---|---|---|" + "---|" * len(yrs) + "---|"]
    for arm, r in {**res, "reference: single rule 5 %": ref}.items():
        L.append(f"| {arm} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['sharpe_h1']:.2f} / {r['sharpe_h2']:.2f} | "
                 f"{r['sharpe_ex2025']:.2f} | {r['invested'] * 100:.0f} % | " + " | ".join(f"{r['by_year'].get(y, float('nan')) * 100:+.0f} %" for y in yrs)
                 + f" | {r.get('verdict', 'reference')} |")
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_COMBO_ML_EXITS_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(),
                              params={"trials": ["stop5", "stop10"], "n_trials_cumulative": n_trials, "cash_floor": FLOOR, "pct": base_pct,
                                      "rules": X.ENS4, "confirms": 281},
                              summary=common.plain({"arms": res, "reference_single": ref}), names=[], report_path=out,
                              note=f"ML-9b: ML stop in the live combo: stop5 {res['stop5']['verdict']}, stop10 {res['stop10']['verdict']}")
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
