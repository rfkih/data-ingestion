#!/usr/bin/env python3
"""Risk models beyond historical replay (operator 2026-09-26: "okay coba lakukan 1 - 6", item 5).

#381 replayed history on the deployed holdings. Three things history replay cannot show, declared before any result was seen
(audit, no trial):

  (a) REGIMES. A 2-state Gaussian hidden Markov model (Hamilton 1989; EM / Baum-Welch, fitted here in numpy) on COMPOSITE daily
      returns 2020-01 -> 2026-09. Each day gets the FILTERED probability of the high-volatility state (forward pass only, known
      at that close - no look-ahead). Read: the combined book and each sleeve (#348 NAVs) on days after a high-vol close
      (p >= 0.5) vs calm - mean, vol, Sharpe, 1-day 99 % VaR, share of days. Does the book behave like a different animal in
      stress, and would a regime switch have been known in time?
  (b) TAIL DEPENDENCE. Empirical lower-tail dependence lambda_L(q) = P(X < q_X and Y < q_Y) / q at q = 5 % and 10 % for the
      sleeve pairs and each sleeve vs COMPOSITE and IDXSMC-LIQ (small caps), next to (i) independence (= q) and (ii) a Gaussian
      copula with the same correlation. Empirical >> Gaussian = the sleeves crash together more than a correlation matrix says.
  (c) HYPOTHETICAL SCENARIOS, designed, not replayed: a two-factor shock on the deployed overnight holdings of every backtest
      day (#381's holdings): r_name = b_comp x F_comp + b_smc x F_smc, betas from 2022-26 daily returns on COMPOSITE and on the
      small-cap spread (IDXSMC-LIQ - COMPOSITE).
        S1 foreign exodus       F_comp -15 %, F_smc -10 %
        S2 small-cap unwind     F_comp  -5 %, F_smc -25 %   (the book's names are small caps; IHSG barely shows it)
        S3 2020 x 1.25          F_comp -47 %, F_smc -10 %
      Loss as % of that day's NAV: median, 95th percentile, worst.
READ-ONLY; one idx.study row (risk_models, kind audit).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "risk_models"
TRADES = os.path.join(ROOT, "research-scratch", "combo_live_combined.csv")
SCEN = {"S1_foreign_exodus": (-0.15, -0.10), "S2_smallcap_unwind": (-0.05, -0.25), "S3_2020x1.25": (-0.47, -0.10)}
QS = (0.05, 0.10)


# ---------------------------------------------------------------------------------------------------------------- HMM
def hmm_fit(x: np.ndarray, iters: int = 300, tol: float = 1e-8) -> dict:
    """2-state Gaussian HMM by EM. State 1 = the higher-variance state. -> params + filtered P(state 1) per day."""
    n = len(x)
    mu = np.array([x.mean(), x.mean()])
    sd = np.array([x.std() * 0.6, x.std() * 1.8])
    A = np.array([[0.98, 0.02], [0.05, 0.95]])
    pi = np.array([0.8, 0.2])
    ll_old = -np.inf
    for _ in range(iters):
        B = np.column_stack([stats.norm.pdf(x, mu[k], sd[k]) for k in (0, 1)]) + 1e-300
        al, c = np.zeros((n, 2)), np.zeros(n)
        al[0] = pi * B[0]
        c[0] = al[0].sum()
        al[0] /= c[0]
        for t in range(1, n):
            al[t] = (al[t - 1] @ A) * B[t]
            c[t] = al[t].sum()
            al[t] /= c[t]
        be = np.ones((n, 2))
        for t in range(n - 2, -1, -1):
            be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
        g = al * be
        g /= g.sum(1, keepdims=True)
        xi = np.zeros((2, 2))
        for t in range(n - 1):
            m = (al[t][:, None] * A) * (B[t + 1] * be[t + 1])[None, :] / c[t + 1]
            xi += m / m.sum()
        A = xi / xi.sum(1, keepdims=True)
        pi = g[0]
        mu = (g * x[:, None]).sum(0) / g.sum(0)
        sd = np.sqrt((g * (x[:, None] - mu) ** 2).sum(0) / g.sum(0))
        ll = np.log(c).sum()
        if abs(ll - ll_old) < tol:
            break
        ll_old = ll
    if sd[0] > sd[1]:                                           # state 1 = high volatility
        mu, sd, A, al, g = mu[::-1], sd[::-1], A[::-1, ::-1], al[:, ::-1], g[:, ::-1]
    return {"mu": mu, "sd": sd, "A": A, "filtered": al[:, 1], "smoothed": g[:, 1], "ll": float(ll)}


# ---------------------------------------------------------------------------------------------------------------- tails
def lambda_l(x: np.ndarray, y: np.ndarray, q: float) -> float:
    qx, qy = np.quantile(x, q), np.quantile(y, q)
    return float(((x <= qx) & (y <= qy)).mean() / q)


def gaussian_lambda(rho: float, q: float) -> float:
    z = stats.norm.ppf(q)
    return float(stats.multivariate_normal(mean=[0, 0], cov=[[1, rho], [rho, 1]]).cdf([z, z]) / q)


def seg_stats(r: pd.Series) -> dict:
    return {"days": int(len(r)), "mean_ann": float(r.mean() * 252), "vol_ann": float(r.std() * np.sqrt(252)),
            "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else None, "var99": float(-np.quantile(r, 0.01))}


def main() -> int:
    store = "--no-store" not in sys.argv
    dsn = AF.dsn()
    with psycopg.connect(dsn) as conn:
        summ = conn.execute("SELECT summary FROM idx.study WHERE id = 348").fetchone()[0]
        idx = pd.read_sql("SELECT trade_date, index_code, close FROM idx.index_daily WHERE index_code IN ('COMPOSITE', 'IDXSMC-LIQ') ORDER BY 1", conn)
        T = pd.read_csv(TRADES, parse_dates=["d_in", "d_out"])
        T = T[T["sleeve"] != "gap"]
        codes = sorted(T["code"].unique())
        px = pd.read_sql("SELECT code, trade_date, close * adj_factor AS c FROM idx.bar WHERE source = 'idx' AND code = ANY(%s) AND trade_date >= '2021-06-01'",
                         conn, params=(codes,))
    summ = json.loads(summ) if isinstance(summ, str) else summ
    I = idx.pivot(index="trade_date", columns="index_code", values="close").astype(float)  # noqa: E741
    I.index = pd.to_datetime(I.index)
    ir = I.pct_change().dropna()
    navs = {k: pd.Series({pd.Timestamp(d): v for d, v in summ[k]["nav"]}).sort_index() for k in ("combined", "gap_only", "trend_only", "ml_only")}
    R = pd.DataFrame({k: v.pct_change() for k, v in navs.items()}).dropna()
    # (a) regimes
    h = hmm_fit(ir["COMPOSITE"].to_numpy())
    p = pd.Series(h["filtered"], index=ir.index)
    hi_prev = (p.shift(1) >= 0.5).reindex(R.index).fillna(False)
    reg = {k: {"high_vol": seg_stats(R.loc[hi_prev, k]), "calm": seg_stats(R.loc[~hi_prev, k])} for k in R.columns}
    comp_reg = {"high_vol": seg_stats(ir["COMPOSITE"].reindex(R.index)[hi_prev]), "calm": seg_stats(ir["COMPOSITE"].reindex(R.index)[~hi_prev])}
    hmm = {"mu_ann": (h["mu"] * 252).tolist(), "vol_ann": (h["sd"] * np.sqrt(252)).tolist(), "stay_calm": float(h["A"][0, 0]),
           "stay_high": float(h["A"][1, 1]), "high_share_2020_26": float((p >= 0.5).mean()), "high_share_backtest": float(hi_prev.mean()),
           "exp_high_spell_days": float(1 / (1 - h["A"][1, 1]))}
    # (b) tails
    J = R.join(ir[["COMPOSITE", "IDXSMC-LIQ"]], how="inner")
    pairs = [("gap_only", "trend_only"), ("gap_only", "ml_only"), ("trend_only", "ml_only"), ("combined", "COMPOSITE"),
             ("combined", "IDXSMC-LIQ"), ("trend_only", "IDXSMC-LIQ"), ("ml_only", "IDXSMC-LIQ"), ("gap_only", "COMPOSITE")]
    tails = {}
    for a, b in pairs:
        x, y = J[a].to_numpy(), J[b].to_numpy()
        m = (x != 0) & (y != 0)                                  # a flat sleeve day (no position) is not a joint observation
        x, y = x[m], y[m]
        rho = float(stats.spearmanr(x, y).statistic)
        rho_g = 2 * np.sin(np.pi * rho / 6)                      # Spearman -> Gaussian-copula correlation
        tails[f"{a}~{b}"] = {"n": int(m.sum()), "spearman": rho, **{f"lambda_{int(q * 100)}": lambda_l(x, y, q) for q in QS},
                             **{f"gauss_{int(q * 100)}": gaussian_lambda(rho_g, q) for q in QS}}
    # (c) scenarios on the holdings
    P = px.pivot(index="trade_date", columns="code", values="c").astype(float)
    P.index = pd.to_datetime(P.index)
    pr = P.pct_change()
    f1 = ir["COMPOSITE"]
    f2 = ir["IDXSMC-LIQ"] - ir["COMPOSITE"]
    W = pr.index >= "2022-01-01"
    betas = {}
    for c in P.columns:
        y = pr.loc[W, c]
        X = pd.concat([f1, f2], axis=1).reindex(y.index)
        ok = y.notna() & X.notna().all(1) & (y != 0)
        if ok.sum() < 60:
            betas[c] = (1.0, 1.0)
            continue
        Xm = np.column_stack([np.ones(ok.sum()), X[ok].to_numpy()])
        b = np.linalg.lstsq(Xm, y[ok].to_numpy(), rcond=None)[0]
        betas[c] = (float(b[1]), float(b[2]))
    Pf = P.ffill()
    nav = navs["combined"]
    rows = []
    for d in nav.index:
        open_ = T[(T["d_in"] <= d) & (T["d_out"] > d)]
        out = {"d": d}
        for s, (fc, fs) in SCEN.items():
            loss = 0.0
            for x in open_.itertuples():
                a0, a1 = Pf[x.code].asof(x.d_in), Pf[x.code].asof(d)
                mv = float(x.cost) * (a1 / a0 if a0 and a0 > 0 and pd.notna(a1) else 1.0)
                bc, bs = betas.get(x.code, (1.0, 1.0))
                loss += mv * max(-1.0, bc * fc + bs * fs)
            out[s] = loss / float(nav[d])
        rows.append(out)
    D = pd.DataFrame(rows).set_index("d")
    scen = {s: {"median": float(D[s].median()), "p05": float(D[s].quantile(0.05)), "worst": float(D[s].min()),
                "worst_date": str(D[s].idxmin().date())} for s in SCEN}
    bsum = pd.DataFrame(betas, index=["b_comp", "b_smc"]).T
    res = {"hmm": hmm, "by_regime": reg, "composite_by_regime": comp_reg, "tails": tails, "scenarios": scen,
           "betas_median": {"comp": float(bsum["b_comp"].median()), "smc": float(bsum["b_smc"].median())}}
    f = lambda v: f"{v * 100:+.1f} %"  # noqa: E731
    L = [f"# Risk models beyond replay - {date.today()}", "",
         "Audit, no trial. Book = the deployed combined configuration (#348 NAVs and trade list).", "",
         "## (a) Regimes: 2-state HMM on COMPOSITE daily returns 2020-01 -> 2026-09 (filtered, no look-ahead)", "",
         f"Calm state: {h['mu'][0] * 252 * 100:+.0f} %/yr, vol {h['sd'][0] * np.sqrt(252) * 100:.0f} %. High-vol state: {h['mu'][1] * 252 * 100:+.0f} %/yr, "
         f"vol {h['sd'][1] * np.sqrt(252) * 100:.0f} %. Persistence: calm {h['A'][0, 0]:.3f}, high {h['A'][1, 1]:.3f} "
         f"(a high-vol spell lasts ~{hmm['exp_high_spell_days']:.0f} sessions). High-vol share: 2020-26 {hmm['high_share_2020_26'] * 100:.0f} %, "
         f"backtest window {hmm['high_share_backtest'] * 100:.0f} %.", "",
         "| series | regime (previous close) | days | mean /yr | vol /yr | Sharpe | 1-day VaR 99 % |", "|---|---|---|---|---|---|---|"]
    for k in (*R.columns, "COMPOSITE"):
        rr = reg[k] if k in reg else comp_reg
        for g in ("calm", "high_vol"):
            v = rr[g]
            L.append(f"| {k} | {g} | {v['days']} | {f(v['mean_ann'])} | {v['vol_ann'] * 100:.1f} % | {v['sharpe'] if v['sharpe'] is None else round(v['sharpe'], 2)} | {v['var99'] * 100:.2f} % |")
    L += ["", "## (b) Lower-tail dependence (days both series moved)", "",
          "| pair | n | Spearman | lambda 5 % | Gaussian 5 % | lambda 10 % | Gaussian 10 % |", "|---|---|---|---|---|---|---|"]
    for k, v in tails.items():
        L.append(f"| {k} | {v['n']} | {v['spearman']:+.2f} | {v['lambda_5']:.2f} | {v['gauss_5']:.2f} | {v['lambda_10']:.2f} | {v['gauss_10']:.2f} |")
    L += ["", "Independence would give lambda = q (0.05 / 0.10). Empirical well above the Gaussian column = crashes arrive together",
          "more often than the correlation implies.", "",
          "## (c) Designed two-factor scenarios on the deployed overnight holdings (loss % of that day's NAV)", "",
          f"Betas 2022-26 (median over held names): COMPOSITE {res['betas_median']['comp']:.2f}, small-cap spread {res['betas_median']['smc']:.2f}.", "",
          "| scenario | F COMPOSITE | F small-cap spread | median day | 95th pct day | worst | worst date |", "|---|---|---|---|---|---|---|"]
    for s, (fc, fs) in SCEN.items():
        v = scen[s]
        L.append(f"| {s} | {fc * 100:+.0f} % | {fs * 100:+.0f} % | {f(v['median'])} | {f(v['p05'])} | {f(v['worst'])} | {v['worst_date']} |")
    L += ["", "Limits: #348 NAVs predate the 2026-09-26 look-ahead fix of the gap-fade eligibility (the gap sleeve is intraday and",
          "flat overnight, so (c) is unaffected; (a)/(b) gap rows slightly flatter the sleeve); one HMM on six years with one crash;",
          "linear betas understate a crash's convexity; no exits during a scenario."]
    text = "\n".join(L)
    print(text)
    out = os.path.join(HERE, f"IDX_RISK_MODELS_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": [], "kind": "audit", "scenarios": SCEN, "qs": list(QS), "sources": [348, 381]},
                                  summary=common.plain(res), names=[], report_path=out, note="HMM regimes, tail dependence, designed two-factor scenarios; no trial")
            conn.commit()
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
