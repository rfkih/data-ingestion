#!/usr/bin/env python3
"""IDX menu 31 PRELIM — machine learning / deep learning on the ORDER BOOK ("supply & demand") to predict the price (operator,
2026-09-23: "coba gunakan machine learning atau deep learning untuk memprediksi harga saham berdasarkan market microstructure,
kan bisa dilihat dari supply demand nya").

Two sessions of the Stockbit feed (09-22 train, 09-23 test). A direction read, not an adoption: re-run at >= 20 sessions.

DESIGN (pre-registered before the first run)
  Grid       every name on a 10-second grid inside the continuous phases (Mon-Thu 09:00-11:59 / 13:30-15:49); the book = the last
             snapshot in each 10 s bucket, carried forward inside a session; prints aggregated per bucket (buy / sell volume by verb).
             Names with >= 600 valid steps per day.
  Labels     smoothed mid move (DeepLOB style): m_h = mean(mid_{t+1..t+h}) - mid_t in TICKS for h = 6 / 30 / 90 steps (1 / 5 / 15 min).
             UP = m_h >= +0.5 tick, DOWN = m_h <= -0.5 tick, else FLAT (3 classes). Binary read = UP vs not. Regression read = bps move.
  Model A    LightGBM on hand-made supply/demand features (no time-of-day - the drift artefact of menu 28):
             OBI at 1/3/5/10 levels (volume) and order-count imbalance at 1/5; microprice - mid in ticks; spread (ticks, bps);
             book sparsity (ticks from level 1 to level 5 on each side); depth concentration (top-3 share of top-10, each side);
             OFI (Cont-Kukanov-Stoikov) summed over 30 s / 1 min / 5 min, scaled by the name's mean top-of-book depth;
             queue change dBV1 / dOV1 over 30 s (log ratio); TFI 1 / 5 min from prints; RET 1 / 5 / 15 min; realised vol 15 min;
             pos_day, dist_hi / dist_lo (ticks); market context = EW market return so far, breadth, market OFI-5 (mean over names).
             Binary UP model (AUC) + regression model (IC) per horizon. 400 rounds, early stop on the last 20 % of the train day by time.
  Model B    DeepLOB-lite (PyTorch, CPU): input = the last 30 steps (5 min) x 40 raw book columns per step
             (10 levels x (price distance from mid in ticks, volume / the name's day-1 median top-10 volume) x 2 sides, missing level =
             distance 50 / volume 0), conv over (price, volume) pairs -> conv over time -> conv over sides -> conv over levels ->
             LSTM(32) -> 3-class softmax. Adam 1e-3, batch 1024, <= 8 epochs, early stop on the validation slice (last 20 % of the
             train day by time). P(up) = softmax[UP].
  Reads      test day (09-23): accuracy vs the majority class; AUC of P(up) for UP-vs-not; IC (Spearman) of the score vs the bps move,
             pooled and per name (share of names with IC > 0); calibration of P(up) in deciles; gross mid move in ticks of the top
             decile vs the half-spread in ticks (does the forecast exceed what a taker pays?).
             Placebo for model A: labels shuffled within name, 10 draws -> AUC percentile. (Model B placebo = the shuffled-label AUC
             of model A at the same horizon; a DL placebo is unaffordable on CPU and would answer the same question.)
  Policy     on the test day, signal = top decile of P(up) for h = 30 / 90 (5 / 15 min): TAKER buy at the offer at t; exit at t+h:
             (i) sell at the bid (what a retail taker gets), (ii) sell at the mid (the optimistic bound of a maker exit). Fees 30 bps.
             One open trade per name at a time. 2 models x 2 horizons x 2 exits = 8 policy trials.
  Trials     model trials 2 x 3 horizons = 6, policy trials 8 -> 14 (cumulative 651 -> 665).
  Bar        MODEL LEAD: test AUC >= 0.60, per-name IC > 0 for >= 70 % of names, placebo pct >= 95.
             POLICY CANDIDATE: >= 100 trades, mean net >= +20 bps, t >= 2.0 on the test day (ONE test day -> flagged as such).
             With two sessions nothing is adoptable; the model bar decides only whether a proper study is worth its 20 sessions.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_lob_ml.py
  [--train 2026-09-22 --test 2026-09-23] [--no-store] [--no-dl] [--out research/IDX_LOB_ML_<test>.md]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import date, datetime

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blackheart-ingest", "src"))
_spec = importlib.util.spec_from_file_location("idx_updown_prob", os.path.join(HERE, "idx_updown_prob.py"))
up = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(up)

STEP_S = 10
SEQ = 30
HORIZONS = {"h1m": 6, "h5m": 30, "h15m": 90}
POLICY_H = ("h5m", "h15m")
MIN_STEPS = 600
FEE_BPS = 30.0
SEED = 20260923
N_PLACEBO = 10
N_TRIALS_BEFORE = 651
BAR_MODEL = {"auc": 0.60, "ic_share": 0.70, "placebo_pct": 95.0}
BAR_POLICY = {"trades": 100, "net": 20.0, "t": 2.0}
LEVELS = 10
FEATS = ["OBI1", "OBI3", "OBI5", "OBI10", "OBN1", "OBN5", "micro", "sprd_t", "sprd_bps", "gap_b", "gap_o", "conc_b", "conc_o",
         "OFI30", "OFI1", "OFI5", "dBV1", "dOV1", "TFI1", "TFI5", "RET1", "RET5", "RET15", "rvol15", "pos_day", "dist_hi", "dist_lo",
         "MKT_RET", "MKT_BREADTH", "MKT_OFI5"]


# ------------------------------------------------------------------------------------------------------------------ data
def load_day(conn: psycopg.Connection, day: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (code, b) code, b AT TIME ZONE 'Asia/Jakarta', bid_px, bid_vol, bid_n, off_px, off_vol, off_n
                       FROM (SELECT code, ts, bid_px, bid_vol, bid_n, off_px, off_vol, off_n,
                                    to_timestamp(floor(extract(epoch FROM ts) / %s) * %s) AS b
                             FROM idx.feed_book WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code <> 'IHSG') x
                       ORDER BY code, b, ts DESC""", (STEP_S, STEP_S, day))
        book = pd.DataFrame(cur.fetchall(), columns=["code", "t", "bid_px", "bid_vol", "bid_n", "off_px", "off_vol", "off_n"])
        cur.execute("""SELECT code, to_timestamp(floor(extract(epoch FROM ts) / %s) * %s) AT TIME ZONE 'Asia/Jakarta',
                              sum(qty) FILTER (WHERE verb = 'B'), sum(qty) FILTER (WHERE verb = 'S'), sum(qty), count(*)
                       FROM idx.feed_trade WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s GROUP BY 1, 2""", (STEP_S, STEP_S, day))
        tr = pd.DataFrame(cur.fetchall(), columns=["code", "t", "bvol", "svol", "vol", "n"])
    book["t"] = pd.to_datetime(book["t"])
    tr["t"] = pd.to_datetime(tr["t"])
    for c in ("bvol", "svol", "vol", "n"):
        tr[c] = pd.to_numeric(tr[c], errors="coerce").astype(float).fillna(0.0)
    return book, tr


def grid_for(day: date) -> pd.DatetimeIndex:
    spec = up.SESSIONS_FRI if day.weekday() == 4 else up.SESSIONS_MON_THU
    parts = [pd.date_range(datetime.combine(day, datetime.strptime(a, "%H:%M").time()),
                           datetime.combine(day, datetime.strptime(b, "%H:%M").time()) + pd.Timedelta(seconds=59), freq=f"{STEP_S}s")
             for a, b in spec]
    return parts


def arr10(col: pd.Series, fill: float) -> np.ndarray:
    out = np.full((len(col), LEVELS), fill, dtype=float)
    for i, v in enumerate(col.to_numpy()):
        if v is None:
            continue
        k = min(len(v), LEVELS)
        if k:
            out[i, :k] = np.asarray(v[:k], dtype=float)
    return out


def build_name(book: pd.DataFrame, tr: pd.DataFrame, day: date) -> dict | None:
    """One name-day -> dict of aligned arrays on the grid (session id, mid, tick, raw 40 cols, features, labels)."""
    parts_idx = grid_for(day)
    b = book.set_index("t").sort_index()
    b = b[~b.index.duplicated(keep="last")]
    t = tr.set_index("t").sort_index()
    rows = []
    for si, idx in enumerate(parts_idx):
        s = b.reindex(idx, method="ffill")                     # carry forward inside the session only
        first_valid = b.index.searchsorted(idx[0])
        if first_valid >= len(b):
            continue
        s = s.join(t.reindex(idx)[["bvol", "svol", "vol", "n"]].fillna(0.0))
        s["session"] = si
        rows.append(s)
    if not rows:
        return None
    s = pd.concat(rows)
    s = s[s["bid_px"].notna() & s["off_px"].notna()]
    if len(s) < MIN_STEPS:
        return None
    bpx, bvl, bn = arr10(s["bid_px"], np.nan), arr10(s["bid_vol"], 0.0), arr10(s["bid_n"], 0.0)
    opx, ovl, on = arr10(s["off_px"], np.nan), arr10(s["off_vol"], 0.0), arr10(s["off_n"], 0.0)
    ok = np.isfinite(bpx[:, 0]) & np.isfinite(opx[:, 0]) & (bpx[:, 0] > 0) & (opx[:, 0] > bpx[:, 0])
    if ok.sum() < MIN_STEPS:
        return None
    s = s[ok]
    bpx, bvl, bn, opx, ovl, on = (a[ok] for a in (bpx, bvl, bn, opx, ovl, on))
    mid = (bpx[:, 0] + opx[:, 0]) / 2
    tick = up.tick_size(mid)
    sess = s["session"].to_numpy()
    n = len(s)
    # ---- raw 40 columns for the DL model: per level (bid dist, bid vol, off dist, off vol), missing = dist 50 / vol 0
    bd = np.where(np.isfinite(bpx), (mid[:, None] - bpx) / tick[:, None], 50.0)
    od = np.where(np.isfinite(opx), (opx - mid[:, None]) / tick[:, None], 50.0)
    raw = np.empty((n, 4 * LEVELS), dtype=np.float32)
    raw[:, 0::4], raw[:, 1::4], raw[:, 2::4], raw[:, 3::4] = bd, bvl, od, ovl
    # ---- features
    F = pd.DataFrame(index=s.index)
    for L in (1, 3, 5, 10):
        bs, os_ = bvl[:, :L].sum(1), ovl[:, :L].sum(1)
        F[f"OBI{L}"] = (bs - os_) / np.where(bs + os_ > 0, bs + os_, np.nan)
    for L in (1, 5):
        bs, os_ = bn[:, :L].sum(1), on[:, :L].sum(1)
        F[f"OBN{L}"] = (bs - os_) / np.where(bs + os_ > 0, bs + os_, np.nan)
    den = bvl[:, 0] + ovl[:, 0]
    micro = (bpx[:, 0] * ovl[:, 0] + opx[:, 0] * bvl[:, 0]) / np.where(den > 0, den, np.nan)
    F["micro"] = (micro - mid) / tick
    F["sprd_t"] = (opx[:, 0] - bpx[:, 0]) / tick
    F["sprd_bps"] = (opx[:, 0] - bpx[:, 0]) / mid * 1e4
    F["gap_b"] = np.where(np.isfinite(bpx[:, 4]), (bpx[:, 0] - bpx[:, 4]) / tick, 50.0)
    F["gap_o"] = np.where(np.isfinite(opx[:, 4]), (opx[:, 4] - opx[:, 0]) / tick, 50.0)
    b10, o10 = bvl.sum(1), ovl.sum(1)
    F["conc_b"] = bvl[:, :3].sum(1) / np.where(b10 > 0, b10, np.nan)
    F["conc_o"] = ovl[:, :3].sum(1) / np.where(o10 > 0, o10, np.nan)
    # OFI (Cont et al.) between consecutive steps inside a session
    pb, pb1, po, po1 = bpx[:, 0], np.roll(bpx[:, 0], 1), opx[:, 0], np.roll(opx[:, 0], 1)
    vb, vb1, vo, vo1 = bvl[:, 0], np.roll(bvl[:, 0], 1), ovl[:, 0], np.roll(ovl[:, 0], 1)
    e = (pb >= pb1) * vb - (pb <= pb1) * vb1 - (po <= po1) * vo + (po >= po1) * vo1
    new_sess = np.r_[True, sess[1:] != sess[:-1]]
    e[new_sess] = 0.0
    depth = np.nanmean(bvl[:, 0] + ovl[:, 0]) / 2 or 1.0
    ef = pd.Series(e / depth)
    g = pd.Series(sess)
    F["OFI30"] = ef.groupby(g).rolling(3, min_periods=1).sum().reset_index(level=0, drop=True).to_numpy()
    F["OFI1"] = ef.groupby(g).rolling(6, min_periods=1).sum().reset_index(level=0, drop=True).to_numpy()
    F["OFI5"] = ef.groupby(g).rolling(30, min_periods=1).sum().reset_index(level=0, drop=True).to_numpy()
    lb, lo_ = pd.Series(np.log1p(bvl[:, 0])), pd.Series(np.log1p(ovl[:, 0]))
    F["dBV1"] = (lb - lb.groupby(g).shift(3)).to_numpy()
    F["dOV1"] = (lo_ - lo_.groupby(g).shift(3)).to_numpy()
    bv, sv = pd.Series(s["bvol"].to_numpy()), pd.Series(s["svol"].to_numpy())
    for k, w in (("TFI1", 6), ("TFI5", 30)):
        B = bv.groupby(g).rolling(w, min_periods=1).sum().reset_index(level=0, drop=True)
        S = sv.groupby(g).rolling(w, min_periods=1).sum().reset_index(level=0, drop=True)
        F[k] = ((B - S) / (B + S).replace(0, np.nan)).to_numpy()
    m = pd.Series(mid)
    for k, w in (("RET1", 6), ("RET5", 30), ("RET15", 90)):
        F[k] = (m / m.groupby(g).shift(w) - 1).to_numpy() * 1e4
    r1 = np.log(m).diff()
    r1[new_sess] = np.nan
    F["rvol15"] = pd.Series(r1).groupby(g).rolling(90, min_periods=30).std().reset_index(level=0, drop=True).to_numpy() * 1e4
    F["pos_day"] = (mid / mid[0] - 1) * 1e4
    F["dist_hi"] = (np.maximum.accumulate(mid) - mid) / tick
    F["dist_lo"] = (mid - np.minimum.accumulate(mid)) / tick
    # ---- labels: smoothed forward mid in ticks, per horizon, inside the session
    lab = {}
    for k, h in HORIZONS.items():
        fwd = np.full(n, np.nan)
        for si in np.unique(sess):
            ix = np.flatnonzero(sess == si)
            mm = mid[ix]
            cs = np.r_[0.0, np.cumsum(mm)]
            L = len(ix)
            valid = np.arange(L - h)
            fwd[ix[valid]] = (cs[valid + 1 + h] - cs[valid + 1]) / h
        lab[k] = (fwd - mid) / tick
        lab[k + "_bps"] = (fwd / mid - 1) * 1e4
    return {"t": s.index.to_numpy(), "session": sess, "mid": mid, "tick": tick, "bid1": bpx[:, 0], "off1": opx[:, 0],
            "raw": raw, "F": F.reset_index(drop=True), "lab": lab, "n": n}


def build_day(conn: psycopg.Connection, day: date) -> dict[str, dict]:
    book, tr = load_day(conn, day)
    out = {}
    for code, g in book.groupby("code"):
        d = build_name(g.drop(columns="code"), tr[tr["code"] == code].drop(columns="code"), day)
        if d is not None:
            out[code] = d
    # market context on the common grid
    frames = [pd.DataFrame({"t": d["t"], "pos": d["F"]["pos_day"].to_numpy(), "ofi5": d["F"]["OFI5"].to_numpy()}) for d in out.values()]
    M = pd.concat(frames).groupby("t").agg(MKT_RET=("pos", "mean"), MKT_BREADTH=("pos", lambda x: float((x > 0).mean())), MKT_OFI5=("ofi5", "mean"))
    for d in out.values():
        mm = M.reindex(d["t"])
        for c in ("MKT_RET", "MKT_BREADTH", "MKT_OFI5"):
            d["F"][c] = mm[c].to_numpy()
    return out


def panel(days: dict[str, dict]) -> pd.DataFrame:
    parts = []
    for code, d in days.items():
        P = d["F"].copy()
        P["code"] = code
        P["i"] = np.arange(d["n"])
        P["session"] = d["session"]
        P["bid1"], P["off1"], P["mid"], P["tick"] = d["bid1"], d["off1"], d["mid"], d["tick"]
        for k in HORIZONS:
            P[k] = d["lab"][k]
            P[k + "_bps"] = d["lab"][k + "_bps"]
        parts.append(P)
    return pd.concat(parts, ignore_index=True)


# ------------------------------------------------------------------------------------------------------------- model A
def lgb_models(tr: pd.DataFrame, te: pd.DataFrame, h: str, seed: int = SEED) -> tuple[np.ndarray, np.ndarray, dict]:
    import lightgbm as lgb
    y_up = (tr[h] >= 0.5).astype(float).to_numpy()
    cut = int(len(tr) * 0.8)                                                        # tr is sorted by i within code -> sort by time
    order = np.argsort(tr["i"].to_numpy(), kind="stable")
    tr_i, va_i = order[:cut], order[cut:]
    params = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 300, "bagging_fraction": 0.8,
              "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 5.0, "seed": seed, "verbose": -1, "num_threads": 16}
    X = tr[FEATS].to_numpy(dtype=float)
    dtr, dva = lgb.Dataset(X[tr_i], y_up[tr_i], feature_name=FEATS), lgb.Dataset(X[va_i], y_up[va_i], feature_name=FEATS)
    m = lgb.train(params, dtr, 400, valid_sets=[dva], callbacks=[lgb.early_stopping(30, verbose=False)])
    p = np.asarray(m.predict(te[FEATS].to_numpy(dtype=float), num_iteration=m.best_iteration))
    gain = np.asarray(m.feature_importance(importance_type="gain"), dtype=float)
    imp = dict(zip(FEATS, (gain / gain.sum()).round(3).tolist(), strict=True))
    pr = dict(params, objective="regression_l2")
    yr = tr[h + "_bps"].to_numpy()
    mr = lgb.train(pr, lgb.Dataset(X[tr_i], yr[tr_i], feature_name=FEATS), 400,
                   valid_sets=[lgb.Dataset(X[va_i], yr[va_i], feature_name=FEATS)], callbacks=[lgb.early_stopping(30, verbose=False)])
    r = np.asarray(mr.predict(te[FEATS].to_numpy(dtype=float), num_iteration=mr.best_iteration))
    return p, r, {"importance": imp, "rounds": int(m.best_iteration), "rounds_reg": int(mr.best_iteration)}


def placebo_auc(tr: pd.DataFrame, te: pd.DataFrame, h: str, rng: np.random.Generator) -> list[float]:
    import lightgbm as lgb
    out = []
    X, Xt = tr[FEATS].to_numpy(dtype=float), te[FEATS].to_numpy(dtype=float)
    yt = (te[h] >= 0.5).astype(float).to_numpy()
    codes = tr["code"].to_numpy()
    base = (tr[h] >= 0.5).astype(float).to_numpy()
    for k in range(N_PLACEBO):
        y = base.copy()
        for c in np.unique(codes):
            ix = np.flatnonzero(codes == c)
            y[ix] = rng.permutation(y[ix])
        params = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 300, "bagging_fraction": 0.8,
                  "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 5.0, "seed": SEED + k, "verbose": -1, "num_threads": 16}
        m = lgb.train(params, lgb.Dataset(X, y, feature_name=FEATS), 150)
        out.append(up.auc_score(yt, np.asarray(m.predict(Xt))))
    return out


# ------------------------------------------------------------------------------------------------------------- model B
def dl_sequences(days: dict[str, dict], h: str, vol_scale: dict[str, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Concatenate raw arrays; return X (N x 40 normalised), y3 (N,), valid end-indices (window inside one session + label), code ids, i."""
    Xs, ys, ends, codes, iis, off = [], [], [], [], [], 0
    for code, d in days.items():
        raw = d["raw"].copy()
        sc = vol_scale.get(code, 1.0)
        raw[:, 1::4] = np.log1p(raw[:, 1::4] / sc)
        raw[:, 3::4] = np.log1p(raw[:, 3::4] / sc)
        raw[:, 0::4] = np.minimum(raw[:, 0::4], 50.0) / 10.0
        raw[:, 2::4] = np.minimum(raw[:, 2::4], 50.0) / 10.0
        lab = d["lab"][h]
        y = np.where(lab >= 0.5, 2, np.where(lab <= -0.5, 0, 1)).astype(np.int64)
        sess = d["session"]
        n = d["n"]
        ok = np.zeros(n, dtype=bool)
        for si in np.unique(sess):
            ix = np.flatnonzero(sess == si)
            if len(ix) > SEQ:
                ok[ix[SEQ - 1:]] = True
        ok &= np.isfinite(lab)
        Xs.append(raw.astype(np.float32))
        ys.append(y)
        ends.append(np.flatnonzero(ok) + off)
        codes.append(np.full(int(ok.sum()), code))
        iis.append(np.flatnonzero(ok))
        off += n
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(ends), np.concatenate(codes), np.concatenate(iis)


def train_dl(Xtr: np.ndarray, ytr: np.ndarray, ends_tr: np.ndarray, Xte: np.ndarray, ends_te: np.ndarray, log: list[str]) -> np.ndarray:
    import torch
    import torch.nn as nn
    torch.manual_seed(SEED)
    torch.set_num_threads(16)

    class DeepLOBLite(nn.Module):
        def __init__(self):
            super().__init__()
            act = nn.LeakyReLU(0.01)
            self.c1 = nn.Sequential(nn.Conv2d(1, 16, (1, 2), stride=(1, 2)), act, nn.Conv2d(16, 16, (4, 1)), act)      # (px,vol) pairs; time
            self.c2 = nn.Sequential(nn.Conv2d(16, 16, (1, 2), stride=(1, 2)), act, nn.Conv2d(16, 16, (4, 1)), act)   # sides; time
            self.c3 = nn.Sequential(nn.Conv2d(16, 32, (1, LEVELS)), act, nn.Conv2d(32, 32, (4, 1)), act)             # levels; time
            self.lstm = nn.LSTM(32, 32, batch_first=True)
            self.out = nn.Linear(32, 3)

        def forward(self, x):                      # x: (B, SEQ, 40) ordered per level as (bd, bv, od, ov)
            B, T, _ = x.shape
            x = x.view(B, T, LEVELS, 4).view(B, 1, T, LEVELS * 4)
            x = self.c1(x)                          # (B,16,T-3, 20): per level (bid pair, off pair)
            x = self.c2(x)                          # (B,16,T-6, 10): per level
            x = self.c3(x)                          # (B,32,T-9, 1)
            x = x.squeeze(-1).transpose(1, 2)       # (B, T', 32)
            o, _ = self.lstm(x)
            return self.out(o[:, -1])

    win = np.arange(-SEQ + 1, 1)
    Xtr_t, Xte_t = torch.from_numpy(Xtr), torch.from_numpy(Xte)
    ytr_t = torch.from_numpy(ytr)
    order = np.argsort(ends_tr, kind="stable")                    # time order within the concatenation is per name; split by position
    cut = int(len(ends_tr) * 0.8)
    rng = np.random.default_rng(SEED)
    per_name_cut = []                                             # validation = last 20 % of each name's windows (time)
    # ends_tr is grouped by name in build order and increasing inside a name -> take the last 20 % per contiguous run
    runs = np.flatnonzero(np.diff(ends_tr) < 0) + 1
    starts = np.r_[0, runs]
    stops = np.r_[runs, len(ends_tr)]
    tr_idx, va_idx = [], []
    for a, b in zip(starts, stops, strict=True):
        c = a + int((b - a) * 0.8)
        tr_idx.append(np.arange(a, c))
        va_idx.append(np.arange(c, b))
    tr_idx, va_idx = np.concatenate(tr_idx), np.concatenate(va_idx)
    model = DeepLOBLite()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    lossf = nn.CrossEntropyLoss()

    def batches(idx: np.ndarray, X_t, ends, bs: int, shuffle: bool):
        if shuffle:
            idx = rng.permutation(idx)
        for k in range(0, len(idx), bs):
            sel = ends[idx[k:k + bs]]
            xb = X_t[torch.from_numpy(sel[:, None] + win[None, :])]
            yield xb, idx[k:k + bs]

    best, best_state, bad = np.inf, None, 0
    for ep in range(8):
        model.train()
        t0 = time.time()
        tl, nb = 0.0, 0
        for xb, sel in batches(tr_idx, Xtr_t, ends_tr, 1024, True):
            opt.zero_grad()
            loss = lossf(model(xb), ytr_t[torch.from_numpy(ends_tr[sel])])
            loss.backward()
            opt.step()
            tl += loss.item()
            nb += 1
        model.eval()
        vl, vn = 0.0, 0
        with torch.no_grad():
            for xb, sel in batches(va_idx, Xtr_t, ends_tr, 4096, False):
                vl += lossf(model(xb), ytr_t[torch.from_numpy(ends_tr[sel])]).item() * len(sel)
                vn += len(sel)
        vl /= max(vn, 1)
        log.append(f"epoch {ep + 1}: train loss {tl / max(nb, 1):.4f}, val loss {vl:.4f}, {time.time() - t0:.0f} s")
        if vl < best - 1e-4:
            best, bad = vl, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= 2:
                break
    model.load_state_dict(best_state)
    model.eval()
    P = []
    with torch.no_grad():
        for xb, _ in batches(np.arange(len(ends_te)), Xte_t, ends_te, 4096, False):
            P.append(torch.softmax(model(xb), dim=1).numpy())
    return np.concatenate(P)


# --------------------------------------------------------------------------------------------------------------- reads
def model_reads(te: pd.DataFrame, score: np.ndarray, h: str) -> dict:
    y = (te[h] >= 0.5).astype(float).to_numpy()
    mv = te[h + "_bps"].to_numpy()
    ok = np.isfinite(score) & np.isfinite(mv)
    y, mv, sc = y[ok], mv[ok], score[ok]
    codes = te["code"].to_numpy()[ok]
    ic_names, auc_names = [], []
    for c in np.unique(codes):
        ix = codes == c
        if ix.sum() >= 200 and np.std(sc[ix]) > 0:
            ic_names.append(float(stats.spearmanr(sc[ix], mv[ix]).statistic))
            a = up.auc_score(y[ix], sc[ix])
            if np.isfinite(a):
                auc_names.append(a)
    ic_names = np.asarray(ic_names)
    top = sc >= np.quantile(sc, 0.9)
    tick = te["tick"].to_numpy()[ok]
    half_spread_t = ((te["off1"] - te["bid1"]) / 2 / te["tick"]).to_numpy()[ok]
    move_t = te[h].to_numpy()[ok]
    dec = pd.qcut(pd.Series(sc), 10, labels=False, duplicates="drop")
    cal = pd.DataFrame({"d": dec, "y": y, "mv": mv}).groupby("d").agg(p_up=("y", "mean"), bps=("mv", "mean"), n=("y", "size")).reset_index()
    return {"auc": up.auc_score(y, sc), "auc_name_median": float(np.median(auc_names)) if auc_names else np.nan, "ic_pooled": float(stats.spearmanr(sc, mv).statistic), "ic_name_median": float(np.median(ic_names)),
            "ic_share_pos": float((ic_names > 0).mean()), "n_names": int(len(ic_names)), "base_up": float(y.mean()),
            "top_up": float(y[top].mean()), "top_move_ticks": float(np.nanmean(move_t[top])), "top_half_spread_ticks": float(np.nanmean(half_spread_t[top])),
            "calibration": cal.to_dict("records"), "n": int(ok.sum())}


def policy(te: pd.DataFrame, score: np.ndarray, h: str, exit_at: str) -> dict:
    H = HORIZONS[h]
    te = te.assign(score=score)
    thr = np.nanquantile(score, 0.9)
    nets = []
    for code, g in te.groupby("code", sort=False):
        g = g.sort_values("i")
        i = g["i"].to_numpy()
        off, bid, mid, sess = g["off1"].to_numpy(), g["bid1"].to_numpy(), g["mid"].to_numpy(), g["session"].to_numpy()
        sc = g["score"].to_numpy()
        pos = {int(v): k for k, v in enumerate(i)}
        busy = -1
        for k in np.flatnonzero(sc >= thr):
            if i[k] <= busy:
                continue
            j = pos.get(int(i[k]) + H)
            if j is None or sess[j] != sess[k] or not np.isfinite(off[k]) or off[k] <= 0:
                continue
            px = bid[j] if exit_at == "bid" else mid[j]
            nets.append((px / off[k] - 1) * 1e4 - FEE_BPS)
            busy = int(i[k]) + H
    a = np.asarray(nets)
    r = {"h": h, "exit": exit_at, "trades": int(len(a)), "mean": float(a.mean()) if len(a) else np.nan,
         "median": float(np.median(a)) if len(a) else np.nan, "p_win": float((a > 0).mean()) if len(a) else np.nan,
         "t": float(a.mean() / a.std(ddof=1) * np.sqrt(len(a))) if len(a) > 2 and a.std(ddof=1) > 0 else np.nan}
    r["CANDIDATE"] = bool(r["trades"] >= BAR_POLICY["trades"] and np.isfinite(r["mean"]) and r["mean"] >= BAR_POLICY["net"] and np.isfinite(r["t"]) and r["t"] >= BAR_POLICY["t"])
    return r


# ---------------------------------------------------------------------------------------------------------------- run
def run(dsn: str, d_train: date, d_test: date, out_path: str, store: bool, study_name: str, do_dl: bool) -> dict:
    t0 = time.time()
    with psycopg.connect(dsn) as conn:
        TR = build_day(conn, d_train)
        TE = build_day(conn, d_test)
    common = sorted(set(TR) & set(TE))
    TR, TE = {c: TR[c] for c in common}, {c: TE[c] for c in common}
    Ptr, Pte = panel(TR), panel(TE)
    log = [f"built {len(common)} names, train {len(Ptr):,} / test {len(Pte):,} steps in {time.time() - t0:.0f} s"]
    res: dict = {"desc": {"train": d_train.isoformat(), "test": d_test.isoformat(), "names": len(common), "rows_train": len(Ptr), "rows_test": len(Pte),
                          "mkt_ret_close": {d_train.isoformat(): float(Ptr.groupby("i")["pos_day"].mean().iloc[-1]),
                                            d_test.isoformat(): float(Pte.groupby("i")["pos_day"].mean().iloc[-1])}},
                 "models": {}, "policies": [], "log": log}
    rng = np.random.default_rng(SEED)
    scores: dict[tuple[str, str], np.ndarray] = {}
    for h in HORIZONS:
        tr = Ptr.dropna(subset=[*FEATS, h])
        te = Pte.dropna(subset=[*FEATS, h])
        p, r, info = lgb_models(tr, te, h)
        rd = model_reads(te, p, h)
        rd["ic_reg_pooled"] = float(stats.spearmanr(r, te[h + "_bps"].to_numpy(), nan_policy="omit").statistic)
        pl = placebo_auc(tr, te, h, rng)
        rd["placebo_auc_mean"] = float(np.mean(pl))
        rd["placebo_pct"] = float((np.asarray(pl) < rd["auc"]).mean() * 100)
        rd.update(info)
        rd["LEAD"] = bool(rd["auc"] >= BAR_MODEL["auc"] and rd["ic_share_pos"] >= BAR_MODEL["ic_share"] and rd["placebo_pct"] >= BAR_MODEL["placebo_pct"])
        res["models"][f"lgb/{h}"] = rd
        full = pd.Series(np.nan, index=Pte.index)
        full.loc[te.index] = p
        scores[("lgb", h)] = full.to_numpy()
        log.append(f"lgb {h}: AUC {rd['auc']:.3f} placebo {rd['placebo_auc_mean']:.3f} IC {rd['ic_pooled']:.3f} ({time.time() - t0:.0f} s)")
    if do_dl:
        vol_scale = {c: float(np.median(TR[c]["raw"][:, 1::4].sum(1) + TR[c]["raw"][:, 3::4].sum(1)) / 20 or 1.0) for c in common}
        for h in HORIZONS:
            Xtr, ytr, ends_tr, _, _ = dl_sequences(TR, h, vol_scale)
            Xte, yte, ends_te, codes_te, i_te = dl_sequences(TE, h, vol_scale)
            P = train_dl(Xtr, ytr, ends_tr, Xte, ends_te, log)
            p_up = P[:, 2] - P[:, 0]                                   # score = P(up) - P(down)
            key = pd.MultiIndex.from_arrays([codes_te, i_te])
            s = pd.Series(p_up, index=key)
            full = s.reindex(pd.MultiIndex.from_arrays([Pte["code"].to_numpy(), Pte["i"].to_numpy()])).to_numpy()
            te = Pte[np.isfinite(full) & Pte[h].notna()]
            rd = model_reads(te, full[np.isfinite(full) & Pte[h].notna().to_numpy()], h)
            rd["accuracy"] = float((P.argmax(1) == yte[ends_te]).mean())
            rd["majority"] = float(np.bincount(yte[ends_te], minlength=3).max() / len(ends_te))
            rd["placebo_pct"] = res["models"][f"lgb/{h}"]["placebo_pct"] if rd["auc"] > res["models"][f"lgb/{h}"]["placebo_auc_mean"] else 0.0
            rd["placebo_auc_mean"] = res["models"][f"lgb/{h}"]["placebo_auc_mean"]
            rd["LEAD"] = bool(rd["auc"] >= BAR_MODEL["auc"] and rd["ic_share_pos"] >= BAR_MODEL["ic_share"] and rd["placebo_pct"] >= BAR_MODEL["placebo_pct"])
            res["models"][f"dl/{h}"] = rd
            scores[("dl", h)] = full
            log.append(f"dl {h}: AUC {rd['auc']:.3f} acc {rd['accuracy']:.3f} vs majority {rd['majority']:.3f} ({time.time() - t0:.0f} s)")
    for (m, h), sc in scores.items():
        if h in POLICY_H:
            for ex in ("bid", "mid"):
                r = policy(Pte, sc, h, ex)
                r["model"] = m
                res["policies"].append(r)
    res["verdict"] = {"leads": [k for k, v in res["models"].items() if v["LEAD"]],
                      "candidates": [f"{r['model']}/{r['h']}/{r['exit']}" for r in res["policies"] if r["CANDIDATE"]],
                      "n_trials": len(res["models"]) + len(res["policies"])}
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, d_test, params={"trials": [*res["models"], *(f"{r['model']}/{r['h']}/{r['exit']}" for r in res["policies"])],
                                                                    "n_trials_cumulative": N_TRIALS_BEFORE + res["verdict"]["n_trials"], "step_s": STEP_S, "seq": SEQ,
                                                                    "horizons": HORIZONS, "feats": FEATS, "bar_model": BAR_MODEL, "bar_policy": BAR_POLICY, "seed": SEED},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                 note=f"leads {res['verdict']['leads'] or 'none'}; policy candidates {res['verdict']['candidates'] or 'none'}")
            res["study_id"] = sid
    return res


def write_report(res: dict, path: str) -> None:
    d = res["desc"]
    f = lambda x, fmt: (fmt % x) if x is not None and np.isfinite(x) else "-"  # noqa: E731
    L = [f"# IDX menu 31 PRELIM — ML / DL on the order book (supply & demand) — train {d['train']} -> test {d['test']}", "",
         f"{d['names']} names on a {STEP_S}-s grid; train {d['rows_train']:,} / test {d['rows_test']:,} steps. Market (EW) closed "
         + ", ".join(f"{k} {v / 100:+.2f} %" for k, v in d["mkt_ret_close"].items()) + ".",
         f"Pre-registered in `research/idx_lob_ml.py`; {res['verdict']['n_trials']} trials (cumulative {N_TRIALS_BEFORE + res['verdict']['n_trials']}).",
         "**One train day, one test day = a direction read. Nothing here is adoptable.**", "",
         "## Models — does the book predict the smoothed mid move?", "",
         "| model | horizon | AUC pooled (up vs not) | AUC per name (median) | placebo AUC | placebo pct | IC pooled | IC per name (median) | names IC>0 | base P(up) | top-decile P(up) | top-decile move (ticks) | half-spread (ticks) | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, m in res["models"].items():
        mo, h = k.split("/")
        L.append(f"| {mo} | {h} | {m['auc']:.3f} | {f(m.get('auc_name_median'), '%.3f')} | {f(m.get('placebo_auc_mean'), '%.3f')} | {f(m.get('placebo_pct'), '%.0f')} | {m['ic_pooled']:+.3f} | "
                 f"{m['ic_name_median']:+.3f} | {m['ic_share_pos'] * 100:.0f} % of {m['n_names']} | {m['base_up']:.3f} | {m['top_up']:.3f} | "
                 f"{m['top_move_ticks']:+.2f} | {m['top_half_spread_ticks']:.2f} | {'LEAD' if m['LEAD'] else 'no'} |")
    for k, m in res["models"].items():
        if k.startswith("lgb"):
            L += ["", f"### {k} — calibration by score decile; importance", "", "| decile | P(up) | mean move bps | n |", "|---|---|---|---|"]
            L += [f"| {int(c['d']) + 1} | {c['p_up']:.3f} | {c['bps']:+.1f} | {int(c['n']):,} |" for c in m["calibration"]]
            L += ["", "- importance (gain share): " + ", ".join(f"{a} {b}" for a, b in sorted(m["importance"].items(), key=lambda kv: -kv[1])[:10]),
                  f"- regression IC (pooled): {m['ic_reg_pooled']:+.3f}; rounds {m['rounds']} / {m['rounds_reg']}"]
        else:
            L += ["", f"### {k} — accuracy {m['accuracy']:.3f} vs majority class {m['majority']:.3f}", "", "| decile | P(up) | mean move bps | n |", "|---|---|---|---|"]
            L += [f"| {int(c['d']) + 1} | {c['p_up']:.3f} | {c['bps']:+.1f} | {int(c['n']):,} |" for c in m["calibration"]]
    L += ["", "## Policies on the test day — taker buy at the offer when the score is in its top decile; exit after the horizon; fees 30 bps", "",
          "| model | horizon | exit | trades | mean bps | median | t | P(win) | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    for r in res["policies"]:
        L.append(f"| {r['model']} | {r['h']} | {r['exit']} | {r['trades']:,} | {f(r['mean'], '%+.1f')} | {f(r['median'], '%+.1f')} | {f(r['t'], '%.2f')} | "
                 f"{f(r['p_win'] * 100 if r['trades'] else np.nan, '%.0f')} % | {'CANDIDATE (1 test day)' if r['CANDIDATE'] else 'no'} |")
    L += ["", "## Training log", "", *[f"- {x}" for x in res["log"]], "", "## Reading", "",
          f"- Model leads by the declared bar (AUC >= 0.60, IC > 0 in >= 70 % of names, placebo >= 95): {', '.join(res['verdict']['leads']) or 'none'}.",
          f"- Policy candidates (>= 100 trades, >= +20 bps, t >= 2, one test day): {', '.join(res['verdict']['candidates']) or 'none'}.",
          "- 'top-decile move (ticks)' vs 'half-spread (ticks)': a forecast is worth a taker's while only when the first exceeds the second",
          "  by the fee; otherwise the book is readable but not tradeable against the spread (menu 28's finding, re-tested with 10 levels + DL).",
          "- The pooled AUC is inflated by between-name base rates (a label-shuffled model still scores ~0.65-0.70 by recognising the name);",
          "  read the per-name AUC / IC and the placebo percentile instead.",
          "- Re-run when >= 20 sessions exist; walk-forward by day, then the placebo must be run for the DL model too.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="2026-09-22")
    ap.add_argument("--test", default="2026-09-23")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--no-dl", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="lob_ml")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_LOB_ML_{a.test}.md")
    res = run(os.environ["INGEST_DB_DSN"], date.fromisoformat(a.train), date.fromisoformat(a.test), out, not a.no_store, a.study_name, not a.no_dl)
    print(json.dumps({"desc": res["desc"], "models": {k: {x: v[x] for x in ("auc", "ic_pooled", "ic_share_pos", "top_move_ticks", "top_half_spread_ticks", "LEAD")}
                                                       for k, v in res["models"].items()},
                      "policies": [{k: r[k] for k in ("model", "h", "exit", "trades", "mean", "t", "CANDIDATE")} for r in res["policies"]],
                      "verdict": res["verdict"], "log": res["log"], "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
