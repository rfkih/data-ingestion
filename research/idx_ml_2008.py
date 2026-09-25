#!/usr/bin/env python3
"""IDX menu ML-8 - the cost-aware ML book and the up-confirmation entry before 2020 (operator, 2026-09-25: "bisa nggak kita test
dari 2008?").

The prediction desk's model (idx/ml/daily.py) needs the IDX tape (bid/offer, foreign legs, frequency), PIT fundamentals, broker
flow and events - none of which exist before 2020. Before 2020 the only prices are the Yahoo cache (research-scratch/idx/*.JK.csv,
split-adjusted OHLCV for ~450 names that still exist today; 124 with bars in 2008). So this menu tests a PRICE-ONLY version of the
same pipeline: the same feature code restricted to what OHLCV, the JKSE and the macro series give, the same LightGBM, the same
walk-forward, the same cost-aware book and the same +5 % confirmation entry. Two honesty limits, as in menu 15 (study #46):
survivorship (the names that went to zero are not in the file; random-on-the-same-file is the fair reference) and a flat cost
model (0.30 % half-spread each side + Stockbit fees; no bid/offer before 2020).

PRE-REGISTERED (2 trials; cumulative 802 + 2 = 804): base = e5 | margin 2 | ema 3 | K 10; wait_up5 = the same with the +5 %/10-day
  confirmation. Scores walk-forward by test year 2008..2019 (fit on 2005.. purged, liquid rows: 60-day median value >= Rp 5 bn on
  adjusted prices, close >= Rp 100). Book 2008-01 -> 2019-12.
  References (not trials): random entries with the base book's mechanics (5 seeds); JKSE buy-and-hold; the same price-only pipeline
  on the Yahoo cache 2020-01 -> 2026-09 next to the full-feature IDX-data result (+36 %/1.38/-27 %) = how much the price-only model
  and the cache differ from the deployed data.
READING RULE: the construction HOLDS before 2020 if wait_up5 2008-2019 has: >= 150 trades; CAGR >= 10 %; Sharpe >= random + 0.5;
  positive in >= 8 of 12 years; and the 2008 drawdown shallower than the JKSE's. Otherwise: a 2020-26 phenomenon.
"""
from __future__ import annotations

import glob
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_ml_confirm as F  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common, daily  # noqa: E402

N_BEFORE = 802
STUDY = "ml_2008"
YAHOO = os.path.join(ROOT, "research-scratch", "idx")
HALF_SPREAD = 0.0030
FEE_BUY, FEE_SELL = 0.0010, 0.0020
LIQ_VALUE, MIN_PRICE = 5e9, 100.0
TEST_YEARS = list(range(2008, 2020))
BRIDGE_YEARS = list(range(2020, 2027))
PRICE_FEATS = [f for f in daily.FEATURES if f in {
    "ret1", "ret5", "ret20", "ret60", "ret120", "ret250", "dist_ma20", "dist_ma50", "dist_ma200", "vol20", "vol60", "atr_pct", "pos20", "dist_hi252",
    "dist_lo252", "volr1", "volr5", "lvalue20", "lvalue60", "gap", "clv", "up_days", "dow", "month", "age", "xs_r1", "xs_r20", "xs_r60", "breadth",
    "comp_r1", "comp_r5", "comp_r20", "comp_r60", "comp_dma200", "comp_vol20", "usdidr_r20", "bi_rate", "us10y", "vix", "vix_r20", "brent_r20",
    "gold_r20", "cpo_r20", "fedfunds", "id_cpi_yoy", "id_gdp_qoq"}]


def load_yahoo() -> tuple[pd.DataFrame, pd.Series]:
    jk = pd.read_csv(os.path.join(YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    jk = jk[~jk.index.duplicated(keep="last")]
    jk = jk[jk.index >= "2004-01-01"]
    rows = []
    for f in sorted(glob.glob(os.path.join(YAHOO, "*.JK.csv"))):
        code = os.path.basename(f).split(".")[0]
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df = df[df.index.isin(jk.index) & (df.index >= "2004-01-01")]
        if df.empty:
            continue
        o = pd.to_numeric(df["open"], errors="coerce") if "open" in df else pd.Series(np.nan, index=df.index)
        B = pd.DataFrame({"code": code, "d": df.index, "open": o.to_numpy(), "high": pd.to_numeric(df["high"], errors="coerce").to_numpy(),
                          "low": pd.to_numeric(df["low"], errors="coerce").to_numpy(), "close": pd.to_numeric(df["close"], errors="coerce").to_numpy(),
                          "volume": pd.to_numeric(df["volume"], errors="coerce").to_numpy()})
        rows.append(B)
    B = pd.concat(rows, ignore_index=True)
    B = B[(B["close"] > 0) & B["close"].notna()]
    B["open"] = B["open"].where(B["open"] > 0, B["close"])
    B["value"] = B["close"] * B["volume"]
    B["adj"] = 1.0
    for c in ("frequency", "bid", "bid_vol", "offer", "offer_vol", "fbuy", "fsell", "listed", "tradeable", "weight", "nonreg_value"):
        B[c] = np.nan
    return B, jk


def index_feats(jk: pd.Series) -> pd.DataFrame:
    lc = np.log(jk)
    ix = pd.DataFrame({"d": jk.index, "comp_r1": lc.diff(1).to_numpy(), "comp_r5": lc.diff(5).to_numpy(), "comp_r20": lc.diff(20).to_numpy(),
                       "comp_r60": lc.diff(60).to_numpy(), "comp_dma200": (jk / jk.rolling(200, min_periods=100).mean() - 1).to_numpy(),
                       "comp_vol20": lc.diff(1).rolling(20).std().to_numpy()})
    return ix


def build_panel(conn) -> pd.DataFrame:
    B, jk = load_yahoo()
    B = daily.price_features(B)
    B["sector"] = np.nan
    B = daily.cross_section(B)
    B = B.merge(index_feats(jk), on="d", how="left")
    B = pd.merge_asof(B.sort_values("d"), daily.load_macro(conn).sort_values("d"), on="d", direction="backward").sort_values(["code", "d"]).reset_index(drop=True)
    B = daily.labels(B)
    v60 = B.groupby("code")["value"].transform(lambda x: x.rolling(60, min_periods=60).median())
    B["liq"] = (v60 >= LIQ_VALUE) & (B["close"] >= MIN_PRICE) & (B["volume"] > 0)
    B["value60"] = v60
    for c in PRICE_FEATS:
        if c not in B:
            B[c] = np.nan
    return B, jk


def scores(P: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    P = P.sort_values(["code", "d"]).reset_index(drop=True)
    cal = np.sort(pd.unique(P["d"]))
    year = P["d"].dt.year.to_numpy()
    X = common.to_matrix(P, PRICE_FEATS)
    P["s5"] = np.nan
    y = np.clip(P["fwd_5d"].to_numpy(float), -1.0, 1.0)
    for Y in years:
        cut = common.purge_cut(cal, np.datetime64(date(Y, 1, 1)), 5)
        fit_m = (P["d"].to_numpy() < cut) & np.isfinite(y) & P["liq"].to_numpy()
        test_m = year == Y
        if fit_m.sum() < 20000 or test_m.sum() == 0:
            M.log(f"score {Y}: skipped ({int(fit_m.sum())} fit rows)")
            continue
        bst = common.fit(X[fit_m], y[fit_m], "ret", common.BASE_PARAMS["ret"], PRICE_FEATS, seed=M.SEED + Y)
        P.loc[test_m, "s5"] = np.asarray(bst.predict(X[test_m]), dtype=float)
        M.log(f"score {Y}: fit {int(fit_m.sum()):,} rows (cut {pd.Timestamp(cut).date()}), scored {int(test_m.sum()):,}")
    return P


def run_books(P: pd.DataFrame, jk: pd.Series, y0: int, y1: int, label: str) -> dict:
    Q = P[(P["d"] >= f"{y0 - 1}-06-01") & (P["d"] <= f"{y1}-12-31")]
    dates = M.wide(Q, "close").index
    codes = M.wide(Q, "close").columns
    g = lambda c: M.wide(Q, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("close").to_numpy(float)
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    S = g("s5").to_numpy(float)
    e5 = C.ema(S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True), 3)
    c_in = np.full(A.shape, HALF_SPREAD + FEE_BUY)
    c_out = np.full(A.shape, HALF_SPREAD + FEE_SELL)
    t0 = int(np.searchsorted(dates, np.datetime64(date(y0, 1, 1))))
    out = {}
    R, log = F.book(A, liq, e5, 10, c_in, c_out, 2.0, t_start=t0)
    out["base"] = {**M.stats(R, dates, t0), "trades": len(log), "win": float((log["net"] > 0).mean()), "avg": float(log["net"].mean())}
    R, log = F.book(A, liq, e5, 10, c_in, c_out, 2.0, t_start=t0, wait=(0.05, 10))
    out["wait_up5"] = {**M.stats(R, dates, t0), "trades": len(log), "win": float((log["net"] > 0).mean()), "avg": float(log["net"].mean())}
    rr = []
    for s in range(5):
        rng = np.random.default_rng(M.SEED + s)
        sh = S.copy()
        for t in range(t0, len(dates)):
            idx = np.flatnonzero(liq[t] & np.isfinite(sh[t]))
            if len(idx) > 1:
                sh[t, idx] = sh[t, rng.permutation(idx)]
        e_sh = C.ema(sh - np.nanmedian(np.where(liq, sh, np.nan), axis=1, keepdims=True), 3)
        Rr, _ = F.book(A, liq, e_sh, 10, c_in, c_out, 2.0, t_start=t0, wait=(0.05, 10))
        rr.append(M.stats(Rr, dates, t0))
    out["random_wait_up5"] = {k: float(np.mean([r[k] for r in rr])) for k in ("cagr", "sharpe", "mdd")}
    jkw = jk[(jk.index >= f"{y0}-01-01") & (jk.index <= f"{y1}-12-31")].dropna()
    out["jkse"] = M.stats(jkw.pct_change().fillna(0).to_numpy(), jkw.index, 0)
    names = liq[t0:].sum(1)
    out["names_per_day"] = {"mean": float(names.mean()), "min": int(names.min()), "max": int(names.max())}
    for k in ("base", "wait_up5"):
        r = out[k]
        M.log(f"{label} {k:<9} CAGR {r['cagr'] * 100:6.1f} % Sharpe {r['sharpe']:5.2f} mDD {r['mdd'] * 100:6.1f} % trades {r['trades']} win {r['win'] * 100:.0f} % "
              + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items()))
    M.log(f"{label} random(wait_up5 mechanics) CAGR {out['random_wait_up5']['cagr'] * 100:.1f} % Sharpe {out['random_wait_up5']['sharpe']:.2f} mDD {out['random_wait_up5']['mdd'] * 100:.0f} % | "
          f"JKSE CAGR {out['jkse']['cagr'] * 100:.1f} % Sharpe {out['jkse']['sharpe']:.2f} mDD {out['jkse']['mdd'] * 100:.0f} % | liquid names/day {out['names_per_day']['mean']:.0f}")
    return out


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        P, jk = build_panel(conn)
    M.log(f"Yahoo panel {len(P):,} rows, {P['code'].nunique()} names, {P['d'].min().date()} -> {P['d'].max().date()}; liquid rows {int(P['liq'].sum()):,}")
    P = scores(P, TEST_YEARS + BRIDGE_YEARS)
    oos = run_books(P, jk, 2008, 2019, "2008-19")
    bridge = run_books(P, jk, 2020, 2026, "2020-26 cache")
    w = oos["wait_up5"]
    checks = {"trades>=150": w["trades"] >= 150, "cagr>=10%": w["cagr"] >= 0.10, "sharpe>=random+0.5": w["sharpe"] >= oos["random_wait_up5"]["sharpe"] + 0.5,
              "years_pos>=8/12": w["years_pos"] >= 8, "2008_dd_shallower_than_jkse": w["by_year"].get(2008, 0) > oos["jkse"]["by_year"].get(2008, 0)}
    verdict = ("HOLDS before 2020" if all(checks.values()) else "a 2020-26 phenomenon: " + ", ".join(k for k, v in checks.items() if not v))
    n_trials = N_BEFORE + 2
    L = [f"# IDX menu ML-8 - the cost-aware ML book before 2020 (price-only model, Yahoo survivors) - {date.today()} - 2 trials, cumulative N = {n_trials}", "",
         f"Price-only features ({len(PRICE_FEATS)}), walk-forward by year from 2005, flat cost 0.30 % + fees, LIQ = 60-day median value >= Rp 5 bn (adjusted). "
         f"Liquid names per day 2008-19: {oos['names_per_day']['mean']:.0f} (min {oos['names_per_day']['min']}, max {oos['names_per_day']['max']}).", "",
         "| window | book | trades | win | avg net | CAGR | Sharpe | mDD | years + | by year |", "|---|---|---|---|---|---|---|---|---|---|"]
    for label, res in (("2008-19", oos), ("2020-26 cache", bridge)):
        for k in ("base", "wait_up5"):
            r = res[k]
            L.append(f"| {label} | {k} | {r['trades']} | {r['win'] * 100:.0f} % | {r['avg'] * 100:+.2f} % | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | "
                     f"{r['years_pos']}/{r['n_years']} | " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items()) + " |")
        L.append(f"| {label} | random (same mechanics) | | | | {res['random_wait_up5']['cagr'] * 100:+.1f} % | {res['random_wait_up5']['sharpe']:.2f} | {res['random_wait_up5']['mdd'] * 100:.0f} % | | |")
        L.append(f"| {label} | JKSE | | | | {res['jkse']['cagr'] * 100:+.1f} % | {res['jkse']['sharpe']:.2f} | {res['jkse']['mdd'] * 100:.0f} % | | "
                 + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in res["jkse"]["by_year"].items()) + " |")
    L += ["", "For scale: the same construction on the deployed IDX data with the full feature set, 2022-26: base +29 % / 0.91 / -51 %, wait_up5 +36 % / 1.38 / -27 %.", "",
          "## Verdict (menu ML-8, study stored)", "", f"{verdict}. Checks: " + ", ".join(f"{k} {'ok' if v else 'FAIL'}" for k, v in checks.items()) + "."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_2008_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["base_2008_19", "wait_up5_2008_19"], "n_trials_cumulative": n_trials, "features": PRICE_FEATS,
                                                                   "cost": [HALF_SPREAD, FEE_BUY, FEE_SELL], "test_years": TEST_YEARS},
                              summary=common.plain({"oos": oos, "bridge": bridge, "checks": checks, "verdict": verdict}), names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
