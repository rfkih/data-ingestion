#!/usr/bin/env python3
"""Phase 1 - how overfit is the way we CHOSE the combined book? (operator 2026-09-26: "oke jalankan fase 1")

Not a strategy search: no arm here can be deployed, the live book is frozen (Phase 0). The question is how much of the
deployed book's backtest (#348: 50.6 %/yr, Sharpe 2.21, mDD -17.1 %) is the product of choosing its construction on the same
2022-26 data it is judged on.

Declared before any result was seen (2026-09-26):
  GRID   every construction choice the desk actually made on this data, crossed (144 configurations):
         ML confirmation  single +5/10 | ens4 (#175)            ML stop   none | -5 % | -10 % same close (#281/#288)
         cash floor       0 | 0.30 (#177)                       gap size  5 | 10 | 20 % NAV (#167)
         trend size       2.5 | 5 % NAV                         ML size   5 | 10 % NAV (sizing check 2026-09-26)
         Signal rules (gap-fade threshold, trend 60/MA200/1.5x/trail10, the ML model) are held fixed: they were ALSO
         chosen in-sample, so every number here is an upper bound on what the construction layer is worth.
  ANCHOR the deployed configuration (ens4, stop 5, floor 0.30, 10/5/10) must reproduce #348 before anything else is read.
  TESTS  (1) CSCV probability of backtest overfitting (Bailey, Borwein, Lopez de Prado, Zhu 2016): 16 time blocks, all
             12,870 half/half splits, best in-sample Sharpe -> its out-of-sample rank; PBO = share with logit <= 0.
         (2) Deflated Sharpe of the deployed configuration for N = 144 (this grid) and N = 1,007 (the desk's ledger).
         (3) Nested walk-forward of the SELECTION PROCESS: at each half-year from 2023-01 the rule picks a configuration
             using only data before the fold, and holds it through the fold. Two rules: max Sharpe; max CAGR with
             mDD >= -25 %. The fold returns are the chosen configuration's daily returns from its full run (the book's
             state at the fold start is that configuration's; a real switch would carry the previous book's positions).
  READ   the selection haircut = deployed configuration's CAGR over the walk-forward window minus the selection process's.
         PBO > 0.5 = the choice is more likely than not to be below median out of sample.
READ-ONLY; one idx.study row (phase1_selection, kind audit - no trial is added: nothing here can be deployed).
Run: IDX_ML_CACHE=tmp/ml_strategy_cache.pkl IDX_BOARD_MODE=pit IDX_EXIT_CACHE=tmp/exit_cache_pit.pkl python research/idx_phase1_selection.py
"""
from __future__ import annotations

import itertools
import os
import pickle
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
import idx_combo_rupiah as CR  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_ens4_exits as X  # noqa: E402
import idx_ml_stop_sameclose as SC  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "phase1_selection"
CACHE = os.path.join(ROOT, "research-scratch", "phase1_navs.pkl")
N_LEDGER = 1007
SD_LEDGER = 0.78
GRID = {"confirm": ["single", "ens4"], "stop": [None, 0.05, 0.10], "floor": [0.0, 0.30],
        "gap": [0.05, 0.10, 0.20], "trend": [0.025, 0.05], "ml": [0.05, 0.10]}
DEPLOYED = {"confirm": "ens4", "stop": 0.05, "floor": 0.30, "gap": 0.10, "trend": 0.05, "ml": 0.10}
ANCHOR = {"cagr": 0.506, "sharpe": 2.21, "mdd": -0.171}
BLOCKS = 16
FOLDS = [pd.Timestamp(x) for x in ("2023-01-01", "2023-07-01", "2024-01-01", "2024-07-01", "2025-01-01", "2025-07-01", "2026-01-01")]
MDD_CAP = -0.25


def name(c: dict) -> str:
    st = "none" if c["stop"] is None else f"{c['stop'] * 100:g}"
    return f"{c['confirm']}|stop{st}|floor{c['floor'] * 100:g}|g{c['gap'] * 100:g}/t{c['trend'] * 100:g}/m{c['ml'] * 100:g}"


def configs() -> list[dict]:
    keys = list(GRID)
    return [dict(zip(keys, v, strict=True)) for v in itertools.product(*(GRID[k] for k in keys))]


def sharpe(r: np.ndarray) -> float:
    s = r.std()
    return float(r.mean() / s * np.sqrt(252)) if s > 0 else 0.0


PPY = 252.0                        # sessions per calendar year of the data, set in main() (#348 annualises CAGR by calendar time)


def cagr(r: np.ndarray) -> float:
    return float(np.prod(1 + r) ** (PPY / len(r)) - 1) if len(r) else 0.0


def mdd(r: np.ndarray) -> float:
    eq = np.cumprod(1 + r)
    return float((eq / np.maximum.accumulate(eq) - 1).min()) if len(r) else 0.0


# ------------------------------------------------------------------------------------------------------------ build NAVs
def build() -> pd.DataFrame:
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
    del P
    tr = CR.trend_trades(dsn, dates)
    gap = CR.gap_events(dsn, dates)
    ml: dict[tuple[int, float | None], list] = {}
    for stop in GRID["stop"]:
        for i, rule in enumerate(X.ENS4, start=1):
            _, log = SC.book_same(A, liq, e5, X.K, c_in, c_out, X.MARGIN, wait=rule, stop=1.0 if stop is None else stop, t_start=t0)
            ml[(i, stop)] = [{"strat": f"ML{i}", "code": codes[r.j], "t_in": int(r.t_in), "t_out": int(r.t_out), "why": r.why}
                             for r in log.itertuples()]
    M.log(f"events: trend {len(tr)}, gap {len(gap)}, ML sets {len(ml)}")
    navs = {}
    for k, c in enumerate(configs()):
        rules = [1, 2, 3, 4] if c["confirm"] == "ens4" else [1]
        ev = [x for i in rules for x in ml[(i, c["stop"])]]
        pct = {"gap": c["gap"], "trend": c["trend"], **{f"ML{i}": (c["ml"] / len(rules) if i in rules else 0.0) for i in range(1, 5)}}
        nav, _ = AF.engine(dates, codes, A, raw, offer, bid, ev, tr, gap, pct, cash_floor=c["floor"])
        navs[name(c)] = pd.Series(nav, index=dates)
        if k % 12 == 0:
            M.log(f"{k + 1}/144 {name(c)}")
    df = pd.DataFrame(navs).dropna(how="all")
    df = df[df.index >= CR.START].dropna()
    df.to_pickle(CACHE)
    return df


# ------------------------------------------------------------------------------------------------------------ tests
def cscv(R: np.ndarray, blocks: int = BLOCKS) -> dict:
    """R: T x N daily returns. -> PBO, the logits, and IS-vs-OOS Sharpe of the chosen configuration per split."""
    T, N = R.shape
    edges = np.linspace(0, T, blocks + 1).astype(int)
    s1 = np.array([R[a:b].sum(0) for a, b in zip(edges[:-1], edges[1:], strict=True)])
    s2 = np.array([(R[a:b] ** 2).sum(0) for a, b in zip(edges[:-1], edges[1:], strict=True)])
    n = np.diff(edges)
    lam, is_sr, oos_sr = [], [], []
    for comb in itertools.combinations(range(blocks), blocks // 2):
        m = np.zeros(blocks, bool)
        m[list(comb)] = True

        def sr(mask):
            k = n[mask].sum()
            mu = s1[mask].sum(0) / k
            var = s2[mask].sum(0) / k - mu ** 2
            return mu / np.sqrt(np.maximum(var, 1e-18)) * np.sqrt(252)
        a, b = sr(m), sr(~m)
        best = int(np.argmax(a))
        rank = stats.rankdata(b)[best]                         # 1 = worst .. N = best
        w = rank / (N + 1)
        lam.append(np.log(w / (1 - w)))
        is_sr.append(a[best])
        oos_sr.append(b[best])
    lam = np.array(lam)
    slope = float(np.polyfit(is_sr, oos_sr, 1)[0])
    return {"pbo": float((lam <= 0).mean()), "logit_median": float(np.median(lam)), "splits": len(lam),
            "is_sr_mean": float(np.mean(is_sr)), "oos_sr_mean": float(np.mean(oos_sr)), "degradation_slope": slope,
            "oos_below_zero": float((np.array(oos_sr) < 0).mean())}


def dsr(r: np.ndarray, sr_all: np.ndarray | None, n_trials: int, sd_annual: float | None = None) -> dict:
    """Deflated Sharpe (Bailey & Lopez de Prado 2014), per-period Sharpe; the variance of the trial Sharpes from the grid, or
    ``sd_annual`` = an assumed cross-trial standard deviation of the annual Sharpe (the ledger's families are not in this grid)."""
    T = len(r)
    sr = r.mean() / r.std()
    var_sr = (sd_annual / np.sqrt(252)) ** 2 if sd_annual is not None else np.var(sr_all / np.sqrt(252), ddof=1)
    emc = 0.5772156649
    sr0 = np.sqrt(var_sr) * ((1 - emc) * stats.norm.ppf(1 - 1 / n_trials) + emc * stats.norm.ppf(1 - 1 / (n_trials * np.e)))
    sk, ku = stats.skew(r), stats.kurtosis(r, fisher=False)
    z = (sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)
    return {"n": n_trials, "sr_annual": float(sr * np.sqrt(252)), "sr0_annual": float(sr0 * np.sqrt(252)), "dsr": float(stats.norm.cdf(z))}


def walk_forward(R: pd.DataFrame, rule: str) -> dict:
    ends = FOLDS[1:] + [R.index[-1] + pd.Timedelta(days=1)]
    parts, picks = [], []
    for a, b in zip(FOLDS, ends, strict=True):
        IS, OOS = R[R.index < a], R[(R.index >= a) & (R.index < b)]
        if rule == "max_sharpe":
            score = IS.apply(lambda s: sharpe(s.to_numpy()))
        else:
            ok = IS.apply(lambda s: mdd(s.to_numpy()) >= MDD_CAP)
            score = IS.apply(lambda s: cagr(s.to_numpy())).where(ok, -np.inf)
        best = score.idxmax()
        picks.append({"fold": str(a.date()), "pick": best, "is_score": float(score[best]),
                      "oos_cagr": cagr(OOS[best].to_numpy()), "oos_rank": int(OOS.apply(lambda s: cagr(s.to_numpy())).rank(ascending=False)[best])})
        parts.append(OOS[best])
    r = pd.concat(parts).to_numpy()
    return {"rule": rule, "cagr": cagr(r), "sharpe": sharpe(r), "mdd": mdd(r), "picks": picks}


def window_stats(r: np.ndarray) -> dict:
    return {"cagr": cagr(r), "sharpe": sharpe(r), "mdd": mdd(r)}


def main() -> int:
    store = "--no-store" not in sys.argv
    df = pd.read_pickle(CACHE) if os.path.exists(CACHE) and "--rebuild" not in sys.argv else build()
    global PPY
    PPY = (len(df) - 1) / ((df.index[-1] - df.index[0]).days / 365.25)
    R = df.pct_change().dropna()
    dep = name(DEPLOYED)
    full = window_stats(R[dep].to_numpy())
    M.log(f"anchor {dep}: CAGR {full['cagr'] * 100:.1f} % Sharpe {full['sharpe']:.2f} mDD {full['mdd'] * 100:.1f} % (#348: 50.6 / 2.21 / -17.1)")
    if abs(full["cagr"] - ANCHOR["cagr"]) > 0.01 or abs(full["sharpe"] - ANCHOR["sharpe"]) > 0.03:
        M.log("ANCHOR FAILED - the grid does not reproduce #348; stopping")
        return 1
    all_stats = pd.DataFrame({c: window_stats(R[c].to_numpy()) for c in R.columns}).T
    rank_dep = int(all_stats["sharpe"].rank(ascending=False)[dep])
    pb = cscv(R.to_numpy())
    srs = all_stats["sharpe"].to_numpy()
    d144, dled = dsr(R[dep].to_numpy(), srs, len(srs)), dsr(R[dep].to_numpy(), srs, N_LEDGER)
    # the ledger's own spread: sd of 6,406 arm-level Sharpes stored in idx.study summaries (170 studies) = 0.78 (2026-09-26);
    # trials are correlated, so the EFFECTIVE number of independent trials is below 1,007 - read the rows as a range
    dsens = {(n, sd): dsr(R[dep].to_numpy(), None, n, sd_annual=sd) for sd in (0.5, SD_LEDGER, 1.0) for n in (100, 300, N_LEDGER)}
    wf = {k: walk_forward(R, k) for k in ("max_sharpe", "max_cagr_mdd25")}
    W = R[R.index >= FOLDS[0]]
    dep_w = window_stats(W[dep].to_numpy())
    med_w = {k: float(np.median([window_stats(W[c].to_numpy())[k] for c in W.columns])) for k in ("cagr", "sharpe", "mdd")}
    ew_w = window_stats(W.mean(axis=1).to_numpy())
    ex25 = W[W.index.year != 2025]
    dep_ex, med_ex = cagr(ex25[dep].to_numpy()), float(np.median([cagr(ex25[c].to_numpy()) for c in ex25.columns]))
    res = {"anchor": full, "deployed_rank_sharpe": rank_dep, "n_configs": len(srs), "cscv": pb, "dsr_144": d144, "dsr_ledger": dled, "dsr_sensitivity": {f"n{k[0]}_sd{k[1]}": v for k, v in dsens.items()},
           "walk_forward": wf, "window": {"from": str(FOLDS[0].date()), "deployed": dep_w, "median_config": med_w, "equal_weight_all": ew_w,
                                          "deployed_ex2025_cagr": dep_ex, "median_ex2025_cagr": med_ex},
           "grid_cagr_range": [float(all_stats["cagr"].min()), float(all_stats["cagr"].max())],
           "grid_sharpe_range": [float(srs.min()), float(srs.max())]}
    for k, v in wf.items():
        M.log(f"WF {k}: CAGR {v['cagr'] * 100:.1f} % Sharpe {v['sharpe']:.2f} mDD {v['mdd'] * 100:.1f} % | deployed same window {dep_w['cagr'] * 100:.1f} %")
    M.log(f"PBO {pb['pbo']:.2f}  DSR@144 {d144['dsr']:.2f}  DSR@{N_LEDGER} {dled['dsr']:.2f}  deployed Sharpe rank {rank_dep}/{len(srs)}")
    L = [f"# Phase 1 - how overfit is the choice of the combined book? - {date.today()}", "",
         "Audit, not a trial (nothing here can be deployed; the live book is frozen). Grid = every construction choice the desk made on",
         f"2022-26: ML confirm x stop x cash floor x gap/trend/ML size = {len(srs)} configurations on the #348 engine. Signal rules held fixed,",
         "so every number is an UPPER bound on what the construction layer is worth.", "",
         f"Anchor: deployed `{dep}` = CAGR {full['cagr'] * 100:.1f} %, Sharpe {full['sharpe']:.2f}, mDD {full['mdd'] * 100:.1f} % "
         f"(#348 50.6 / 2.21 / -17.1) - reproduced. It ranks **{rank_dep} of {len(srs)}** by Sharpe.", "",
         f"Grid spread: CAGR {res['grid_cagr_range'][0] * 100:.1f} .. {res['grid_cagr_range'][1] * 100:.1f} %, Sharpe {srs.min():.2f} .. {srs.max():.2f}.", "",
         "## 1. Probability of backtest overfitting (CSCV, 16 blocks, 12,870 splits)", "",
         "| PBO | median logit | IS Sharpe of the pick | its OOS Sharpe | IS->OOS slope | OOS Sharpe < 0 |", "|---|---|---|---|---|---|",
         f"| **{pb['pbo']:.2f}** | {pb['logit_median']:+.2f} | {pb['is_sr_mean']:.2f} | {pb['oos_sr_mean']:.2f} | {pb['degradation_slope']:+.2f} | {pb['oos_below_zero'] * 100:.0f} % |", "",
         "## 2. Deflated Sharpe of the deployed configuration", "",
         "| trials N | Sharpe | expected max Sharpe of N noise trials | DSR |", "|---|---|---|---|",
         f"| {d144['n']} (this grid) | {d144['sr_annual']:.2f} | {d144['sr0_annual']:.2f} | **{d144['dsr']:.2f}** |",
         f"| {dled['n']} (desk ledger) | {dled['sr_annual']:.2f} | {dled['sr0_annual']:.2f} | **{dled['dsr']:.2f}** |", "",
         "These two rows are NOT reassuring: the 144 configurations are near-copies of one book (Sharpe sd across the grid ~0.2), so the",
         "expected best of N is low. The desk's 1,007 trials were mostly OTHER families with a much wider Sharpe spread. Sensitivity with",
         f"a cross-trial Sharpe sd (annual); the ledger's MEASURED spread is {SD_LEDGER} (6,406 arm Sharpes in 170 stored studies).",
         "Trials are correlated, so the effective N is below 1,007:", "",
         "| effective N | Sharpe sd | expected max Sharpe of N noise trials | DSR |", "|---|---|---|---|",
         *[f"| {n} | {sd} | {v['sr0_annual']:.2f} | **{v['dsr']:.2f}** |" for (n, sd), v in dsens.items()], "",
         f"## 3. Nested walk-forward of the selection process ({FOLDS[0].date()} -> end, half-year folds)", "",
         "| | CAGR | Sharpe | mDD |", "|---|---|---|---|"]
    for k, v in wf.items():
        L.append(f"| selection rule `{k}` (out of sample) | {v['cagr'] * 100:.1f} % | {v['sharpe']:.2f} | {v['mdd'] * 100:.1f} % |")
    L += [f"| deployed configuration (chosen with hindsight) | {dep_w['cagr'] * 100:.1f} % | {dep_w['sharpe']:.2f} | {dep_w['mdd'] * 100:.1f} % |",
          f"| median configuration of the grid | {med_w['cagr'] * 100:.1f} % | {med_w['sharpe']:.2f} | {med_w['mdd'] * 100:.1f} % |",
          f"| equal weight of all {len(srs)} (no choice at all) | {ew_w['cagr'] * 100:.1f} % | {ew_w['sharpe']:.2f} | {ew_w['mdd'] * 100:.1f} % |", "",
          f"Without 2025 (same window): deployed {dep_ex * 100:.1f} %/yr, median configuration {med_ex * 100:.1f} %/yr.", ""]
    for k, v in wf.items():
        L += [f"Picks, `{k}`:", "", "| fold | picked | OOS CAGR | OOS rank of 144 |", "|---|---|---|---|"]
        L += [f"| {p['fold']} | `{p['pick']}` | {p['oos_cagr'] * 100:+.1f} % | {p['oos_rank']} |" for p in v["picks"]]
        L.append("")
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_PHASE1_SELECTION_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    if store:
        with psycopg.connect(AF.dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(),
                                  params={"trials": [], "kind": "audit", "grid": GRID, "deployed": DEPLOYED, "blocks": BLOCKS,
                                          "folds": [str(f.date()) for f in FOLDS], "mdd_cap": MDD_CAP, "n_ledger": N_LEDGER, "sources": [348]},
                                  summary=common.plain(res), names=[], report_path=out,
                                  note="Phase 1 audit: PBO / deflated Sharpe / nested walk-forward of the combo construction choices; no trial")
            conn.commit()
        M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
