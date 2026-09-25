#!/usr/bin/env python3
"""IDX menu ML-6c — the cost-aware ML book as a SLEEVE next to the proven books (follow-up to ML-6/6b, 2026-09-25).

ML-6b left the cost-aware ML book at +29 %/yr, Sharpe 0.9, mDD -51 % (2022): a selection signal without a risk rule, and
no single-book overlay fixed it. The desk's own answer to that shape was the combined book (menu 21 B: value 50 / trend 50
passed the money rule that neither sleeve passed alone). This menu asks the same question with the ML book as a sleeve.

PRE-REGISTERED (3 trials; cumulative 757 + 3 = 760; the first stored run #156 is VOID - the trend sleeve was NaN - and is superseded by the rerun). Daily returns 2022-01 -> end, every sleeve on its own simulator:
  ML     = ML-6 e5|2|3|10 on LIQ (study #154)             trend = the deployed trend book (small, trail-10, regime gate)
  value  = composite_q, May rebalances from 2022-05 (idx_value_quality; before the first rebalance the sleeve is cash)
  Arms: ml_trend_50   50 % ML / 50 % trend, rebalanced to weights daily (the desk's convention for the combined book)
        ml_trend_value 1/3 each
        ml_vt_trend_50 50 % ML with ML-6b's 20 % vol target / 50 % trend
  References: each sleeve alone; value 50 / trend 50 on the same window; correlations of daily returns.
READING RULE: the money rule (Sharpe >= 1.0, mDD >= -25 %) AND Sharpe >= value/trend 50/50 on the same window + 0.15 AND
  >= 4/5 years positive -> CANDIDATE (a paper combined book, operator's decision).
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
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_beyond as BY  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_costaware2 as C2  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_value_quality as V  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 757
STUDY = "ml_sleeves"
ARMS = ["ml_trend_50", "ml_trend_value", "ml_vt_trend_50"]
FROM = pd.Timestamp("2022-01-01")


def ml_sleeve() -> pd.Series:
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    c_in, c_out = M.costs(g("close").to_numpy(float), g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    Sc = g("s5").to_numpy(float)
    e5 = C.ema(Sc - np.nanmedian(np.where(liq, Sc, np.nan), axis=1, keepdims=True), 3)
    t0 = int(np.searchsorted(dates, np.datetime64(FROM)))
    R, n, hold = C2.book(A, liq, e5, 10, c_in, c_out, 2.0, t_start=t0)
    M.log(f"ML sleeve: {n} trades, hold {hold:.0f} d")
    return pd.Series(R, index=dates)[dates >= FROM]


def trend_sleeve(dsn: str) -> pd.Series:
    P, unis, comp, Hp, Lp = E.load_all(dsn, os.environ.get("IDX_EXIT_CACHE"))
    c_in, c_out = S.costs(P)
    adj, vol = P["adj"], P["volume"]
    dates = adj.index
    A, H, L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(60, min_periods=60).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool) & np.asarray(dates >= FROM)[:, None] & ~BY.regime_off_mask(comp, dates)[:, None]
    prev = adj.shift(1)
    tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
    ATR = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
    ma20, ma50 = (adj.rolling(n, min_periods=n).mean().to_numpy(float) for n in (20, 50))
    d = adj.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    RSI = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy(float)
    LO10 = Lp.shift(1).rolling(10, min_periods=10).min().to_numpy(float)
    LO20 = Lp.shift(1).rolling(20, min_periods=20).min().to_numpy(float)
    rule = E.make_rules(A, H, L, ATR, ma20, ma50, RSI, LO10, LO20)["trail10"]
    small = (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool)
    R, trs, _ = E.run_book(A, H, L, c_in, c_out, entry, vr.to_numpy(float), rule, small)
    R = np.nan_to_num(np.asarray(R, dtype=float))                 # run_book leaves NaN on days with nothing held
    return pd.Series(R, index=dates)[dates >= FROM]


def value_sleeve(dsn: str) -> pd.Series:
    with psycopg.connect(dsn) as conn:
        close, vol, delisted, div, _ = V.load(conn)
        rebals = [D for D in V.rebalance_dates(close.index, 5) if D >= FROM]
        sel = {}
        for D in rebals:
            rows = cand.build(conn, D.date())["all_rows"]
            pool = cand.rank_pool([dict(r) for r in rows], gate="strict", keys=cand.KEYS)
            sel[D] = {r["code"] for r in pool if r["selected"]}
        nav = V.simulate(sel, close, vol, delisted, div, rebals[0], close.index[-1], True)
    r = nav.pct_change().fillna(0.0)
    return r[r.index >= FROM]


def combine(parts: dict[str, pd.Series], weights: dict[str, float]) -> pd.Series:
    idx = sorted(set().union(*[set(p.index) for p in parts.values()]))
    df = pd.DataFrame({k: p.reindex(idx).fillna(0.0) for k, p in parts.items()})
    return sum(df[k] * w for k, w in weights.items())


def stats(r: pd.Series) -> dict:
    return M.stats(r.to_numpy(float), pd.DatetimeIndex(r.index), 0)


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    ml = ml_sleeve()
    ml_vt = pd.Series(C2.vol_target(ml.to_numpy(float)), index=ml.index)
    tr = trend_sleeve(dsn)
    va = value_sleeve(dsn)
    sleeves = {"ML": ml, "ML_vt": ml_vt, "trend": tr, "value": va}
    df = pd.DataFrame({k: v for k, v in sleeves.items()}).fillna(0.0)
    corr = df[["ML", "trend", "value"]].corr().round(2).to_dict()
    res, refs = {}, {}
    for k, v in sleeves.items():
        refs[k] = stats(v)
        M.log(f"sleeve {k:<6} CAGR {refs[k]['cagr'] * 100:6.1f} % Sharpe {refs[k]['sharpe']:5.2f} mDD {refs[k]['mdd'] * 100:6.1f} %")
    refs["value_trend_50"] = stats(combine({"trend": tr, "value": va}, {"trend": 0.5, "value": 0.5}))
    M.log(f"value/trend 50/50: CAGR {refs['value_trend_50']['cagr'] * 100:.1f} % Sharpe {refs['value_trend_50']['sharpe']:.2f} mDD {refs['value_trend_50']['mdd'] * 100:.0f} %")
    combos = {"ml_trend_50": ({"ML": ml, "trend": tr}, {"ML": 0.5, "trend": 0.5}),
              "ml_trend_value": ({"ML": ml, "trend": tr, "value": va}, {"ML": 1 / 3, "trend": 1 / 3, "value": 1 / 3}),
              "ml_vt_trend_50": ({"ML": ml_vt, "trend": tr}, {"ML": 0.5, "trend": 0.5})}
    bar = refs["value_trend_50"]["sharpe"] + 0.15
    for name, (parts, w) in combos.items():
        st = stats(combine(parts, w))
        fails = []
        if st["sharpe"] < 1.0:
            fails.append(f"sharpe {st['sharpe']:.2f} < 1.0")
        if st["mdd"] < -0.25:
            fails.append(f"mdd {st['mdd'] * 100:.0f} % < -25 %")
        if st["sharpe"] < bar:
            fails.append(f"sharpe < value/trend {refs['value_trend_50']['sharpe']:.2f} + 0.15")
        if st["years_pos"] < min(4, st["n_years"]):
            fails.append(f"{st['years_pos']}/{st['n_years']} years positive")
        st["verdict"] = "CANDIDATE" if not fails else "not a candidate: " + "; ".join(fails)
        res[name] = st
        M.log(f"{name:<15} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % years+ {st['years_pos']}/{st['n_years']} -> {st['verdict']}")
    n_trials = N_BEFORE + len(ARMS)
    L = [f"# IDX menu ML-6c — the cost-aware ML book as a sleeve next to the proven books — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
         "Daily returns 2022-01 -> end, each sleeve on its own simulator; combined books rebalanced to weights daily.", "",
         "| book | CAGR | Sharpe | mDD | years + | by year | verdict |", "|---|---|---|---|---|---|---|"]
    for k in ("ML", "ML_vt", "trend", "value", "value_trend_50"):
        r = refs[k]
        L.append(f"| {k} (sleeve) | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['years_pos']}/{r['n_years']} | "
                 + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items()) + " | reference |")
    for k in ARMS:
        r = res[k]
        L.append(f"| {k} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['years_pos']}/{r['n_years']} | "
                 + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items()) + f" | {r['verdict']} |")
    L += ["", f"Daily-return correlations: ML/trend {corr['ML']['trend']:.2f}, ML/value {corr['ML']['value']:.2f}, trend/value {corr['trend']['value']:.2f}.", "",
          "## Verdict (menu ML-6c, study stored)", "", f"Candidates: {', '.join(a for a in ARMS if res[a]['verdict'] == 'CANDIDATE') or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_SLEEVES_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "source": "#154 #155"},
                              summary={"arms": common.plain(res), "refs": common.plain(refs), "corr": corr}, names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
