#!/usr/bin/env python3
"""IDX menu FE-1 - COVARIANCE-AWARE PORTFOLIO CONSTRUCTION on the deployed combo book, 2026-09-26.

The deployed book (gap-fade 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots, lots of 100, Rp 20 M, cash floor 30 %)
sizes every trade at a fixed share of NAV and ignores how the holdings move together. Per-name vol sizing, pyramiding and
book-level vol targets / overlays are CLOSED (#177, #184) and not repeated. This menu tests what a financial-engineering
curriculum adds: a covariance matrix of the holdings, known at the previous close.

ENGINE / TRADES / COSTS = the official baseline of #192 (`idx_engine_fix`, (d)): `idx_construction.engine` (copied below with
hooks; asserted equal to K.engine with no arm active), gap events from `K.gap_events` (-> idx_gapfade.build -> idx_daytrade.load,
opens restricted to open_src='idx'), trend trades from `CR.trend_trades` (fixed mapping, IDX_BOARD_MODE=pit,
tmp/exit_cache_pit.pkl), ML ens4 from `K.ml_ens_trades` (tmp/ml_strategy_cache.pkl); closing offer/bid, Stockbit fees 0.10/0.20 %,
2022-01-01 -> 2026-09-16. SANITY GATE: the re-run baseline must print 33.8 % / 1.83 / -17.9 % (+-0.15 pp / +-0.01) or the script
stops before any arm is run.

RISK MODEL (all arms). Daily returns of adjusted closes (ML panel `ac`). The covariance used for a decision at close t (or the open
of t) uses returns up to close t-1 only. Default: 120-session window, Ledoit-Wolf shrinkage to the scaled identity
(sklearn.covariance.ledoit_wolf); a name with < max(20, window/3) returns in the window gets the median variance of the others and
zero covariance; missing returns inside the window count as 0. Book weights = overnight position value / NAV, aggregated per
code. The gap-fade sleeve is intraday (bought at the open, sold at the close): a close-to-close covariance does not describe it, so
A and C leave gap-fade sizing exactly as deployed (it still counts against the slots, cash and floor as in the baseline).

PRE-REGISTERED (12 trials max; cumulative N_BEFORE 942 -> ids 943..954; 11 used as registered below):
 A. Position level (trend + ML overnight entries)
   943 A1 mrc      marginal-risk-contribution cap: a new entry is sized at the largest of {1, 0.75, 0.5, 0.25} x its nominal size
                   for which its share of the book's ex-ante variance (w_j (Sigma w)_j / w'Sigma w, after adding) is
                   <= max(15 %, 1.5 / n_names_after); otherwise skipped.
   944 A2 erc      equal risk contribution across open overnight positions: every 5th session (close, after exits, before
                   entries) the overnight book is re-weighted to ERC weights at unchanged overnight gross, target per name
                   capped at 10 % of NAV; lots of 100; a re-weight is skipped if |delta| < 25 % of the position or < 1 lot;
                   buys at the closing offer, sells at the closing bid, fees charged. New entries enter at the nominal size.
   945 A3 mvtilt   minimum-variance tilt: the day's trend+ML entry candidates are taken greedily in order of lowest marginal
                   increase of book variance (instead of trend-first/first-come); identical to the baseline on days when every
                   candidate fits; the number of rationed days is reported.
 B. Sleeve level (walk-forward by construction): sleeve daily returns = each sleeve alone on the same engine at deployed
    sizing; on the first session of each month the sleeve weights w (sum 1, long-only) are computed from the trailing 120
    sessions (through the previous close; deployed sizing until 120 sessions exist) and applied to NEW trades of that month:
    per-trade pct_s = deployed_s x 3 w_s, clipped to [0.5x, 2x] deployed (equal weights = the deployed book). Open positions are
    not re-sized (no rebalancing turnover).
   946 B1 rp       sleeve risk parity (ERC on the 3x3 covariance)
   947 B2 mv       long-only minimum variance
   948 B3 md       long-only maximum diversification (max w'sigma / sqrt(w'Sigma w))
 C. Factor-aware caps (ex-ante, rolling OLS betas of each name on COMPOSITE daily returns, 120 sessions through t-1, min 40
    obs, missing beta = 1; sector = the ML panel's sector on the day):
   949 C1 beta     a new overnight entry is shrunk (>= 1 lot) or skipped so that the book's beta (sum w_i beta_i) stays <= 0.50
   950 C2 sector   ... so that no sector's overnight value exceeds 25 % of NAV (caps the largest sector)
 NEIGHBOUR FAMILIES (each family = one trial, run on all 8 arms):
   951 N60   window 60 sessions (covariance, sleeve covariance, betas)
   952 N250  window 250 sessions
   953 NSHR  alternative shrinkage: fixed delta 0.5 to the scaled identity (A, B); Vasicek-style beta 0.5 x beta + 0.5 (C)
READING RULE (fixed before the run; same-run pair vs the deployed baseline): an arm IMPROVES if
     (Sharpe +0.15 AND mDD not deeper by > 1 pp AND CAGR >= 0.9 x baseline) OR (mDD shallower by >= 3 pp AND CAGR >= 0.9 x)
  on the full window AND in both halves (K.halves: split at the window's middle date, each half re-based, vs the baseline's
  same half) AND all three neighbours pass the full-window rule. B is walk-forward by construction (only trailing data).
  Reported, not part of the verdict: turnover (traded value / mean NAV per year), fees, rebalancing trades/costs, re-weights
  skipped for lot size, mean ex-ante book vol and beta, and every arm again at Rp 200 M (same trades; liquidity not modelled).
Any change to the live book (combo_book) is the operator's call. READ-ONLY on market tables; one idx.study row ('fe_covariance').
Env: INGEST_DB_DSN (blackheart-ingest/idx-local.env), IDX_BOARD_MODE=pit, IDX_EXIT_CACHE=tmp/exit_cache_pit.pkl,
IDX_ML_CACHE=tmp/ml_strategy_cache.pkl.
"""
from __future__ import annotations

import os
import pickle
import sys
import time
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
os.environ.setdefault("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
os.environ.setdefault("IDX_EXIT_CACHE", os.path.join(ROOT, "tmp", "exit_cache_pit.pkl"))
os.environ.setdefault("IDX_BOARD_MODE", "pit")
import idx_combo_rupiah as CR  # noqa: E402
import idx_construction as K  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402
from scipy.optimize import minimize  # noqa: E402
from sklearn.covariance import ledoit_wolf  # noqa: E402

STUDY = "fe_covariance"
N_BEFORE = 942
ARMS = ["A1_mrc", "A2_erc", "A3_mvtilt", "B1_rp", "B2_mv", "B3_md", "C1_beta", "C2_sector"]
NEIGH = {"N60": {"win": 60}, "N250": {"win": 250}, "NSHR": {"shrink": "fixed"}}
TRIAL_IDS = {**{a: 943 + i for i, a in enumerate(ARMS)}, "N60": 951, "N250": 952, "NSHR": 953}
INPUTS = os.path.join(ROOT, "tmp", "fe_cov_inputs.pkl")
OUT = os.path.join(HERE, "IDX_FE_COVARIANCE_2026-09-26.md")
PCT, FLOOR = K.PCT, K.FLOOR
MRC_MIN, MRC_MULT = 0.15, 1.5
ERC_EVERY, ERC_BAND, ERC_CAP = 5, 0.25, 0.10
BETA_CAP, SECTOR_CAP = 0.50, 0.25
REF = {"cagr": 0.338, "sharpe": 1.83, "mdd": -0.179}


# ---- inputs ------------------------------------------------------------------------------------------------------------------
def prep() -> dict:
    if os.path.exists(INPUTS):
        return pickle.load(open(INPUTS, "rb"))
    d = K.dsn()
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    sect = P.pivot_table(index="d", columns="code", values="sector", aggfunc="first").reindex(index=dates, columns=codes)
    SECT = sect.to_numpy(object)
    SECT = np.where(pd.isna(SECT), None, SECT)
    comp = P.groupby("d")["comp_r1"].median().reindex(dates).to_numpy(float)
    ml = K.ml_ens_trades(P, dates, codes, A, raw, offer, bid, liq)
    del P
    gap, o = K.gap_events(d, dates)
    OPEN = o.reindex(index=dates, columns=codes).to_numpy(float)
    cs = set(codes)
    tr = [dict(y, tag="p", frac=1.0) for y in CR.trend_trades(d, dates) if y["code"] in cs]
    D = {"dates": dates, "codes": codes, "A": A, "raw": raw, "offer": offer, "bid": bid, "OPEN": OPEN, "SECT": SECT, "comp": comp,
         "ml": ml, "tr": tr, "gap": gap}
    pickle.dump(D, open(INPUTS, "wb"))
    return D


def returns(D) -> np.ndarray:
    A = D["A"]
    R = np.full_like(A, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        R[1:] = A[1:] / A[:-1] - 1
    R[~np.isfinite(R)] = np.nan
    return R


def betas(D, R, win: int) -> np.ndarray:
    """beta row t = OLS beta on COMPOSITE over the `win` returns ending at t-1 (known at the previous close)."""
    m = pd.Series(D["comp"])
    Rd = pd.DataFrame(R)
    mask = Rd.notna()
    mm = pd.DataFrame(np.where(mask, m.to_numpy()[:, None], np.nan))
    cov = (Rd * mm).rolling(win, min_periods=40).mean() - Rd.rolling(win, min_periods=40).mean() * mm.rolling(win, min_periods=40).mean()
    var = (mm ** 2).rolling(win, min_periods=40).mean() - mm.rolling(win, min_periods=40).mean() ** 2
    b = (cov / var.replace(0, np.nan)).shift(1).to_numpy(float)
    return np.where(np.isfinite(b), b, 1.0)


def cov_at(R, t, cols, win, shrink):
    X = R[max(0, t - win):t][:, cols]
    n_ok = np.isfinite(X).sum(0)
    ok = n_ok >= max(20, win // 3)
    p = len(cols)
    S = np.zeros((p, p))
    if ok.sum() >= 2:
        Xo = np.nan_to_num(X[:, ok])
        if shrink == "lw":
            So = ledoit_wolf(Xo)[0]
        else:
            Sm = np.cov(Xo, rowvar=False)
            mu = np.trace(Sm) / Sm.shape[0]
            So = 0.5 * Sm + 0.5 * mu * np.eye(Sm.shape[0])
        S[np.ix_(ok, ok)] = So
        fill = float(np.median(np.diag(So)))
    elif ok.sum() == 1:
        fill = float(np.nanvar(X[:, ok]))
        S[ok, ok] = fill
    else:
        fill = 0.03 ** 2
    for i in np.where(~ok)[0]:
        S[i, i] = fill
    return S


def erc_weights(S, iters=500):
    n = S.shape[0]
    w = 1 / np.sqrt(np.diag(S))
    w /= w.sum()
    for _ in range(iters):
        mrc = S @ w
        rc = w * mrc
        w_new = w * (rc.mean() / np.maximum(rc, 1e-18)) ** 0.5
        w_new /= w_new.sum()
        if np.max(np.abs(w_new - w)) < 1e-10:
            w = w_new
            break
        w = w_new
    return w if n else w


# ---- engine: K.engine (no caps / recycle) + risk hooks ------------------------------------------------------------------------
def engine(D, R, *, use=("gap", "trend", "ML"), capital=CR.CAPITAL, arm=None, win=120, shrink="lw", B=None, pct_fn=None, beta_shr=False):
    dates, codes, A, raw, offer, bid = D["dates"], D["codes"], D["A"], D["raw"], D["offer"], D["bid"]
    SECT = D["SECT"]
    idx = {c: i for i, c in enumerate(codes)}
    T = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    tick = common.tick
    entries, exits, gaps = {}, {}, {}
    for n, x in enumerate(e for e in D["ml"] + D["tr"] if e["strat"] in use):
        x = dict(x, id=n)
        entries.setdefault(x["t_in"], []).append(x)
        exits.setdefault(x["t_out"], []).append(x)
    for x in (D["gap"] if "gap" in use else []):
        gaps.setdefault(x["t"], []).append(x)
    cash = capital
    held: dict[tuple, dict] = {}
    nav = np.full(T, np.nan)
    st = {"buy": 0.0, "sell": 0.0, "fees": 0.0, "spread": 0.0, "rebal_n": 0, "rebal_value": 0.0, "rebal_cost": 0.0, "rebal_skip_lot": 0,
          "rebal_skip_band": 0, "shrunk": 0, "skipped": 0, "rationed_days": 0, "reordered_days": 0, "exante_vol": [], "beta": []}

    def val(p, t, j):
        return p["units"] * (A[t, j] / p["a_in"]) if not np.isnan(A[t, j]) else p["units"]

    def mval(t):
        return sum(p["units"] * (A[t, idx[k[2]]] / p["a_in"]) for k, p in held.items() if not np.isnan(A[t, idx[k[2]]]))

    def names():
        return {(k[0], k[2]) for k in held}

    def book(t):
        agg: dict[int, float] = {}
        for k, p in held.items():
            j = idx[k[2]]
            agg[j] = agg.get(j, 0.0) + val(p, t, j)
        return agg

    def pct(t, s):
        return pct_fn(t)[s] if pct_fn is not None else PCT[s]

    for t in range(t0, T):
        nav_prev = nav[t - 1] if t > t0 else capital
        day_gap, n_gap, mv_open = 0.0, 0, None
        for x in gaps.get(t, []):
            px = (x["open"] + tick(x["open"])) * (1 + CR.FEE_BUY)
            lots = int((pct(t, "gap") * nav_prev) // (px * CR.LOT))
            cost = lots * CR.LOT * px
            if lots < 1:
                continue
            if mv_open is None:
                mv_open = mval(t)
            if len(names()) + n_gap >= CR.MAX_POS or cost > cash or (FLOOR > 0 and (mv_open + cost) / nav_prev > 1 - FLOOR):
                continue
            cash -= cost
            n_gap += 1
            day_gap += cost * (1 + x["net"])
            st["buy"] += cost
            st["sell"] += cost * (1 + x["net"])
            st["fees"] += cost * CR.FEE_BUY / (1 + CR.FEE_BUY) + cost * (1 + x["net"]) * CR.FEE_SELL / (1 - CR.FEE_SELL)
        cash += day_gap
        for x in exits.get(t, []):
            k = (x["strat"], x["tag"], x["code"])
            if k in held and held[k]["id"] == x["id"]:
                p = held.pop(k)
                j = idx[k[2]]
                px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])
                value = p["units"] * (A[t, j] / p["a_in"]) * (px / raw[t, j]) if not np.isnan(A[t, j]) else p["units"]
                proceeds = value * (1 - CR.FEE_SELL)
                cash += proceeds
                st["sell"] += proceeds
                st["fees"] += value * CR.FEE_SELL
                if not np.isnan(A[t, j]):
                    st["spread"] += value * (raw[t, j] / px - 1)
        # ---- A2: ERC re-weight of the overnight book (close, before entries) ----
        if arm == "A2_erc" and (t - t0) % ERC_EVERY == 0 and held:
            agg = book(t)
            cols = [j for j in agg if not np.isnan(A[t, j]) and raw[t, j] > 0]
            if len(cols) >= 2:
                nav_now = cash + mval(t)
                S = cov_at(R, t, cols, win, shrink)
                w = erc_weights(S)
                gross = sum(agg[j] for j in cols)
                tgt = np.minimum(w * gross, ERC_CAP * nav_now)
                order = sorted(range(len(cols)), key=lambda i: tgt[i] - agg[cols[i]])       # sells first, then buys
                for i in order:
                    j = cols[i]
                    cur = agg[j]
                    delta = tgt[i] - cur
                    if abs(delta) < ERC_BAND * cur:
                        st["rebal_skip_band"] += 1
                        continue
                    ks = [k for k in held if idx[k[2]] == j]
                    k = max(ks, key=lambda kk: val(held[kk], t, j))
                    p = held[k]
                    pv = val(p, t, j)
                    pps = pv / p["sh"]
                    dsh = int(abs(delta) / (pps * CR.LOT)) * CR.LOT
                    if delta < 0:
                        dsh = min(dsh, p["sh"] - CR.LOT)
                    if dsh < CR.LOT:
                        st["rebal_skip_lot"] += 1
                        continue
                    if delta > 0:
                        pxr = offer[t, j] / raw[t, j] if offer[t, j] > 0 and offer[t, j] >= raw[t, j] else (raw[t, j] + tick(raw[t, j])) / raw[t, j]
                        cost = dsh * pps * pxr * (1 + CR.FEE_BUY)
                        if cost > cash:
                            dsh = int(cash / (pps * pxr * (1 + CR.FEE_BUY) * CR.LOT)) * CR.LOT
                            if dsh < CR.LOT:
                                continue
                            cost = dsh * pps * pxr * (1 + CR.FEE_BUY)
                        cash -= cost
                        p["units"] += dsh * pps * p["a_in"] / A[t, j]
                        p["sh"] += dsh
                        p["cost"] += cost
                        st["buy"] += cost
                        st["rebal_cost"] += cost - dsh * pps
                    else:
                        pxr = bid[t, j] / raw[t, j] if 0 < bid[t, j] <= raw[t, j] else (raw[t, j] - tick(raw[t, j])) / raw[t, j]
                        proceeds = dsh * pps * pxr * (1 - CR.FEE_SELL)
                        cash += proceeds
                        frac = dsh / p["sh"]
                        p["units"] -= dsh * pps * p["a_in"] / A[t, j]
                        p["cost"] *= 1 - frac
                        p["sh"] -= dsh
                        st["sell"] += proceeds
                        st["rebal_cost"] += dsh * pps - proceeds
                    st["rebal_n"] += 1
                    st["rebal_value"] += dsh * pps
        mv = mval(t)
        nav_now = cash + mv
        cand = sorted(entries.get(t, []), key=lambda z: 0 if z["strat"] == "trend" else 1)
        agg = book(t) if arm is not None else {}
        if arm == "A3_mvtilt" and len(cand) > 1:
            cols0 = sorted(set(agg) | {idx[x["code"]] for x in cand})
            S0 = cov_at(R, t, cols0, win, shrink)
            pos0 = {j: i for i, j in enumerate(cols0)}
            wv = np.zeros(len(cols0))
            for j, v in agg.items():
                wv[pos0[j]] = v / nav_now
            rest, ordered = list(cand), []
            while rest:
                def mvar(x):
                    i = pos0[idx[x["code"]]]
                    w0 = PCT[x["strat"]] * x["frac"]
                    return 2 * w0 * (S0[i] @ wv) + w0 * w0 * S0[i, i]
                b = min(rest, key=mvar)
                rest.remove(b)
                ordered.append(b)
                wv[pos0[idx[b["code"]]]] += PCT[b["strat"]] * b["frac"]
            if [id(x) for x in ordered] != [id(x) for x in cand]:
                st["reordered_days"] += 1
            cand = ordered
        n_block = 0
        for x in cand:
            k = (x["strat"], x["tag"], x["code"])
            j = idx[x["code"]]
            if k in held or np.isnan(A[t, j]) or raw[t, j] <= 0:
                continue
            new_name = (x["strat"], x["code"]) not in names()
            px = offer[t, j] if offer[t, j] > 0 and offer[t, j] >= raw[t, j] else raw[t, j] + tick(raw[t, j])
            target = pct(t, x["strat"]) * x["frac"] * nav_now
            if arm in ("A1_mrc", "C1_beta", "C2_sector"):
                agg = book(t)
                mult = None
                if arm == "A1_mrc":
                    cols = sorted(set(agg) | {j})
                    S = cov_at(R, t, cols, win, shrink)
                    wb = np.array([agg.get(c, 0.0) for c in cols]) / nav_now
                    ij = cols.index(j)
                    n_after = len(set(agg) | {j})
                    cap = max(MRC_MIN, MRC_MULT / n_after)
                    for m_ in (1.0, 0.75, 0.5, 0.25):
                        w = wb.copy()
                        w[ij] += m_ * target / nav_now
                        v = w @ S @ w
                        if v <= 0 or w[ij] * (S[ij] @ w) / v <= cap:
                            mult = m_
                            break
                    tgt_v = target * mult if mult is not None else 0.0
                elif arm == "C1_beta":
                    bt = B[t]
                    bb = (lambda b_: 0.5 * b_ + 0.5) if beta_shr else (lambda b_: b_)
                    bk = sum(v * bb(bt[c]) for c, v in agg.items()) / nav_now
                    bj = bb(bt[j])
                    room = BETA_CAP - bk
                    tgt_v = target if bj <= 0 or bk + bj * target / nav_now <= BETA_CAP else max(0.0, room / bj * nav_now)
                else:
                    sec = SECT[t, j]
                    if sec is None:
                        tgt_v = target
                    else:
                        sv = sum(v for c, v in agg.items() if SECT[t, c] == sec)
                        tgt_v = min(target, max(0.0, SECTOR_CAP * nav_now - sv))
                if tgt_v < target:
                    st["shrunk" if tgt_v >= px * CR.LOT * (1 + CR.FEE_BUY) else "skipped"] += 1
                target = tgt_v
            lots = int(target // (px * CR.LOT))
            cost = lots * CR.LOT * px * (1 + CR.FEE_BUY)
            if lots < 1:
                continue
            if (new_name and len(names()) >= CR.MAX_POS) or cost > cash or (FLOOR > 0 and (mv + cost) / nav_now > 1 - FLOOR):
                n_block += 1
                continue
            cash -= cost
            mv += cost / (1 + CR.FEE_BUY)
            held[k] = {"t": t, "a_in": A[t, j], "units": lots * CR.LOT * raw[t, j], "cost": cost, "id": x["id"], "sh": lots * CR.LOT}
            st["buy"] += cost
            st["fees"] += cost * CR.FEE_BUY / (1 + CR.FEE_BUY)
            st["spread"] += lots * CR.LOT * (px - raw[t, j])
        if n_block:
            st["rationed_days"] += 1
        nav[t] = cash + mval(t)
        if arm is not None and held and (t - t0) % 5 == 0:                                  # ex-ante diagnostics, weekly
            agg = book(t)
            cols = sorted(agg)
            S = cov_at(R, t + 1, cols, win, shrink)
            w = np.array([agg[c] for c in cols]) / nav[t]
            st["exante_vol"].append(float(np.sqrt(max(w @ S @ w, 0)) * np.sqrt(252)))
            if B is not None:
                st["beta"].append(float(sum(w[i] * B[min(t + 1, T - 1), c] for i, c in enumerate(cols))))
    navs = pd.Series(nav[t0:], index=dates[t0:])
    yrs = (navs.index[-1] - navs.index[0]).days / 365.25
    st["turnover"] = (st["buy"] + st["sell"]) / 2 / float(navs.mean()) / yrs
    st["exante_vol"] = float(np.mean(st["exante_vol"])) if st["exante_vol"] else float("nan")
    st["beta"] = float(np.mean(st["beta"])) if st["beta"] else float("nan")
    return navs, st


# ---- B: sleeve weights ---------------------------------------------------------------------------------------------------------
def sleeve_weights(S, method):
    n = S.shape[0]
    if method == "rp":
        return erc_weights(S)
    cons = ({"type": "eq", "fun": lambda w: w.sum() - 1},)
    bnds = [(0, 1)] * n
    w0 = np.ones(n) / n
    if method == "mv":
        f = lambda w: w @ S @ w * 1e4  # noqa: E731
    else:
        sig = np.sqrt(np.diag(S))
        f = lambda w: -(w @ sig) / np.sqrt(max(w @ S @ w, 1e-18))  # noqa: E731
    r = minimize(f, w0, bounds=bnds, constraints=cons, method="SLSQP")
    w = np.clip(r.x, 0, None)
    return w / w.sum()


def make_pct_fn(D, sleeve_ret, method, win, shrink):
    dates = D["dates"]
    T = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    order = ["gap", "trend", "ML"]
    X = sleeve_ret[order].reindex(dates).to_numpy(float)          # NaN before t0
    table = {}
    log = []
    cur = dict(PCT)
    for t in range(t0, T):
        if t == t0 or dates[t].month != dates[t - 1].month:
            hist = X[t0:t]
            if len(hist) >= win:
                Xw = np.nan_to_num(hist[-win:])
                if shrink == "lw":
                    S = ledoit_wolf(Xw)[0]
                else:
                    Sm = np.cov(Xw, rowvar=False)
                    S = 0.5 * Sm + 0.5 * np.trace(Sm) / 3 * np.eye(3)
                w = sleeve_weights(S, method)
                cur = {s: float(np.clip(PCT[s] * 3 * w[i], 0.5 * PCT[s], 2 * PCT[s])) for i, s in enumerate(order)}
            else:
                cur = dict(PCT)
            log.append((str(dates[t].date()), cur))
        table[t] = cur
    return (lambda t: table[t]), log


# ---- reading -------------------------------------------------------------------------------------------------------------------
def s3(nav):
    s = CR.stats(nav)
    return {k: s[k] for k in ("final", "cagr", "sharpe", "mdd", "by_year")}


def rule(a, b) -> bool:
    dd = (a["mdd"] - b["mdd"]) * 100
    ok_c = a["cagr"] >= 0.9 * b["cagr"]
    return bool(ok_c and ((a["sharpe"] - b["sharpe"] >= 0.15 and dd >= -1) or dd >= 3))


def run_arm(D, R, BET, arm, sleeve_ret, *, win=120, shrink="lw", capital=CR.CAPITAL):
    kw = dict(capital=capital, win=win, shrink=shrink)
    if arm.startswith("B"):
        fn, log = make_pct_fn(D, sleeve_ret, {"B1_rp": "rp", "B2_mv": "mv", "B3_md": "md"}[arm], win, shrink)
        nav, st = engine(D, R, arm="B", pct_fn=fn, B=BET[120], **kw)
        st["pct_log"] = log
    elif arm.startswith("C1"):
        nav, st = engine(D, R, arm=arm, B=BET[win], beta_shr=(shrink != "lw"), **kw)
    else:
        nav, st = engine(D, R, arm=arm, B=BET[120], **kw)
    return nav, st


def main() -> int:
    t_start = time.time()
    D = prep()
    R = returns(D)
    M.log(f"inputs: {len(D['dates'])} dates x {len(D['codes'])} codes; ML {len(D['ml'])} rule-trades, trend {len(D['tr'])}, gap {len(D['gap'])} events")
    # ---- sanity gate ----
    nav_k, _ = K.engine(D["dates"], D["codes"], D["A"], D["raw"], D["offer"], D["bid"], D["OPEN"], D["SECT"], D["ml"] + D["tr"], D["gap"])
    base = s3(nav_k)
    M.log(f"BASELINE (K.engine) {base['cagr'] * 100:.2f} % / {base['sharpe']:.3f} / {base['mdd'] * 100:.2f} %  (ref 33.8 / 1.83 / -17.9)")
    if abs(base["cagr"] - REF["cagr"]) > 0.0015 or abs(base["sharpe"] - REF["sharpe"]) > 0.01 or abs(base["mdd"] - REF["mdd"]) > 0.0015:
        M.log("SANITY GATE FAILED - baseline does not reproduce #192 (d); stopping before any arm")
        return 2
    nav0, st0 = engine(D, R)
    assert np.allclose(nav0.to_numpy(), nav_k.to_numpy(), rtol=0, atol=1e-3), "hooked engine != K.engine"
    M.log("hooked engine == K.engine (no arm)")
    if os.environ.get("FE_SANITY_ONLY"):
        return 0
    BET = {w: betas(D, R, w) for w in (60, 120, 250)}
    sleeve_ret = pd.DataFrame({s: engine(D, R, use=(s,))[0].pct_change().fillna(0.0) for s in ("gap", "trend", "ML")})
    _, st_b = engine(D, R, arm="diag", B=BET[120])                                         # baseline diagnostics (no effect on trading)
    res = {"baseline": {**base, "h": [s3(h) for h in [nav_k[nav_k.index <= nav_k.index[0] + (nav_k.index[-1] - nav_k.index[0]) / 2],
                                                      nav_k[nav_k.index > nav_k.index[0] + (nav_k.index[-1] - nav_k.index[0]) / 2]]], "st": st_b}}
    hb = K.halves(nav_k)
    res["baseline"]["h"] = [{k: h[k] for k in ("cagr", "sharpe", "mdd")} for h in hb]
    for arm in ARMS:
        nav, st = run_arm(D, R, BET, arm, sleeve_ret)
        s = s3(nav)
        h = K.halves(nav)
        s["h"] = [{k: x[k] for k in ("cagr", "sharpe", "mdd")} for x in h]
        s["st"] = st
        s["pass_full"] = rule(s, base)
        s["pass_halves"] = [rule(a, b) for a, b in zip(s["h"], res["baseline"]["h"])]
        s["neigh"] = {}
        for nn, kw in NEIGH.items():
            nv, _ = run_arm(D, R, BET, arm, sleeve_ret, **kw)
            q = s3(nv)
            s["neigh"][nn] = {**{k: q[k] for k in ("cagr", "sharpe", "mdd")}, "pass": rule(q, base)}
        s["improves"] = bool(s["pass_full"] and all(s["pass_halves"]) and all(v["pass"] for v in s["neigh"].values()))
        res[arm] = s
        M.log(f"{arm:<10} {s['cagr'] * 100:5.1f} % / {s['sharpe']:.2f} / {s['mdd'] * 100:5.1f} % | H {[(round(x['cagr'] * 100, 1), round(x['sharpe'], 2)) for x in s['h']]} "
              f"| full {s['pass_full']} halves {s['pass_halves']} | nb " + " ".join(f"{k}:{v['cagr'] * 100:.1f}/{v['sharpe']:.2f}/{v['mdd'] * 100:.1f}/{v['pass']}" for k, v in s["neigh"].items())
              + f" | turnover {st['turnover']:.1f}x rebal {st['rebal_n']} shrunk {st['shrunk']} skipped {st['skipped']} | {time.time() - t_start:.0f}s")
    # ---- Rp 200 M ----
    nav200, st200 = engine(D, R, capital=200_000_000.0)
    res["cap200"] = {"baseline": {**s3(nav200), "turnover": st200["turnover"]}}
    for arm in ARMS:
        nv, stv = run_arm(D, R, BET, arm, sleeve_ret, capital=200_000_000.0)
        q = s3(nv)
        res["cap200"][arm] = {**q, "turnover": stv["turnover"], "rebal_n": stv["rebal_n"], "rebal_skip_lot": stv["rebal_skip_lot"], "rebal_cost": stv["rebal_cost"],
                              "pass": rule(q, res["cap200"]["baseline"])}
        M.log(f"Rp200M {arm:<10} {q['cagr'] * 100:5.1f} % / {q['sharpe']:.2f} / {q['mdd'] * 100:5.1f} % (base {res['cap200']['baseline']['cagr'] * 100:.1f} / "
              f"{res['cap200']['baseline']['sharpe']:.2f} / {res['cap200']['baseline']['mdd'] * 100:.1f}) rebal {stv['rebal_n']} skip-lot {stv['rebal_skip_lot']}")
    pickle.dump(res, open(os.path.join(ROOT, "tmp", "fe_cov_results.pkl"), "wb"))
    M.log(f"done in {time.time() - t_start:.0f}s")
    return 0


def f3(s):
    return f"{s['cagr'] * 100:.1f} % / {s['sharpe']:.2f} / {s['mdd'] * 100:.1f} %"


def report() -> int:
    import psycopg
    from blackheart_ingest.idx import research_store as rs
    res = pickle.load(open(os.path.join(ROOT, "tmp", "fe_cov_results.pkl"), "rb"))
    b = res["baseline"]
    n_after = N_BEFORE + len(TRIAL_IDS)
    L = [f"# IDX FE-1 - covariance-aware portfolio construction - 2026-09-26 - {len(TRIAL_IDS)} trials, cumulative N {N_BEFORE} -> {n_after}", "",
         "Script `research/idx_fe_covariance.py` (pre-registration in its docstring). Deployed combo book (gap 10 / trend 5 / ML ens4 5 % of NAV "
         "per trade, 20 slots, lots of 100, Rp 20 M, cash floor 30 %), #192 engine and trades, 2022-01-01 -> 2026-09-16. "
         "Covariance: Ledoit-Wolf, 120 sessions, returns through the previous close. Cells CAGR / Sharpe / mDD.", "",
         f"**Sanity gate:** re-run baseline {b['cagr'] * 100:.2f} % / {b['sharpe']:.3f} / {b['mdd'] * 100:.2f} % vs #192 (d) 33.8 % / 1.83 / -17.9 % - "
         "reproduced; the hooked engine equals `idx_construction.engine` to 1e-3 rupiah with no arm active. Gap events come through "
         "`idx_daytrade.load` (opens with open_src='idx' only).", "",
         "## Arms (same run, Rp 20 M)", "",
         "| trial | arm | full | H1 | H2 | N60 | N250 | NSHR | turnover /yr | ex-ante vol | beta | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|",
         f"| - | baseline (deployed) | {f3(b)} | {f3(b['h'][0])} | {f3(b['h'][1])} | - | - | - | {b['st']['turnover']:.1f}x | {b['st']['exante_vol'] * 100:.1f} % | "
         f"{b['st']['beta']:.2f} | reference |"]
    verdicts = {}
    for a in ARMS:
        s = res[a]
        st = s["st"]
        nb = s["neigh"]
        mark = lambda ok: "" if ok else " (x)"  # noqa: E731
        if s["improves"]:
            v = "IMPROVES"
        elif s["pass_full"] and all(s["pass_halves"]):
            v = "FRAGILE (neighbours disagree)"
        elif s["pass_full"]:
            v = "no (halves fail)"
        else:
            v = "no"
        verdicts[a] = v
        L.append(f"| {TRIAL_IDS[a]} | {a} | {f3(s)}{mark(s['pass_full'])} | {f3(s['h'][0])}{mark(s['pass_halves'][0])} | {f3(s['h'][1])}{mark(s['pass_halves'][1])} | "
                 + " | ".join(f"{f3(nb[k])}{mark(nb[k]['pass'])}" for k in ("N60", "N250", "NSHR"))
                 + f" | {st['turnover']:.1f}x | {st['exante_vol'] * 100:.1f} % | {st['beta']:.2f} | **{v}** |")
    L += ["", "(x) = fails the reading rule on that cell. Neighbour families 951 N60, 952 N250, 953 NSHR (fixed shrinkage 0.5 / beta 0.5b+0.5).", "",
          "## Mechanics and costs", "",
          "| arm | entries shrunk | entries skipped | days rationed | days re-ordered | re-weights | re-weight value | re-weight cost (fees+spread) | skipped: band | skipped: < 1 lot |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for a in ["baseline"] + ARMS:
        st = res[a]["st"]
        L.append(f"| {a} | {st['shrunk']} | {st['skipped']} | {st['rationed_days']} | {st['reordered_days']} | {st['rebal_n']} | Rp {st['rebal_value'] / 1e6:.1f} M | "
                 f"Rp {st['rebal_cost'] / 1e6:.2f} M | {st['rebal_skip_band']} | {st['rebal_skip_lot']} |")
    L += ["", "Sleeve weights chosen by B (per-trade % of NAV gap/trend/ML, first session of the month; deployed until 120 sessions exist):", ""]
    for a in ("B1_rp", "B2_mv", "B3_md"):
        lg = res[a]["st"]["pct_log"]
        pick = [x for x in lg if x[0][5:7] in ("01", "07")]
        L.append(f"- {a}: " + ", ".join(f"{d_[:7]} {p['gap'] * 100:.1f}/{p['trend'] * 100:.1f}/{p['ML'] * 100:.1f}" for d_, p in pick))
    c2 = res["cap200"]
    L += ["", "## Rp 200 M (same trades, liquidity not modelled; lots bind 10x less)", "", "| arm | CAGR / Sharpe / mDD | vs Rp 200 M baseline | turnover | re-weights | skipped < 1 lot | re-weight cost |",
          "|---|---|---|---|---|---|---|", f"| baseline | {f3(c2['baseline'])} | reference | {c2['baseline']['turnover']:.1f}x | - | - | - |"]
    for a in ARMS:
        q = c2[a]
        L.append(f"| {a} | {f3(q)} | {'passes rule' if q['pass'] else 'no'} | {q['turnover']:.1f}x | {q['rebal_n']} | {q['rebal_skip_lot']} | Rp {q['rebal_cost'] / 1e6:.2f} M |")
    imp = [a for a in ARMS if verdicts[a] == "IMPROVES"]
    L += ["", "## Verdict", "", "Improves the deployed book (rule: (Sharpe +0.15, mDD not deeper by > 1 pp, CAGR >= 0.9x) or (mDD >= 3 pp shallower, "
          "CAGR >= 0.9x), full + both halves + all three neighbours): " + (", ".join(imp) if imp else "**none**") + ".", "",
          "- **C1 beta cap 0.50 is the only arm that passes on the full window** (mDD -17.9 -> -13.2 %, Sharpe +0.08, CAGR 0.97x) and all three "
          "neighbours pass (N60 -11.5 %, N250 -12.9 %, NSHR -12.5 %). It FAILS half 1 by the letter: slightly better on every metric "
          "(15.0 / 1.33 / -10.0 vs 14.5 / 1.25 / -10.5) but not by the bar. The whole mDD gain is 2026: both books' mDD is the same "
          "4-session crash (2026-01-27 -> 02-02), and the deepest drawdown after it goes -14.9 -> -11.8 %. Before 2026 the mDD goes -10.5 -> -10.0 % "
          "(N60: -11.4 %, worse). At Rp 200 M: mDD -16.6 -> -13.3 % but CAGR 0.896x (bar 0.9x), so it fails. Verdict **PARTIAL: do not wire**. "
          "Re-test after 6 more months of live data; if a second high-beta selloff shows the same cut, it becomes a one-line entry check.",
          "- A1 MRC cap and A2 ERC cut ex-ante vol (11.4 -> 9.2 / 10.4 %) but pay for it in CAGR. ERC's weekly re-weights cost Rp 1.5 M at "
          "Rp 20 M (539 trades, 1,566 skipped by the band, 59 below one lot) and Rp 16.4 M at Rp 200 M. Diversifying the holdings does not "
          "raise this book's return per unit of risk.",
          "- A3 min-variance tilt changes the order on 119 days, but the floor rations only ~27 days, so it moves nothing (34.0 vs 33.8 %). "
          "At Rp 200 M it reads 40.6 / 2.05 vs 38.4 / 1.97, which is still below the bar.",
          "- B (sleeve RP / MV / MD, walk-forward) moves size to gap-fade (up to 20 % per trade in 2023-24) and loses Sharpe. The sleeves are "
          "nearly uncorrelated already, so a covariance adds nothing over the deployed 10/5/5.",
          "- C2 sector cap 25 % binds only 12 times. Its neighbours are degenerate (a sector cap has no window or shrinkage), so they repeat the arm.",
          "- Baseline book beta averages 0.36 and ex-ante vol 11.4 %/yr. The book is already a low-beta, diversified book, which is why "
          "covariance-aware construction has little left to take."]
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))
    if os.environ.get("FE_NOSTORE"):
        return 0
    summ = {a: {k: v for k, v in res[a].items() if k != "st"} | {"st": {k: v for k, v in res[a]["st"].items() if k != "pct_log"}} for a in ["baseline"] + ARMS}
    for a in ("B1_rp", "B2_mv", "B3_md"):
        summ[a]["pct_log"] = res[a]["st"]["pct_log"]
    with psycopg.connect(K.dsn()) as conn:
        sid = rs.record_study(conn, STUDY, date(2026, 9, 26),
                              params={"n_trials_cumulative": n_after, "n_trials_before": N_BEFORE, "trials_added": len(TRIAL_IDS), "trial_ids": TRIAL_IDS,
                                      "arms": ARMS, "neighbours": NEIGH, "deployed": PCT, "cash_floor": FLOOR, "slots": CR.MAX_POS, "capital": CR.CAPITAL,
                                      "window": [str(CR.START.date()), str(CR.END.date())], "cov": "ledoit_wolf, 120 sessions, returns through t-1",
                                      "mrc": [MRC_MIN, MRC_MULT], "erc": {"every": ERC_EVERY, "band": ERC_BAND, "cap": ERC_CAP}, "beta_cap": BETA_CAP,
                                      "sector_cap": SECTOR_CAP, "env": {"IDX_BOARD_MODE": "pit", "IDX_EXIT_CACHE": "tmp/exit_cache_pit.pkl", "IDX_ML_CACHE": "tmp/ml_strategy_cache.pkl"}},
                              summary=common.plain({"arms": summ, "cap200": c2, "verdicts": verdicts, "improves": imp}),
                              names=[], report_path=OUT, note="FE-1 covariance-aware construction (MRC cap, ERC, min-var tilt, sleeve RP/MV/MD, beta/sector caps)")
    M.log(f"study #{sid} stored; report {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(report() if os.environ.get("FE_REPORT") else main())
