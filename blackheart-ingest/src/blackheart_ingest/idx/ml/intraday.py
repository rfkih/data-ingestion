"""The minute panel off the tick feed: one row per (name, session minute) on the trading grid, with the state of the tape
and the book at that minute and the forward log return of the MID price 1 / 10 / 30 / 60 grid minutes ahead (never across
the close). The mid, not the last trade: the last trade alternates bid/offer and "predicting" that bounce is not a forecast.

Grid: Mon-Thu 09:00-11:59 + 13:30-15:59 WIB, Fri 09:00-11:29 + 14:00-15:59 (session I/II; the pre-closing auction and the
post-close prints are outside it). A horizon counts grid minutes, so a 30-minute forecast made at 11:45 matures at 13:45.

Sources: idx.feed_bar_1m and idx.feed_book_1m (Timescale continuous aggregates, real-time), idx.bar for the previous close
and the daily context of each name. Only names the collector subscribes to have rows (idx.feed_symbol, liquid).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import tuple_row

from .common import UTC, WIB, tick
from .spec import INTRADAY

logger = logging.getLogger(__name__)

FEATURES: list[str] = [
    "r1", "r5", "r15", "r30", "r60", "rv15", "rv60", "vwap_dev", "volr5", "lvol5", "imb1", "imb5", "imb15", "lnt5",
    "obi", "obi1", "obi3", "spread_t", "spread_bps", "micro_dev", "last_dev", "lupd5", "tod", "mins_left",
    "day_ret", "gap", "day_pos", "day_range", "since_trade",
    "mom20", "vol20", "lvalue20", "dist_ma200", "dow",
]
MAX_FIT_DAYS = 120
MIN_MINUTES_FOR_ROW = 5             # skip the first minutes of a name's day: no lookback yet


def session_grid(d: date) -> pd.DatetimeIndex:
    """Every grid minute of day ``d`` as aware WIB timestamps; empty on Sat/Sun."""
    if d.weekday() >= 5:
        return pd.DatetimeIndex([], tz=WIB)
    if d.weekday() == 4:
        parts = [(time(9, 0), time(11, 29)), (time(14, 0), time(15, 59))]
    else:
        parts = [(time(9, 0), time(11, 59)), (time(13, 30), time(15, 59))]
    idx = []
    for a, b in parts:
        idx.append(pd.date_range(datetime.combine(d, a, tzinfo=WIB), datetime.combine(d, b, tzinfo=WIB), freq="1min"))
    return idx[0].append(idx[1])


def grid_position(ts: datetime) -> tuple[int, pd.DatetimeIndex] | None:
    """Position of the last grid minute <= ts (WIB) on that day's grid, or None outside the session."""
    t = ts.astimezone(WIB)
    g = session_grid(t.date())
    if len(g) == 0:
        return None
    floor = t.replace(second=0, microsecond=0)
    pos = g.searchsorted(floor, side="right") - 1
    if pos < 0:
        return None
    if floor > g[pos] + timedelta(minutes=2):       # the break or after the close: no live minute to score
        return None
    return int(pos), g


# ---- loaders -----------------------------------------------------------------------------------------------------------
def _frame(conn: psycopg.Connection, sql: str, params: tuple, cols: list[str]) -> pd.DataFrame:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=cols)


def feed_days(conn: psycopg.Connection, limit: int = MAX_FIT_DAYS) -> list[date]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT DISTINCT (ts AT TIME ZONE 'Asia/Jakarta')::date AS d FROM idx.feed_trade ORDER BY d DESC LIMIT %s", (limit,))
        return sorted(r[0] for r in cur.fetchall())


def load_minutes(conn: psycopg.Connection, day_from: date, day_to: date, codes: list[str] | None = None) -> pd.DataFrame:
    """1-minute bars joined to the end-of-minute book, WIB-stamped, for the days [day_from, day_to]."""
    t0 = datetime.combine(day_from, time(0, 0), tzinfo=WIB).astimezone(UTC)
    t1 = datetime.combine(day_to + timedelta(days=1), time(0, 0), tzinfo=WIB).astimezone(UTC)
    M = _frame(conn, """
        SELECT b.minute, b.code, b.open, b.high, b.low, b.close, b.volume, b.value, b.n_trades, b.buy_volume, b.sell_volume,
               k.bid_px[1], k.bid_vol[1], k.off_px[1], k.off_vol[1], k.bid_total, k.off_total, k.n_updates,
               (SELECT sum(x) FROM unnest(k.bid_vol[1:3]) x), (SELECT sum(x) FROM unnest(k.off_vol[1:3]) x)
          FROM idx.feed_bar_1m b
          LEFT JOIN idx.feed_book_1m k ON k.code = b.code AND k.minute = b.minute
         WHERE b.minute >= %s AND b.minute < %s AND (%s::text[] IS NULL OR b.code = ANY(%s))
         ORDER BY b.code, b.minute""", (t0, t1, codes, codes),
        ["minute", "code", "open", "high", "low", "close", "volume", "value", "n_trades", "buy_vol", "sell_vol",
         "bid_px", "bid_vol", "off_px", "off_vol", "bid_total", "off_total", "n_updates", "bid_vol3", "off_vol3"])
    if M.empty:
        return M
    for c in M.columns:
        if c not in ("minute", "code"):
            M[c] = pd.to_numeric(M[c], errors="coerce").astype(float)
    M["minute"] = pd.to_datetime(M["minute"], utc=True).dt.tz_convert(WIB)
    return M


def load_daily_context(conn: psycopg.Connection, codes: list[str], upto: date) -> pd.DataFrame:
    """Per (code, bar date): previous close and the slow context (momentum, vol, liquidity, MA200) known at that close."""
    B = _frame(conn, """
        SELECT code, trade_date, close, adj_factor, value FROM idx.bar
         WHERE source = 'idx' AND close > 0 AND code = ANY(%s) AND trade_date > %s AND trade_date <= %s ORDER BY code, trade_date""",
        (codes, upto - timedelta(days=400), upto), ["code", "d", "close", "adj", "value"])
    B = B.assign(close=B["close"].astype(float), adj=B["adj"].astype(float), value=B["value"].astype(float))
    B["d"] = pd.to_datetime(B["d"]).dt.date
    g = B.groupby("code", sort=False)
    ac = B["close"] * B["adj"]
    lc = np.log(ac)
    B["mom20"] = lc - lc.groupby(B["code"]).shift(20)
    B["vol20"] = lc.diff().groupby(B["code"]).transform(lambda x: x.rolling(20, min_periods=10).std())
    B["lvalue20"] = np.log1p(g["value"].transform(lambda x: x.rolling(20, min_periods=5).mean()))
    B["dist_ma200"] = ac / ac.groupby(B["code"]).transform(lambda x: x.rolling(200, min_periods=100).mean()) - 1
    B = B.rename(columns={"close": "prev_close"})
    return B[["code", "d", "prev_close", "mom20", "vol20", "lvalue20", "dist_ma200"]]


# ---- features -----------------------------------------------------------------------------------------------------------
def _one_day(M: pd.DataFrame, d: date) -> pd.DataFrame:
    """Reindex every name of day ``d`` onto the grid and compute the minute features. Labels too."""
    g = session_grid(d)
    if len(g) == 0 or M.empty:
        return pd.DataFrame()
    n = len(g)
    frames = []
    for code, X in M.groupby("code", sort=False):
        X = X.set_index("minute").reindex(g)
        if X["close"].notna().sum() < MIN_MINUTES_FOR_ROW:
            continue
        had = X["close"].notna()
        observed = had | X["bid_px"].notna()
        last_obs = int(np.flatnonzero(observed.to_numpy())[-1])       # beyond this minute nothing was seen: no label there
        for c in ("volume", "value", "n_trades", "buy_vol", "sell_vol", "n_updates"):
            X[c] = X[c].fillna(0.0)
        for c in ("close", "bid_px", "off_px", "bid_vol", "off_vol", "bid_total", "off_total", "bid_vol3", "off_vol3"):
            X[c] = X[c].ffill()
        X["high"] = X["high"].fillna(X["close"])
        X["low"] = X["low"].fillna(X["close"])
        # the price the forecast is about: the mid of the end-of-minute book. The last trade alternates between bid and
        # offer, so "will the last trade be higher" is mostly the bounce (menu 28); the mid is what a forecast can move.
        two_sided = (X["bid_px"] > 0) & (X["off_px"] > 0) & (X["off_px"] >= X["bid_px"])
        X["px"] = ((X["bid_px"] + X["off_px"]) / 2).where(two_sided, X["close"])
        lc = np.log(X["px"])
        pos = np.arange(n, dtype=float)
        F = pd.DataFrame(index=g)
        F["code"] = code
        F["pos"] = pos
        F["close"] = X["px"]
        F["last"] = X["close"]
        F["had_trade"] = had.astype(float)
        for k in (1, 5, 15, 30, 60):
            F[f"r{k}"] = lc - lc.shift(k)
        r1 = lc.diff()
        F["rv15"] = r1.rolling(15, min_periods=5).std()
        F["rv60"] = r1.rolling(60, min_periods=15).std()
        cv, cq = X["value"].cumsum(), X["volume"].cumsum()
        F["vwap_dev"] = X["px"] / (cv / cq.replace(0, np.nan)) - 1
        avg_so_far = cq / (pos + 1)
        v5 = X["volume"].rolling(5, min_periods=1).sum()
        F["volr5"] = v5 / (avg_so_far * 5).replace(0, np.nan)
        F["lvol5"] = np.log1p(v5)
        for k in (1, 5, 15):
            b = X["buy_vol"].rolling(k, min_periods=1).sum()
            s = X["sell_vol"].rolling(k, min_periods=1).sum()
            F[f"imb{k}"] = (b - s) / (b + s).replace(0, np.nan)
        F["lnt5"] = np.log1p(X["n_trades"].rolling(5, min_periods=1).sum())
        bt, ot = X["bid_total"], X["off_total"]
        F["obi"] = (bt - ot) / (bt + ot).replace(0, np.nan)
        F["obi1"] = (X["bid_vol"] - X["off_vol"]) / (X["bid_vol"] + X["off_vol"]).replace(0, np.nan)
        F["obi3"] = (X["bid_vol3"] - X["off_vol3"]) / (X["bid_vol3"] + X["off_vol3"]).replace(0, np.nan)
        tk = X["px"].map(tick)
        sp = (X["off_px"] - X["bid_px"])
        F["spread_t"] = (sp / tk).where((X["bid_px"] > 0) & (X["off_px"] > 0))
        F["spread_bps"] = (sp / X["px"] * 1e4).where((X["bid_px"] > 0) & (X["off_px"] > 0))
        micro = (X["bid_px"] * X["off_vol"] + X["off_px"] * X["bid_vol"]) / (X["bid_vol"] + X["off_vol"]).replace(0, np.nan)
        F["micro_dev"] = (micro / X["px"] - 1).where((X["bid_px"] > 0) & (X["off_px"] > 0))
        F["last_dev"] = (X["close"] / X["px"] - 1)
        F["lupd5"] = np.log1p(X["n_updates"].rolling(5, min_periods=1).sum())
        F["tod"] = pos / n
        F["mins_left"] = n - 1 - pos
        F["day_high"] = X["high"].cummax()
        F["day_low"] = X["low"].cummin()
        F["first_close"] = X["close"][had].iloc[0]
        F["since_trade"] = (~had).astype(float).groupby(had.cumsum()).cumsum()
        F["dow"] = float(d.weekday())
        for h in INTRADAY:
            fwd = lc.shift(-h.steps) - lc
            fwd[pos + h.steps > last_obs] = np.nan
            F[f"fwd_{h.key}"] = fwd
        frames.append(F[F["had_trade"] > 0].reset_index().rename(columns={"index": "minute"}))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_panel(conn: psycopg.Connection, days: list[date], codes: list[str] | None = None) -> pd.DataFrame:
    if not days:
        return pd.DataFrame()
    M = load_minutes(conn, min(days), max(days), codes)
    if M.empty:
        return M
    M["d"] = M["minute"].dt.date
    parts = [_one_day(X.drop(columns=["d"]), d) for d, X in M.groupby("d", sort=True) if d in set(days)]
    parts = [p for p in parts if not p.empty]                       # a day where no name reached MIN_MINUTES_FOR_ROW -> nothing
    P = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if P.empty:
        return P
    P["d"] = P["minute"].dt.date
    ctx = load_daily_context(conn, sorted(P["code"].unique()), max(days))
    P = _attach_context(P, ctx)
    return P


def _attach_context(P: pd.DataFrame, ctx: pd.DataFrame) -> pd.DataFrame:
    """The previous bar's context for each (code, day): the last bar strictly before the day."""
    if ctx.empty:
        for c in ("prev_close", "mom20", "vol20", "lvalue20", "dist_ma200"):
            P[c] = np.nan
    else:
        P = P.sort_values("d")
        ctx = ctx.sort_values("d")
        P["dk"] = pd.to_datetime(P["d"])
        ctx["dk"] = pd.to_datetime(ctx["d"]) + pd.Timedelta(days=1)       # a bar dated D is known from D+1 on
        P = pd.merge_asof(P, ctx.drop(columns=["d"]), on="dk", by="code", direction="backward").drop(columns=["dk"])
    P["day_ret"] = P["close"] / P["prev_close"] - 1
    P["gap"] = P["first_close"] / P["prev_close"] - 1
    rng = (P["day_high"] - P["day_low"]).replace(0, np.nan)
    P["day_pos"] = (P["close"] - P["day_low"]) / rng
    P["day_range"] = (P["day_high"] - P["day_low"]) / P["prev_close"]
    return P.sort_values(["code", "minute"]).reset_index(drop=True)


def live_rows(conn: psycopg.Connection, now: datetime) -> tuple[pd.DataFrame, list[datetime]]:
    """Today's panel cut at the last grid minute <= now: one row per name to score, plus the target minute per horizon."""
    gp = grid_position(now)
    if gp is None:
        return pd.DataFrame(), []
    pos, g = gp
    d = now.astimezone(WIB).date()
    M = load_minutes(conn, d, d)
    if M.empty:
        return pd.DataFrame(), []
    M = M[M["minute"] <= g[pos]]
    P = _one_day(M, d)
    if P.empty:
        return P, []
    P["d"] = d
    ctx = load_daily_context(conn, sorted(P["code"].unique()), d)
    P = _attach_context(P, ctx)
    P = P[P["pos"] == pos]
    targets = [g[pos + h.steps].to_pydatetime().astimezone(UTC) if pos + h.steps < len(g) else None for h in INTRADAY]
    return P, targets


def fit_rows(P: pd.DataFrame) -> pd.DataFrame:
    return P[P["pos"] >= MIN_MINUTES_FOR_ROW]
