#!/usr/bin/env python3
"""The combined book AS DEPLOYED (operator, 2026-09-26: "lengkapi informasi statistiknya selengkap mungkin") - a reporting run
of the live configuration, not a new trial (no rule is chosen here; cumulative N unchanged).

Configuration (live-fae554 settings v2, 2026-09-26): Rp 20 M, one cash pool, 20 slots, cash floor 30 %,
  gap-fade  10 % of NAV per trade (deployed rule, IDX-only opens), bought at the open + tick, sold at the close - tick
  trend     5 % of NAV per trade (small universe, 60-day high / > MA200 / volume, trail-10, regime gate)
  ML        10 % of NAV per name as ens4: four confirmation rules (+5/10, +8/10, +10/10, +8/5), each a quarter of the slot,
            with the same-day stop -5 % (study #288: a close <= fill x 0.95 sells at that close)
Engine idx_alloc_frontier.engine (the combo engine with the cash floor, #263/#282), 2022-01 -> 2026-09-16.
Arms: combined, and each sleeve alone at its deployed size on the same engine (what each strategy page shows as its backtest).

Stored per arm - everything the Strategies page shows: total, CAGR, Sharpe, Sortino, volatility, max DD (and in rupiah),
longest drawdown (sessions), Calmar, time in market, per year / per month returns, Sharpe per half and without 2025, and the
trade statistics (count, win rate, average / median / best / worst trade, average hold, profit factor, expectancy); the daily NAV
as [date, nav] pairs. Trade lists go to research-scratch/combo_live_<arm>.csv for idx strategy-backtest import.
Run: INGEST_DB_DSN=... IDX_ML_CACHE=... IDX_BOARD_MODE=pit IDX_EXIT_CACHE=... python research/idx_combo_live.py
"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
import idx_combo_rupiah as CR  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_ens4_exits as X  # noqa: E402
import idx_ml_stop_sameclose as SC  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "combo_live"
FLOOR = 0.30
PCT = {"gap": 0.10, "trend": 0.05, "ML": 0.10}
STOP = 0.05
HALF_SPLIT = pd.Timestamp("2024-05-01")


def _sharpe(r: pd.Series) -> float | None:
    return float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 1 and r.std() > 0 else None


def _cagr(r: pd.Series) -> float | None:
    return float((1 + r).prod() ** (252 / len(r)) - 1) if len(r) else None


def book_stats(nav: pd.Series, invested: list[float]) -> dict:
    r = nav.pct_change().dropna()
    eq = nav / nav.iloc[0]
    dd = eq / eq.cummax() - 1
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1)
    down = r[r < 0]
    longest = cur = 0
    for v in dd.to_numpy():
        cur = cur + 1 if v < 0 else 0
        longest = max(longest, cur)
    by_y = nav.groupby(nav.index.year).agg(["first", "last"])
    prev, years = float(nav.iloc[0]), {}
    for y, v in by_y.iterrows():
        years[int(y)] = float(v["last"] / prev - 1)
        prev = float(v["last"])
    m_end = nav.groupby([nav.index.year, nav.index.month]).last()
    months, prev = {}, float(nav.iloc[0])
    for (y, m), v in m_end.items():
        months[f"{y}-{m:02d}"] = float(v / prev - 1)
        prev = float(v)
    ex = r[r.index.year != 2025]
    return {"final": float(nav.iloc[-1]), "total": float(eq.iloc[-1] - 1), "cagr": cagr, "vol": float(r.std() * np.sqrt(252)),
            "sharpe": _sharpe(r), "sortino": float(r.mean() / np.sqrt((down ** 2).mean()) * np.sqrt(252)) if len(down) else None,
            "mdd": float(dd.min()), "mdd_rp": float((nav - nav.cummax()).min()), "mdd_long": int(longest),
            "calmar": cagr / -float(dd.min()) if dd.min() < 0 else None, "invested_share": float(np.mean(invested)) if invested else None,
            "sharpe_h1": _sharpe(r[r.index < HALF_SPLIT]), "sharpe_h2": _sharpe(r[r.index >= HALF_SPLIT]),
            "cagr_ex2025": _cagr(ex), "sharpe_ex2025": _sharpe(ex), "best_day": float(r.max()), "worst_day": float(r.min()),
            "pos_months": sum(1 for v in months.values() if v > 0), "n_months": len(months),
            "by_year": years, "by_month": months, "sessions": len(nav), "from": str(nav.index[0].date()), "to": str(nav.index[-1].date()),
            "nav": [[str(d.date()), round(float(v), 2)] for d, v in nav.items()]}


def trade_stats(T: pd.DataFrame) -> dict:
    if not len(T):
        return {"trades": 0}
    ret = T["pnl"] / T["cost"]
    gain, loss = T.loc[T["pnl"] > 0, "pnl"].sum(), -T.loc[T["pnl"] < 0, "pnl"].sum()
    return {"trades": int(len(T)), "win": float((T["pnl"] > 0).mean()), "avg": float(ret.mean()), "median": float(ret.median()),
            "best": float(ret.max()), "worst": float(ret.min()), "avg_win": float(ret[ret > 0].mean()) if (ret > 0).any() else None,
            "avg_loss": float(ret[ret < 0].mean()) if (ret < 0).any() else None, "profit_factor": float(gain / loss) if loss > 0 else None,
            "expectancy_rp": float(T["pnl"].mean()), "pnl_rp": float(T["pnl"].sum()), "hold": float(T["hold"].mean()),
            "per_strategy": {s: {"n": int(len(X_)), "win": float((X_["pnl"] > 0).mean()), "pnl": float(X_["pnl"].sum()),
                                 "avg": float((X_["pnl"] / X_["cost"]).mean())} for s, X_ in T.groupby("sleeve")}}


def main() -> int:
    store = "--no-store" not in sys.argv                              # --no-store: rewrite the trade lists only
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
    ml = []
    for i, rule in enumerate(X.ENS4, start=1):
        _, log = SC.book_same(A, liq, e5, X.K, c_in, c_out, X.MARGIN, wait=rule, stop=STOP, t_start=t0)
        ml += [{"strat": f"ML{i}", "code": codes[r.j], "t_in": int(r.t_in), "t_out": int(r.t_out), "why": r.why} for r in log.itertuples()]
    M.log(f"events: ML {len(ml)} rule-trades, trend {len(tr)}, gap-fade {len(gap)}")
    pct_all = {"gap": PCT["gap"], "trend": PCT["trend"], **{f"ML{i}": PCT["ML"] / 4 for i in range(1, 5)}}
    arms = {"combined": pct_all, "gap_only": {"gap": PCT["gap"]}, "trend_only": {"trend": PCT["trend"]},
            "ml_only": {k: v for k, v in pct_all.items() if k.startswith("ML")}}
    res = {}
    for name, pct in arms.items():
        lg: dict = {}
        use_ml = ml if any(k.startswith("ML") for k in pct) else []
        use_tr = tr if "trend" in pct else []
        use_gap = gap if "gap" in pct else []
        nav, _ = AF.engine(dates, codes, A, raw, offer, bid, use_ml, use_tr, use_gap, {**{k: 0.0 for k in pct_all}, **pct},
                           cash_floor=FLOOR, log=lg)
        T = pd.DataFrame(lg.get("trades", []))
        if len(T):
            T["pnl"] = T["proceeds"] - T["cost"]
            T["hold"] = T["t_out"] - T["t_in"]
            T["sleeve"] = T["strat"].map(lambda s: "ML" if s.startswith("ML") else s)
            T.assign(d_in=dates[T["t_in"]].date, d_out=dates[T["t_out"]].date).to_csv(
                os.path.join(ROOT, "research-scratch", f"combo_live_{name}.csv"), index=False)
        st = {**book_stats(nav, lg.get("invested", [])), **trade_stats(T)}
        res[name] = st
        M.log(f"{name:<10} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:.2f} Sortino {st['sortino']:.2f} vol {st['vol'] * 100:.1f} % "
              f"mDD {st['mdd'] * 100:.1f} % ({st['mdd_long']} sessions) invested {st['invested_share'] * 100:.0f} % trades {st.get('trades')} "
              f"win {st.get('win', 0) * 100:.0f} % ex-2025 {st['cagr_ex2025'] * 100:.1f} %")
    L = [f"# The combined book as deployed (live-fae554 v2) - {date.today()}", "",
         "Rp 20 M, floor 30 %, gap 10 % / trend 5 % / ML 10 % (ens4, same-day stop -5 %). Reporting run, no trial.", "",
         "| arm | total | CAGR | Sharpe | Sortino | vol | mDD | longest DD | Calmar | invested | ex-2025 CAGR | trades | win | avg | median | PF |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in res.items():
        L.append(f"| {name} | {s['total'] * 100:+.0f} % | {s['cagr'] * 100:.1f} % | {s['sharpe']:.2f} | {s['sortino']:.2f} | {s['vol'] * 100:.1f} % | "
                 f"{s['mdd'] * 100:.1f} % | {s['mdd_long']} | {s['calmar']:.2f} | {s['invested_share'] * 100:.0f} % | {s['cagr_ex2025'] * 100:.1f} % | "
                 f"{s['trades']} | {s['win'] * 100:.0f} % | {s['avg'] * 100:+.2f} % | {s['median'] * 100:+.2f} % | {s['profit_factor']:.2f} |")
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_COMBO_LIVE_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    if not store:
        M.log("--no-store: trade lists written, no study row")
        return 0
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(),
                              params={"trials": [], "kind": "reporting", "config": {"capital": CR.CAPITAL, "floor": FLOOR, "pct": PCT, "rules": X.ENS4,
                                                                                    "stop": STOP, "stop_mode": "same_close", "from": str(CR.START.date()),
                                                                                    "to": str(CR.END.date())}, "sources": [263, 282, 288]},
                              summary=common.plain(res), names=[], report_path=out,
                              note="the combined book as deployed 2026-09-26 (10/5/10, ens4, same-day stop 5 %), each sleeve alone too; reporting, no trial")
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
