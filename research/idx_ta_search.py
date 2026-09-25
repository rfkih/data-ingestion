#!/usr/bin/env python3
"""IDX menu 43 - an edge from the desk's own technical indicators, alone or combined (operator 2026-09-25: "find any edge with all
the tools we have - combine correlated or uncorrelated technical indicators").

Indicators: the 55 research readings of the web chart's catalog (blackheart-idx-web/src/lib/ta/catalog.ts), ported 1:1 in
research/idx_ta_lib.py at DEFAULT parameters (all 79 TS plots reproduced to machine precision on BBCA; packing checked on GOTO
and ASPI), computed on split-adjusted OHLC (volume / adj_factor), each name over the bars it has (as the chart does).
Universe: LIQ with the point-in-time board (IDX_BOARD_MODE=pit, #192; cache tmp/exit_cache_pit.pkl).

PRE-REGISTERED (written 2026-09-25 before any number of this study was seen; nothing below is tuned afterwards).
Counting: ledger max before this run = 916 (#192 engine_fix; the caller quoted 915, range 915..944) -> counted trials 917..944,
at most 28. Every stage-1 rule evaluated in-sample and eligible for selection is ONE counted trial.

STAGE 0 - screening (NOT counted). IN-SAMPLE ONLY: every panel is CUT at 2023-12-29 before anything is computed, so no
  forward return can reach 2024. Days 2020-07-01 .. 2023-12-29 (warm-up before), LIQ names of the day.
  (a) daily cross-sectional rank IC of each reading vs the forward return h = 5 / 10 / 20 sessions from the next close
      (entry close t+1 -> close t+1+h, adjusted); mean IC and t = mean / sd x sqrt(days / h) (overlap-adjusted).
      Hurdle: Q5 = the top fifth by the reading oriented by the sign of its IC; Q5 excess = its mean forward return minus the
      LIQ mean; hurdle = 2 x the Q5 names' real round trip (closing offer in + closing bid out + Stockbit fees). CLEARS if
      Q5 excess > hurdle.
  (b) correlation matrix = pooled within-day rank correlation (every 5th day); families = average-linkage hierarchical
      clustering on 1 - |corr|, cut at distance 0.5 (a family = readings whose average |corr| >= 0.5).
  (c) redundancy vs the ML daily model: its 30 price / volume / tape features (ret1..ret250, dist_ma20/50/200, vol20/60,
      atr_pct, pos20, dist_hi252, dist_lo252, volr1, volr5, lvalue20/60, gap, clv, up_days, freq_ratio, spread_bps, bo_imb,
      fnet1/5/20, lmcap, free_float) from tmp/ml_strategy_cache.pkl. Per day: regress the reading's rank on the features'
      ranks (OLS, NaN -> median rank); R2 = how much of the reading the ML already sees; partial IC = rank IC of the residual.
      REDUNDANT if mean R2 >= 0.80. NEW INFORMATION if |partial IC t| >= 3 at h = 5, 10 or 20 (overlap-adjusted t).
STAGE 1 - design, IN-SAMPLE 2020-07-01 .. 2023-12-29 (same cut). Book: idx_exit.run_book, K = 10 equal slots, signal at close
  t, entry at close t+1 paying the closing offer + 0.10 %, exit at a close receiving the closing bid + 0.20 % (S.costs), no
  lots here (lots / rupiah only in the combo). Candidates ranked by the rule's own oriented score when > free slots.
  Rule templates (only the catalog's own levels are used as thresholds, no tuning):
    (i)   single family: the family representative (member with the largest |IC10 t|) in its IC-sign state;
    (ii)  AND of two UNcorrelated families (|corr| < 0.3 between representatives);
    (iii) agreement of 2-3 CORRELATED momentum readings (all in the same state);
    (iv)  equal-weight composite: mean of the within-day z-scores of the family representatives (each oriented by its IC10
          sign), enter the top 10 of LIQ each day the composite ranks them (no fitted weights);
    (v)   a family state as a FILTER on (a) the deployed trend entry (60-day high / > MA200 / vol >= 1.5x, small universe,
          IHSG gate, trail10) and (b) the ML ens4 cost-aware entries (idx_construction.ml_ens_trades path, liq & filter);
          ML in-sample = 2022-01 .. 2023-12 only (the combo's start).
  States: strength side = above the catalog's upper level (RSI > 70, MFI > 80, Stoch / StochRSI > 80, CCI > 100, %R > -20,
    UO > 70, CMO > 50, Fisher > 1.5, %B > 1, band position > 1, ADX > 25, CHOP < 38.2) or > 0 for unbounded / signed ones
    (price vs a line, MACD / PPO / TSI / TRIX / ROC / MOM / AO / Coppock / DPO / BoP / CMF / flows, DI / Aroon / Vortex spreads);
    weakness side = below the lower level (RSI < 30, MFI < 20, Stoch / StochRSI < 20, CCI < -100, %R < -80, UO < 30,
    CMO < -50, Fisher < -1.5, %B / band position < 0, ADX < 20, CHOP > 61.8) or < 0. Donchian position: >= 0.95 / <= 0.05.
    Volume ratio: > 1.5 / < 0.7. Mass index: > 27 / < 25. Volatility readings (ATR%, StdDev%, HV, BBW): top / bottom fifth of
    LIQ that day.
  Exit by rule type (fixed, not searched): any strength / trend / breakout leg -> trail10 (the trend book's exit); all legs on
  the weakness (mean-reversion) side -> hold 10 sessions; composite -> hold 20; filters keep their host's exit.
  SELECTION (frozen before stage 2): standalone rules (i)-(iv) need >= 100 closed in-sample trades; the best 2 by in-sample
  Sharpe after costs with Sharpe >= 0.5 become finalists; plus the best filter (v) if it raises its host's in-sample Sharpe
  by >= 0.10 with CAGR >= 0.9 x the host's and keeps >= 40 % of its trades. At most 3 finalists, written to
  research-scratch/ta_frozen.json and into STAGE1_FROZEN below before stage 2 runs.
STAGE 2 - the counted test, ONCE per finalist. Out-of-sample 2024-01-02 .. 2026-09-16 (entries from 2024-01-02 only), and
  for price/volume-only rules 2005-01-01 .. 2019-12-31 on the Yahoo survivors (research-scratch/idx/*.JK.csv, as #46: flat
  0.30 % half-spread + fees, LIQ / small by 60-day median value on adjusted prices; trend-filter host = the ungated trend rule
  on small, as #46).
  Battery (standalone rules; filters read the same way on their host's delta):
    P placebo: 200 books with random LIQ entries at the rule's own daily entry count, same exit and K; PASS if the rule's
      OOS Sharpe >= the 95th pct (filters: 200 random filters dropping the same share of host entries; PASS if delta Sharpe
      >= 95th pct).
    N neighbours: all indicator lengths x 0.75 / x 1.25; thresholds moved 25 % closer to / further from their midline (for
      rules whose thresholds are all signs (0) the two level-neighbours are the exit param +/- 25 %: hold 8 / 12 or 13 / 25,
      trail 7.5 / 12.5 %); a neighbour PASSES if its OOS Sharpe >= the placebo 90th pct (filters: delta Sharpe > 0);
      PASS if >= 3/4.
    T time: OOS calendar years 2024 / 2025 / 2026 positive in >= 2/3 AND (price/volume rules) 2005-2019 Sharpe >= the
      random-entry reference + 0.3 with >= 9/15 positive years.
    C costs x 1.5: OOS CAGR > 0 (filters: delta Sharpe > 0).   D 1-day-late entry: OOS CAGR > 0 and Sharpe >= 0.5 x on time.
    M deflated Sharpe at cumulative N (916 + counted) and at the stage-1 search size (reported, not a gate).
  VERDICT: CLOSED if OOS Sharpe <= 0 or below the placebo median; else ROBUST if P, N, T pass (C / D reported); PARTIAL if one
    of P/N/T fails (P passing); FRAGILE if P fails or two fail.
  Combo effect (not a trial, pre-set mode): standalone finalist = a 4th sleeve at 5 % of NAV per trade (its own K-10 trades,
    replayed after trend and ML at the close); filter finalist = replaces its host's trade list. Corrected #192 engine
    (idx_construction.engine, gap 10 / trend 5 / ML ens4 5 %, 20 slots, floor 30 %, Rp 20 M, 2022-01 -> 2026-09-16), same-run
    pair vs the re-run baseline (must reproduce 33.8 % / 1.83 / -17.9 %); read on the full window AND on 2024+ only.
    Correlation of the finalist sleeve's daily returns with each deployed sleeve alone.
ADDENDUM A (written after stage 0, before stage 1 ran; in-sample numbers only were seen):
  Families at the 0.5 cut (8): F1 volatility {atr, stdev, hv, bbw} rep ATR% (IC10 t -4.3 -> low side); F2 {chop} (t +1.9 ->
  high side); F3 {adx} (t -0.1 -> low side); F4 {volume, volosc} rep volume ratio (t +1.9 -> high); F5 {alma, hma, netvol,
  bop} rep ALMA (t +1.2 -> high); F6 {ichimoku, trix} rep Ichimoku (t +2.4 -> high); F7 the other 40 (price vs every MA /
  band / SAR / Supertrend / pivots, all oscillators, all flows) rep UO (t +3.0 -> high); F8 {mass} (t +2.7 -> high).
  Rep correlations < 0.3 (uncorrelated) include uo-atr -0.21, uo-chop +0.03, uo-adx +0.04, uo-volume +0.16, uo-mass +0.24,
  ichimoku-volume +0.04, atr-volume -0.10, adx-ichimoku +0.22.
  THE 26 COUNTED STAGE-1 RULES (ids 917..942). Exit: T = trail10, H10 / H20 = hold. Non-directional single legs (volatility,
  chop, adx-low, volume, mass) are not strength/trend legs -> hold 10.
   (i)   R01 atr_lo (ATR% bottom fifth) H10 | R02 chop_hi (> 61.8) H10 | R03 adx_lo (< 20) H10 | R04 volume_hi (> 1.5x) H10 |
         R05 alma_hi (C > ALMA 9) T | R06 ichimoku_hi (C > cloud) T | R07 uo_hi (UO > 70) T | R08 mass_hi (> 27) H10
   (ii)  R09 adx_hi & uo_lo (trend strength + oscillator pullback) T | R10 ichimoku_hi & volume_hi T | R11 atr_lo & volume_hi
         (quiet name, volume spike) H10 | R12 atr_lo & uo_hi (squeeze + buying pressure) T | R13 uo_hi & volume_hi T |
         R14 mass_hi & uo_hi T | R15 chop_lo (< 38.2) & uo_hi T | R16 adx_hi & ichimoku_hi T
   (iii) R17 rsi_hi & stoch_hi & uo_hi (3 overbought = persistence) T | R18 rsi_lo & stoch_lo & uo_lo (3 oversold) H10 |
         R19 cmf > 0 & chaikinosc > 0 & ad > 0 (the three flow readings with the best partial IC) T
   (iv)  R20 composite of the 8 reps (within-day z, oriented by IC10 sign, equal weight), top 10 of LIQ daily, H20
   (v)   trend host: R21 & cmf > 0 | R22 & mass_hi | R23 & atr_lo ; ML ens4 host: R24 & cmf > 0 | R25 & mass_hi | R26 & atr_lo
  Score when candidates > free slots: mean within-day LIQ rank of the legs' IC-oriented readings.
  Neighbour detail: hold 20 +/- 25 % = 15 / 25 (not 13); a FILTER whose threshold is a sign (0) moves it to +/- 0.25 x the
  reading's pooled in-sample LIQ standard deviation (host exit unchanged).
STAGE1_FROZEN (written after stage 1, BEFORE stage 2 ran; research-scratch/ta_frozen.json holds the same):
  Search size 26 rules (all counted: ids 917..942, cumulative N = 942). R08 / R14 / R22 / R25 (mass > 27) had 0 trades - at the
  catalog's default length 10 the Mass Index sits near 10, so the classic 27 bulge is unreachable; they stay counted, not fixed.
  In-sample references: random LIQ entries + trail10 Sharpe 0.03, + hold10 -0.74; trend host 1.27 (27.9 %, 254 trades);
  ML ens4 host 2022-23 1.76 (20.8 %).
  F1 = R10  Ichimoku (9/26/52/26) close above the displaced cloud top AND volume > 1.5 x its 20-bar SMA; LIQ (pit), K 10,
            score = mean LIQ rank of (close / cloud top - 1, volume ratio); trail10. IS: 351 trades, 42.5 % / 1.52 / -38.5 %
            (years 20 +29, 21 +149, 22 -3, 23 +8). Neighbours: lengths x0.75 / x1.25 (Ichimoku and the volume MA); volume
            level 1.375 / 1.625.
  F2 = R05  close above ALMA (9, 0.85, 6); LIQ, K 10, score = LIQ rank of close / ALMA - 1; trail10. IS: 459 trades, 40.1 % /
            1.40 / -50.5 % (20 +30, 21 +116, 22 -15, 23 +32). Neighbours: ALMA 7 / 11; exit trail 7.5 % / 12.5 %.
  F3 = R21  deployed trend entry (small, IHSG gate, trail10) AND CMF(20) > 0. IS: 240 of 254 host trades (94 %), 38.5 % / 1.70
            / -15.8 % vs host 27.9 % / 1.27 / -15.3 % (delta Sharpe +0.43). Neighbours: CMF 15 / 25; threshold +/- 0.25 x
            in-sample sd (0.2186) = +/- 0.0546.
  Mode in the combo (pre-set): F1, F2 = 4th sleeve at 5 % of NAV per trade; F3 = replaces the trend sleeve's trade list.
  F3 filter battery in detail: P = 200 random filters keeping each host entry-signal with the same probability as CMF > 0
  did over the OOS window, PASS if the real delta Sharpe >= their 95th pct; T = (filtered - host) calendar-year return > 0 in
  >= 2/3 OOS years AND delta Sharpe > 0 on 2005-2019 Yahoo (ungated trend on small, as #46); C / D = delta Sharpe > 0 at costs
  x 1.5 / with both books one day late.
READ-ONLY on market tables; one idx.study row ('ta_search'). No commits. Shared engine files are imported, not edited.
Run: IDX_BOARD_MODE=pit python research/idx_ta_search.py stage0 | stage1 | stage2
"""
from __future__ import annotations

import json
import math
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
os.environ.setdefault("IDX_BOARD_MODE", "pit")
os.environ["IDX_EXIT_CACHE"] = os.path.join(ROOT, "tmp", "exit_cache_pit.pkl")
os.environ.setdefault("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_ta_lib as TA  # noqa: E402

PIT_CACHE = os.environ["IDX_EXIT_CACHE"]
ML_CACHE = os.environ["IDX_ML_CACHE"]
SCR = os.path.join(ROOT, "research-scratch")
N_BEFORE = 916
MAX_TRIALS = 28
IS_START, IS_END = pd.Timestamp("2020-07-01"), pd.Timestamp("2023-12-29")
OOS_START, OOS_END = pd.Timestamp("2024-01-02"), pd.Timestamp("2026-09-16")
HORIZONS = (5, 10, 20)
ML_FEATS = ["ret1", "ret5", "ret20", "ret60", "ret120", "ret250", "dist_ma20", "dist_ma50", "dist_ma200", "vol20", "vol60", "atr_pct",
            "pos20", "dist_hi252", "dist_lo252", "volr1", "volr5", "lvalue20", "lvalue60", "gap", "clv", "up_days", "freq_ratio",
            "spread_bps", "bo_imb", "fnet1", "fnet5", "fnet20", "lmcap", "free_float"]
SEED = 20260925


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    import re
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    os.environ["INGEST_DB_DSN"] = env["INGEST_DB_DSN"].strip().strip('"')
    return os.environ["INGEST_DB_DSN"]


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.now():%H:%M:%S}] {msg}", flush=True)


# ---- data ------------------------------------------------------------------------------------------------------------------
def load_panels(cut: pd.Timestamp | None):
    """IDX panels (pit board). cut: drop every row after this date BEFORE anything is computed (in-sample guard)."""
    P, unis, comp, Hp, Lp = E.load_all(dsn(), PIT_CACHE, board="pit")
    adj = P["adj"]
    with psycopg.connect(dsn()) as conn:
        # opens back-filled from Yahoo (open_src='yahoo') are chart data, not IDX opening prints: keep them out
        o = pd.DataFrame(conn.execute("SELECT code, trade_date, (CASE WHEN open_src = 'idx' THEN open END)::float8 AS open, adj_factor::float8 FROM idx.bar WHERE source = 'idx'").fetchall(),
                         columns=["code", "d", "open", "af"])
    o["d"] = pd.to_datetime(o["d"])
    Op = o.pivot(index="d", columns="code", values="open").reindex(index=adj.index, columns=adj.columns)
    AF = o.pivot(index="d", columns="code", values="af").reindex(index=adj.index, columns=adj.columns).fillna(1.0)
    X = {"adj": adj, "close": P["close"], "H": Hp, "L": Lp, "O": Op * (adj / P["close"]), "V": P["volume"] / AF.where(AF > 0, 1.0),
         "bid": P["bid"], "offer": P["offer"], "LIQ": unis["LIQ"], "BLUE": unis["BLUE"], "v60": P["v60"], "Vraw": P["volume"]}
    if cut is not None:
        X = {k: v.loc[:cut] for k, v in X.items()}
        comp = comp.loc[:cut]
    X["comp"] = comp
    return X


def ta_values(X, names=None, params=None, scale=1.0):
    dates = X["adj"].index
    return TA.compute(X["O"].to_numpy(float), X["H"].to_numpy(float), X["L"].to_numpy(float), X["adj"].to_numpy(float),
                      X["V"].to_numpy(float), dates, names=names, params=params, scale=scale)


def costs(X, mult=1.0):
    P = {"close": X["close"], "offer": X["offer"], "bid": X["bid"]}
    c_in, c_out = S.costs(P)
    if mult != 1.0:
        c_in, c_out = c_in * mult, c_out * mult
    return c_in, c_out


def fwd(A, h):
    T = A.shape[0]
    out = np.full_like(A, np.nan)
    if T > h + 1:
        out[: T - h - 1] = A[h + 1:] / A[1: T - h] - 1
    return out


# ---- stage 0 ---------------------------------------------------------------------------------------------------------------
def _rank_rows(M):
    return pd.DataFrame(M).rank(axis=1, pct=True).to_numpy()


def _row_corr(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    a = np.where(m, a, np.nan); b = np.where(m, b, np.nan)
    am = a - np.nanmean(a, axis=1, keepdims=True); bm = b - np.nanmean(b, axis=1, keepdims=True)
    num = np.nansum(am * bm, axis=1)
    den = np.sqrt(np.nansum(am ** 2, axis=1) * np.nansum(bm ** 2, axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = num / den
    r[m.sum(axis=1) < 30] = np.nan
    return r


def stage0():
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    X = load_panels(IS_END)
    dates, codes = X["adj"].index, X["adj"].columns
    assert dates.max() <= IS_END
    A = X["adj"].to_numpy(float)
    liq = X["LIQ"].to_numpy(bool)
    c_in, c_out = costs(X)
    log(f"panel {A.shape}, computing {len(TA.VALUE_NAMES)} readings")
    V = ta_values(X)
    day = (dates >= IS_START) & (dates <= IS_END)
    F = {h: fwd(A, h) for h in HORIZONS}
    sh = lambda M, k: np.vstack([M[k:], np.full((k, M.shape[1]), np.nan)])  # noqa: E731  (value at t+k)
    rt = {h: sh(c_in, 1) + sh(c_out, h + 1) for h in HORIZONS}          # entry close t+1 (offer), exit close t+1+h (bid)
    res = {}
    uni = liq & day[:, None]
    for nm in TA.VALUE_NAMES:
        v = np.where(uni & np.isfinite(V[nm]), V[nm], np.nan)
        rv = _rank_rows(v)
        r = {"coverage": float(np.isfinite(v).sum() / max(1, uni.sum()))}
        for h in HORIZONS:
            f = np.where(np.isfinite(v), F[h], np.nan)
            ic = _row_corr(rv, _rank_rows(f))
            ic = ic[np.isfinite(ic)]
            mu, sd = float(ic.mean()), float(ic.std())
            t = mu / sd * math.sqrt(len(ic) / h) if sd > 0 else 0.0
            sgn = 1.0 if mu >= 0 else -1.0
            q = (rv * sgn if sgn > 0 else 1 - rv)
            top = (q >= 0.8) & np.isfinite(f)
            allm = np.isfinite(f) & np.isfinite(v)
            with np.errstate(invalid="ignore"):
                ex = np.nanmean(np.where(top, f, np.nan), axis=1) - np.nanmean(np.where(allm, f, np.nan), axis=1)
                hur = 2 * np.nanmean(np.where(top, rt[h], np.nan), axis=1)
            r[f"ic{h}"], r[f"t{h}"], r[f"q5ex{h}"], r[f"hurdle{h}"] = mu, t, float(np.nanmean(ex)), float(np.nanmean(hur))
        res[nm] = r
        log(f"{nm:<11} IC5 {r['ic5']:+.3f} ({r['t5']:+.1f}) IC10 {r['ic10']:+.3f} ({r['t10']:+.1f}) IC20 {r['ic20']:+.3f} ({r['t20']:+.1f}) "
            f"Q5ex10 {r['q5ex10'] * 1e4:+.0f} bps vs hurdle {r['hurdle10'] * 1e4:.0f}")
    # (b) correlation matrix + families
    names = TA.VALUE_NAMES
    sample = np.flatnonzero(day)[::5]
    rows = []
    for t in sample:
        m = liq[t]
        blk = np.column_stack([V[nm][t, m] for nm in names])
        ok = np.isfinite(blk).all(axis=1)
        if ok.sum() < 30:
            continue
        R = pd.DataFrame(blk[ok]).rank(pct=True).to_numpy()
        rows.append(R - R.mean(axis=0))
    Z = np.vstack(rows)
    Cm = np.corrcoef(Z.T)
    D = 1 - np.abs(Cm)
    np.fill_diagonal(D, 0)
    Lk = linkage(squareform(D, checks=False), method="average")
    fam = fcluster(Lk, t=0.5, criterion="distance")
    # (c) partial IC vs the ML features
    ML = pickle.load(open(ML_CACHE, "rb"))
    ML = ML[(ML["d"] >= IS_START) & (ML["d"] <= IS_END)][["code", "d"] + ML_FEATS]
    ci = {c: i for i, c in enumerate(codes)}
    ti = {d: i for i, d in enumerate(dates)}
    ML = ML[ML["code"].isin(ci) & ML["d"].isin(ti)]
    feat = np.full((len(dates), len(codes), len(ML_FEATS)), np.nan, dtype=np.float32)
    feat[ML["d"].map(ti).to_numpy(), ML["code"].map(ci).to_numpy()] = ML[ML_FEATS].to_numpy(np.float32)
    del ML
    part = {nm: {h: [] for h in HORIZONS} for nm in names}
    r2 = {nm: [] for nm in names}
    for t in np.flatnonzero(day):
        m = liq[t] & np.isfinite(F[5][t])
        if m.sum() < 50:
            continue
        Xf = pd.DataFrame(feat[t, m].astype(float)).rank(pct=True).fillna(0.5).to_numpy()
        Xf = np.column_stack([np.ones(m.sum()), Xf])
        Y = pd.DataFrame(np.column_stack([V[nm][t, m] for nm in names])).rank(pct=True)
        okY = Y.notna().to_numpy()
        Y = Y.fillna(0.5).to_numpy()
        beta, *_ = np.linalg.lstsq(Xf, Y, rcond=None)
        res_ = Y - Xf @ beta
        ss = ((Y - Y.mean(axis=0)) ** 2).sum(axis=0)
        for k, nm in enumerate(names):
            if okY[:, k].sum() < 50:
                continue
            r2[nm].append(1 - (res_[:, k] ** 2).sum() / ss[k] if ss[k] > 0 else np.nan)
            for h in HORIZONS:
                f = F[h][t, m]
                ok = okY[:, k] & np.isfinite(f)
                if ok.sum() < 30:
                    continue
                a = pd.Series(res_[ok, k]).rank().to_numpy(); b = pd.Series(f[ok]).rank().to_numpy()
                part[nm][h].append(np.corrcoef(a, b)[0, 1])
    for nm in names:
        res[nm]["r2_ml"] = float(np.nanmean(r2[nm])) if r2[nm] else float("nan")
        for h in HORIZONS:
            x = np.array(part[nm][h])
            res[nm][f"pic{h}"] = float(x.mean()) if len(x) else float("nan")
            res[nm][f"pt{h}"] = float(x.mean() / x.std() * math.sqrt(len(x) / h)) if len(x) and x.std() > 0 else 0.0
        res[nm]["family"] = int(fam[names.index(nm)])
        res[nm]["group"] = TA.GROUP[nm]
        res[nm]["redundant_ml"] = bool(res[nm]["r2_ml"] >= 0.80)
        res[nm]["new_info"] = bool(max(abs(res[nm][f"pt{h}"]) for h in HORIZONS) >= 3)
    out = {"results": res, "names": names, "corr": Cm.tolist(), "family": fam.tolist(), "is": [str(IS_START.date()), str(IS_END.date())],
           "n_days": int(day.sum())}
    json.dump(out, open(os.path.join(SCR, "ta_stage0.json"), "w"))
    fams = {}
    for nm in names:
        fams.setdefault(res[nm]["family"], []).append(nm)
    for f_, mem in sorted(fams.items()):
        rep = max(mem, key=lambda n: abs(res[n]["t10"]))
        log(f"family {f_}: rep {rep} | " + ", ".join(f"{n}({res[n]['t10']:+.1f}/R2 {res[n]['r2_ml']:.2f}/pt10 {res[n]['pt10']:+.1f})" for n in mem))
    return out


# ---- states, books ------------------------------------------------------------------------------------------------------------
HI = {"rsi": 70, "mfi": 80, "stoch": 80, "stochrsi": 80, "cci": 100, "wpr": -20, "uo": 70, "cmo": 50, "fisher": 1.5, "bbpb": 1.0, "bb": 1.0,
      "kc": 1.0, "env": 1.0, "dc": 0.95, "adx": 25, "chop": 61.8, "volume": 1.5, "mass": 27}
LO = {"rsi": 30, "mfi": 20, "stoch": 20, "stochrsi": 20, "cci": -100, "wpr": -80, "uo": 30, "cmo": -50, "fisher": -1.5, "bbpb": 0.0, "bb": 0.0,
      "kc": 0.0, "env": 0.0, "dc": 0.05, "adx": 20, "chop": 38.2, "volume": 0.7, "mass": 25}
MID = {"rsi": 50, "mfi": 50, "stoch": 50, "stochrsi": 50, "cci": 0, "wpr": -50, "uo": 50, "cmo": 0, "fisher": 0, "bbpb": 0.5, "bb": 0.5, "kc": 0.5,
       "env": 0.5, "dc": 0.5, "adx": 0, "chop": 50, "volume": 1.0, "mass": 26}
VOLQ = {"atr", "stdev", "hv", "bbw"}                                    # read by cross-sectional fifth


def state(nm, v, side, liq, lvl=1.0):
    """side 'hi' = value above the upper level (or > 0), 'lo' = below the lower level (or < 0). lvl scales the threshold's
    distance from its midline (neighbours 0.75 / 1.25)."""
    with np.errstate(invalid="ignore"):
        if nm in VOLQ:
            r = pd.DataFrame(np.where(liq, v, np.nan)).rank(axis=1, pct=True).to_numpy()
            q = 0.2 * lvl
            return (r > 1 - q) if side == "hi" else (r <= q)
        if nm in HI:
            m = MID[nm]
            thr = m + ((HI if side == "hi" else LO)[nm] - m) * lvl
            return (v > thr) if side == "hi" else (v < thr)
        return (v > 0) if side == "hi" else (v < 0)


def xs_rank(v, liq):
    return pd.DataFrame(np.where(liq & np.isfinite(v), v, np.nan)).rank(axis=1, pct=True).to_numpy()


def exit_rule(A, kind, prm):
    if kind == "hold":
        H = int(prm)
        return lambda t, j, p: 1.0 if t - p["e"] >= H - 1 else 0
    x = float(prm)
    return lambda t, j, p: 1.0 if A[t, j] <= (1 - x) * p["peak"] else 0


def book(A, entry, score, uni, kind, prm, c_in, c_out, dates, lo, hi, H=None, L=None):
    """run_book with entries only on [lo, hi]; returns (daily R on [lo, end], trades)."""
    win = np.asarray((dates >= lo) & (dates <= hi))[:, None]
    H = A if H is None else H
    L = A if L is None else L
    R, trs, _ = E.run_book(A, H, L, c_in, c_out, entry & win, np.nan_to_num(score, nan=-1e9), exit_rule(A, kind, prm), uni)
    R.index = dates
    return R[R.index >= lo], trs


def st(R: pd.Series, trades=None) -> dict:
    R = R.fillna(0.0)
    eq = (1 + R).cumprod()
    yrs = max(len(R) / 250, 1e-9)
    sd = R.std()
    out = {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1) if eq.iloc[-1] > 0 else -1.0, "sharpe": float(R.mean() / sd * math.sqrt(250)) if sd > 0 else 0.0,
           "mdd": float((eq / eq.cummax() - 1).min()), "years": {int(y): float((1 + s).prod() - 1) for y, s in R.groupby(R.index.year)}}
    if trades is not None:
        n = np.array([t[3] for t in trades]) if trades else np.array([])
        out.update({"n": len(trades), "avg_net": float(n.mean()) if len(n) else 0.0, "hit": float((n > 0).mean()) if len(n) else 0.0})
    return out


def placebo_mask(entry, uni, rng):
    """Random names from uni, as many per day as the rule's own entry mask has."""
    T, N = entry.shape
    out = np.zeros_like(entry)
    cnt = (entry & uni).sum(axis=1)
    for t in np.flatnonzero(cnt):
        cand = np.flatnonzero(uni[t])
        if len(cand):
            out[t, rng.choice(cand, size=min(int(cnt[t]), len(cand)), replace=False)] = True
    return out


# ---- stage 1 ---------------------------------------------------------------------------------------------------------------
T_, H10, H20 = ("trail", 0.10), ("hold", 10), ("hold", 20)
RULES = [
    ("R01", "i", [("atr", "lo")], H10, None), ("R02", "i", [("chop", "hi")], H10, None), ("R03", "i", [("adx", "lo")], H10, None),
    ("R04", "i", [("volume", "hi")], H10, None), ("R05", "i", [("alma", "hi")], T_, None), ("R06", "i", [("ichimoku", "hi")], T_, None),
    ("R07", "i", [("uo", "hi")], T_, None), ("R08", "i", [("mass", "hi")], H10, None),
    ("R09", "ii", [("adx", "hi"), ("uo", "lo")], T_, None), ("R10", "ii", [("ichimoku", "hi"), ("volume", "hi")], T_, None),
    ("R11", "ii", [("atr", "lo"), ("volume", "hi")], H10, None), ("R12", "ii", [("atr", "lo"), ("uo", "hi")], T_, None),
    ("R13", "ii", [("uo", "hi"), ("volume", "hi")], T_, None), ("R14", "ii", [("mass", "hi"), ("uo", "hi")], T_, None),
    ("R15", "ii", [("chop", "lo"), ("uo", "hi")], T_, None), ("R16", "ii", [("adx", "hi"), ("ichimoku", "hi")], T_, None),
    ("R17", "iii", [("rsi", "hi"), ("stoch", "hi"), ("uo", "hi")], T_, None), ("R18", "iii", [("rsi", "lo"), ("stoch", "lo"), ("uo", "lo")], H10, None),
    ("R19", "iii", [("cmf", "hi"), ("chaikinosc", "hi"), ("ad", "hi")], T_, None),
    ("R20", "iv", "composite", H20, None),
    ("R21", "v", [("cmf", "hi")], None, "trend"), ("R22", "v", [("mass", "hi")], None, "trend"), ("R23", "v", [("atr", "lo")], None, "trend"),
    ("R24", "v", [("cmf", "hi")], None, "ML"), ("R25", "v", [("mass", "hi")], None, "ML"), ("R26", "v", [("atr", "lo")], None, "ML"),
]
assert len(RULES) <= MAX_TRIALS
RULE = {r[0]: r for r in RULES}
REPS = ["atr", "chop", "adx", "volume", "alma", "ichimoku", "uo", "mass"]
NEEDED = sorted({nm for r in RULES if r[2] != "composite" for nm, _ in r[2]} | set(REPS))
ENS4_ML = [(0.05, 10), (0.08, 10), (0.10, 10), (0.08, 5)]
ML_START = pd.Timestamp("2022-01-01")


def s0():
    return json.load(open(os.path.join(SCR, "ta_stage0.json")))


def sign_of(nm, S0):
    return 1.0 if S0["results"][nm]["ic10"] >= 0 else -1.0


def rule_mask(rule, V, liq, S0, lvl=1.0, shift=None, restrict=True):
    """Entry mask and score of a rule (legs AND-ed). shift: {name: threshold} for sign readings (filter neighbours)."""
    legs = rule[2]
    if legs == "composite":
        Z = []
        for nm in REPS:
            v = np.where(liq & np.isfinite(V[nm]), V[nm], np.nan) * sign_of(nm, S0)
            with np.errstate(invalid="ignore", divide="ignore"):
                mu, sd = np.nanmean(v, axis=1, keepdims=True), np.nanstd(v, axis=1, keepdims=True)
                Z.append((v - mu) / sd)
        Z = np.stack(Z)
        with np.errstate(invalid="ignore"):
            comp = np.nanmean(Z, axis=0)
        comp = np.where(np.isfinite(Z).sum(axis=0) >= 6, comp, np.nan)
        rk = pd.DataFrame(np.where(liq, comp, np.nan)).rank(axis=1, ascending=False).to_numpy()
        return (rk <= 10), np.nan_to_num(comp, nan=-1e9)
    m = liq.copy() if restrict else np.ones_like(liq)          # filters: any name; quintiles still ranked within LIQ
    sc = np.zeros(liq.shape)
    for nm, side in legs:
        v = V[nm]
        if shift and nm in shift:
            with np.errstate(invalid="ignore"):
                s_ = (v > shift[nm]) if side == "hi" else (v < shift[nm])
        else:
            s_ = state(nm, v, side, liq, lvl)
        m &= np.asarray(s_, bool) & np.isfinite(v)
        sc += np.nan_to_num(xs_rank(v * sign_of(nm, S0), liq), nan=0.0)
    return m, sc / len(legs)


def trend_entry(X, gate=True):
    """The deployed trend entry, exactly as CR.trend_trades (raw volume ratio)."""
    import idx_beyond as BY
    adj, vol = X["adj"], X["Vraw"]
    dates = adj.index
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(60, min_periods=60).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool)
    if gate:
        entry &= ~BY.regime_off_mask(X["comp"], dates)[:, None]
    small = (X["LIQ"] & ~X["BLUE"]).to_numpy(bool)
    return entry, vr.to_numpy(float), small


_MLW = {}


def ml_grid(cut):
    key = str(cut)
    if key not in _MLW:
        import idx_ml_costaware as C
        import idx_ml_strategy as M
        P = pickle.load(open(ML_CACHE, "rb"))
        P = P[(P["d"] >= "2021-06-01") & (P["d"] <= cut)].copy()
        dates, codes = M.wide(P, "close").index, M.wide(P, "close").columns
        g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
        A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
        offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
        liq = g("liq").fillna(False).astype(bool).to_numpy()
        S_ = g("s5").to_numpy(float)
        e5 = C.ema(S_ - np.nanmedian(np.where(liq, S_, np.nan), axis=1, keepdims=True), 3)
        _MLW[key] = {"dates": dates, "codes": codes, "A": A, "raw": raw, "offer": offer, "bid": bid, "liq": liq, "e5": e5}
    return _MLW[key]


def ml_host(filt, lo, hi, cut, cost_mult=1.0, delay=0):
    """ML ens4 cost-aware sleeve (4 rule-books, 1/4 each) on liq & filt; filt = DataFrame on any grid or None."""
    import idx_ml_confirm as F
    import idx_ml_strategy as M
    W = ml_grid(cut)
    dates, codes = W["dates"], W["codes"]
    mask = W["liq"].copy()
    if filt is not None:
        mask &= filt.reindex(index=dates, columns=codes).fillna(False).astype(bool).to_numpy()
    e5 = W["e5"]
    if delay:
        e5 = np.vstack([np.full((delay, e5.shape[1]), np.nan), e5[:-delay]])
        mask = np.vstack([np.zeros((delay, mask.shape[1]), bool), mask[:-delay]])
    c_in, c_out = M.costs(W["raw"], W["offer"], W["bid"])
    c_in, c_out = c_in * cost_mult, c_out * cost_mult
    t0 = int(np.searchsorted(dates, np.datetime64(lo)))
    Rs, n = [], 0
    for rule in ENS4_ML:
        R, lg = F.book(W["A"], mask, e5, 10, c_in, c_out, 2.0, t_start=t0, wait=rule)
        Rs.append(R)
        n += len(lg)
    R = pd.Series(np.mean(Rs, axis=0), index=dates)
    return R[(R.index >= lo) & (R.index <= hi)], n


def _delay(M_, k):
    return np.vstack([np.zeros((k,) + M_.shape[1:], M_.dtype), M_[:-k]]) if k else M_


def run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, lvl=1.0, exit_override=None, shift=None, delay=0, placebo_rng=None,
             filt_override=None, cost_mult=1.0):
    """Standalone -> (R, trades) on LIQ.  trend filter -> (R, trades) on small.  ML filter -> (R, n)."""
    host = rule[4]
    A = X["adj"].to_numpy(float)
    dates = X["adj"].index
    if host is None:
        m, sc = rule_mask(rule, V, liq, S0, lvl, shift)
        if placebo_rng is not None:
            m = placebo_mask(m, liq, placebo_rng)
            sc = placebo_rng.random(m.shape)
        m, sc = _delay(m, delay), _delay(sc, delay)
        kind, prm = exit_override or rule[3]
        return book(A, m, sc, liq, kind, prm, c_in, c_out, dates, lo, hi)
    fm = filt_override if filt_override is not None else rule_mask(rule, V, liq, S0, lvl, shift, restrict=False)[0]
    if host == "trend":
        entry, vr, small = trend_entry(X)
        return book(A, _delay(entry & fm, delay), _delay(vr, delay), small, "trail", 0.10, c_in, c_out, dates, lo, hi)
    return ml_host(pd.DataFrame(fm, index=dates, columns=X["adj"].columns), lo, hi, dates.max(), cost_mult=cost_mult, delay=delay)


def stage1():
    S0 = s0()
    X = load_panels(IS_END)
    assert X["adj"].index.max() <= IS_END
    dates = X["adj"].index
    liq = X["LIQ"].to_numpy(bool)
    c_in, c_out = costs(X)
    log(f"readings {NEEDED}")
    V = ta_values(X, names=NEEDED)
    A = X["adj"].to_numpy(float)
    res = {}
    rng = np.random.default_rng(SEED)
    ref = {}
    for ex in (T_, H10, H20):                                  # references, not trials
        Rr, _, _ = E.run_book(A, A, A, c_in, c_out, None, None, exit_rule(A, *ex), liq & np.asarray(dates >= IS_START)[:, None], rng=rng)
        Rr.index = dates
        ref[f"random_{ex[0]}{ex[1]}"] = st(Rr[Rr.index >= IS_START])
    entry, vr, small = trend_entry(X)
    Rh, th = book(A, entry, vr, small, "trail", 0.10, c_in, c_out, dates, IS_START, IS_END)
    ref["host_trend"] = st(Rh, th)
    Rm, nm_ = ml_host(None, ML_START, IS_END, IS_END)
    ref["host_ML"] = dict(st(Rm), n=nm_)
    log("refs " + " | ".join(f"{k} {v['sharpe']:.2f}/{v['cagr'] * 100:.1f}%" for k, v in ref.items()))
    inis = liq & np.asarray(dates >= IS_START)[:, None]
    sd = {nm: float(np.nanstd(np.where(inis, V[nm], np.nan))) for nm in NEEDED}
    for rule in RULES:
        rid, typ, legs, ex, host = rule
        if host == "ML":
            R, n = run_rule(rule, X, V, liq, S0, ML_START, IS_END, c_in, c_out)
            r = dict(st(R), n=n)
        else:
            R, trs = run_rule(rule, X, V, liq, S0, IS_START, IS_END, c_in, c_out)
            r = st(R, trs)
        if host:
            r["host"] = ref[f"host_{host}"]
            r["keep"] = r["n"] / max(1, r["host"]["n"])
            r["d_sharpe"] = r["sharpe"] - r["host"]["sharpe"]
        res[rid] = r
        log(f"{rid} {typ:<3} {str(legs):<55} {host or '':<5} n {r['n']:>5} CAGR {r['cagr'] * 100:6.1f} % Sharpe {r['sharpe']:5.2f} "
            f"mDD {r['mdd'] * 100:6.1f} %" + (f" | dSharpe {r['d_sharpe']:+.2f} keep {r['keep'] * 100:.0f} %" if host else ""))
    stand = [r[0] for r in RULES if r[4] is None and res[r[0]]["n"] >= 100 and res[r[0]]["sharpe"] >= 0.5]
    stand = sorted(stand, key=lambda k: -res[k]["sharpe"])[:2]
    filt = [r[0] for r in RULES if r[4] and res[r[0]]["d_sharpe"] >= 0.10 and res[r[0]]["cagr"] >= 0.9 * res[r[0]]["host"]["cagr"] and res[r[0]]["keep"] >= 0.40]
    filt = sorted(filt, key=lambda k: -res[k]["d_sharpe"])[:1]
    finals = stand + filt
    frozen = {"finalists": finals, "rules": {k: {"type": RULE[k][1], "legs": RULE[k][2], "exit": RULE[k][3], "host": RULE[k][4]} for k in finals},
              "in_sample": {k: res[k] for k in finals}, "sd_is": sd, "ic10_sign": {nm: sign_of(nm, S0) for nm in NEEDED},
              "frozen_at": str(pd.Timestamp.now()), "search_size": len(RULES)}
    json.dump({"results": res, "refs": ref, "frozen": frozen}, open(os.path.join(SCR, "ta_stage1.json"), "w"), default=float)
    json.dump(frozen, open(os.path.join(SCR, "ta_frozen.json"), "w"), default=float)
    log(f"FINALISTS {finals}")
    return res


# ---- stage 2 ---------------------------------------------------------------------------------------------------------------
YAHOO = os.path.join(SCR, "idx")
LH = (pd.Timestamp("2005-01-01"), pd.Timestamp("2019-12-31"))
HALF_SPREAD = 0.0030
N_PLACEBO = int(os.environ.get("TA_PLACEBO", "200"))


def load_yahoo():
    import glob
    jk = pd.read_csv(os.path.join(YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    jk = jk[~jk.index.duplicated(keep="last")]
    dates = jk.index[jk.index >= "2004-01-01"]
    cols = {c: {} for c in ("open", "close", "high", "low", "volume")}
    for f in sorted(glob.glob(os.path.join(YAHOO, "*.JK.csv"))):
        code = os.path.basename(f).split(".")[0]
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        for c in cols:
            cols[c][code] = pd.to_numeric(df[c], errors="coerce")
    P = {c: pd.DataFrame(cols[c]).reindex(dates) for c in cols}
    adj, vol = P["close"], P["volume"]
    v60 = (adj * vol).rolling(60, min_periods=60).median()
    liq = (v60 >= S.LIQ) & (adj >= S.MIN_PRICE) & (vol > 0) & adj.notna()
    blue = liq & (v60 >= S.BLUE_LIQ) & (adj >= S.BLUE_PRICE)
    X = {"adj": adj, "close": adj, "H": P["high"], "L": P["low"], "O": P["open"], "V": vol, "Vraw": vol, "LIQ": liq, "BLUE": blue,
         "comp": jk.reindex(dates)}
    c_in = np.full(adj.shape, HALF_SPREAD + S.FEE_BUY)
    c_out = np.full(adj.shape, HALF_SPREAD + S.FEE_SELL)
    return X, c_in, c_out


def dsr(R: pd.Series, n: int) -> float:
    import idx_foreign_gate as FG
    r = R.to_numpy(float)
    return float(FG.deflated_sharpe(r[r != 0], n))


def rule_names(rule):
    return sorted({nm for nm, _ in rule[2]})


def battery_standalone(rid, X, c_in, c_out, S0, fz, Y):
    rule = RULE[rid]
    liq = X["LIQ"].to_numpy(bool)
    names = rule_names(rule)
    V = ta_values(X, names=names)
    lo, hi = OOS_START, OOS_END
    R, trs = run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out)
    main = st(R, trs)
    log(f"{rid} OOS {main['n']} trades CAGR {main['cagr'] * 100:.1f} % Sharpe {main['sharpe']:.2f} mDD {main['mdd'] * 100:.1f} % years {main['years']}")
    rng = np.random.default_rng(SEED + int(rid[1:]))
    pl = np.array([st(run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, placebo_rng=rng)[0])["sharpe"] for _ in range(N_PLACEBO)])
    p50, p90, p95 = (float(np.percentile(pl, q)) for q in (50, 90, 95))
    pct = float((pl < main["sharpe"]).mean() * 100)
    nb = {}
    for s_ in (0.75, 1.25):
        Vs = ta_values(X, names=names, scale=s_)
        nb[f"len x{s_}"] = st(*run_rule(rule, X, Vs, liq, S0, lo, hi, c_in, c_out))
    has_level = any(nm in HI for nm, _ in rule[2])
    for l_ in (0.75, 1.25):
        if has_level:
            nb[f"level x{l_}"] = st(*run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, lvl=l_))
        else:
            kind, prm = rule[3]
            nb[f"exit {kind} {prm * l_:g}"] = st(*run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, exit_override=(kind, prm * l_ if kind == "trail" else round(prm * l_))))
    for k, v in nb.items():
        v["pass"] = bool(v["sharpe"] >= p90)
    cost15 = st(*run_rule(rule, X, V, liq, S0, lo, hi, c_in * 1.5, c_out * 1.5))
    late = st(*run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, delay=1))
    # long history (Yahoo survivors)
    Xy, ci_y, co_y = Y
    liq_y = Xy["LIQ"].to_numpy(bool)
    Vy = ta_values(Xy, names=names)
    Ry, try_ = run_rule(rule, Xy, Vy, liq_y, S0, *LH, ci_y, co_y)
    Ry = Ry[Ry.index <= LH[1]]
    lh = st(Ry, try_)
    rng2 = np.random.default_rng(SEED + 100 + int(rid[1:]))
    lh_pl = []
    for _ in range(50):
        Rp, _ = run_rule(rule, Xy, Vy, liq_y, S0, *LH, ci_y, co_y, placebo_rng=rng2)
        lh_pl.append(st(Rp[Rp.index <= LH[1]])["sharpe"])
    lh["random_median"] = float(np.median(lh_pl))
    lh["pos_years"] = sum(1 for v in lh["years"].values() if v > 0)
    n_cum = N_BEFORE + fz["search_size"]
    P_ = pct >= 95
    N_ = sum(v["pass"] for v in nb.values()) >= 3
    yrs = [main["years"].get(y, 0) for y in (2024, 2025, 2026)]
    T1 = sum(v > 0 for v in yrs) >= 2
    T2 = lh["sharpe"] >= lh["random_median"] + 0.3 and lh["pos_years"] >= 9
    C_ = cost15["cagr"] > 0
    D_ = late["cagr"] > 0 and late["sharpe"] >= 0.5 * main["sharpe"]
    fails = [k for k, ok in (("P", P_), ("N", N_), ("T", T1 and T2)) if not ok]
    if main["sharpe"] <= 0 or main["sharpe"] < p50:
        verdict = "CLOSED"
    elif not fails:
        verdict = "ROBUST"
    elif len(fails) == 1 and P_:
        verdict = "PARTIAL"
    else:
        verdict = "FRAGILE"
    out = {"oos": main, "placebo": {"pct": pct, "p50": p50, "p90": p90, "p95": p95}, "neighbours": nb, "cost15": cost15, "late": late, "long": lh,
           "dsr_cum": dsr(R, n_cum), "dsr_search": dsr(R, fz["search_size"]), "n_cum": n_cum,
           "pass": {"P": P_, "N": N_, "T_oos": T1, "T_long": T2, "C": C_, "D": D_}, "verdict": verdict}
    log(f"{rid} placebo pct {pct:.0f} (p50 {p50:.2f} p95 {p95:.2f}) | nb " + ", ".join(f"{k} {v['sharpe']:.2f}{'*' if v['pass'] else ''}" for k, v in nb.items())
        + f" | x1.5 {cost15['sharpe']:.2f}/{cost15['cagr'] * 100:.1f}% | late {late['sharpe']:.2f}/{late['cagr'] * 100:.1f}% | 2005-19 {lh['sharpe']:.2f} "
        f"(rand {lh['random_median']:.2f}, {lh['pos_years']}/15 yrs) | DSR {out['dsr_cum']:.2f} | {verdict}")
    return out, R, trs


def battery_filter(rid, X, c_in, c_out, S0, fz, Y):
    rule = RULE[rid]
    assert rule[4] == "trend"
    liq = X["LIQ"].to_numpy(bool)
    names = rule_names(rule)
    V = ta_values(X, names=names)
    lo, hi = OOS_START, OOS_END
    ones = np.ones_like(liq)
    Rh, th = run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, filt_override=ones)
    Rf, tf = run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out)
    host, filt = st(Rh, th), st(Rf, tf)
    d = filt["sharpe"] - host["sharpe"]
    log(f"{rid} OOS host {host['n']} {host['cagr'] * 100:.1f}/{host['sharpe']:.2f}/{host['mdd'] * 100:.1f} | filtered {filt['n']} {filt['cagr'] * 100:.1f}/{filt['sharpe']:.2f}/{filt['mdd'] * 100:.1f} | d {d:+.2f}")
    entry, _, small = trend_entry(X)
    fm = rule_mask(rule, V, liq, S0, restrict=False)[0]
    win = np.asarray((X["adj"].index >= lo) & (X["adj"].index <= hi))[:, None]
    base = entry & small & win
    p_keep = float((base & fm).sum() / max(1, base.sum()))
    rng = np.random.default_rng(SEED + int(rid[1:]))
    pl = np.array([st(run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, filt_override=rng.random(liq.shape) < p_keep)[0])["sharpe"] - host["sharpe"]
                   for _ in range(N_PLACEBO)])
    pct = float((pl < d).mean() * 100)
    nb = {}
    for s_ in (0.75, 1.25):
        Vs = ta_values(X, names=names, scale=s_)
        v = st(*run_rule(rule, X, Vs, liq, S0, lo, hi, c_in, c_out))
        nb[f"len x{s_}"] = dict(v, d=v["sharpe"] - host["sharpe"])
    sd = fz["sd_is"][names[0]]
    for sg in (-1, 1):
        v = st(*run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, shift={names[0]: sg * 0.25 * sd}))
        nb[f"thr {sg * 0.25 * sd:+.4f}"] = dict(v, d=v["sharpe"] - host["sharpe"])
    for v in nb.values():
        v["pass"] = bool(v["d"] > 0)
    ch = st(*run_rule(rule, X, V, liq, S0, lo, hi, c_in * 1.5, c_out * 1.5, filt_override=ones))
    cf = st(*run_rule(rule, X, V, liq, S0, lo, hi, c_in * 1.5, c_out * 1.5))
    lh_ = st(*run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, filt_override=ones, delay=1))
    lf = st(*run_rule(rule, X, V, liq, S0, lo, hi, c_in, c_out, delay=1))
    # long history: ungated trend on small, Yahoo
    Xy, ci_y, co_y = Y
    Vy = ta_values(Xy, names=names)
    Ay = Xy["adj"].to_numpy(float)
    ent_y, vr_y, small_y = trend_entry(Xy, gate=False)
    fm_y = rule_mask(rule, Vy, Xy["LIQ"].to_numpy(bool), S0, restrict=False)[0]
    dy = Xy["adj"].index
    Rhy, thy = book(Ay, ent_y, vr_y, small_y, "trail", 0.10, ci_y, co_y, dy, *LH)
    Rfy, tfy = book(Ay, ent_y & fm_y, vr_y, small_y, "trail", 0.10, ci_y, co_y, dy, *LH)
    lhh, lhf = st(Rhy[Rhy.index <= LH[1]], thy), st(Rfy[Rfy.index <= LH[1]], tfy)
    yd = {y: filt["years"].get(y, 0) - host["years"].get(y, 0) for y in (2024, 2025, 2026)}
    n_cum = N_BEFORE + fz["search_size"]
    P_ = pct >= 95
    N_ = sum(v["pass"] for v in nb.values()) >= 3
    T1 = sum(v > 0 for v in yd.values()) >= 2
    T2 = lhf["sharpe"] > lhh["sharpe"]
    C_ = cf["sharpe"] > ch["sharpe"]
    D_ = lf["sharpe"] > lh_["sharpe"]
    fails = [k for k, ok in (("P", P_), ("N", N_), ("T", T1 and T2)) if not ok]
    if d <= 0 or d < float(np.percentile(pl, 50)):
        verdict = "CLOSED"
    elif not fails:
        verdict = "ROBUST"
    elif len(fails) == 1 and P_:
        verdict = "PARTIAL"
    else:
        verdict = "FRAGILE"
    out = {"oos": filt, "host": host, "d_sharpe": d, "keep_signal_share": p_keep, "placebo": {"pct": pct, "p50": float(np.percentile(pl, 50)),
           "p95": float(np.percentile(pl, 95))}, "neighbours": nb, "cost15": {"host": ch, "filt": cf}, "late": {"host": lh_, "filt": lf},
           "long": {"host": lhh, "filt": lhf}, "year_diff": yd, "dsr_cum": dsr(Rf, n_cum), "dsr_search": dsr(Rf, fz["search_size"]), "n_cum": n_cum,
           "pass": {"P": P_, "N": N_, "T_oos": T1, "T_long": T2, "C": C_, "D": D_}, "verdict": verdict}
    log(f"{rid} placebo pct {pct:.0f} | nb " + ", ".join(f"{k} d{v['d']:+.2f}" for k, v in nb.items()) + f" | x1.5 {ch['sharpe']:.2f}->{cf['sharpe']:.2f} | late "
        f"{lh_['sharpe']:.2f}->{lf['sharpe']:.2f} | 2005-19 host {lhh['sharpe']:.2f} ({lhh['n']}) filt {lhf['sharpe']:.2f} ({lhf['n']}) | yrs {yd} | {verdict}")
    return out, Rf, tf


def pin_idx_opens():
    """idx.bar.open was back-filled from Yahoo at 2026-09-25 23:31 WIB (open_src = 'yahoo', 885k rows), AFTER #192. The gap-fade
    loader (idx_daytrade.load) counts every non-null open as a real IDX open, so the gap sleeve silently changed population.
    Restore the view #192 measured (Yahoo-sourced opens = NULL in idx.bar, then the loader's own Yahoo fill marks them 'yahoo'
    and excludes them) by wrapping the loader IN THIS PROCESS ONLY; the shared file is not edited."""
    import idx_daytrade as D
    if getattr(D, "_ta_pinned", False):
        return
    orig_read_sql = pd.read_sql

    def read_sql(sql, conn, *a, **k):
        if isinstance(sql, str) and "FROM idx.bar b JOIN idx.daily_summary s" in sql and "b.open," in sql:
            sql = sql.replace("b.open,", "CASE WHEN b.open_src = 'yahoo' THEN NULL ELSE b.open END AS open,", 1)
        return orig_read_sql(sql, conn, *a, **k)

    D.pd = type("pdproxy", (), {"__getattr__": lambda self, n: read_sql if n == "read_sql" else getattr(pd, n)})()
    D._ta_pinned = True


def combo(finals, X, c_in, c_out, S0):
    """Effect on the deployed book on the corrected #192 engine (same run pairs)."""
    pin_idx_opens()
    import idx_combo_rupiah as CR
    import idx_construction as K
    import idx_ml_strategy as M
    d = dsn()
    P = pickle.load(open(ML_CACHE, "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates, codes = M.wide(P, "close").index, M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq_ml = g("liq").fillna(False).astype(bool).to_numpy()
    ml = K.ml_ens_trades(P, dates, codes, A, raw, offer, bid, liq_ml)
    del P
    gap, o = K.gap_events(d, dates)
    OPEN = o.reindex(index=dates, columns=codes).to_numpy(float)
    SECT = np.full((len(dates), len(codes)), None, dtype=object)
    cs = set(codes)
    tr = [dict(y, tag="p", frac=1.0) for y in CR.trend_trades(d, dates, cache=PIT_CACHE, board="pit") if y["code"] in cs]
    pos = {x: i for i, x in enumerate(dates)}
    d_tr, cols = X["adj"].index, list(X["adj"].columns)
    Ax = X["adj"].to_numpy(float)
    liq = X["LIQ"].to_numpy(bool)

    def to_combo(trs, strat):
        out = []
        for tup in trs:
            e, j, hold = tup[0], tup[1], tup[4]
            if e + hold >= len(d_tr):
                continue
            a, b = d_tr[e], d_tr[e + hold]
            if a in pos and b in pos and cols[j] in cs:
                out.append({"strat": strat, "tag": "p", "frac": 1.0, "code": cols[j], "t_in": pos[a], "t_out": pos[b]})
        return out

    entry, vr, small = trend_entry(X)
    _, trs0 = book(Ax, entry, vr, small, "trail", 0.10, c_in, c_out, d_tr, CR.START, OOS_END)
    mine = to_combo(trs0, "trend")
    assert [(x["code"], x["t_in"], x["t_out"]) for x in mine] == [(x["code"], x["t_in"], x["t_out"]) for x in tr], "trend replica != CR.trend_trades"
    K.PCT["TA"] = 0.05
    use_all = ("gap", "trend", "ML", "TA")

    def run(src, use=use_all):
        nav, _ = K.engine(dates, codes, A, raw, offer, bid, OPEN, SECT, src, gap, use=use)
        return nav

    def s3(nav):
        s_ = CR.stats(nav)
        s2 = CR.stats(nav[nav.index >= OOS_START])
        return {"full": {k: s_[k] for k in ("cagr", "sharpe", "mdd", "by_year")}, "oos": {k: s2[k] for k in ("cagr", "sharpe", "mdd")}}

    base = run(ml + tr)
    out = {"baseline": s3(base)}
    log(f"combo baseline {out['baseline']['full']['cagr'] * 100:.1f} / {out['baseline']['full']['sharpe']:.2f} / {out['baseline']['full']['mdd'] * 100:.1f} | 2024+ "
        f"{out['baseline']['oos']['cagr'] * 100:.1f} / {out['baseline']['oos']['sharpe']:.2f} / {out['baseline']['oos']['mdd'] * 100:.1f}")
    alone = {s_: run(ml + tr, use=(s_,)).pct_change().fillna(0.0) for s_ in ("gap", "trend", "ML")}
    for rid in finals:
        rule = RULE[rid]
        V = ta_values(X, names=rule_names(rule))
        if rule[4] is None:
            m, sc = rule_mask(rule, V, liq, S0)
            _, trs = book(Ax, m, sc, liq, rule[3][0], rule[3][1], c_in, c_out, d_tr, CR.START, OOS_END)
            ta = to_combo(trs, "TA")
            nav = run(ml + tr + ta)
            sl = run(ml + tr + ta, use=("TA",)).pct_change().fillna(0.0)
            mode = "4th sleeve (5 %)"
        else:
            fm = rule_mask(rule, V, liq, S0, restrict=False)[0]
            _, trs = book(Ax, entry & fm, vr, small, "trail", 0.10, c_in, c_out, d_tr, CR.START, OOS_END)
            ft = to_combo(trs, "trend")
            nav = run(ml + ft)
            sl = run(ml + ft, use=("trend",)).pct_change().fillna(0.0)
            mode = "replaces the trend trade list"
        r = s3(nav)
        r["mode"] = mode
        r["n_trades"] = len(trs)
        r["corr"] = {k: {"full": float(np.corrcoef(sl, v)[0, 1]), "oos": float(np.corrcoef(sl[sl.index >= OOS_START], v[v.index >= OOS_START])[0, 1])} for k, v in alone.items()}
        sa = CR.stats((1 + sl).cumprod() * CR.CAPITAL)
        r["sleeve_alone"] = {k: sa[k] for k in ("cagr", "sharpe", "mdd")}
        out[rid] = r
        log(f"combo {rid} ({mode}) {r['full']['cagr'] * 100:.1f} / {r['full']['sharpe']:.2f} / {r['full']['mdd'] * 100:.1f} | 2024+ {r['oos']['cagr'] * 100:.1f} / "
            f"{r['oos']['sharpe']:.2f} / {r['oos']['mdd'] * 100:.1f} | corr " + ", ".join(f"{k} {v['oos']:+.2f}" for k, v in r["corr"].items()))
    return out


def stage2():
    S0 = s0()
    fz = json.load(open(os.path.join(SCR, "ta_frozen.json")))
    X = load_panels(None)
    c_in, c_out = costs(X)
    Y = load_yahoo()
    log(f"finalists {fz['finalists']}; panel {X['adj'].shape} to {X['adj'].index.max().date()}; yahoo {Y[0]['adj'].shape}")
    res = {}
    for rid in fz["finalists"]:
        res[rid] = (battery_filter if RULE[rid][4] else battery_standalone)(rid, X, c_in, c_out, S0, fz, Y)[0]
    cmb = combo(fz["finalists"], X, c_in, c_out, S0)
    json.dump({"battery": res, "combo": cmb}, open(os.path.join(SCR, "ta_stage2.json"), "w"), default=float)
    return res, cmb


def combo_only():
    """Re-run only the combo step (after pinning the IDX opens); the battery does not read opens (no finalist uses BoP)."""
    S0 = s0()
    fz = json.load(open(os.path.join(SCR, "ta_frozen.json")))
    X = load_panels(None)
    c_in, c_out = costs(X)
    cmb = combo(fz["finalists"], X, c_in, c_out, S0)
    o = json.load(open(os.path.join(SCR, "ta_stage2.json")))
    o["combo_unpinned_first_run"] = o.get("combo")
    o["combo"] = cmb
    json.dump(o, open(os.path.join(SCR, "ta_stage2.json"), "w"), default=float)


FAM_NAME = {"atr": "F1 volatility", "chop": "F2 choppiness", "adx": "F3 ADX", "volume": "F4 volume activity", "alma": "F5 fast MA / bar shape",
            "ichimoku": "F6 Ichimoku / TRIX", "uo": "F7 price position + momentum + flow", "mass": "F8 Mass Index"}


def report():
    S0, S1, S2 = s0(), json.load(open(os.path.join(SCR, "ta_stage1.json"))), json.load(open(os.path.join(SCR, "ta_stage2.json")))
    R0, names, C = S0["results"], S0["names"], np.array(S0["corr"])
    fam = {nm: R0[nm]["family"] for nm in names}
    fid = {R0[r]["family"]: r for r in REPS}
    fams = sorted(set(fam.values()))
    fname = {f: FAM_NAME[fid[f]] for f in fams}
    FM = np.zeros((len(fams), len(fams)))
    for a, fa in enumerate(fams):
        for b, fb in enumerate(fams):
            ia = [names.index(n) for n in names if fam[n] == fa]
            ib = [names.index(n) for n in names if fam[n] == fb]
            blk = np.abs(C[np.ix_(ia, ib)])
            FM[a, b] = (blk[~np.eye(len(ia), dtype=bool)].mean() if len(ia) > 1 else 1.0) if a == b else blk.mean()
    fz, res1, ref1 = S1["frozen"], S1["results"], S1["refs"]
    B, CB = S2["battery"], S2["combo"]
    n_cum = N_BEFORE + len(RULES)
    f3 = lambda s: f"{s['cagr'] * 100:.1f} % / {s['sharpe']:.2f} / {s['mdd'] * 100:.1f} %"  # noqa: E731
    L = ["# IDX menu 43 - technical-indicator search (desk chart catalog, alone and combined) - 2026-09-25", "",
         f"Study `ta_search`. {len(RULES)} counted trials (ids {N_BEFORE + 1}..{n_cum}); cumulative N {N_BEFORE} -> {n_cum} (ledger max before the run = 916, "
         "#192; the caller quoted 915). Stage 0 screening (55 readings x 3 horizons) is NOT counted. Script `research/idx_ta_search.py` "
         "(pre-registration + addenda A and STAGE1_FROZEN in its docstring), port `research/idx_ta_lib.py`, "
         "intermediate files research-scratch/ta_stage0/1/2.json, ta_frozen.json.", "",
         "## Verdict", ""]
    for rid in fz["finalists"]:
        b = B[rid]
        L.append(f"- **{rid} -> {b['verdict']}**. OOS 2024-01..2026-09-16 {f3(b['oos'])} ({b['oos']['n']} trades); placebo pct {b['placebo']['pct']:.0f}; "
                 f"passes {', '.join(k for k, v in b['pass'].items() if v) or 'none'}; fails {', '.join(k for k, v in b['pass'].items() if not v) or 'none'}; "
                 f"DSR {b['dsr_cum']:.2f} @ N {n_cum} ({b['dsr_search']:.2f} @ search size {len(RULES)}).")
    L += ["", "Nothing is deployable. R10 is PARTIAL only by the letter of the pre-registered rule. It beats random entries (pct 96) and 3 of 4 neighbours, but it earns its whole OOS "
          "return in 2025 (+116 %, then -38 % in 2026 YTD). A one-day-late fill kills it (Sharpe 0.61 -> 0.07), its drawdown is -54 %, the DSR is 0.01, and as a 4th sleeve it "
          "cuts the combo book's CAGR from 33.8 % to 19.6 %. R05 is FRAGILE on every check. R21 (CMF > 0 on the trend entry) is CLOSED on its pre-registered test: "
          "its OOS delta Sharpe on the trend book is negative (-0.29) and below the random-filter median. It does lift the combo book (37.5 % / 2.03 / -15.5 % vs 33.8 % / 1.83 / -17.9 %), "
          "but that gain sits mostly in 2022 (in-sample), 2024+ moves only 54.6 % -> 56.9 %, and 3 of 4 neighbours lose. Do not wire it.", "",
          "## Data notes (read before quoting)", "",
          "- Port check: all 79 plots of the TS catalog (every indicator at its defaults) reproduced to machine precision on BBCA via Node running catalog.ts; per-name packing "
          "checked on GOTO (late listing) and ASPI (gaps). Research readings use split-ADJUSTED OHLC (volume / adj_factor). The chart draws UNADJUSTED exchange bars, "
          "so the levels differ across splits. The formulas are identical.",
          "- **idx.bar.open was back-filled from Yahoo at 2026-09-25 23:31 WIB** (open_src = 'yahoo', 885k rows), after #192 ran. `idx_daytrade.load` counts every "
          "non-null open as an IDX open, so re-running the combo now gives gap-fade 407 events and 42 % alone, and the baseline reads 73.1 % / 3.11. That is a data change, not an edge. "
          "This study pins the pre-backfill view in-process (Yahoo-sourced opens -> NULL), which reproduces #192 exactly (33.8 % / 1.83 / -17.9 %; gap alone 12.8 % / 1.39). "
          "**Every gap-fade study re-run from now on is affected until idx_daytrade.load filters open_src.** Stage 0's BoP reading was computed after the backfill "
          "(no rule uses BoP).",
          "- Mass Index at the catalog default (10) sits near 10, so the classic 25/27 bulge levels never trigger. R08/R14/R22/R25 had 0 trades. They stay counted and were not fixed.", "",
          "## Stage 0 - screening, in-sample 2020-07..2023-12 only (853 days, LIQ with the point-in-time board)", "",
          "Rank IC vs the forward return from the next close (t = overlap-adjusted). Q5 excess = top fifth (by IC sign) minus the LIQ mean at 20 d, against 2 x the real "
          "round trip (closing offer/bid + fees). R2 = share of the reading's cross-section explained by the ML model's 30 price/volume/tape features. pt = t of the partial IC "
          "after regressing on them.", "",
          "| family | reading | IC5 t | IC10 t | IC20 t | Q5 excess 20d / hurdle (bps) | R2 vs ML | partial t 5/10/20 |", "|---|---|---|---|---|---|---|---|"]
    for nm in sorted(names, key=lambda n: (fam[n], -abs(R0[n]["t10"]))):
        r = R0[nm]
        L.append(f"| {fname[fam[nm]].split(' ')[0]} | {nm} | {r['t5']:+.1f} | {r['t10']:+.1f} | {r['t20']:+.1f} | {r['q5ex20'] * 1e4:+.0f} / {r['hurdle20'] * 1e4:.0f} | "
                 f"{r['r2_ml']:.2f} | {r['pt5']:+.1f} / {r['pt10']:+.1f} / {r['pt20']:+.1f} |")
    L += ["", "Findings:", "",
          "1. **Eight families at the pre-registered cut (average |corr| >= 0.5), and one of them is almost the whole catalog.** F7 holds 40 of 55 readings: price vs every MA / band / "
          "SAR / Supertrend / pivot, every momentum oscillator, and the flow lines (CMF, A/D, Chaikin, OBV, MFI, EOM, EFI, PVT). On IDX daily bars they are one factor, recent "
          "price position. SMA/ENV and BB/%B are identical by construction. Stoch and %R are identical at the same length.",
          "2. **Not one reading's top fifth clears the 2x round-trip hurdle** at 10 or 20 days (best: BB/%B +143 bps vs 162, CCI +138 vs 162). The strongest ICs are the "
          "volatility family's NEGATIVE ones (ATR% t -4.3..-5.0: low-vol names rank better), but their top-fifth excess is ~0 bps. The rank edge is in the losers' tail, "
          "not in anything a long-only book can buy.",
          "3. **Nothing carries information the ML does not already see** (pre-registered bar |partial t| >= 3: 0 of 55). Largest partial t: UO 2.7, Chaikin / A-D 2.5, "
          "CMF 2.4, Mass 2.2 (h = 5). Pure redundancy (R2 >= 0.80 AND partial |t| < 1.5): the moving-average family (SMA/EMA/WMA/VWMA/ALMA, R2 0.84-1.00 = dist_ma20/50), "
          "Donchian / Stoch / %R (R2 0.94-1.00 = pos20), Bollinger / Keltner / Envelope / %B, pivots, Ichimoku, TRIX, RSI / CCI / TSI / PPO / MACD / DPO, volume ratio and "
          "volume oscillator (R2 0.90-1.00 = volr1/volr5), ATR% / HV (R2 0.84-0.98 = atr_pct/vol20). The least redundant readings (CHOP 0.44, ADX 0.44, Mass 0.62, CMF 0.63) have no partial IC at the bar (|t| <= 2.4).", "",
          "### Family correlation matrix (mean |within-day rank corr| between members; diagonal = mean within the family)", "",
          "| | " + " | ".join(fname[f].split(" ")[0] for f in fams) + " |", "|---|" + "---|" * len(fams)]
    for a, f in enumerate(fams):
        L.append(f"| {fname[f]} | " + " | ".join(f"{FM[a, b]:.2f}" for b in range(len(fams))) + " |")
    L += ["", "Representatives' signed correlation (the stage-1 legs):", "", "| | " + " | ".join(REPS) + " |", "|---|" + "---|" * len(REPS)]
    for a in REPS:
        L.append(f"| {a} | " + " | ".join(f"{C[names.index(a), names.index(b)]:+.2f}" for b in REPS) + " |")
    L += ["", "Members: " + "; ".join(f"{fname[f]}: " + ", ".join(n for n in names if fam[n] == f) for f in fams) + ".", "",
          "## Stage 1 - 26 counted rules, in-sample 2020-07..2023-12 (ML filters 2022-23)", "",
          f"K-10 book on LIQ (pit), entry at the next close paying the closing offer + 0.10 %, exit at a close receiving the bid + 0.20 %. References (not trials): random LIQ "
          f"entries + trail10 Sharpe {ref1['random_trail0.1']['sharpe']:.2f}, + hold10 {ref1['random_hold10']['sharpe']:.2f}; trend host {f3(ref1['host_trend'])} "
          f"({ref1['host_trend']['n']} trades); ML ens4 host 2022-23 {f3(ref1['host_ML'])}.", "",
          "| id | type | rule | exit | trades | CAGR / Sharpe / mDD | vs host |", "|---|---|---|---|---|---|---|"]
    for r in RULES:
        x = res1[r[0]]
        legs = "composite of 8 reps" if r[2] == "composite" else " & ".join(f"{a}_{b}" for a, b in r[2])
        ex = "host" if r[4] else (f"trail {r[3][1] * 100:.0f} %" if r[3][0] == "trail" else f"hold {r[3][1]}")
        L.append(f"| {r[0]}{' **finalist**' if r[0] in fz['finalists'] else ''} | {r[1]} | {legs}{' on ' + r[4] if r[4] else ''} | {ex} | {x['n']} | {f3(x)} | "
                 + (f"dSharpe {x['d_sharpe']:+.2f}, keeps {x['keep'] * 100:.0f} %" if r[4] else "") + " |")
    L += ["", "Reading: only the price-position rules made money in-sample, R05/R06/R10 at 40-43 % CAGR. Every one of them earned it in 2021 (+116..+149 %) with -38..-51 % "
          "drawdowns. All mean-reversion / weakness-side rules lost heavily (R18 3x oversold: -36.5 %/yr). The composite (R20) is flat.", "",
          "## Stage 2 - the counted test (run once per frozen finalist)", "",
          "| | R10 ichimoku_hi & volume_hi | R05 alma_hi | R21 trend & CMF > 0 |", "|---|---|---|---|"]
    b10, b05, b21 = B["R10"], B["R05"], B["R21"]
    yr = lambda s: " ".join(f"{str(y)[2:]} {v * 100:+.0f}" for y, v in sorted(s["years"].items()))  # noqa: E731
    nbtxt = lambda r: ", ".join((f"{k} {v['sharpe']:.2f}" if "d" not in v else f"{k} d{v['d']:+.2f}") + (" ok" if v["pass"] else "")  # noqa: E731
                                for k, v in B[r]["neighbours"].items()) + f" -> {'PASS' if B[r]['pass']['N'] else 'fail'}"
    L += [f"| in-sample 2020-07..2023 | {f3(res1['R10'])} | {f3(res1['R05'])} | {f3(res1['R21'])} (host {f3(ref1['host_trend'])}) |",
          f"| **OOS 2024-01..2026-09-16** | {f3(b10['oos'])}, {b10['oos']['n']} tr | {f3(b05['oos'])}, {b05['oos']['n']} tr | {f3(b21['oos'])} vs host {f3(b21['host'])}; dSharpe {b21['d_sharpe']:+.2f} |",
          f"| OOS years | {yr(b10['oos'])} | {yr(b05['oos'])} | filt - host: " + " ".join(f"{str(y)[2:]} {v * 100:+.0f}" for y, v in b21['year_diff'].items()) + " |",
          f"| P placebo (200) | pct {b10['placebo']['pct']:.0f} (p50 {b10['placebo']['p50']:.2f}, p95 {b10['placebo']['p95']:.2f}) PASS | pct {b05['placebo']['pct']:.0f} (p95 {b05['placebo']['p95']:.2f}) fail | "
          f"pct {b21['placebo']['pct']:.0f} of random filters keeping {b21['keep_signal_share'] * 100:.0f} % (p95 d {b21['placebo']['p95']:+.2f}) fail |",
          f"| N neighbours | {nbtxt('R10')} | {nbtxt('R05')} | {nbtxt('R21')} |",
          f"| T 2005-19 Yahoo survivors | {f3(b10['long'])}, {b10['long']['n']} tr; random {b10['long']['random_median']:.2f}; {b10['long']['pos_years']}/15 yrs -> fail (bar {b10['long']['random_median'] + 0.3:.2f}) | "
          f"{f3(b05['long'])}; random {b05['long']['random_median']:.2f}; {b05['long']['pos_years']}/15 -> fail | host {f3(b21['long']['host'])} ({b21['long']['host']['n']}) vs filt {f3(b21['long']['filt'])} ({b21['long']['filt']['n']}) -> PASS |",
          f"| C costs x1.5 | {f3(b10['cost15'])} ok | {f3(b05['cost15'])} fail | host {b21['cost15']['host']['sharpe']:.2f} -> filt {b21['cost15']['filt']['sharpe']:.2f} fail |",
          f"| D 1 day late | {f3(b10['late'])} **fail** | {f3(b05['late'])} fail | host {b21['late']['host']['sharpe']:.2f} -> filt {b21['late']['filt']['sharpe']:.2f} fail |",
          f"| M DSR @ N {n_cum} / @ 26 | {b10['dsr_cum']:.2f} / {b10['dsr_search']:.2f} | {b05['dsr_cum']:.2f} / {b05['dsr_search']:.2f} | {b21['dsr_cum']:.2f} / {b21['dsr_search']:.2f} |",
          f"| **verdict** | **{b10['verdict']}** | **{b05['verdict']}** | **{b21['verdict']}** |", "",
          "## Effect on the combo book (corrected #192 engine, same run, gap 10 / trend 5 / ML ens4 5 %, 20 slots, floor 30 %, Rp 20 M, 2022-01..2026-09-16)", "",
          "Mode fixed before the run: R10 / R05 = a 4th sleeve at 5 % of NAV per trade; R21 = replaces the trend sleeve's trade list. 2024+ = the same NAV path from 2024-01-02.", "",
          "| book | full CAGR / Sharpe / mDD | 2024+ | sleeve alone on the engine | corr with gap / trend / ML (2024+) | per year |", "|---|---|---|---|---|---|"]
    bb = CB["baseline"]
    L.append(f"| baseline (reproduces #192) | {f3(bb['full'])} | {f3(bb['oos'])} | - | - | " + " ".join(f"{str(y)[2:]} {v * 100:+.0f}" for y, v in bb["full"]["by_year"].items()) + " |")
    for rid in fz["finalists"]:
        c = CB[rid]
        L.append(f"| + {rid} ({c['mode']}) | {f3(c['full'])} | {f3(c['oos'])} | {f3(c['sleeve_alone'])} | " + " / ".join(f"{c['corr'][k]['oos']:+.2f}" for k in ("gap", "trend", "ML"))
                 + " | " + " ".join(f"{str(y)[2:]} {v * 100:+.0f}" for y, v in c["full"]["by_year"].items()) + " |")
    L += ["", "The two standalone rules are the trend sleeve's own exposure again (corr +0.45..+0.55 with trend, +0.35 with ML). They compete for the same 20 slots and the 30 % "
          "floor and cost the book 14-26 pp CAGR. R21 is the trend sleeve with a flow check (corr +0.84 with the deployed trend). Its combo gain comes mainly from 2022 (+19 % vs +5 %), "
          "which is in-sample.", "",
          "## What this closes", "",
          f"- The desk's ~50 chart indicators at default settings, alone, AND-combined across uncorrelated families, as oscillator agreement, as an equal-weight composite, "
          f"and as filters on the trend and ML entries: 26 rules, 0 ROBUST. Cumulative N {n_cum}.",
          "- On daily IDX bars the catalog is one price-position/momentum factor plus low-vol. The ML already sees both (dist_ma*, pos20, ret*, volr*, atr_pct, vol20), "
          "and neither pays a 2x round trip from the long side. More indicators or combinations of them are accuracy work, and #174/#176 already showed that route "
          "loses on this desk.",
          "- Left open, not tested: flow readings (CMF / A-D / Chaikin) as an ML FEATURE. They have the highest partial IC (t 2.4-2.5), but it is below the bar, so this is low priority."]
    text = "\n".join(L) + "\n"
    out = os.path.join(HERE, "IDX_TA_SEARCH_2026-09-25.md")
    open(out, "w", encoding="utf-8").write(text)
    print(text)
    if os.environ.get("TA_NOSTORE"):
        return
    from blackheart_ingest.idx import research_store as rs
    from blackheart_ingest.idx.ml import common
    stage1_sum = {}
    for k, v in res1.items():
        stage1_sum[k] = {x: v[x] for x in ("n", "cagr", "sharpe", "mdd") if x in v}
        if "d_sharpe" in v:
            stage1_sum[k]["d_sharpe"] = v["d_sharpe"]
    with psycopg.connect(dsn()) as conn:
        sid = rs.record_study(conn, "ta_search", date(2026, 9, 25),
                              params={"n_trials_cumulative": n_cum, "n_trials_before": N_BEFORE, "n_before_stated_by_caller": 915, "trials_added": len(RULES),
                                      "trial_ids": [N_BEFORE + 1, n_cum], "search_size": len(RULES), "stage0_screen_not_counted": {"readings": len(names), "horizons": list(HORIZONS)},
                                      "rules": {r[0]: {"type": r[1], "legs": r[2], "exit": r[3], "host": r[4]} for r in RULES}, "finalists": fz["finalists"],
                                      "in_sample": [str(IS_START.date()), str(IS_END.date())], "oos": [str(OOS_START.date()), str(OOS_END.date())],
                                      "long_history": [str(LH[0].date()), str(LH[1].date())], "board": "pit", "cache": PIT_CACHE, "n_placebo": N_PLACEBO,
                                      "data_note": "idx.bar.open back-filled from Yahoo 2026-09-25 23:31 WIB; combo pinned to pre-backfill opens (reproduces #192)"},
                              summary=common.plain({"verdicts": {k: B[k]["verdict"] for k in B}, "battery": B, "combo": CB, "stage1": stage1_sum,
                                                    "stage0": {nm: {k: R0[nm][k] for k in ("family", "ic5", "ic10", "ic20", "t5", "t10", "t20", "q5ex20", "hurdle20", "r2_ml", "pt5", "pt10", "pt20")} for nm in names},
                                                    "family_matrix": {"families": [fname[f] for f in fams], "mean_abs_corr": FM.tolist()}}),
                              names=[], report_path=out,
                              note="menu 43 TA search: 26 rules, finalists R10 PARTIAL (by the letter; not deployable), R05 FRAGILE, R21 CLOSED; no TA family adds info beyond the ML")
        conn.commit()
    log(f"study #{sid} stored; report {out}")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "stage0"
    {"stage0": stage0, "stage1": stage1, "stage2": stage2, "combo": combo_only, "report": report}[what]()
