#!/usr/bin/env python3
"""IDX menu ML-3b — which names lock at ARA tomorrow: bars + closing-book MICROSTRUCTURE, LightGBM vs a GRU (deep learning),
a ranked list and its accuracy (operator, 2026-09-24: "bikin model ML/DL atau algoritma untuk memprediksi saham akan ARA, bisa
juga cek dari market microstructure nya, bikin rank, terus bikin juga akurasi model ini berapa").

Menu ML-3 (study 2026-09-22) settled that a bar-only LightGBM ranks tomorrow's ARA well (AUC 0.86-0.92) and that BUYING its
picks loses (the predictable part is the locked chain nobody can buy). This study asks the two open questions:
  (1) does the closing order book / tape (queue imbalance, spread, frequency, average trade size, foreign flow, non-regular
      share) add to the bars? IDX publishes it daily since 2020 in idx.daily_summary - the only microstructure with history
      (the Stockbit tick feed has 3 sessions and ZERO ARA touches among its 136 liquid names, so a tick-level model waits);
  (2) does a sequence model (GRU over the last 20 days of 12 daily channels + the static features) beat the trees?
It then reports the accuracy of the ranked list in the terms an operator can use (precision@K per day, lift, recall, AUC,
calibration) and the list for the next session. It is NOT a trade study: nothing here writes a ticket.

PRE-REGISTERED (6 trials; cumulative 711 + 6 = 717). Declared before the run; nothing tuned afterwards.
  Sample   every (name, day) 2020-01 -> 2026-09-23 on the main boards (notation digit 1/2: Utama + Pengembangan; Akselerasi and
           Pemantauan Khusus have 10 % bands), previous >= Rp 50, value traded on the day >= Rp 1 bn, next day traded.
  Labels   LOCK1 = tomorrow's close is tomorrow's ARA price (ARA = highest tick <= previous x (1 + 35/25/20 %), rule II-A);
           TOUCH1 = tomorrow's high reaches it (the nightly ara.py label). LOCK1 is the primary label.
  Features BAR (23): ret1/5/20/60, vr, vr5, log_value, log_price, clv, hl_range, dist_hi20/60, vol20, touch/lock/near today,
           band_use, days_since_ara, streak, up_days, n_ara20/60, breadth_ara, breadth_near, mkt_ret1/5, dow, band, age.
           MICRO (20, all from the closing summary of day t): qimb = (bidvol - offvol)/(bidvol + offvol), no_offer, no_bid,
           spread in ticks, log(bidvol/vol), log(offvol/vol), log((bidvol+1)/(offvol+1)), close_at_bid, close_at_offer,
           log avg trade (value/frequency), avg-trade ratio vs its 20d median, frequency ratio vs 20d median, foreign net share
           of volume (1d, 5d, 20d), foreign participation, non-regular share, turnover of tradeable shares, gap at the open,
           qimb yesterday, qimb 5d mean.
  Models   LightGBM binary (num_leaves 15, 300 rounds, lr 0.05, min_child_samples 200, feature_fraction 0.8, bagging 0.8,
           scale_pos_weight = neg/pos, seed 20260924) on BAR, on MICRO, on BAR+MICRO (three trials, LOCK1) and BAR+MICRO on
           TOUCH1 (trial 4). DL (trial 5): GRU(12 -> 32) over the last 20 trading days of [ret1, hl_range, clv, log1p vr, qimb,
           spread/20, log1p freq_ratio, fnet, touch, band_use, log bidvol/vol, log offvol/vol] concatenated with an MLP(64) of
           the standardised static BAR+MICRO features -> FC(64) -> logit; BCE with pos_weight = min(neg/pos, 50), Adam 1e-3,
           batch 4096, <= 6 epochs, early stop on the AUC of the last 10 % of the training period. ENS (trial 6): mean of the
           within-day percentile ranks of the BAR+MICRO tree score and the DL score.
  Walk-forward  test years 2022..2026; train on every earlier row (labels realised before the test year begins).
  Accuracy      per year: AUC, average precision, precision@5/10/20 per day (mean over days), recall@20 (share of the year's
           ARA locks inside the daily top-20), lift = precision@5 / base rate, Brier; the operating point = the top 1 % of the
           training score distribution -> precision, recall, F1, balanced accuracy, plain accuracy (with the always-no
           accuracy beside it, because at a 0.5 % base rate plain accuracy says nothing); calibration by score decile (2026);
           BUYABLE precision@10 = precision among daily top-10 picks that still had an offer at the close (not locked today) -
           the only picks a holder-to-be could have bought; next-day return of the picks for context.
           Placebo: LOCK1 shuffled within the 2026 test year, 3 draws, BAR+MICRO AUC percentile.
  READING RULE (declared before the run)
           MICRO ADDS if BAR+MICRO beats BAR on AUC by >= +0.01 AND on precision@10 by >= +1 pp in >= 4 of 5 test years.
           DL USEFUL if its AUC >= BAR+MICRO tree AUC - 0.005 in >= 3 of 5 years; ENS ADOPTED as the rank if it beats the tree
           on precision@10 in >= 4 of 5 years. Otherwise the tree on BAR+MICRO (or BAR, if micro does not add) is the rank.
           Every model's numbers are reported whatever the verdict, so the size of the miss is visible.
  Output   research/IDX_ARA_MICRO_<end>.md (+ the ranked top-20 for the next session), study 'ml_ara_micro' in idx.study with
           the top-20 as names (score = P(LOCK1)). Read-only on the market tables.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_ara_micro.py
  [--end 2026-09-24] [--no-dl] [--no-store] [--out research/IDX_ARA_MICRO_<end>.md]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import date, datetime

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))

START = date(2020, 1, 1)
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
SEED = 20260924
N_BEFORE = 711
N_TRIALS = 6
MIN_PREV, MIN_VALUE = 50.0, 1e9
K_LIST = (5, 10, 20)
L_SEQ = 20
FLAG_Q = 0.99
N_PLACEBO = 3
LGB = {"objective": "binary", "num_leaves": 15, "learning_rate": 0.05, "min_child_samples": 200, "feature_fraction": 0.8,
       "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0, "seed": SEED, "verbose": -1, "num_threads": 8}
ROUNDS = 300
BAR = ["ret1", "ret5", "ret20", "ret60", "vr", "vr5", "log_value", "log_price", "clv", "hl_range", "dist_hi20", "dist_hi60", "vol20",
       "touch", "lock", "near", "band_use", "days_since_ara", "streak", "up_days", "n_ara20", "n_ara60", "breadth_ara", "breadth_near",
       "mkt_ret1", "mkt_ret5", "dow", "band", "age"]
MICRO = ["qimb", "no_offer", "no_bid", "sprd_t", "log_bv_vol", "log_ov_vol", "bv_ov", "close_at_bid", "close_at_off", "log_avg_trade",
         "atr_ratio", "freq_ratio", "fnet", "fnet5", "fnet20", "fpart", "nonreg_share", "turnover", "gap_open", "qimb_yday", "qimb5"]
SEQ_CH = ["ret1", "hl_range", "clv", "lvr", "qimb0", "sprd0", "lfreq", "fnet0", "touchf", "band_use", "log_bv_vol0", "log_ov_vol0"]
SETS = {"BAR": BAR, "MICRO": MICRO, "BAR+MICRO": BAR + MICRO}
BAR_MICRO = {"auc": 0.01, "p10": 0.01, "years": 4}
BAR_DL = {"auc_slack": 0.005, "years": 3}
BAR_ENS = {"years": 4}


# ------------------------------------------------------------------------------------------------------------------ data
def load(conn: psycopg.Connection, end: date) -> pd.DataFrame:
    cols = ["code", "d", "prev", "open", "high", "low", "close", "vol", "val", "freq", "bid", "bv", "off", "ov", "fb", "fs", "nreg", "tsh", "bd", "adj"]
    with conn.cursor() as cur:
        # the open as the live model reads it (ara_model.load_summary): IDX's own, else the validated fill in idx.bar
        # (jobs/bar_open.py, 2026-09-26). The first run (#146) read daily_summary.open, NULL outside the pre-opening session.
        cur.execute("""SELECT s.code, s.trade_date, s.previous::float8, COALESCE(b.open, s.open)::float8, s.high::float8, s.low::float8, s.close::float8,
                              s.volume::float8, s.value::float8, s.frequency::float8, s.bid::float8, s.bid_volume::float8, s.offer::float8,
                              s.offer_volume::float8, s.foreign_buy::float8, s.foreign_sell::float8, s.nonreg_volume::float8,
                              s.tradeable_shares::float8, substr(s.remarks, 5, 1), b.adj_factor::float8
                       FROM idx.daily_summary s LEFT JOIN idx.bar b ON b.code = s.code AND b.trade_date = s.trade_date AND b.source = 'idx'
                       WHERE s.trade_date BETWEEN %s AND %s AND s.close > 0""", (START, end))
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    df["d"] = pd.to_datetime(df["d"])
    return df


def tick_of(px: np.ndarray) -> np.ndarray:
    return np.select([px < 200, px < 500, px < 2000, px < 5000], [1.0, 2.0, 5.0, 10.0], 25.0)


def band_of(prev: np.ndarray) -> np.ndarray:
    return np.where(prev <= 200, 0.35, np.where(prev <= 5000, 0.25, 0.20))


def ara_of(prev: np.ndarray) -> np.ndarray:
    raw = prev * (1 + band_of(prev))
    t = tick_of(raw)
    return np.floor(raw / t + 1e-9) * t


def roll(X: np.ndarray, w: int, fn: str, minp: int) -> np.ndarray:
    return getattr(pd.DataFrame(X).rolling(w, min_periods=minp), fn)().to_numpy()


def lag(X: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(X, np.nan)
    out[k:] = X[:-k]
    return out


def lead(X: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(X, np.nan)
    out[:-k] = X[k:]
    return out


def safe_div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = a / b
    return np.where(np.isfinite(out), out, np.nan)


class Panel:
    """Every column as a (T, N) float array; features, labels and sequence channels on the same grid."""

    def __init__(self, df: pd.DataFrame):
        dates = np.sort(df["d"].unique())
        codes = np.sort(df["code"].unique())
        self.dates, self.codes = pd.DatetimeIndex(dates), codes
        self.T, self.N = len(dates), len(codes)
        ti = np.searchsorted(dates, df["d"].to_numpy())
        ni = np.searchsorted(codes, df["code"].to_numpy())

        def g(col, fill=np.nan):
            out = np.full((self.T, self.N), fill, dtype=float)
            v = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
            out[ti, ni] = v
            return out

        for c in ("prev", "open", "high", "low", "close", "vol", "val", "freq", "bid", "bv", "off", "ov", "fb", "fs", "nreg", "tsh", "adj"):
            setattr(self, c, g(c))
        main = np.zeros((self.T, self.N), dtype=bool)
        main[ti, ni] = df["bd"].isin(["1", "2"]).to_numpy()
        self.main = main
        self.F: dict[str, np.ndarray] = {}
        self._features()
        self._labels()
        self._channels()

    def _features(self):
        F, T, N = self.F, self.T, self.N
        prev, close, high, low, vol, val = self.prev, self.close, self.high, self.low, self.vol, self.val
        adj = np.where(np.isfinite(self.adj) & (self.adj > 0), self.adj, 1.0)
        A = close * adj
        band = band_of(prev)
        ara_px = ara_of(prev)
        ok = np.isfinite(close) & np.isfinite(prev) & (prev > 0)
        touch = ok & (high >= ara_px - 1e-6)
        lock = touch & (close >= ara_px - 1e-6)
        F["touch"], F["lock"] = touch.astype(float), lock.astype(float)
        F["near"] = (ok & (high >= prev * (1 + 0.6 * band))).astype(float)
        F["band_use"] = safe_div(high / prev - 1, band)
        F["ret1"] = close / prev - 1
        for k in (5, 20, 60):
            F[f"ret{k}"] = A / lag(A, k) - 1
        vmed = roll(lag(vol, 1), 20, "median", 10)
        F["vr"] = safe_div(vol, vmed)
        F["vr5"] = roll(F["vr"], 5, "mean", 1)
        F["log_value"] = np.log10(np.where(val > 0, val, np.nan))
        F["log_price"] = np.log10(close)
        F["clv"] = safe_div(close - low, high - low)
        F["hl_range"] = (high - low) / prev
        F["dist_hi20"] = A / roll(A, 20, "max", 10) - 1
        F["dist_hi60"] = A / roll(A, 60, "max", 20) - 1
        F["vol20"] = roll(pd.DataFrame(A).pct_change().to_numpy(), 20, "std", 15)
        since, streak, updays = np.full(N, 60.0), np.zeros(N), np.zeros(N)
        S, ST, UD = np.zeros((T, N)), np.zeros((T, N)), np.zeros((T, N))
        up = F["ret1"] > 0
        for t in range(T):
            since = np.where(lock[t], 0.0, np.minimum(60.0, since + 1))
            streak = np.where(lock[t], streak + 1, 0.0)
            updays = np.where(up[t], updays + 1, np.where(ok[t], 0.0, updays))
            S[t], ST[t], UD[t] = since, streak, updays
        F["days_since_ara"], F["streak"], F["up_days"] = S, ST, UD
        F["n_ara20"] = roll(lock.astype(float), 20, "sum", 1)
        F["n_ara60"] = roll(lock.astype(float), 60, "sum", 1)
        uni = self.main & ok & (val >= MIN_VALUE)
        n_uni = np.maximum(uni.sum(axis=1), 1)
        F["breadth_ara"] = np.repeat(((lock & uni).sum(axis=1) / n_uni)[:, None], N, axis=1)
        F["breadth_near"] = np.repeat(((F["near"] > 0) & uni).sum(axis=1)[:, None] / n_uni[:, None], N, axis=1)
        r1 = np.where(uni, F["ret1"], np.nan)
        with np.errstate(all="ignore"):
            mkt = np.nanmean(r1, axis=1)
        mkt = np.where(np.isfinite(mkt), mkt, 0.0)
        F["mkt_ret1"] = np.repeat(mkt[:, None], N, axis=1)
        F["mkt_ret5"] = np.repeat(pd.Series(mkt).rolling(5, min_periods=1).sum().to_numpy()[:, None], N, axis=1)
        F["dow"] = np.repeat(self.dates.dayofweek.to_numpy(float)[:, None], N, axis=1)
        F["band"] = np.select([prev <= 200, prev <= 5000], [0.0, 1.0], 2.0)
        F["age"] = np.cumsum(ok, axis=0).astype(float)
        # ---- closing-book / tape microstructure
        bv, ov, bid, off, freq, fb, fs = self.bv, self.ov, self.bid, self.off, self.freq, self.fb, self.fs
        bv0, ov0 = np.nan_to_num(bv), np.nan_to_num(ov)
        F["qimb"] = safe_div(bv0 - ov0, bv0 + ov0)
        F["no_offer"] = (ok & (ov0 <= 0)).astype(float)
        F["no_bid"] = (ok & (bv0 <= 0)).astype(float)
        F["sprd_t"] = np.where((bid > 0) & (off > 0), safe_div(off - bid, tick_of(close)), np.nan)
        F["log_bv_vol"] = np.log1p(safe_div(bv0, vol))
        F["log_ov_vol"] = np.log1p(safe_div(ov0, vol))
        F["bv_ov"] = np.log((bv0 + 1) / (ov0 + 1))
        F["close_at_bid"] = (ok & (bid > 0) & (np.abs(close - bid) < 1e-6)).astype(float)
        F["close_at_off"] = (ok & (off > 0) & (np.abs(close - off) < 1e-6)).astype(float)
        avg_trade = safe_div(val, np.where(freq > 0, freq, np.nan))
        F["log_avg_trade"] = np.log10(avg_trade)
        F["atr_ratio"] = safe_div(avg_trade, roll(lag(avg_trade, 1), 20, "median", 10))
        F["freq_ratio"] = safe_div(freq, roll(lag(freq, 1), 20, "median", 10))
        fnet = np.nan_to_num(fb) - np.nan_to_num(fs)
        F["fnet"] = safe_div(fnet, vol)
        F["fnet5"] = safe_div(roll(fnet, 5, "sum", 1), roll(vol, 5, "sum", 1))
        F["fnet20"] = safe_div(roll(fnet, 20, "sum", 5), roll(vol, 20, "sum", 5))
        F["fpart"] = safe_div(np.nan_to_num(fb) + np.nan_to_num(fs), 2 * vol)
        F["nonreg_share"] = safe_div(np.nan_to_num(self.nreg), vol + np.nan_to_num(self.nreg))
        F["turnover"] = safe_div(vol, np.where(self.tsh > 0, self.tsh, np.nan))
        F["gap_open"] = self.open / prev - 1
        F["qimb_yday"] = lag(F["qimb"], 1)
        F["qimb5"] = roll(F["qimb"], 5, "mean", 1)
        self.ok, self.ara_px = ok, ara_px

    def _labels(self):
        prev_n, close_n, high_n = lead(self.prev, 1), lead(self.close, 1), lead(self.high, 1)
        ara_n = ara_of(prev_n)
        valid = np.isfinite(close_n) & np.isfinite(prev_n) & (prev_n > 0)
        self.LOCK1 = np.where(valid, (close_n >= ara_n - 1e-6).astype(float), np.nan)
        self.TOUCH1 = np.where(valid, (high_n >= ara_n - 1e-6).astype(float), np.nan)
        self.ret_n = np.where(valid, close_n / prev_n - 1, np.nan)
        self.ara_next = ara_of(self.close)                              # tomorrow's limit if nothing adjusts overnight

    def _channels(self):
        F = self.F
        ch = {"ret1": F["ret1"], "hl_range": F["hl_range"], "clv": F["clv"], "lvr": np.log1p(F["vr"]), "qimb0": F["qimb"],
              "sprd0": np.clip(F["sprd_t"], 0, 20) / 20, "lfreq": np.log1p(F["freq_ratio"]), "fnet0": F["fnet"], "touchf": F["touch"],
              "band_use": F["band_use"], "log_bv_vol0": F["log_bv_vol"], "log_ov_vol0": F["log_ov_vol"]}
        self.CH = np.stack([np.nan_to_num(np.clip(ch[c], -5, 5)).astype(np.float32) for c in SEQ_CH])   # (C, T, N)

    def sample(self, need_label: bool) -> pd.DataFrame:
        m = self.main & self.ok & (self.prev >= MIN_PREV) & (self.val >= MIN_VALUE)
        if need_label:
            m &= np.isfinite(self.LOCK1)
        m[: L_SEQ - 1] = False
        ti, ni = np.nonzero(m)
        out = {"ti": ti, "ni": ni, "d": self.dates[ti], "code": self.codes[ni], "close": self.close[ti, ni], "ara_px_next": self.ara_next[ti, ni],
               "LOCK1": self.LOCK1[ti, ni], "TOUCH1": self.TOUCH1[ti, ni], "ret_n": self.ret_n[ti, ni], "buyable": (np.nan_to_num(self.ov)[ti, ni] > 0).astype(float)}
        for k, v in self.F.items():
            out[k] = v[ti, ni]
        df = pd.DataFrame(out)
        df["year"] = df["d"].dt.year
        return df


# --------------------------------------------------------------------------------------------------------------- metrics
def auc(y: np.ndarray, s: np.ndarray) -> float:
    y = y.astype(bool)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = stats.rankdata(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def avg_precision(y: np.ndarray, s: np.ndarray) -> float:
    o = np.argsort(-s, kind="stable")
    yy = y[o]
    hits = np.cumsum(yy)
    prec = hits / np.arange(1, len(yy) + 1)
    return float(prec[yy > 0].mean()) if yy.sum() else float("nan")


def topk(df: pd.DataFrame, score: str, k: int) -> pd.DataFrame:
    return df.sort_values(["d", score], ascending=[True, False]).groupby("d", sort=False).head(k)


def accuracy_block(df: pd.DataFrame, score: str, label: str, thr: float) -> dict:
    """Everything an operator calls 'akurasi', per (test set, model)."""
    y, s = df[label].to_numpy(float), df[score].to_numpy(float)
    out = {"n": int(len(df)), "pos": int(y.sum()), "base": float(y.mean()), "auc": auc(y, s), "ap": avg_precision(y, s),
           "brier": float(np.mean((s - y) ** 2)) if score.startswith("p_") else float("nan")}
    for k in K_LIST:
        pk = topk(df, score, k)
        out[f"p@{k}"] = float(pk.groupby("d")[label].mean().mean())
        out[f"r@{k}"] = float(pk[label].sum() / max(y.sum(), 1))
        out[f"ret@{k}"] = float(pk["ret_n"].mean())
    out["lift@5"] = out["p@5"] / out["base"] if out["base"] > 0 else float("nan")
    p10 = topk(df, score, 10)
    b = p10[p10["buyable"] > 0]
    out["buyable_share@10"] = float(len(b) / max(len(p10), 1))
    out["buyable_p@10"] = float(b[label].mean()) if len(b) else float("nan")
    out["buyable_ret@10"] = float(b["ret_n"].mean()) if len(b) else float("nan")
    flag = s >= thr
    tp, fp = int((flag & (y > 0)).sum()), int((flag & (y == 0)).sum())
    fn, tn = int((~flag & (y > 0)).sum()), int((~flag & (y == 0)).sum())
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    out.update({"flagged": int(flag.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec, "recall": rec,
                "f1": 2 * prec * rec / max(prec + rec, 1e-12), "accuracy": (tp + tn) / max(len(y), 1), "always_no": 1 - out["base"],
                "bal_acc": 0.5 * (rec + tn / max(tn + fp, 1))})
    return out


def deciles(df: pd.DataFrame, score: str, label: str) -> list[dict]:
    q = pd.qcut(df[score].rank(method="first"), 10, labels=False) + 1
    g = df.groupby(q)
    return [{"decile": int(k), "p_obs": float(v[label].mean()), "p_pred": float(v[score].mean()), "ret": float(v["ret_n"].mean()), "n": int(len(v))}
            for k, v in g]


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def platt_fit(p: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Monotone recalibration sigmoid(a * logit(p) + b) fitted by log loss on OUT-OF-FOLD scores. Ranks, AUC and
    precision@K are untouched; only the printed probability changes (scale_pos_weight inflates the raw score)."""
    from scipy.optimize import minimize
    x, y = _logit(p), np.asarray(y, float)

    def nll(ab):
        z = ab[0] * x + ab[1]
        return float(np.mean(np.logaddexp(0, -z) * y + np.logaddexp(0, z) * (1 - y)))

    r = minimize(nll, x0=np.array([1.0, 0.0]), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-7, "maxiter": 2000})
    return float(r.x[0]), float(r.x[1])


def platt_apply(p, ab) -> np.ndarray:
    return 1 / (1 + np.exp(-(ab[0] * _logit(p) + ab[1])))


# ---------------------------------------------------------------------------------------------------------------- models
def fit_lgb(tr: pd.DataFrame, feats: list[str], label: str):
    import lightgbm as lgb
    y = tr[label].to_numpy(float)
    p = dict(LGB, scale_pos_weight=float((len(y) - y.sum()) / max(y.sum(), 1)))
    return lgb.train(p, lgb.Dataset(tr[feats].to_numpy(float), y, feature_name=feats), ROUNDS)


def importance(m, feats: list[str], top: int = 12) -> list[tuple[str, float]]:
    g = np.asarray(m.feature_importance("gain"), float)
    g = g / max(g.sum(), 1e-12)
    o = np.argsort(-g)[:top]
    return [(feats[i], float(g[i])) for i in o]


class DL:
    """GRU over the last L_SEQ days of the 12 channels + MLP over the standardised static features."""

    def __init__(self, panel: Panel, feats: list[str], seed: int = SEED):
        import torch
        self.torch, self.panel, self.feats = torch, panel, feats
        torch.manual_seed(seed)
        torch.set_num_threads(8)
        self.CH = torch.from_numpy(panel.CH)                              # (C, T, N)
        self.offs = torch.arange(L_SEQ - 1, -1, -1)
        self.mu = self.sd = None
        self.net = None

    def _static(self, df: pd.DataFrame):
        X = df[self.feats].to_numpy(np.float32)
        if self.mu is None:
            self.mu = np.nanmean(X, axis=0)
            self.sd = np.nanstd(X, axis=0) + 1e-6
        Z = np.clip((X - self.mu) / self.sd, -5, 5)
        return self.torch.from_numpy(np.nan_to_num(Z).astype(np.float32))

    def _seq(self, ti, ni):
        t_idx = ti[:, None] - self.offs[None, :]                          # (B, L)
        return self.CH[:, t_idx, ni[:, None]].permute(1, 2, 0)            # (B, L, C)

    def _build(self, n_static: int):
        nn = self.torch.nn

        class Net(nn.Module):
            def __init__(s):
                super().__init__()
                s.gru = nn.GRU(len(SEQ_CH), 32, batch_first=True)
                s.mlp = nn.Sequential(nn.Linear(n_static, 64), nn.ReLU(), nn.Dropout(0.1))
                s.head = nn.Sequential(nn.Linear(32 + 64, 64), nn.ReLU(), nn.Linear(64, 1))

            def forward(s, seq, st):
                _, h = s.gru(seq)
                return s.head(self.torch.cat([h[-1], s.mlp(st)], 1)).squeeze(1)

        return Net()

    def predict(self, df: pd.DataFrame, bs: int = 16384) -> np.ndarray:
        torch = self.torch
        st = self._static(df)
        ti, ni = torch.from_numpy(df["ti"].to_numpy(np.int64)), torch.from_numpy(df["ni"].to_numpy(np.int64))
        self.net.eval()
        out = []
        with torch.no_grad():
            for i in range(0, len(df), bs):
                sl = slice(i, i + bs)
                out.append(torch.sigmoid(self.net(self._seq(ti[sl], ni[sl]), st[sl])).numpy())
        return np.concatenate(out)

    def fit(self, tr: pd.DataFrame, label: str, epochs: int = 6, bs: int = 4096, lr: float = 1e-3, log=print) -> dict:
        torch = self.torch
        self.mu = self.sd = None
        cut = tr["d"].quantile(0.9)
        va, tr = tr[tr["d"] > cut], tr[tr["d"] <= cut]
        st = self._static(tr)
        y = torch.from_numpy(tr[label].to_numpy(np.float32))
        ti, ni = torch.from_numpy(tr["ti"].to_numpy(np.int64)), torch.from_numpy(tr["ni"].to_numpy(np.int64))
        self.net = self._build(st.shape[1])
        pos = float(y.sum())
        pw = torch.tensor(min((len(y) - pos) / max(pos, 1.0), 50.0))
        opt = torch.optim.Adam(self.net.parameters(), lr=lr)
        lossf = torch.nn.BCEWithLogitsLoss(pos_weight=pw)
        best, best_state, hist = -1.0, None, []
        g = torch.Generator().manual_seed(SEED)
        for ep in range(epochs):
            self.net.train()
            perm = torch.randperm(len(y), generator=g)
            tot = 0.0
            for i in range(0, len(y), bs):
                b = perm[i:i + bs]
                opt.zero_grad()
                loss = lossf(self.net(self._seq(ti[b], ni[b]), st[b]), y[b])
                loss.backward()
                opt.step()
                tot += float(loss) * len(b)
            a = auc(va[label].to_numpy(float), self.predict(va))
            hist.append({"epoch": ep + 1, "loss": tot / len(y), "val_auc": a})
            log(f"    dl epoch {ep + 1} loss {tot / len(y):.4f} val_auc {a:.4f}")
            if a > best:
                best, best_state = a, {k: v.clone() for k, v in self.net.state_dict().items()}
            elif ep >= 2:
                break
        self.net.load_state_dict(best_state)
        return {"val_auc": best, "epochs": hist}


# ------------------------------------------------------------------------------------------------------------------ run
def pct_rank_in_day(df: pd.DataFrame, col: str) -> np.ndarray:
    return df.groupby("d")[col].rank(pct=True).to_numpy()


def run(conn, end: date, use_dl: bool, log=print) -> dict:
    t0 = time.time()
    df = load(conn, end)
    log(f"loaded {len(df):,} summary rows, {df['code'].nunique()} names, {df['d'].min().date()} -> {df['d'].max().date()} in {time.time() - t0:.0f}s")
    P = Panel(df)
    S = P.sample(need_label=True)
    log(f"sample {len(S):,} name-days, LOCK1 {int(S['LOCK1'].sum()):,} ({S['LOCK1'].mean() * 100:.2f} %), TOUCH1 {int(S['TOUCH1'].sum()):,} ({S['TOUCH1'].mean() * 100:.2f} %) in {time.time() - t0:.0f}s")
    res = {"end": str(end), "n": len(S), "names": int(S["code"].nunique()), "base": {"LOCK1": float(S["LOCK1"].mean()), "TOUCH1": float(S["TOUCH1"].mean())},
           "by_year": {}, "importance": {}, "dl_hist": {}, "deciles": {}, "placebo": {}}
    scored = []
    for yr in TEST_YEARS:
        tr, te = S[S["year"] < yr], S[S["year"] == yr].copy()
        log(f"== test {yr}: train {len(tr):,} ({int(tr['LOCK1'].sum())} locks) test {len(te):,} ({int(te['LOCK1'].sum())} locks)")
        row = {}
        for name, feats in SETS.items():
            m = fit_lgb(tr, feats, "LOCK1")
            te[f"p_{name}"] = m.predict(te[feats].to_numpy(float))
            thr = float(np.quantile(m.predict(tr[feats].to_numpy(float)), FLAG_Q))
            row[name] = accuracy_block(te, f"p_{name}", "LOCK1", thr)
            if yr == TEST_YEARS[-1]:
                res["importance"][name] = importance(m, feats)
                res["deciles"][name] = deciles(te, f"p_{name}", "LOCK1")
                if name == "BAR+MICRO":
                    rng = np.random.default_rng(SEED)
                    pl = []
                    for _ in range(N_PLACEBO):
                        sh = tr.copy()
                        sh["LOCK1"] = rng.permutation(sh["LOCK1"].to_numpy())
                        mm = fit_lgb(sh, feats, "LOCK1")
                        pl.append(auc(te["LOCK1"].to_numpy(float), mm.predict(te[feats].to_numpy(float))))
                    res["placebo"] = {"aucs": pl, "real": row[name]["auc"], "pct": float(100 * np.mean(np.array(pl) < row[name]["auc"]))}
            log(f"  lgb {name:10s} auc {row[name]['auc']:.3f} ap {row[name]['ap']:.3f} p@5 {row[name]['p@5'] * 100:.1f} % p@10 {row[name]['p@10'] * 100:.1f} % r@20 {row[name]['r@20'] * 100:.0f} % buyable p@10 {row[name]['buyable_p@10'] * 100:.1f} %")
        m = fit_lgb(tr, BAR + MICRO, "TOUCH1")
        te["p_TOUCH"] = m.predict(te[BAR + MICRO].to_numpy(float))
        thr = float(np.quantile(m.predict(tr[BAR + MICRO].to_numpy(float)), FLAG_Q))
        row["TOUCH1 BAR+MICRO"] = accuracy_block(te, "p_TOUCH", "TOUCH1", thr)
        log(f"  lgb TOUCH1     auc {row['TOUCH1 BAR+MICRO']['auc']:.3f} p@5 {row['TOUCH1 BAR+MICRO']['p@5'] * 100:.1f} % p@10 {row['TOUCH1 BAR+MICRO']['p@10'] * 100:.1f} %")
        if use_dl:
            dl = DL(P, BAR + MICRO)
            res["dl_hist"][yr] = dl.fit(tr, "LOCK1", log=log)
            te["p_DL"] = dl.predict(te)
            thr = float(np.quantile(dl.predict(tr), FLAG_Q))
            row["DL"] = accuracy_block(te, "p_DL", "LOCK1", thr)
            te["s_ENS"] = 0.5 * (pct_rank_in_day(te, "p_BAR+MICRO") + pct_rank_in_day(te, "p_DL"))
            row["ENS"] = accuracy_block(te, "s_ENS", "LOCK1", float(np.quantile(te["s_ENS"], FLAG_Q)))
            log(f"  DL             auc {row['DL']['auc']:.3f} p@5 {row['DL']['p@5'] * 100:.1f} % p@10 {row['DL']['p@10'] * 100:.1f} %  | ENS p@10 {row['ENS']['p@10'] * 100:.1f} %")
            if yr == TEST_YEARS[-1]:
                res["deciles"]["DL"] = deciles(te, "p_DL", "LOCK1")
        res["by_year"][yr] = row
        scored.append(te)
        log(f"  ({time.time() - t0:.0f}s)")
    # ---- verdicts by the pre-registered rule
    by = res["by_year"]
    micro_wins = sum(1 for y in TEST_YEARS if by[y]["BAR+MICRO"]["auc"] >= by[y]["BAR"]["auc"] + BAR_MICRO["auc"] and by[y]["BAR+MICRO"]["p@10"] >= by[y]["BAR"]["p@10"] + BAR_MICRO["p10"])
    res["verdict"] = {"micro_adds": micro_wins >= BAR_MICRO["years"], "micro_years": micro_wins}
    if use_dl:
        dl_ok = sum(1 for y in TEST_YEARS if by[y]["DL"]["auc"] >= by[y]["BAR+MICRO"]["auc"] - BAR_DL["auc_slack"])
        ens_ok = sum(1 for y in TEST_YEARS if by[y]["ENS"]["p@10"] > by[y]["BAR+MICRO"]["p@10"])
        res["verdict"].update({"dl_useful": dl_ok >= BAR_DL["years"], "dl_years": dl_ok, "ens_adopted": ens_ok >= BAR_ENS["years"], "ens_years": ens_ok})
    rank_model = "ENS" if res["verdict"].get("ens_adopted") else ("BAR+MICRO" if res["verdict"]["micro_adds"] else "BAR")
    res["verdict"]["rank_model"] = rank_model
    # ---- recalibrate the printed probabilities on the pooled out-of-fold scores (monotone: ranks unchanged)
    oof = pd.concat(scored)
    res["calib"] = {"tree": platt_fit(oof["p_BAR+MICRO"], oof["LOCK1"]), "touch": platt_fit(oof["p_TOUCH"], oof["TOUCH1"])}
    if use_dl:
        res["calib"]["dl"] = platt_fit(oof["p_DL"], oof["LOCK1"])
    te26 = scored[-1]
    te26 = te26.assign(pc=platt_apply(te26["p_BAR+MICRO"], res["calib"]["tree"]))
    res["deciles"]["BAR+MICRO"] = deciles(te26, "p_BAR+MICRO", "LOCK1")
    for d_, v in zip(res["deciles"]["BAR+MICRO"], te26.groupby(pd.qcut(te26["p_BAR+MICRO"].rank(method="first"), 10, labels=False))["pc"].mean()):
        d_["p_cal"] = float(v)
    # ---- the list for the next session: fit on everything labelled, score the last bar
    last = P.sample(need_label=False)
    last = last[last["d"] == last["d"].max()].copy()
    feats = BAR + MICRO if rank_model != "BAR" else BAR
    m_all = fit_lgb(S, feats, "LOCK1")
    last["p_tree"] = platt_apply(m_all.predict(last[feats].to_numpy(float)), res["calib"]["tree"])
    m_t = fit_lgb(S, BAR + MICRO, "TOUCH1")
    last["p_touch"] = platt_apply(m_t.predict(last[BAR + MICRO].to_numpy(float)), res["calib"]["touch"])
    if use_dl:
        dl = DL(P, BAR + MICRO)
        res["dl_hist"]["final"] = dl.fit(S, "LOCK1", log=log)
        last["p_dl"] = platt_apply(dl.predict(last), res["calib"]["dl"])
        last["score"] = 0.5 * (last["p_tree"].rank(pct=True) + last["p_dl"].rank(pct=True)) if rank_model == "ENS" else last["p_tree"]
    else:
        last["score"] = last["p_tree"]
    last = last.sort_values("score", ascending=False)
    res["rank_date"] = str(last["d"].max().date())
    res["rank"] = [{"code": r.code, "rank": i + 1, "p_lock": float(r.p_tree), "p_touch": float(r.p_touch), "p_dl": float(getattr(r, "p_dl", float("nan"))),
                    "score": float(r.score), "close": float(r.close), "ara_px": float(r.ara_px_next), "buyable": bool(r.buyable > 0), "locked_today": bool(r.lock > 0),
                    "ret1": float(r.ret1), "vr": float(r.vr), "qimb": float(r.qimb), "freq_ratio": float(r.freq_ratio), "fnet": float(r.fnet),
                    "days_since_ara": float(r.days_since_ara)} for i, r in enumerate(last.head(20).itertuples())]
    res["importance"]["final"] = importance(m_all, feats)
    res["seconds"] = time.time() - t0
    res["feed_note"] = feed_note(conn)
    return res


def feed_note(conn) -> dict:
    """How much tick history exists and how many ARA touches it holds (the reason the tick-level model waits)."""
    with conn.cursor() as cur:
        cur.execute("""WITH days AS (SELECT (ts AT TIME ZONE 'Asia/Jakarta')::date d, code, max(price) hi FROM idx.feed_trade GROUP BY 1, 2),
                            prev AS (SELECT code, trade_date, close, lead(trade_date) OVER (PARTITION BY code ORDER BY trade_date) nxt
                                     FROM idx.daily_summary WHERE trade_date >= '2026-09-01')
                       SELECT count(DISTINCT d.d), count(*), sum((d.hi >= p.close * (1 + CASE WHEN p.close <= 200 THEN 0.35 WHEN p.close <= 5000 THEN 0.25 ELSE 0.20 END) * 0.999)::int)
                       FROM days d JOIN prev p ON p.code = d.code AND p.nxt = d.d""")
        n_days, n_rows, n_touch = cur.fetchone()
    return {"sessions": int(n_days or 0), "name_days": int(n_rows or 0), "ara_touches": int(n_touch or 0)}


# --------------------------------------------------------------------------------------------------------------- report
def pc(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f} %"


def f3(x):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.3f}"


def render(res: dict, use_dl: bool) -> str:
    by, V = res["by_year"], res["verdict"]
    models = ["BAR", "MICRO", "BAR+MICRO"] + (["DL", "ENS"] if use_dl else [])
    L = [f"# IDX menu ML-3b — ARA besok dari bar + microstructure penutupan, LightGBM vs GRU — {res['end']} — {N_TRIALS} trials, cumulative N = {N_BEFORE + N_TRIALS}", ""]
    L.append(f"{res['n']:,} name-days ({res['names']} names) on the main boards, previous >= Rp 50, value >= Rp 1 bn, 2020-01 -> {res['end']}; walk-forward by test year. "
             f"Base rate LOCK1 (closes at ARA tomorrow) {pc(res['base']['LOCK1'], 2)}, TOUCH1 (touches it) {pc(res['base']['TOUCH1'], 2)}. Pre-registered in `research/idx_ara_micro.py`.")
    L.append("")
    L.append("## Accuracy of the ranked list, per test year (label LOCK1)")
    L.append("")
    L.append("| model | year | rows | base | AUC | AP | precision@5 | precision@10 | precision@20 | recall@20 | lift@5 | buyable share of top-10 | precision@10 among buyable | next-day ret top-10 | ret buyable top-10 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in models:
        for y in TEST_YEARS:
            r = by[y][m]
            L.append(f"| {m} | {y} | {r['n']:,} | {pc(r['base'], 2)} | {f3(r['auc'])} | {f3(r['ap'])} | **{pc(r['p@5'])}** | **{pc(r['p@10'])}** | {pc(r['p@20'])} | {pc(r['r@20'], 0)} | {r['lift@5']:.1f}x | {pc(r['buyable_share@10'], 0)} | {pc(r['buyable_p@10'])} | {pc(r['ret@10'], 2)} | {pc(r['buyable_ret@10'], 2)} |")
    L.append("")
    L.append("Reading: precision@K = of the K names the model ranks highest each day, the share that closes at ARA the next day (mean over days). recall@20 = the share of the year's ARA locks that were inside the daily top-20. lift = precision@5 / base rate. 'Buyable' = the pick still had an offer at today's close (not locked today).")
    L.append("")
    L.append("## Does the closing-book microstructure add to the bars? (BAR+MICRO minus BAR)")
    L.append("")
    L.append("| year | ΔAUC | Δprecision@10 | Δrecall@20 | Δbuyable precision@10 | MICRO alone AUC | MICRO alone precision@10 |")
    L.append("|---|---|---|---|---|---|---|")
    for y in TEST_YEARS:
        a, b, c = by[y]["BAR"], by[y]["BAR+MICRO"], by[y]["MICRO"]
        L.append(f"| {y} | {b['auc'] - a['auc']:+.3f} | {(b['p@10'] - a['p@10']) * 100:+.1f} pp | {(b['r@20'] - a['r@20']) * 100:+.1f} pp | {(b['buyable_p@10'] - a['buyable_p@10']) * 100:+.1f} pp | {f3(c['auc'])} | {pc(c['p@10'])} |")
    L.append("")
    L.append(f"**Rule (>= +0.01 AUC and >= +1 pp precision@10 in >= 4/5 years): {V['micro_years']}/5 years -> micro {'ADDS' if V['micro_adds'] else 'does NOT add'}.**")
    if use_dl:
        L.append(f"**DL (GRU) within 0.005 AUC of the tree in {V['dl_years']}/5 years -> {'USEFUL' if V['dl_useful'] else 'NOT useful'}; ENS beats the tree on precision@10 in {V['ens_years']}/5 -> {'ADOPTED' if V['ens_adopted'] else 'not adopted'}.**")
    L.append(f"**Rank model: {V['rank_model']}.**")
    L.append("")
    t = by[TEST_YEARS[-1]]["TOUCH1 BAR+MICRO"]
    L.append(f"Secondary label TOUCH1 (touches ARA tomorrow, BAR+MICRO): " + "; ".join(f"{y}: AUC {f3(by[y]['TOUCH1 BAR+MICRO']['auc'])}, p@5 {pc(by[y]['TOUCH1 BAR+MICRO']['p@5'])}, p@10 {pc(by[y]['TOUCH1 BAR+MICRO']['p@10'])}" for y in TEST_YEARS) + ".")
    L.append("")
    L.append("## 'Akurasi' at one operating point — flag the top 1 % of scores (threshold fixed on the training years)")
    L.append("")
    L.append("| model | year | flagged | TP | FP | FN | precision | recall | F1 | balanced acc | plain accuracy | always-'no' accuracy |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in (["BAR+MICRO"] + (["DL"] if use_dl else [])):
        for y in TEST_YEARS:
            r = by[y][m]
            L.append(f"| {m} | {y} | {r['flagged']:,} | {r['tp']} | {r['fp']:,} | {r['fn']} | **{pc(r['precision'])}** | **{pc(r['recall'])}** | {r['f1']:.3f} | {pc(r['bal_acc'])} | {pc(r['accuracy'], 2)} | {pc(r['always_no'], 2)} |")
    L.append("")
    L.append("Plain accuracy is not the number to quote: saying 'no ARA' for every name is already right 99.4-99.7 % of the time. Precision (how often a flagged name locks) and recall (how many of the locks were flagged) are the accuracy of this model.")
    L.append("")
    L.append(f"## Calibration by score decile, {TEST_YEARS[-1]} (BAR+MICRO)")
    L.append("")
    L.append("| decile | raw model P | calibrated P | observed P(LOCK1) | next-day return | n |")
    L.append("|---|---|---|---|---|---|")
    for r in res["deciles"]["BAR+MICRO"]:
        L.append(f"| {r['decile']} | {pc(r['p_pred'], 2)} | {pc(r.get('p_cal', float('nan')), 2)} | {pc(r['p_obs'], 2)} | {pc(r['ret'], 2)} | {r['n']:,} |")
    c = res["calib"]
    L.append("")
    L.append(f"The raw score is inflated by scale_pos_weight (decile 10 says {pc(res['deciles']['BAR+MICRO'][-1]['p_pred'], 0)}, reality {pc(res['deciles']['BAR+MICRO'][-1]['p_obs'], 1)}); every probability printed below is Platt-recalibrated on the pooled out-of-fold scores (tree a={c['tree'][0]:.2f} b={c['tree'][1]:.2f}" + (f", GRU a={c['dl'][0]:.2f} b={c['dl'][1]:.2f}" if 'dl' in c else "") + "). Ranks, AUC and precision@K do not change under a monotone map.")
    L.append("")
    L.append("## What the model looks at (gain share, final fit) and the placebo")
    L.append("")
    L.append("- BAR+MICRO: " + ", ".join(f"{k} {v * 100:.1f} %" for k, v in res["importance"]["BAR+MICRO"]))
    L.append("- MICRO alone: " + ", ".join(f"{k} {v * 100:.1f} %" for k, v in res["importance"]["MICRO"]))
    pl = res["placebo"]
    L.append(f"- placebo (LOCK1 shuffled in the training set, {N_PLACEBO} draws): AUC {', '.join(f'{a:.3f}' for a in pl['aucs'])} vs real {pl['real']:.3f} -> percentile {pl['pct']:.0f}.")
    if use_dl:
        h = res["dl_hist"].get(TEST_YEARS[-1], {})
        L.append(f"- GRU {TEST_YEARS[-1]} fold: best validation AUC {h.get('val_auc', float('nan')):.3f} after {len(h.get('epochs', []))} epochs; final fit val AUC {res['dl_hist']['final']['val_auc']:.3f}.")
    L.append("")
    fn = res["feed_note"]
    L.append("## Tick-level microstructure (Stockbit feed) — why it is not in the model yet")
    L.append("")
    L.append(f"The feed holds {fn['sessions']} sessions, {fn['name_days']:,} name-days over ~136 liquid names, and **{fn['ara_touches']} ARA touches**. A classifier cannot be trained on zero positives; ARA is a small-cap event and the feed covers the liquid tail. Pre-registered for when the feed reaches >= 20 sessions and >= 30 touches: intraday re-rank of the nightly list at 09:15 / 10:00 from OBI1/5, OFI 5-min, TFI, spread, distance to ARA in ticks, market OFI (the menu-31 feature set), label = touches ARA later that day; bar = AUC >= 0.70 and precision@5 >= 2x the nightly list's.")
    L.append("")
    L.append(f"## Ranked list for the session after {res['rank_date']} (model {V['rank_model']}, fit on every labelled day)")
    L.append("")
    L.append("| rank | code | P(lock at ARA), calibrated | P(touch), calibrated | P(GRU), calibrated | close | ARA price | locked today | buyable (offer at close) | ret1 | vol ratio | queue imbalance | freq ratio | foreign net | days since ARA |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in res["rank"]:
        xr = lambda v: "n/a" if not np.isfinite(v) else f"{v:.1f}x"  # noqa: E731
        L.append(f"| {r['rank']} | **{r['code']}** | **{pc(r['p_lock'])}** | {pc(r['p_touch'])} | {pc(r['p_dl'])} | {r['close']:,.0f} | {r['ara_px']:,.0f} | {'yes' if r['locked_today'] else '-'} | {'yes' if r['buyable'] else 'NO'} | {pc(r['ret1'])} | {xr(r['vr'])} | {r['qimb']:+.2f} | {xr(r['freq_ratio'])} | {pc(r['fnet'])} | {r['days_since_ara']:.0f} |")
    L.append("")
    L.append("Not a ticket. Menu ML-3 / menu 16: the names most likely to lock are mostly locked already (no offer to buy); the buyable picks lose on average. Use: a holder sells INTO a lock; a watcher knows which names to look at. ARA scope stays frozen (operator, 2026-09-23) - this is a study, not a screen.")
    L.append("")
    L.append(f"_Run {datetime.now():%Y-%m-%d %H:%M}, {res['seconds'] / 60:.1f} min._")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="2026-09-24")
    ap.add_argument("--no-dl", action="store_true")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    end = date.fromisoformat(a.end)
    out = a.out or os.path.join(HERE, f"IDX_ARA_MICRO_{end}.md")
    dsn = os.environ["INGEST_DB_DSN"]
    use_dl = not a.no_dl

    def log(s):
        print(s, flush=True)

    with psycopg.connect(dsn) as conn:
        res = run(conn, end, use_dl, log=log)
        md = render(res, use_dl)
        with open(out, "w", encoding="utf-8") as f:
            f.write(md)
        with open(out.replace(".md", ".json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, default=str)
        log(f"wrote {out}")
        if not a.no_store:
            from blackheart_ingest.idx import research_store as rs
            V = res["verdict"]
            summary = {"n_trials": N_TRIALS, "trials_cumulative": N_BEFORE + N_TRIALS, "verdict": V, "base": res["base"], "placebo": res["placebo"],
                       "by_year": {str(y): {m: {k: r[k] for k in ("auc", "ap", "p@5", "p@10", "p@20", "r@20", "buyable_p@10", "precision", "recall", "f1")}
                                            for m, r in row.items()} for y, row in res["by_year"].items()}, "feed": res["feed_note"]}
            names = [{"code": r["code"], "screens": ["ara_rank"], "score": r["p_lock"], "rank": r["rank"],
                      "features": {k: r[k] for k in ("ret1", "vr", "qimb", "freq_ratio", "fnet", "days_since_ara")},
                      "context": {"ara_px": r["ara_px"], "close": r["close"], "buyable": r["buyable"], "locked_today": r["locked_today"], "p_touch": r["p_touch"], "p_dl": r["p_dl"]}}
                     for r in res["rank"]]
            sid = rs.record_study(conn, "ml_ara_micro", end, params={"labels": ["LOCK1", "TOUCH1"], "feature_sets": {k: len(v) for k, v in SETS.items()}, "lgb": LGB,
                                                                     "rounds": ROUNDS, "seq_len": L_SEQ, "seq_channels": SEQ_CH, "test_years": TEST_YEARS, "seed": SEED},
                                  summary=summary, names=names, report_path=os.path.relpath(out, ROOT).replace("\\", "/"),
                                  note=f"menu ML-3b: micro {'adds' if V['micro_adds'] else 'no add'}, rank model {V['rank_model']}")
            log(f"stored study #{sid}")


if __name__ == "__main__":
    main()
