#!/usr/bin/env python3
"""Is the combined book's return ALPHA or small-cap BETA? (operator 2026-09-26 "okay do all", evidence item 4)

Declared before any result was seen; audit, no trial. Daily returns of the deployed book (#386 combined NAV) and of each sleeve
alone, 2022-01 -> 2026-09-16, regressed on:
  M1  COMPOSITE (IHSG)                                    - the market
  M2  COMPOSITE + small-cap spread (IDXSMC-LIQ - COMPOSITE) - the book trades small caps; is that all it is?
  M3  M2 + a momentum factor: the equal-weight daily return of the top-decile minus bottom-decile liquid names by their 120-day
      return up to the previous close (built here from idx.bar, adjusted closes; liquid = 60-day median value >= Rp 5 bn)
Newey-West (HAC, 5 lags) standard errors on the intercept. Alpha is annualised x 252. READ: an intercept that survives M3 with
t >= 2 is return the market, small caps and momentum do not explain. Same regressions on live returns monthly once they exist.
READ-ONLY; one idx.study row (factor_attribution, kind audit).
"""
from __future__ import annotations

import json
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
import idx_alloc_frontier as AF  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "factor_attribution"
REF = 386
LAGS = 5


def ols_nw(y: np.ndarray, X: np.ndarray, lags: int = LAGS) -> tuple[np.ndarray, np.ndarray, float]:
    """OLS with a constant; Newey-West standard errors. -> (coefs, se, R2); coef[0] = intercept."""
    X = np.column_stack([np.ones(len(y)), X])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    n = len(y)
    XtX_inv = np.linalg.inv(X.T @ X)
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (G + G.T)
    V = XtX_inv @ S @ XtX_inv
    r2 = 1 - (e @ e) / (((y - y.mean()) ** 2).sum())
    return b, np.sqrt(np.diag(V)) * np.sqrt(n / (n - X.shape[1])), float(r2)


def main() -> int:
    store = "--no-store" not in sys.argv
    dsn = AF.dsn()
    with psycopg.connect(dsn) as conn:
        summ = conn.execute("SELECT summary FROM idx.study WHERE id = %s", (REF,)).fetchone()[0]
        idx = pd.read_sql("SELECT trade_date, index_code, close FROM idx.index_daily WHERE index_code IN ('COMPOSITE', 'IDXSMC-LIQ') ORDER BY 1", conn)
        bars = pd.read_sql("""SELECT b.code, b.trade_date, b.close * b.adj_factor AS ac, s.value FROM idx.bar b JOIN idx.daily_summary s USING (code, trade_date)
                              WHERE b.source = 'idx' AND b.trade_date >= '2021-03-01'""", conn)
    summ = json.loads(summ) if isinstance(summ, str) else summ
    navs = {k: pd.Series({pd.Timestamp(d): v for d, v in summ[k]["nav"]}).sort_index() for k in ("combined", "gap_only", "trend_only", "ml_only")}
    R = pd.DataFrame({k: v.pct_change() for k, v in navs.items()}).dropna()
    I = idx.pivot(index="trade_date", columns="index_code", values="close").astype(float)  # noqa: E741
    I.index = pd.to_datetime(I.index)
    ir = I.pct_change()
    for c in ("ac", "value"):
        bars[c] = pd.to_numeric(bars[c], errors="coerce")
    P = bars.pivot(index="trade_date", columns="code", values="ac").sort_index()
    V = bars.pivot(index="trade_date", columns="code", values="value").sort_index()
    P.index = pd.to_datetime(P.index)
    V.index = P.index
    ret = P.pct_change()
    liq = V.rolling(60, min_periods=40).median().shift(1) >= 5e9
    mom = (P.shift(1) / P.shift(121) - 1).where(liq)
    q_hi, q_lo = mom.quantile(0.9, axis=1), mom.quantile(0.1, axis=1)
    umd = ret.where(mom.ge(q_hi, axis=0)).mean(axis=1) - ret.where(mom.le(q_lo, axis=0)).mean(axis=1)
    F = pd.DataFrame({"mkt": ir["COMPOSITE"], "smc": ir["IDXSMC-LIQ"] - ir["COMPOSITE"], "umd": umd}).reindex(R.index)
    ok = F.notna().all(axis=1)
    R, F = R[ok], F[ok]
    models = {"M1": ["mkt"], "M2": ["mkt", "smc"], "M3": ["mkt", "smc", "umd"]}
    res: dict = {"n": int(len(R)), "from": str(R.index[0].date()), "to": str(R.index[-1].date()), "series": {}}
    for s in R.columns:
        y = R[s].to_numpy()
        res["series"][s] = {"raw_ann": float(y.mean() * 252)}
        for m, cols in models.items():
            b, se, r2 = ols_nw(y, F[cols].to_numpy())
            res["series"][s][m] = {"alpha_ann": float(b[0] * 252), "alpha_t": float(b[0] / se[0]), "r2": r2,
                                   **{f"beta_{c}": float(b[i + 1]) for i, c in enumerate(cols)},
                                   **{f"t_{c}": float(b[i + 1] / se[i + 1]) for i, c in enumerate(cols)}}
    L = [f"# Alpha or small-cap beta? Factor attribution of the combined book (#{REF}) - {date.today()}", "",
         f"Daily returns {res['from']} -> {res['to']} ({res['n']} sessions). Factors: COMPOSITE, small-cap spread (IDXSMC-LIQ - COMPOSITE),",
         "momentum (top-minus-bottom decile of liquid names by 120-day return). Newey-West (5 lags). Alpha annualised (x 252, arithmetic). Audit, no trial.", "",
         "| series | raw mean /yr | M1 alpha /yr (t) | M2 alpha /yr (t) | M3 alpha /yr (t) | beta mkt | beta small-cap | beta momentum | R2 (M3) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for s, v in res["series"].items():
        m3 = v["M3"]
        L.append(f"| {s} | {v['raw_ann'] * 100:+.1f} % | {v['M1']['alpha_ann'] * 100:+.1f} % ({v['M1']['alpha_t']:.2f}) | "
                 f"{v['M2']['alpha_ann'] * 100:+.1f} % ({v['M2']['alpha_t']:.2f}) | {m3['alpha_ann'] * 100:+.1f} % ({m3['alpha_t']:.2f}) | "
                 f"{m3['beta_mkt']:.2f} | {m3['beta_smc']:.2f} | {m3['beta_umd']:.2f} | {m3['r2']:.2f} |")
    c3 = res["series"]["combined"]["M3"]
    L += ["", f"Reading: the combined book keeps {c3['alpha_ann'] * 100:+.1f} %/yr of alpha (t {c3['alpha_t']:.2f}) after the market, small caps and",
          f"momentum, which explain R2 = {c3['r2']:.2f} of its daily variance. " +
          ("The return is NOT mainly factor beta." if c3["alpha_t"] >= 2 else "The intercept is not distinguishable from zero after the factors."),
          "", "Limits: in-sample 2022-26 like everything else (this separates alpha from beta, it does not prove persistence); arithmetic",
          "alpha differs from the geometric CAGR; the momentum factor is equal-weight and gross of costs; no value or liquidity factor."]
    text = "\n".join(L)
    print(text)
    out = os.path.join(HERE, f"IDX_FACTOR_ATTRIBUTION_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": [], "kind": "audit", "ref": REF, "lags": LAGS, "sources": [REF]},
                                  summary=common.plain(res), names=[], report_path=out, note="factor attribution of #386; no trial")
            conn.commit()
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
