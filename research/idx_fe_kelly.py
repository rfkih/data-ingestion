#!/usr/bin/env python3
"""IDX menu FE-3 - how much capital per strategy: Bayesian shrinkage + fractional Kelly, head to head with RL-1 (2026-09-26).

WORLD. The four daily sleeve streams RL-1 built on the corrected engine (#192) in the same run (research/idx_rl_alloc_run.py
dumps them to tmp/rl_streams_<date>.pkl): gap (20 %/event), trend (10 %/trade), ML (10 %/trade, cost-aware + confirmation),
value (strict composite, annual May). RL-1's weekly blocks, turnover cost (0.30 % x turnover), stats() and baselines are
imported from that file, so every row below is a same-run pair.

1. SHRINKAGE (the posterior expected return of each sleeve; pre-registered here, before any result was seen).
   Likelihood: the sleeve's annualised mean daily return mu_hat ~ N(mu, se_eff^2), se^2 = sigma_ann^2 / T_years, inflated by
   three evidence-quality factors:
     k_ep   = max(1, T_years / T_eff); T_eff = 1 / sum_y p_y^2, p_y = the share of the sleeve's ACTIVE days (non-zero return)
              that fall in calendar year y (Herfindahl effective number of years: gap-fade, 93 % of events in 2025-26, is
              ~2 independent years, not 4.7)
     k_dsr  = 1 / max(DSR, 0.25); DSR = deflated Sharpe (Bailey / Lopez de Prado, the desk's idx_foreign_gate formula) of the
              daily stream at the cumulative trial count N = 967
     k_plc  = 1 if the sleeve's placebo percentile in its own study >= 95, else 2 (ledger: gap 100 #86/#89, trend 99 #63,
              ML 100 ML-6g, value 100 #66)
   Prior: mu ~ N(0, tau^2) - centred on NO edge, because every sleeve is the survivor of a search (a grand-mean prior would
   inherit that selection bias). tau^2 by empirical Bayes (method of moments across the four sleeves):
   tau^2 = max(0.05^2, mean_s(mu_hat_s^2 - se_eff_s^2)). Posterior mean = (1 - B_s) mu_hat_s, B_s = se_eff^2 / (se_eff^2 + tau^2).
   Reported per sleeve on the full stream (2022-01 -> engine end) as the desk's PLANNING NUMBERS; the haircut B_s is scale-free,
   so it is also applied to the deployed-size sleeve-alone CAGRs of #192 (gap 12.8 %, trend 12.7 %, ML ens4 9.8 %) and value #66.
   A grand-mean (EB) prior is printed as a sensitivity column (not a trial).

2. FRACTIONAL KELLY (walk-forward, same test years as RL-1: 2024, 2025, 2026 stitched; each year's weights fitted ONLY on weeks
   before Jan 1 of that year, from 2022-01).
   Weekly sleeve returns (compounded daily blocks). Covariance: Ledoit-Wolf (2004) shrinkage of the sample covariance toward
   the scaled identity. Means: unshrunk = sample weekly mean; shrunk = (1 - B_s) x sample mean with B_s from step 1 recomputed
   on the training window only. Kelly: w* = argmax mu'w - 1/2 w'Sigma w, w >= 0 (long-only, coordinate descent). Fraction
   f in {1, 1/2, 1/4}: w = f w*. CASH-FLOOR CAP: the combo's 30 % floor -> sum(w) <= 0.70 (scaled down proportionally when
   above); the rest is cash at 0 %. Weights are held for the test year (daily re-set to target, as RL-1's templates);
   0.30 % x turnover when the weights change at a year boundary (the first span starts free, as in RL-1).
   PRE-REGISTERED: 6 trials = {full, half, quarter} x {shrunk, unshrunk}. Cumulative N_BEFORE = 960; RL-1 = trial 961 (its own
   row), these six = 962..967.
   Baselines (not trials), identical to RL-1 on the same stitched window: FIXED_EQ, REGIME, WF_BEST, RANDOM (200 draws, rng 7);
   plus the DEPLOYED combo (gap 10 / trend 5 / ML ens4 5 % per trade, 20 slots, 30 % floor, #192 engine d) on the same days.
   READING RULE (RL-1's): an arm is BETTER if its stitched Sharpe >= the best of {FIXED_EQ, REGIME, WF_BEST} + 0.15, its CAGR >=
   0.85 x that baseline's, its mDD no more than 2 pp deeper, and its Sharpe >= the 95th percentile of RANDOM (the per-seed check
   of RL-1 does not apply: Kelly is deterministic). The deployed combo is reported beside it, not part of the rule.
READ-ONLY; one idx.study row ('fe_kelly_rl'). INGEST_DB_DSN, IDX_BOARD_MODE=pit, IDX_EXIT_CACHE=tmp/exit_cache_pit.pkl, IDX_ML_CACHE.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import sys
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_rl_alloc_run as RL  # noqa: E402  (same streams, weekly world, stats, run_policy)

import idx_combo_rupiah as CR  # noqa: E402
import idx_construction as K  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "fe_kelly_rl"
N_BEFORE, N_RL = 960, 961
N_AT = 967
FRACS = {"full": 1.0, "half": 0.5, "quarter": 0.25}
ARMS = [f"{f}_{m}" for m in ("shrunk", "unshrunk") for f in FRACS]
CAP = 0.70
TAU_FLOOR = 0.05
DSR_FLOOR = 0.25
PLACEBO = {"gap": (100, "#86/#89"), "trend": (99, "#63"), "ML": (100, "ML-6g"), "value": (100, "#66")}
DEPLOYED_ALONE = {"gap": (0.128, "#192 gap alone"), "trend": (0.127, "#192 trend alone (d)"), "ML": (0.098, "#192 ML ens4 alone"),
                  "value": (0.218, "#66 value strict")}
STREAMS = RL.STREAMS
TODAY = date.today()


def log(m: str) -> None:
    M.log(f"[fe3] {m}")


# ------------------------------------------------------------------------------------------------ evidence + shrinkage
def dsr(r: np.ndarray, n_trials: int) -> float:
    r = np.asarray(r, float)
    n, sd = len(r), r.std()
    if n < 10 or sd == 0:
        return 0.0
    sr = r.mean() / sd
    sk = ((r - r.mean()) ** 3).mean() / sd ** 3
    ku = ((r - r.mean()) ** 4).mean() / sd ** 4
    Z, e = NormalDist(), 0.5772156649015329
    v = (1 - sk * sr + (ku - 1) / 4.0 * sr ** 2) / (n - 1)
    if v <= 0:
        return 0.0
    emax = Z.inv_cdf(1 - 1.0 / n_trials) * (1 - e) + Z.inv_cdf(1 - 1.0 / (n_trials * math.e)) * e
    return Z.cdf((sr - math.sqrt(v) * emax) / math.sqrt(v))


def evidence(R: pd.DataFrame, n_trials: int = N_AT) -> pd.DataFrame:
    rows = {}
    T = len(R) / 250
    for s in STREAMS:
        r = R[s]
        mu, sig = r.mean() * 250, r.std() * math.sqrt(250)
        act = (r != 0).groupby(r.index.year).sum()
        p = act / act.sum()
        t_eff = float(1 / (p ** 2).sum())
        k_ep = max(1.0, T / t_eff)
        d_ = dsr(r.to_numpy(), n_trials)
        k_dsr = 1 / max(d_, DSR_FLOOR)
        k_plc = 1.0 if PLACEBO[s][0] >= 95 else 2.0
        se2 = sig ** 2 / T
        rows[s] = {"mu": mu, "sigma": sig, "sharpe": mu / sig if sig else 0.0, "T": T, "active_by_year": {int(k): int(v) for k, v in act.items()},
                   "T_eff": t_eff, "k_ep": k_ep, "dsr": d_, "k_dsr": k_dsr, "placebo": PLACEBO[s][0], "k_plc": k_plc,
                   "se": math.sqrt(se2), "se_eff": math.sqrt(se2 * k_ep * k_dsr * k_plc)}
    E = pd.DataFrame(rows).T
    se2 = E["se_eff"].astype(float) ** 2
    mu = E["mu"].astype(float)
    tau2 = max(TAU_FLOOR ** 2, float((mu ** 2 - se2).mean()))
    B = se2 / (se2 + tau2)
    E["tau"] = math.sqrt(tau2)
    E["B"] = B
    E["post"] = (1 - B) * mu
    # sensitivity (not a trial): EB prior centred on the precision-weighted grand mean, DerSimonian-Laird tau
    w = 1 / se2
    m0 = float((w * mu).sum() / w.sum())
    Q = float((w * (mu - m0) ** 2).sum())
    tau2_dl = max(0.0, (Q - (len(mu) - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    w2 = 1 / (se2 + tau2_dl)
    m0 = float((w2 * mu).sum() / w2.sum())
    B2 = se2 / (se2 + tau2_dl) if tau2_dl > 0 else pd.Series(1.0, index=mu.index)
    E["post_grand"] = B2 * m0 + (1 - B2) * mu
    E["grand_m0"] = m0
    return E


# ------------------------------------------------------------------------------------------------ Kelly
def ledoit_wolf(X: np.ndarray) -> tuple[np.ndarray, float]:
    n, p = X.shape
    Xc = X - X.mean(axis=0)
    S = Xc.T @ Xc / n
    m = np.trace(S) / p
    d2 = np.sum((S - m * np.eye(p)) ** 2) / p
    b2 = sum(np.sum((np.outer(x, x) - S) ** 2) for x in Xc) / n ** 2 / p
    b2 = min(b2, d2)
    a = b2 / d2 if d2 > 0 else 1.0
    return a * m * np.eye(p) + (1 - a) * S, float(a)


def kelly_long(mu: np.ndarray, S: np.ndarray, iters: int = 5000) -> np.ndarray:
    w = np.zeros(len(mu))
    for _ in range(iters):
        w0 = w.copy()
        for i in range(len(mu)):
            w[i] = max(0.0, (mu[i] - S[i] @ w + S[i, i] * w[i]) / S[i, i])
        if np.max(np.abs(w - w0)) < 1e-12:
            break
    return w


def cap(w: np.ndarray) -> np.ndarray:
    s = w.sum()
    return w * (CAP / s) if s > CAP else w


def run_weights(world: dict, spans, wts: list[np.ndarray]) -> np.ndarray:
    out, last = [], None
    for (a, b), w in zip(spans, wts, strict=True):
        cost = RL.COST * float(np.abs(w - last).sum() + abs((1 - w.sum()) - (1 - last.sum()))) / 2 if last is not None else 0.0
        first = True
        for i in range(a, b):
            r = world["blocks"][i] @ w
            r = r.copy()
            if first and len(r):
                r[0] -= cost
                first = False
            out.extend(r.tolist())
        last = w
    return np.array(out)


# ------------------------------------------------------------------------------------------------ deployed combo
def deployed_nav(d: str) -> pd.Series:
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = K.ml_ens_trades(P, dates, codes, A, raw, offer, bid, liq)
    del P
    gap, o = K.gap_events(d, dates)
    OPEN = o.reindex(index=dates, columns=codes).to_numpy(float)
    SECT = np.full((len(dates), len(codes)), None, dtype=object)
    cs = set(codes)
    x = CR.trend_trades(d, dates, cache=os.environ["IDX_EXIT_CACHE"], board="pit")
    tr = [dict(y, tag="p", frac=1.0) for y in x if y["code"] in cs]
    nav, _ = K.engine(dates, codes, A, raw, offer, bid, OPEN, SECT, ml + tr, gap)
    return nav


# ------------------------------------------------------------------------------------------------ main
def main() -> int:
    d = RL.AF.dsn()
    pk = os.path.join(ROOT, "tmp", f"rl_streams_{TODAY}.pkl")
    S = pickle.load(open(pk, "rb"))
    R, comp_d = S["R"], S["comp_d"]
    world = RL.weekly(R, comp_d)
    ends = world["ends"]
    first = {y: int(np.searchsorted(ends, pd.Timestamp(f"{y}-01-01"))) for y in RL.TEST_YEARS}
    last_i = len(world["weeks"])
    spans = [(first[y], first[RL.TEST_YEARS[k + 1]] if k + 1 < len(RL.TEST_YEARS) else last_i) for k, y in enumerate(RL.TEST_YEARS)]
    day_idx = pd.DatetimeIndex([dd for i in range(spans[0][0], last_i) for dd in R.index[R.index.to_period("W-FRI") == world["weeks"][i]]])
    WK = np.array([(1 + b).prod(axis=0) - 1 for b in world["blocks"]])          # weekly compounded sleeve returns

    # ---- baselines (RL-1's own code, same world) ----
    res: dict = {}
    eqi, defi = RL.NAMES.index("EQ"), RL.NAMES.index("DEF")
    res["FIXED_EQ"] = RL.stats(np.concatenate([RL.run_policy(world, a, b, lambda i, dd, l: eqi, eqi)[0] for a, b in spans]), day_idx)
    res["REGIME"] = RL.stats(np.concatenate([RL.run_policy(world, a, b, lambda i, dd, l: eqi if world["comp_up"][i - 1] else defi, eqi)[0]
                                             for a, b in spans]), day_idx)
    parts, picks = [], {}
    for (a, b), y in zip(spans, RL.TEST_YEARS, strict=True):
        best, best_s = eqi, -9.0
        for k in range(len(RL.NAMES)):
            rr, _ = RL.run_policy(world, 13, a, lambda i, dd, l, k=k: k, k)
            s_ = rr.mean() / rr.std() * np.sqrt(250) if rr.std() > 0 else -9.0
            if s_ > best_s:
                best, best_s = k, s_
        picks[y] = RL.NAMES[best]
        parts.append(RL.run_policy(world, a, b, lambda i, dd, l, k=best: k, best)[0])
    res["WF_BEST"] = RL.stats(np.concatenate(parts), day_idx)
    res["WF_BEST"]["picks"] = picks
    rng = np.random.default_rng(7)
    rand_sh = []
    for _ in range(200):
        rr = np.concatenate([RL.run_policy(world, a, b, lambda i, dd, l: int(rng.integers(len(RL.NAMES))), eqi)[0] for a, b in spans])
        rand_sh.append(rr.mean() / rr.std() * np.sqrt(250))
    rand_sh = np.array(rand_sh)
    res["RANDOM"] = {"sharpe_median": float(np.median(rand_sh)), "sharpe_p95": float(np.percentile(rand_sh, 95))}
    log("baselines: " + ", ".join(f"{k} {res[k]['cagr']:+.1%}/{res[k]['sharpe']:.2f}/{res[k]['mdd']:.1%}" for k in ("FIXED_EQ", "REGIME", "WF_BEST"))
        + f"; RANDOM p95 {res['RANDOM']['sharpe_p95']:.2f}")

    # ---- deployed combo on the same days ----
    nav = deployed_nav(d)
    full = CR.stats(nav)
    log(f"deployed combo full span: CAGR {full['cagr']:+.1%} Sharpe {full['sharpe']:.2f} mDD {full['mdd']:.1%} (expect 33.8 / 1.83 / -17.9)")
    rd = nav.pct_change().reindex(day_idx).fillna(0.0).to_numpy()
    res["DEPLOYED"] = RL.stats(rd, day_idx)
    res["DEPLOYED"]["full_span"] = {k: full[k] for k in ("cagr", "sharpe", "mdd")}

    # ---- planning numbers: full stream ----
    Efull = evidence(R)
    log("planning:\n" + Efull[["mu", "sigma", "T_eff", "k_ep", "dsr", "k_dsr", "se_eff", "B", "post", "post_grand"]].to_string())

    # ---- walk-forward Kelly ----
    fits = {}
    wts = {a: [] for a in ARMS}
    for (a, b), y in zip(spans, RL.TEST_YEARS, strict=True):
        tr_days = R.index < pd.Timestamp(f"{y}-01-01")
        Ey = evidence(R[tr_days])
        X = WK[:a]
        Sig, shrink = ledoit_wolf(X)
        mu_u = X.mean(axis=0)
        mu_s = mu_u * (1 - Ey["B"].astype(float).to_numpy())
        ku, ks = kelly_long(mu_u, Sig), kelly_long(mu_s, Sig)
        fits[y] = {"weeks": int(a), "lw_shrink": shrink, "mu_ann_unshrunk": dict(zip(STREAMS, (mu_u * 52).round(4))),
                   "mu_ann_shrunk": dict(zip(STREAMS, (mu_s * 52).round(4))), "B": dict(zip(STREAMS, Ey["B"].astype(float).round(3))),
                   "dsr": dict(zip(STREAMS, Ey["dsr"].astype(float).round(3))), "T_eff": dict(zip(STREAMS, Ey["T_eff"].astype(float).round(2))),
                   "kelly_full_unshrunk": dict(zip(STREAMS, ku.round(3))), "kelly_full_shrunk": dict(zip(STREAMS, ks.round(3))), "w": {}}
        for m, kv in (("shrunk", ks), ("unshrunk", ku)):
            for f, fr in FRACS.items():
                w = cap(fr * kv)
                wts[f"{f}_{m}"].append(w)
                fits[y]["w"][f"{f}_{m}"] = dict(zip(STREAMS, w.round(3)))
        log(f"{y}: LW {shrink:.2f} | Kelly full unshrunk {np.round(ku, 2)} shrunk {np.round(ks, 2)} | B {Ey['B'].astype(float).round(2).to_dict()}")
    for arm in ARMS:
        r = run_weights(world, spans, wts[arm])
        st = RL.stats(r, day_idx)
        st["random_pct"] = float((rand_sh < st["sharpe"]).mean() * 100)
        res[arm] = st
        log(f"{arm}: CAGR {st['cagr']:+.1%} Sharpe {st['sharpe']:.2f} mDD {st['mdd']:.1%} rand pct {st['random_pct']:.0f}")

    # ---- RL-1 result (its own run, same streams) ----
    rlj = os.path.join(HERE, f"IDX_RL_ALLOC_{TODAY}.json")
    rl = json.load(open(rlj))["res"] if os.path.exists(rlj) else None

    # ---- verdicts ----
    best_k = max(("FIXED_EQ", "REGIME", "WF_BEST"), key=lambda k: res[k]["sharpe"])
    bb = res[best_k]
    verdict = {}
    for arm in ARMS:
        s = res[arm]
        chk = {"sharpe": s["sharpe"] >= bb["sharpe"] + RL.BAR["sharpe_up"], "cagr": s["cagr"] >= RL.BAR["cagr_keep"] * bb["cagr"],
               "mdd": s["mdd"] >= bb["mdd"] - RL.BAR["mdd_slack"], "random": s["sharpe"] >= res["RANDOM"]["sharpe_p95"]}
        verdict[arm] = {"checks": chk, "better": all(chk.values())}
    n_better = sum(v["better"] for v in verdict.values())

    # ---- report ----
    Y = RL.TEST_YEARS
    fmt = lambda s: f"{s['cagr']:+.1%} | {s['sharpe']:.2f} | {s['mdd']:.1%} | " + " | ".join(f"{s['years'].get(y, 0):+.0%}" for y in Y)  # noqa: E731
    L = [f"# IDX menu FE-3 - capital per strategy: Bayesian shrinkage + fractional Kelly vs RL-1 - {TODAY} - 7 trials (RL-1 961, Kelly 962..967), cumulative N = {N_AT}", "",
         f"Streams: RL-1's four daily sleeve streams from the same run (corrected engine #192, pit board, IDX-only opens), {R.index[0].date()} -> {R.index[-1].date()}. "
         f"Walk-forward test {Y[0]}-{Y[-1]} stitched ({day_idx[0].date()} -> {day_idx[-1].date()}, {len(day_idx)} days). Script `research/idx_fe_kelly.py`; RL-1 run copy "
         "`research/idx_rl_alloc_run.py` (deviations: corrected engine, N 865 -> 960, streams dumped; design untouched).", "",
         "## 1. Planning numbers - posterior expected return per sleeve (full stream, quote these instead of the raw backtest)", "",
         f"Prior N(0, tau^2), tau = {float(Efull['tau'].iloc[0]):.1%} (EB, floor {TAU_FLOOR:.0%}); se inflated by episodes (k_ep), DSR @ N {N_AT} (k_dsr = 1/max(DSR, {DSR_FLOOR})), placebo (k_plc). "
         "Stream sizing = RL-1's (gap 20 %/event, trend 10 %, ML 10 %, value full); the haircut is scale-free, so the last column applies it to the deployed-size sleeve-alone CAGR.", "",
         "| sleeve | raw mean/yr | vol | Sharpe | active days by year | T_eff / T (yrs) | k_ep | DSR | k_dsr | placebo | se_eff | shrink B | **posterior mean/yr** | haircut | grand-mean prior (sens.) | deployed-size raw -> planning |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in STREAMS:
        e = Efull.loc[s]
        dep, src = DEPLOYED_ALONE[s]
        L.append(f"| {s} | {e['mu']:+.1%} | {e['sigma']:.1%} | {e['sharpe']:.2f} | {' / '.join(str(v) for v in e['active_by_year'].values())} | "
                 f"{e['T_eff']:.2f} / {e['T']:.2f} | {e['k_ep']:.2f} | {e['dsr']:.2f} | {e['k_dsr']:.2f} | {e['placebo']} ({PLACEBO[s][1]}) | {e['se_eff']:.1%} | "
                 f"{e['B']:.2f} | **{e['post']:+.1%}** | -{e['B']:.0%} | {e['post_grand']:+.1%} | {dep:.1%} -> **{dep * (1 - e['B']):.1%}** ({src}) |")
    L += ["", f"Sensitivity prior centre (grand mean, DerSimonian-Laird): {float(Efull['grand_m0'].iloc[0]):+.1%}/yr.", "",
          "## 2. Walk-forward fits (each on weeks before Jan 1 of the test year)", ""]
    for y, fz in fits.items():
        L.append(f"- **{y}** ({fz['weeks']} training weeks, LW shrinkage {fz['lw_shrink']:.2f}): mu unshrunk {fz['mu_ann_unshrunk']}, shrunk {fz['mu_ann_shrunk']}, "
                 f"B {fz['B']}, T_eff {fz['T_eff']}, DSR {fz['dsr']}; full Kelly unshrunk {fz['kelly_full_unshrunk']}, shrunk {fz['kelly_full_shrunk']}; "
                 f"held weights (cap {CAP:.0%}): " + "; ".join(f"{k} {v}" for k, v in fz["w"].items()))
    L += ["", "## 3. Head to head (stitched test window, same run)", "",
          "| allocator | CAGR | Sharpe | mDD | " + " | ".join(str(y) for y in Y) + " | RANDOM pct | verdict |", "|---|---|---|---|" + "---|" * len(Y) + "---|---|"]
    for k in ("FIXED_EQ", "REGIME", "WF_BEST", "DEPLOYED"):
        tag = " (best baseline)" if k == best_k else (" (reported, not in the rule)" if k == "DEPLOYED" else "")
        L.append(f"| {k}{tag} | {fmt(res[k])} | {(rand_sh < res[k]['sharpe']).mean() * 100:.0f} | - |")
    if rl:
        r_ = rl["RL"]
        rv = json.load(open(rlj))
        L.append(f"| RL-1 (seed mean; range {r_['sharpe_min']:.2f}..{r_['sharpe_max']:.2f}) | {r_['cagr']:+.1%} | {r_['sharpe']:.2f} | {r_['mdd']:.1%} | "
                 + " | ".join(f"{np.mean([s_['years'].get(str(y), s_['years'].get(y, 0)) for s_ in rl['RL_seeds']]):+.0%}" for y in Y)
                 + f" | {(rand_sh < r_['sharpe']).mean() * 100:.0f} | {'BETTER' if rv['better'] else 'NOT better'} ({', '.join(f'{a} {chr(121) if b else chr(110)}' for a, b in rv['verdict'].items())}) |")
    for arm in ARMS:
        v = verdict[arm]
        L.append(f"| Kelly {arm} | {fmt(res[arm])} | {res[arm]['random_pct']:.0f} | {'BETTER' if v['better'] else 'NOT better'} ("
                 + ", ".join(f"{a} {'y' if b else 'n'}" for a, b in v["checks"].items()) + ") |")
    L += ["", f"RANDOM (200 weekly-random templates): Sharpe median {res['RANDOM']['sharpe_median']:.2f}, p95 {res['RANDOM']['sharpe_p95']:.2f}. WF_BEST picks {picks}. "
          f"Deployed combo full span on this run: {full['cagr']:+.1%} / {full['sharpe']:.2f} / {full['mdd']:.1%}.", "",
          "## Verdict (pre-registered, RL-1's rule)", "",
          f"Best baseline {best_k} ({bb['cagr']:+.1%} / {bb['sharpe']:.2f} / {bb['mdd']:.1%}); bar Sharpe >= {bb['sharpe'] + 0.15:.2f}, CAGR >= {0.85 * bb['cagr']:+.1%}, "
          f"mDD >= {bb['mdd'] - 0.02:.1%}, Sharpe >= RANDOM p95 {res['RANDOM']['sharpe_p95']:.2f}. Kelly arms BETTER: **{n_better}/6**."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_FE_KELLY_RL_{TODAY}.md")
    open(out, "w", encoding="utf-8", newline="\n").write(text + "\n")
    print(text)
    planning = {s: {"raw_mu": float(Efull.loc[s, "mu"]), "posterior_mu": float(Efull.loc[s, "post"]), "B": float(Efull.loc[s, "B"]),
                    "T_eff": float(Efull.loc[s, "T_eff"]), "dsr": float(Efull.loc[s, "dsr"]),
                    "deployed_raw": DEPLOYED_ALONE[s][0], "deployed_planning": DEPLOYED_ALONE[s][0] * (1 - float(Efull.loc[s, "B"]))} for s in STREAMS}
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, TODAY,
                              params={"trials": ARMS, "rl1_trial": N_RL, "n_before": N_BEFORE, "n_trials_cumulative": N_AT, "cap_sum_w": CAP,
                                      "tau_floor": TAU_FLOOR, "dsr_floor": DSR_FLOOR, "placebo": PLACEBO, "test_years": RL.TEST_YEARS, "bar": RL.BAR,
                                      "engine": "#192 corrected (pit board, trend fix), IDX-only opens", "streams": pk},
                              summary=common.plain({"planning": planning, "baselines": {k: res[k] for k in ("FIXED_EQ", "REGIME", "WF_BEST", "RANDOM", "DEPLOYED")},
                                                    "kelly": {a: res[a] for a in ARMS}, "verdict": verdict, "n_better": n_better, "fits": fits,
                                                    "rl1": {"RL": rl["RL"], "better": json.load(open(rlj))["better"]} if rl else None, "best_baseline": best_k}),
                              names=[], report_path=out, note="menu FE-3: Bayesian-shrunk planning numbers + fractional Kelly vs RL-1, walk-forward 2024-26")
    log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
