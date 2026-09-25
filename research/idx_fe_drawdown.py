#!/usr/bin/env python3
"""Planning drawdown of the deployed combo (added to IDX_FE_KELLY_RL_2026-09-26.md section 1b; measurement, not a trial).
Step 1 rebuilds the #192 corrected combo NAV (variant d) exactly as idx_engine_fix.main does, WITHOUT writing a study row.
Step 2: stationary block bootstrap (20-day blocks, 4,000 paths, seed 7) of the demeaned daily log returns, re-drifted to the
backtest CAGR, the planning CAGR (backtest x the deployed-size posterior/raw ratio from FE-3) and zero; max drawdown per path.
Env: INGEST_DB_DSN (idx-local.env); uses tmp/exit_cache_pit.pkl and tmp/ml_strategy_cache.pkl."""
import os, sys, pickle
NAV_PKL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp", "fe_drawdown_nav.pkl")
os.environ["IDX_BOARD_MODE"] = "pit"
sys.path.insert(0, r"C:\Project\research")
import numpy as np
import idx_engine_fix as F
from idx_engine_fix import FG, M, K, CR
d = FG.dsn()
P = pickle.load(open(F.ML_CACHE, "rb"))
P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
dates = M.wide(P, "close").index; codes = M.wide(P, "close").columns
g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)
A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
liq = g("liq").fillna(False).astype(bool).to_numpy()
ml = K.ml_ens_trades(P, dates, codes, A, raw, offer, bid, liq); del P
gap, o = K.gap_events(d, dates)
cache, board, legacy = F.VARIANTS["d_fixed"]
cs = set(codes)
tr = [dict(y, tag="p", frac=1.0) for y in CR.trend_trades(d, dates, cache=cache, board=board, legacy_shift=legacy) if y["code"] in cs]
nav, _, _ = F.engine_attr(dates, codes, A, raw, offer, bid, ml + tr, gap)
print(F.st(nav))
pickle.dump(nav, open(NAV_PKL, "wb"))

# ---- step 2: bootstrap ----
r = np.log(nav).diff().dropna().to_numpy()
T = 245
def mdd(x):
    c = np.cumsum(x); peak = np.maximum.accumulate(np.concatenate([[0], c]))[1:]
    return np.min(np.exp(c - peak) - 1)
bt_cagr = np.exp(r.mean() * T) - 1
# planning CAGR of the combo: the sleeves' posterior/raw ratio at deployed size (FE-3): (8.6+6.0+5.4)/(12.8+12.7+9.8)
ratio = (8.6 + 6.0 + 5.4) / (12.8 + 12.7 + 9.8)
plan_cagr = bt_cagr * ratio
print(f"backtest CAGR {bt_cagr:.1%}  vol {r.std()*np.sqrt(T):.1%}  realised mDD {mdd(r):.1%}  planning CAGR {plan_cagr:.1%}")
rng = np.random.default_rng(7)
def boot(mu_ann, years, n=4000, block=20):
    x = r - r.mean() + np.log(1 + mu_ann) / T
    L = years * T; out = np.empty(n)
    for i in range(n):
        idx = []
        while len(idx) < L:
            s = rng.integers(0, len(x)); idx.extend(range(s, min(s + block, len(x))))
        out[i] = mdd(x[np.array(idx[:L])])
    return out
for label, mu in (("backtest drift", bt_cagr), ("planning drift", plan_cagr), ("zero edge", 0.0)):
    for yrs in (1, 3, 5):
        d = boot(mu, yrs)
        print(f"{label:15s} {yrs}y  median {np.median(d):6.1%}  1-in-4 {np.percentile(d,25):6.1%}  1-in-10 {np.percentile(d,10):6.1%}  1-in-20 {np.percentile(d,5):6.1%}")
