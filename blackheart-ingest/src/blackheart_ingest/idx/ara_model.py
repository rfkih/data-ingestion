"""The ARA-tomorrow model behind the evening watch list (study #146, menu ML-3b, 2026-09-24; operator: "terapkan di page
ARA untuk prediksi dan keyakinannya").

What it predicts: for every main-board name, the probability that the NEXT session closes at its upper auto-rejection
price (LOCK) and that the next session's high reaches it (TOUCH), from today's daily bar and today's closing book
(idx.daily_summary: bid/offer queues, frequency, foreign flow, non-regular share, turnover). Two learners:
  * LightGBM on the 50 static features (one model per label);
  * a GRU over the last 20 days of 12 daily channels + an MLP over the same static features (LOCK only; optional,
    needs torch). The rank is the mean of the two within-day percentile ranks (ENS) - the study's adopted rank model,
    it beat the tree alone on precision@10 in 5/5 walk-forward years.
Probabilities are Platt-recalibrated on a 12-month holdout before the final refit: LightGBM with scale_pos_weight prints
raw scores ~15x too high (study: decile 10 said 73 %, reality 4.3 %). Only calibrated numbers leave this module.

Accuracy, out of sample by year 2022-2026 (research/IDX_ARA_MICRO_2026-09-24.md): AUC 0.88-0.93; of the 5 names ranked
highest each day 8-20 % lock the next day against a base rate of 0.3-0.9 % (lift ~20x); 48-76 % of the year's locks were
in the daily top-20. Closing-book microstructure alone reaches AUC 0.79-0.89 but adds nothing measurable over the bars.
Not a trade model: the names most likely to lock are mostly locked already (no offer), the buyable picks lose on average.

Pure functions on frames so the tests can feed a synthetic tape; the only I/O is ``load_summary``.
"""
from __future__ import annotations

import logging
import os
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import tuple_row

logger = logging.getLogger(__name__)

START = date(2020, 1, 1)
SEED = 20260924
MIN_PREV, MIN_VALUE = 50.0, 1e9
L_SEQ = 20
HOLDOUT_DAYS = 250
LGB = {"objective": "binary", "num_leaves": 15, "learning_rate": 0.05, "min_child_samples": 200, "feature_fraction": 0.8,
       "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0, "seed": SEED, "verbose": -1, "num_threads": 4}
ROUNDS = 300
BAR = ["ret1", "ret5", "ret20", "ret60", "vr", "vr5", "log_value", "log_price", "clv", "hl_range", "dist_hi20", "dist_hi60", "vol20",
       "touch", "lock", "near", "band_use", "days_since_ara", "streak", "up_days", "n_ara20", "n_ara60", "breadth_ara", "breadth_near",
       "mkt_ret1", "mkt_ret5", "dow", "band", "age"]
MICRO = ["qimb", "no_offer", "no_bid", "sprd_t", "log_bv_vol", "log_ov_vol", "bv_ov", "close_at_bid", "close_at_off", "log_avg_trade",
         "atr_ratio", "freq_ratio", "fnet", "fnet5", "fnet20", "fpart", "nonreg_share", "turnover", "gap_open", "qimb_yday", "qimb5"]
FEATS = BAR + MICRO
SEQ_CH = ["ret1", "hl_range", "clv", "lvr", "qimb0", "sprd0", "lfreq", "fnet0", "touchf", "band_use", "log_bv_vol0", "log_ov_vol0"]
# the study's calibration, used only when a run has too few holdout positives to fit its own
STUDY_CALIB = {"lock": (0.64, -3.92), "touch": (0.70, -3.40), "dl": (0.92, -3.72)}
MIN_CALIB_POS = 30
# what the app says about the model - the study's out-of-sample numbers, never recomputed at run time
FACTS = {"study": 146, "report": "research/IDX_ARA_MICRO_2026-09-24.md", "auc": "0.88-0.93", "precision_top5": "8-20 %",
         "base_rate": "0.3-0.9 %", "lift": "~20x", "recall_top20": "48-76 %", "test_years": "2022-2026",
         "note": "nama yang paling mungkin terkunci biasanya sudah terkunci hari ini; yang masih bisa dibeli rata-rata rugi besok",
         # the same figures as numbers, for a screen that has to print them: the model's own scorecard (study #146) and
         # what happens after a touch (study #101, the sell-at-ARA work the evening watch was built on)
         "scores": {"auc_lo": 0.88, "auc_hi": 0.93, "precision_top5_lo": 0.08, "precision_top5_hi": 0.20,
                    "recall_top20_lo": 0.48, "recall_top20_hi": 0.76, "base_rate_lo": 0.003, "base_rate_hi": 0.009,
                    "years": "2022-2026"},
         "outcomes": {"study": 101,
                      "lock_hold": {"bps": 431, "n": 440, "what": "closed locked, measured the next day against the ARA price"},
                      "touch_fade": {"bps": -661, "n": 231, "what": "touched the limit and faded, measured at that day's close"},
                      "touch_holds": {"rate": 0.59, "n": 671, "what": "share of touches that hold to the close"}}}
CONFIDENCE = (("high", 0.10), ("medium", 0.03))


def confidence(p_lock: float) -> str:
    """The word the page shows next to the calibrated P(lock). Bands come from the study's calibration table: the top
    decile realises ~4-5 %, the daily top-5 8-20 %; >= 10 % is almost always a name already locked today."""
    if not np.isfinite(p_lock):
        return "low"
    for word, floor in CONFIDENCE:
        if p_lock >= floor:
            return word
    return "low"


# ------------------------------------------------------------------------------------------------------------------ data
COLS = ["prev", "open", "high", "low", "close", "vol", "val", "freq", "bid", "bv", "off", "ov", "fb", "fs", "nreg", "tsh", "adj"]
ALIASES = {"volume": "vol", "value": "val", "trade_date": "d", "previous": "prev", "offer": "off", "bid_volume": "bv", "offer_volume": "ov",
           "frequency": "freq", "foreign_buy": "fb", "foreign_sell": "fs", "nonreg_volume": "nreg", "tradeable_shares": "tsh", "adj_factor": "adj"}


def load_summary(conn: psycopg.Connection, start: date = START, end: date | None = None) -> pd.DataFrame:
    """Every daily-summary row (all boards) with the bar's adjustment factor; ~1.4 M rows for 2020->today in ~15 s."""
    cols = ["code", "d", *COLS[:-1], "bd", "adj"]
    with conn.cursor(row_factory=tuple_row) as cur:                      # the desk's connections default to dict rows
        cur.execute("""SELECT s.code, s.trade_date, s.previous::float8, s.open::float8, s.high::float8, s.low::float8, s.close::float8,
                              s.volume::float8, s.value::float8, s.frequency::float8, s.bid::float8, s.bid_volume::float8, s.offer::float8,
                              s.offer_volume::float8, s.foreign_buy::float8, s.foreign_sell::float8, s.nonreg_volume::float8,
                              s.tradeable_shares::float8, substr(s.remarks, 5, 1), b.adj_factor::float8
                       FROM idx.daily_summary s LEFT JOIN idx.bar b ON b.code = s.code AND b.trade_date = s.trade_date AND b.source = 'idx'
                       WHERE s.trade_date >= %s AND (%s::date IS NULL OR s.trade_date <= %s) AND s.close > 0""", (start, end, end))
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    df["d"] = pd.to_datetime(df["d"])
    return df


def tick_of(px: np.ndarray) -> np.ndarray:
    return np.select([px < 200, px < 500, px < 2000, px < 5000], [1.0, 2.0, 5.0, 10.0], 25.0)


def band_of(prev: np.ndarray) -> np.ndarray:
    return np.where(prev <= 200, 0.35, np.where(prev <= 5000, 0.25, 0.20))


def ara_of(prev: np.ndarray) -> np.ndarray:
    """Upper auto-rejection price: the highest tick at or below prev x (1 + 35/25/20 %), on the tick of the price it lands on."""
    raw = prev * (1 + band_of(prev))
    t = tick_of(raw)
    return np.floor(raw / t + 1e-9) * t


def _roll(X: np.ndarray, w: int, fn: str, minp: int) -> np.ndarray:
    return getattr(pd.DataFrame(X).rolling(w, min_periods=minp), fn)().to_numpy()


def _lag(X: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(X, np.nan)
    out[k:] = X[:-k]
    return out


def _lead(X: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(X, np.nan)
    out[:-k] = X[k:]
    return out


def _div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = a / b
    return np.where(np.isfinite(out), out, np.nan)


class Panel:
    """Every column as a (T, N) float array; features, labels and sequence channels on the same date x name grid.
    Accepts a long frame with at least code, d (or trade_date), high, close, volume/vol, value/val; every other column
    is optional (missing -> NaN, so a bar-only tape still yields the BAR features and NaN micro features)."""

    def __init__(self, df: pd.DataFrame):
        df = df.rename(columns={k: v for k, v in ALIASES.items() if k in df.columns and v not in df.columns})
        dates = np.sort(df["d"].unique())
        codes = np.sort(df["code"].unique())
        self.dates, self.codes = pd.DatetimeIndex(dates), codes
        self.T, self.N = len(dates), len(codes)
        ti = np.searchsorted(dates, df["d"].to_numpy())
        ni = np.searchsorted(codes, df["code"].to_numpy())

        def g(col):
            out = np.full((self.T, self.N), np.nan, dtype=float)
            if col in df.columns:
                out[ti, ni] = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
            return out

        for c in COLS:
            setattr(self, c, g(c))
        if "prev" not in df.columns:
            self.prev = _lag(self.close, 1)
        if "low" not in df.columns:
            self.low = np.minimum(self.close, self.prev)
        main = np.isfinite(self.close)
        if "bd" in df.columns:
            main = np.zeros((self.T, self.N), dtype=bool)
            main[ti, ni] = df["bd"].isin(["1", "2"]).to_numpy()
        self.main = main
        self.F: dict[str, np.ndarray] = {}
        self._features()
        self._labels()
        self._channels()

    # ---- features ---------------------------------------------------------------------------------------------------
    def _features(self) -> None:
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
        F["band_use"] = _div(high / prev - 1, band)
        F["ret1"] = close / prev - 1
        for k in (5, 20, 60):
            F[f"ret{k}"] = A / _lag(A, k) - 1
        F["vr"] = _div(vol, _roll(_lag(vol, 1), 20, "median", 10))
        F["vr5"] = _roll(F["vr"], 5, "mean", 1)
        F["log_value"] = np.log10(np.where(val > 0, val, np.nan))
        F["log_price"] = np.log10(close)
        F["clv"] = _div(close - low, high - low)
        F["hl_range"] = (high - low) / prev
        F["dist_hi20"] = A / _roll(A, 20, "max", 10) - 1
        F["dist_hi60"] = A / _roll(A, 60, "max", 20) - 1
        F["vol20"] = _roll(pd.DataFrame(A).pct_change().to_numpy(), 20, "std", 15)
        since, streak, updays = np.full(N, 60.0), np.zeros(N), np.zeros(N)
        S, ST, UD = np.zeros((T, N)), np.zeros((T, N)), np.zeros((T, N))
        up = F["ret1"] > 0
        for t in range(T):
            since = np.where(lock[t], 0.0, np.minimum(60.0, since + 1))
            streak = np.where(lock[t], streak + 1, 0.0)
            updays = np.where(up[t], updays + 1, np.where(ok[t], 0.0, updays))
            S[t], ST[t], UD[t] = since, streak, updays
        F["days_since_ara"], F["streak"], F["up_days"] = S, ST, UD
        F["n_ara20"] = _roll(lock.astype(float), 20, "sum", 1)
        F["n_ara60"] = _roll(lock.astype(float), 60, "sum", 1)
        uni = self.main & ok & (np.nan_to_num(val) >= MIN_VALUE)
        n_uni = np.maximum(uni.sum(axis=1), 1)
        F["breadth_ara"] = np.repeat(((lock & uni).sum(axis=1) / n_uni)[:, None], N, axis=1)
        F["breadth_near"] = np.repeat((((F["near"] > 0) & uni).sum(axis=1) / n_uni)[:, None], N, axis=1)
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)                 # a day with no liquid main-board name is an empty mean
            mkt = np.nanmean(np.where(uni, F["ret1"], np.nan), axis=1)
        mkt = np.where(np.isfinite(mkt), mkt, 0.0)
        F["mkt_ret1"] = np.repeat(mkt[:, None], N, axis=1)
        F["mkt_ret5"] = np.repeat(pd.Series(mkt).rolling(5, min_periods=1).sum().to_numpy()[:, None], N, axis=1)
        F["dow"] = np.repeat(self.dates.dayofweek.to_numpy(float)[:, None], N, axis=1)
        F["band"] = np.select([prev <= 200, prev <= 5000], [0.0, 1.0], 2.0)
        F["age"] = np.cumsum(ok, axis=0).astype(float)
        # ---- the closing book and tape
        bv, ov, bid, off, freq = self.bv, self.ov, self.bid, self.off, self.freq
        bv0, ov0 = np.nan_to_num(bv), np.nan_to_num(ov)
        have_book = np.isfinite(bv) | np.isfinite(ov)
        F["qimb"] = np.where(have_book, _div(bv0 - ov0, bv0 + ov0), np.nan)
        F["no_offer"] = np.where(have_book, (ok & (ov0 <= 0)).astype(float), np.nan)
        F["no_bid"] = np.where(have_book, (ok & (bv0 <= 0)).astype(float), np.nan)
        F["sprd_t"] = np.where((bid > 0) & (off > 0), _div(off - bid, tick_of(close)), np.nan)
        F["log_bv_vol"] = np.where(have_book, np.log1p(_div(bv0, vol)), np.nan)
        F["log_ov_vol"] = np.where(have_book, np.log1p(_div(ov0, vol)), np.nan)
        F["bv_ov"] = np.where(have_book, np.log((bv0 + 1) / (ov0 + 1)), np.nan)
        F["close_at_bid"] = np.where(have_book, (ok & (bid > 0) & (np.abs(close - bid) < 1e-6)).astype(float), np.nan)
        F["close_at_off"] = np.where(have_book, (ok & (off > 0) & (np.abs(close - off) < 1e-6)).astype(float), np.nan)
        avg_trade = _div(val, np.where(freq > 0, freq, np.nan))
        F["log_avg_trade"] = np.log10(avg_trade)
        F["atr_ratio"] = _div(avg_trade, _roll(_lag(avg_trade, 1), 20, "median", 10))
        F["freq_ratio"] = _div(freq, _roll(_lag(freq, 1), 20, "median", 10))
        have_f = np.isfinite(self.fb) | np.isfinite(self.fs)
        fnet = np.where(have_f, np.nan_to_num(self.fb) - np.nan_to_num(self.fs), np.nan)
        F["fnet"] = _div(fnet, vol)
        F["fnet5"] = _div(_roll(fnet, 5, "sum", 1), _roll(vol, 5, "sum", 1))
        F["fnet20"] = _div(_roll(fnet, 20, "sum", 5), _roll(vol, 20, "sum", 5))
        F["fpart"] = np.where(have_f, _div(np.nan_to_num(self.fb) + np.nan_to_num(self.fs), 2 * vol), np.nan)
        F["nonreg_share"] = np.where(np.isfinite(self.nreg), _div(np.nan_to_num(self.nreg), vol + np.nan_to_num(self.nreg)), np.nan)
        F["turnover"] = _div(vol, np.where(self.tsh > 0, self.tsh, np.nan))
        F["gap_open"] = self.open / prev - 1
        F["qimb_yday"] = _lag(F["qimb"], 1)
        F["qimb5"] = _roll(F["qimb"], 5, "mean", 1)
        self.ok, self.ara_px = ok, ara_px

    def _labels(self) -> None:
        prev_n, close_n, high_n = _lead(self.prev, 1), _lead(self.close, 1), _lead(self.high, 1)
        ara_n = ara_of(prev_n)
        valid = np.isfinite(close_n) & np.isfinite(prev_n) & (prev_n > 0)
        self.LOCK1 = np.where(valid, (close_n >= ara_n - 1e-6).astype(float), np.nan)
        self.TOUCH1 = np.where(valid, (high_n >= ara_n - 1e-6).astype(float), np.nan)
        self.ara_next = ara_of(self.close)                            # tomorrow's limit if nothing adjusts overnight

    def _channels(self) -> None:
        F = self.F
        ch = {"ret1": F["ret1"], "hl_range": F["hl_range"], "clv": F["clv"], "lvr": np.log1p(F["vr"]), "qimb0": F["qimb"],
              "sprd0": np.clip(F["sprd_t"], 0, 20) / 20, "lfreq": np.log1p(F["freq_ratio"]), "fnet0": F["fnet"], "touchf": F["touch"],
              "band_use": F["band_use"], "log_bv_vol0": F["log_bv_vol"], "log_ov_vol0": F["log_ov_vol"]}
        self.CH = np.stack([np.nan_to_num(np.clip(ch[c], -5, 5)).astype(np.float32) for c in SEQ_CH])   # (C, T, N)

    # ---- long frames --------------------------------------------------------------------------------------------------
    def frame(self, mask: np.ndarray) -> pd.DataFrame:
        ti, ni = np.nonzero(mask)
        out = {"ti": ti, "ni": ni, "d": self.dates[ti], "code": self.codes[ni], "close": self.close[ti, ni], "ara_px_next": self.ara_next[ti, ni],
               "LOCK1": self.LOCK1[ti, ni], "TOUCH1": self.TOUCH1[ti, ni], "buyable": np.where(np.isfinite(self.ov[ti, ni]), self.ov[ti, ni] > 0, self.F["lock"][ti, ni] == 0).astype(float)}
        for k, v in self.F.items():
            out[k] = v[ti, ni]
        return pd.DataFrame(out)

    def training(self) -> pd.DataFrame:
        """Main boards, prev >= Rp 50, value >= Rp 1 bn, next day traded, at least L_SEQ days into the panel."""
        m = self.main & self.ok & (self.prev >= MIN_PREV) & (np.nan_to_num(self.val) >= MIN_VALUE) & np.isfinite(self.LOCK1)
        m[: L_SEQ - 1] = False
        return self.frame(m)

    def last_day(self) -> pd.DataFrame:
        """Every main-board name that traded on the last bar (no value floor: a thin held name still gets a number)."""
        m = np.zeros((self.T, self.N), dtype=bool)
        m[-1] = self.main[-1] & self.ok[-1] & (self.prev[-1] >= MIN_PREV)
        return self.frame(m)

    def all_rows(self) -> pd.DataFrame:
        return self.frame(np.isfinite(self.close))


def features(df: pd.DataFrame) -> pd.DataFrame:
    """Long (code, d) frame with every feature, the labels and ara_px_next - pure, for the tests and for auditing."""
    return Panel(df).all_rows().sort_values(["code", "d"]).reset_index(drop=True)


# --------------------------------------------------------------------------------------------------------------- learners
def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def platt_fit(p: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """sigmoid(a * logit(p) + b) by log loss on held-out scores. Monotone: ranks and precision@K do not move."""
    from scipy.optimize import minimize
    x, y = _logit(p), np.asarray(y, float)

    def nll(ab):
        z = ab[0] * x + ab[1]
        return float(np.mean(np.logaddexp(0, -z) * y + np.logaddexp(0, z) * (1 - y)))

    r = minimize(nll, x0=np.array([1.0, 0.0]), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-7, "maxiter": 2000})
    return float(r.x[0]), float(r.x[1])


def platt_apply(p, ab: tuple[float, float]) -> np.ndarray:
    return 1 / (1 + np.exp(-(ab[0] * _logit(p) + ab[1])))


def fit_tree(tr: pd.DataFrame, label: str):
    import lightgbm as lgb
    y = tr[label].to_numpy(float)
    p = dict(LGB, scale_pos_weight=float((len(y) - y.sum()) / max(y.sum(), 1)))
    return lgb.train(p, lgb.Dataset(tr[FEATS].to_numpy(float), y, feature_name=FEATS), ROUNDS)


def predict_tree(m, df: pd.DataFrame) -> np.ndarray:
    return np.asarray(m.predict(df[FEATS].to_numpy(float)), float)


class GRUModel:
    """GRU(12 -> 32) over the last L_SEQ days of the channels + MLP(64) over the standardised static features -> logit."""

    def __init__(self, panel: Panel, seed: int = SEED, threads: int = 4):
        import torch
        self.torch, self.panel = torch, panel
        torch.manual_seed(seed)
        torch.set_num_threads(threads)
        self.CH = torch.from_numpy(panel.CH)
        self.offs = torch.arange(L_SEQ - 1, -1, -1)
        self.mu = self.sd = None
        self.net = None

    def _static(self, df: pd.DataFrame):
        X = df[FEATS].to_numpy(np.float32)
        if self.mu is None:
            self.mu = np.nanmean(X, axis=0)
            self.sd = np.nanstd(X, axis=0) + 1e-6
        Z = np.clip((X - self.mu) / self.sd, -5, 5)
        return self.torch.from_numpy(np.nan_to_num(Z).astype(np.float32))

    def _seq(self, ti, ni):
        return self.CH[:, (ti[:, None] - self.offs[None, :]).clamp(min=0), ni[:, None]].permute(1, 2, 0)

    def _build(self, n_static: int):
        nn, torch = self.torch.nn, self.torch

        class Net(nn.Module):
            def __init__(s):
                super().__init__()
                s.gru = nn.GRU(len(SEQ_CH), 32, batch_first=True)
                s.mlp = nn.Sequential(nn.Linear(n_static, 64), nn.ReLU(), nn.Dropout(0.1))
                s.head = nn.Sequential(nn.Linear(32 + 64, 64), nn.ReLU(), nn.Linear(64, 1))

            def forward(s, seq, st):
                _, h = s.gru(seq)
                return s.head(torch.cat([h[-1], s.mlp(st)], 1)).squeeze(1)

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
        return np.concatenate(out) if out else np.zeros(0)

    def fit(self, tr: pd.DataFrame, label: str = "LOCK1", epochs: int = 6, bs: int = 4096, lr: float = 1e-3, log: Callable[[str], None] | None = None) -> float:
        torch = self.torch
        self.mu = self.sd = None
        cut = tr["d"].quantile(0.9)
        va, tr = tr[tr["d"] > cut], tr[tr["d"] <= cut]
        st = self._static(tr)
        y = torch.from_numpy(tr[label].to_numpy(np.float32))
        ti, ni = torch.from_numpy(tr["ti"].to_numpy(np.int64)), torch.from_numpy(tr["ni"].to_numpy(np.int64))
        self.net = self._build(st.shape[1])
        pos = float(y.sum())
        lossf = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(min((len(y) - pos) / max(pos, 1.0), 50.0)))
        opt = torch.optim.Adam(self.net.parameters(), lr=lr)
        best, best_state = -1.0, None
        g = torch.Generator().manual_seed(SEED)
        for ep in range(epochs):
            self.net.train()
            perm = torch.randperm(len(y), generator=g)
            for i in range(0, len(y), bs):
                b = perm[i:i + bs]
                opt.zero_grad()
                loss = lossf(self.net(self._seq(ti[b], ni[b]), st[b]), y[b])
                loss.backward()
                opt.step()
            a = auc(va[label].to_numpy(float), self.predict(va))
            if log:
                log(f"gru epoch {ep + 1} val_auc {a:.4f}")
            if a > best:
                best, best_state = a, {k: v.clone() for k, v in self.net.state_dict().items()}
            elif ep >= 2:
                break
        self.net.load_state_dict(best_state)
        return best


def auc(y: np.ndarray, s: np.ndarray) -> float:
    from scipy import stats
    y = np.asarray(y).astype(bool)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = stats.rankdata(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


# ---------------------------------------------------------------------------------------------------------------- the fit
@dataclass
class Fitted:
    tree_lock: Any
    tree_touch: Any
    gru: GRUModel | None
    calib: dict[str, tuple[float, float]]
    info: dict[str, Any] = field(default_factory=dict)


def dl_wanted() -> bool:
    if os.environ.get("IDX_ARA_DL", "1").lower() in ("0", "false", "no", "off"):
        return False
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def train(P: Panel, use_dl: bool | None = None, log: Callable[[str], None] | None = None) -> Fitted:
    """Calibrate on the last HOLDOUT_DAYS of labelled history (models fitted before it), then refit on everything."""
    log = log or (lambda s: logger.info("ara model: %s", s))
    use_dl = dl_wanted() if use_dl is None else use_dl
    S = P.training()
    if len(S) < 20000 or S["LOCK1"].sum() < 200:
        raise RuntimeError(f"ara model: not enough history ({len(S)} rows, {int(S['LOCK1'].sum())} locks)")
    days = np.sort(S["d"].unique())
    cut = days[-HOLDOUT_DAYS] if len(days) > HOLDOUT_DAYS + 250 else days[len(days) // 2]
    tr, ho = S[S["d"] < cut], S[S["d"] >= cut]
    calib: dict[str, tuple[float, float]] = {}
    info: dict[str, Any] = {"rows": len(S), "locks": int(S["LOCK1"].sum()), "touches": int(S["TOUCH1"].sum()), "holdout_from": str(pd.Timestamp(cut).date()),
                            "holdout_rows": len(ho), "holdout_locks": int(ho["LOCK1"].sum()), "base_rate": float(S["LOCK1"].mean()), "dl": use_dl}
    for key, label in (("lock", "LOCK1"), ("touch", "TOUCH1")):
        m = fit_tree(tr, label)
        p = predict_tree(m, ho)
        calib[key] = platt_fit(p, ho[label]) if ho[label].sum() >= MIN_CALIB_POS else STUDY_CALIB[key]
        info[f"holdout_auc_{key}"] = auc(ho[label].to_numpy(float), p)
        log(f"{label}: holdout auc {info[f'holdout_auc_{key}']:.3f}, calib a={calib[key][0]:.2f} b={calib[key][1]:.2f}")
    gru = None
    if use_dl:
        try:
            g = GRUModel(P)
            g.fit(tr, log=log)
            p = g.predict(ho)
            calib["dl"] = platt_fit(p, ho["LOCK1"]) if ho["LOCK1"].sum() >= MIN_CALIB_POS else STUDY_CALIB["dl"]
            info["holdout_auc_dl"] = auc(ho["LOCK1"].to_numpy(float), p)
            log(f"GRU: holdout auc {info['holdout_auc_dl']:.3f}")
            gru = GRUModel(P)
            gru.fit(S, log=log)
        except Exception as e:                                          # the tree list still goes out
            logger.exception("ara model: GRU failed, tree only")
            info["dl_error"] = f"{type(e).__name__}: {e}"
            gru = None
    return Fitted(fit_tree(S, "LOCK1"), fit_tree(S, "TOUCH1"), gru, calib, info)


def score_last(P: Panel, F: Fitted) -> pd.DataFrame:
    """One row per main-board name on the last bar: calibrated p_lock / p_touch / p_dl, the ENS score, flags, features."""
    last = P.last_day().copy()
    last["p_lock"] = platt_apply(predict_tree(F.tree_lock, last), F.calib["lock"])
    last["p_touch"] = platt_apply(predict_tree(F.tree_touch, last), F.calib["touch"])
    if F.gru is not None and len(last):
        last["p_dl"] = platt_apply(F.gru.predict(last), F.calib["dl"])
        last["score"] = 0.5 * (last["p_lock"].rank(pct=True) + last["p_dl"].rank(pct=True))
    else:
        last["p_dl"] = np.nan
        last["score"] = last["p_lock"]
    last["locked_today"] = last["lock"] > 0
    last["buyable"] = last["buyable"] > 0
    last["confidence"] = [confidence(p) for p in last["p_lock"]]
    return last.sort_values(["score", "p_lock"], ascending=False).reset_index(drop=True)
