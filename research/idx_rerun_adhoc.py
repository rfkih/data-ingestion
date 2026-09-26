"""Re-runs of the three studies that were run by hand, with no script of their own (2026-09-26 re-run after the open fill).

  wide       #163 ml_confirm_stops_wide - idx_ml_confirm_stops with the wide stop arms (30 / 35 / 40 %) on the wait_up5 base
  gapsize    #167 combo_rupiah_gapsize  - the combined book with gap-fade sized at 5 / 10 / 20 % of NAV (trend and ML 5 %)
  trendsize  #168 combo_rupiah_trendsize - the deployed sizing (gap 10 / trend 5 / ML 5), without trend, and trend at 2.5 %

Same study names, trials and summary keys as the originals, on the current engine (idx_combo_rupiah after the 2026-09-26
engine fixes) and the current data. #168's original carried per-sleeve P&L from a one-off engine; the sizing engine used
here (idx_alloc_frontier.engine) returns the NAV only, so that one field is left out and noted in the row's params.

Run: INGEST_DB_DSN=... IDX_ML_CACHE=C:/Project/tmp/ml_strategy_cache.pkl python research/idx_rerun_adhoc.py wide|gapsize|trendsize
"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import date

import numpy as np
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))

import idx_combo_rupiah as CR  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402


def _inputs():
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = CR.ml_trades(P, dates, codes, A, raw, offer, bid, liq)
    tr = CR.trend_trades(dsn, dates)
    gap = CR.gap_events(dsn, dates)
    return dsn, dates, codes, A, raw, offer, bid, ml, tr, gap


def _store(dsn: str, name: str, trials: list[str], res: dict, extra: dict | None = None) -> int:
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, name, date.today(), params={"trials": trials, **(extra or {})}, summary=common.plain(res), names=[],
                              note="re-run 2026-09-26 on corrected opens and the fixed engine")
        conn.commit()
    M.log(f"{name}: study #{sid} stored")
    return sid


def gapsize() -> int:
    dsn, dates, codes, A, raw, offer, bid, ml, tr, gap = _inputs()
    res = {}
    for p in (0.05, 0.10, 0.20):
        nav, T_, inv = CR.engine(dates, codes, A, raw, offer, bid, ml, tr, gap, {"gap", "trend", "ML"}, pct_gap=p)
        st = CR.stats(nav)
        st["per"] = {s_: {"n": len(X), "win": float((X["pnl"] > 0).mean()), "pnl": float(X["pnl"].sum()), "worst": float(X["pnl"].min())}
                     for s_, X in T_.groupby("strat")}
        st["invested"] = inv
        res[f"gap {int(p * 100)} %"] = st
        M.log(f"gap {p:.0%}: CAGR {st['cagr'] * 100:.1f} % Sharpe {st['sharpe']:.2f} mDD {st['mdd'] * 100:.0f} %")
    return _store(dsn, "combo_rupiah_gapsize", list(res), res)


def trendsize() -> int:
    import idx_alloc_frontier as AF
    dsn, dates, codes, A, raw, offer, bid, ml, tr, gap = _inputs()
    arms = {"trend 5 / ML 5 / gap 10": {"gap": 0.10, "trend": 0.05, "ML": 0.05},
            "ML 5 / gap 10 (tanpa trend)": {"gap": 0.10, "trend": 0.0, "ML": 0.05},
            "trend 2.5 / ML 5 / gap 10": {"gap": 0.10, "trend": 0.025, "ML": 0.05}}
    res = {}
    for name, pct in arms.items():
        nav, expo = AF.engine(dates, codes, A, raw, offer, bid, ml, tr, gap, pct)
        st = CR.stats(nav)
        st["invested"] = float(np.nanmean(expo)) if expo is not None else None
        ex = nav[nav.index.year != 2025]
        r = ex.pct_change().dropna()
        yrs = len(r) / 252 if len(r) else None
        st["cagr_ex2025"] = float((1 + r).prod() ** (1 / yrs) - 1) if yrs else None
        res[name] = st
        M.log(f"{name}: CAGR {st['cagr'] * 100:.1f} % Sharpe {st['sharpe']:.2f} mDD {st['mdd'] * 100:.0f} %")
    return _store(dsn, "combo_rupiah_trendsize", list(res), res,
                  {"note": "per-sleeve P&L of the original one-off engine not reproduced (sizing engine returns NAV only)"})


def wide() -> int:
    import idx_ml_confirm_stops as CS
    CS.ARMS = {"stop30": dict(stop=0.30), "stop35": dict(stop=0.35), "stop40": dict(stop=0.40)}
    CS.STUDY = "ml_confirm_stops_wide"
    return CS.main()


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"wide": wide, "gapsize": gapsize, "trendsize": trendsize}.get(what)
    if fn is None:
        sys.exit("usage: idx_rerun_adhoc.py wide|gapsize|trendsize")
    r = fn()
    sys.exit(0 if isinstance(r, int) and r >= 0 else 1)
