"""Phase-1b overlay features -> ``idx.feature_daily`` (+ optional mirror into ``feature_values``).

Point-in-time rule: a feature for ``trade_date`` may only use rows whose publication time is at or
before that day's close (16:00 WIB is used as the daily cut, since IDX publishes the summary ~16:00).
Foreign flow is part of the same-day Ringkasan Saham row, so it is available at the cut; a disclosure
published at 16:10 WIB counts from the NEXT trading day.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg

from . import runlog

logger = logging.getLogger(__name__)
JOB = "features"
WIB = ZoneInfo("Asia/Jakarta")
DAILY_CUT = time(16, 0)         # WIB
EVENT_WINDOWS = {"ownership_change": ("ev_ownership_30d", 30), "exchange_query": ("ev_exchange_query_10d", 10),
                 "dividend": ("ev_dividend_30d", 30), "buyback": ("ev_buyback_30d", 30),
                 "material_info": ("ev_material_30d", 30), "rights": ("ev_rights_60d", 60)}

# feature_values mirror (platform contract): name -> (column, family, description)
MIRRORED = {
    "idx_foreign_net_share_5d": ("foreign_net_share_5d", "positioning"),
    "idx_foreign_net_share_20d": ("foreign_net_share_20d", "positioning"),
    "idx_value_60d_median": ("value_60d_median", "liquidity"),
    "idx_ev_ownership_30d": ("ev_ownership_30d", "events"),
    "idx_ev_exchange_query_10d": ("ev_exchange_query_10d", "events"),
}


def _frame(conn: psycopg.Connection, sql: str, params: dict[str, Any] | None, cols: list[str]) -> pd.DataFrame:
    """pandas.read_sql does not support psycopg3 connections; fetch explicitly (dict or tuple rows)."""
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        rows = cur.fetchall()
    if rows and isinstance(rows[0], dict):
        return pd.DataFrame(rows, columns=cols)
    return pd.DataFrame(rows, columns=cols)


def cut_utc(d: date) -> datetime:
    return datetime.combine(d, DAILY_CUT, tzinfo=WIB).astimezone(UTC)


def event_effective_date(published_at: datetime, trading_days: pd.DatetimeIndex) -> date | None:
    """First trading day whose 16:00-WIB cut is >= published_at (PIT: never the same day if after the cut)."""
    p = published_at.astimezone(WIB)
    d0 = p.date() if p.time() <= DAILY_CUT else p.date() + timedelta(days=1)
    pos = trading_days.searchsorted(pd.Timestamp(d0))
    return trading_days[pos].date() if pos < len(trading_days) else None


def compute(conn: psycopg.Connection, *, codes: list[str] | None, since: date | None) -> pd.DataFrame:
    q = """
        SELECT trade_date, code, close, volume, listed_shares, foreign_buy, foreign_sell, value
          FROM idx.daily_summary WHERE close > 0 {codes_clause}
         ORDER BY code, trade_date
    """.format(codes_clause="AND code = ANY(%(codes)s)" if codes else "")
    df = _frame(conn, q, {"codes": codes} if codes else None,
                ["trade_date", "code", "close", "volume", "listed_shares", "foreign_buy", "foreign_sell", "value"])
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    for c in ("close", "volume", "listed_shares", "foreign_buy", "foreign_sell", "value"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    g = df.groupby("code", sort=False)
    net = df["foreign_buy"] - df["foreign_sell"]
    df["_net"] = net
    for w in (5, 20):
        s_net = g["_net"].transform(lambda s, w=w: s.rolling(w, min_periods=w).sum())
        s_vol = g["volume"].transform(lambda s, w=w: s.rolling(w, min_periods=w).sum())
        df[f"foreign_net_share_{w}d"] = (s_net / s_vol.where(s_vol > 0)).round(5)
    df["foreign_net_shares_20d"] = g["_net"].transform(lambda s: s.rolling(20, min_periods=20).sum())
    df["value_60d_median"] = g["value"].transform(lambda s: s.rolling(60, min_periods=60).median())
    df["mcap"] = (df["listed_shares"] * df["close"]).where(df["listed_shares"] > 0)
    df["mcap_quintile"] = df.groupby("trade_date")["mcap"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]) if s.notna().sum() >= 5 else pd.Series([None] * len(s), index=s.index))

    # events -> effective trading day -> trailing counts
    ev = _frame(conn,
                "SELECT code, kind, published_at FROM idx.event WHERE kind = ANY(%(kinds)s) {cc}".format(
                    cc="AND code = ANY(%(codes)s)" if codes else ""),
                {"kinds": list(EVENT_WINDOWS), "codes": codes}, ["code", "kind", "published_at"])
    trading_days = pd.DatetimeIndex(sorted(df["trade_date"].unique()))
    for col, _ in EVENT_WINDOWS.values():
        df[col] = 0
    if not ev.empty:
        ev["published_at"] = pd.to_datetime(ev["published_at"], utc=True)
        ev["eff"] = [event_effective_date(t.to_pydatetime(), trading_days) for t in ev["published_at"]]
        ev = ev.dropna(subset=["eff"])
        ev["eff"] = pd.to_datetime(ev["eff"])
        counts = ev.groupby(["code", "eff", "kind"]).size().rename("n").reset_index()
        key = df.set_index(["code", "trade_date"]).index
        for kind, (col, win) in EVENT_WINDOWS.items():
            ck = counts[counts["kind"] == kind]
            if ck.empty:
                continue
            daily = pd.Series(ck["n"].values, index=pd.MultiIndex.from_arrays([ck["code"], ck["eff"]]))
            aligned = daily.reindex(key, fill_value=0).to_numpy()
            df["_tmp"] = aligned
            df[col] = df.groupby("code", sort=False)["_tmp"].transform(lambda s, win=win: s.rolling(win, min_periods=1).sum()).astype(int)
        df = df.drop(columns=["_tmp"], errors="ignore")
    if since is not None:
        df = df[df["trade_date"] >= pd.Timestamp(since)]
    return df.drop(columns=["_net"])


_UPSERT = """
INSERT INTO idx.feature_daily (trade_date, code, foreign_net_share_5d, foreign_net_share_20d, foreign_net_shares_20d,
    value_60d_median, mcap, mcap_quintile, ev_ownership_30d, ev_exchange_query_10d, ev_dividend_30d, ev_buyback_30d,
    ev_material_30d, ev_rights_60d, computed_at)
VALUES (%(trade_date)s, %(code)s, %(foreign_net_share_5d)s, %(foreign_net_share_20d)s, %(foreign_net_shares_20d)s,
    %(value_60d_median)s, %(mcap)s, %(mcap_quintile)s, %(ev_ownership_30d)s, %(ev_exchange_query_10d)s, %(ev_dividend_30d)s,
    %(ev_buyback_30d)s, %(ev_material_30d)s, %(ev_rights_60d)s, now())
ON CONFLICT (trade_date, code) DO UPDATE SET
    foreign_net_share_5d = EXCLUDED.foreign_net_share_5d, foreign_net_share_20d = EXCLUDED.foreign_net_share_20d,
    foreign_net_shares_20d = EXCLUDED.foreign_net_shares_20d, value_60d_median = EXCLUDED.value_60d_median,
    mcap = EXCLUDED.mcap, mcap_quintile = EXCLUDED.mcap_quintile, ev_ownership_30d = EXCLUDED.ev_ownership_30d,
    ev_exchange_query_10d = EXCLUDED.ev_exchange_query_10d, ev_dividend_30d = EXCLUDED.ev_dividend_30d,
    ev_buyback_30d = EXCLUDED.ev_buyback_30d, ev_material_30d = EXCLUDED.ev_material_30d,
    ev_rights_60d = EXCLUDED.ev_rights_60d, computed_at = now()
"""


def _nn(v: Any):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def write(conn: psycopg.Connection, df: pd.DataFrame) -> int:
    cols = ["trade_date", "code", "foreign_net_share_5d", "foreign_net_share_20d", "foreign_net_shares_20d", "value_60d_median",
            "mcap", "mcap_quintile", "ev_ownership_30d", "ev_exchange_query_10d", "ev_dividend_30d", "ev_buyback_30d",
            "ev_material_30d", "ev_rights_60d"]
    rows = []
    for rec in df[cols].itertuples(index=False):
        d = dict(zip(cols, rec, strict=True))
        d["trade_date"] = d["trade_date"].date()
        for k in cols[2:]:
            d[k] = _nn(d[k])
        for k in ("foreign_net_shares_20d", "value_60d_median", "mcap"):
            if d[k] is not None:
                d[k] = int(d[k])
        if d["mcap_quintile"] is not None:
            d["mcap_quintile"] = int(d["mcap_quintile"])
        rows.append(d)
    with conn.cursor() as cur:
        for i in range(0, len(rows), 5000):
            cur.executemany(_UPSERT, rows[i:i + 5000])
    conn.commit()
    return len(rows)


def run(conn: psycopg.Connection, *, codes: list[str] | None = None, since: date | None = None) -> runlog.RunResult:
    r = runlog.RunResult(JOB, since.isoformat() if since else "full")
    run_id = runlog.start(conn, JOB, r.run_key)
    try:
        df = compute(conn, codes=codes, since=since)
        r.rows_in = len(df)
        r.rows_out = write(conn, df) if not df.empty else 0
        r.detail["codes"] = int(df["code"].nunique()) if not df.empty else 0
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx features failed")
    runlog.finish(conn, run_id, r)
    return r


def publish_feature_values(conn: psycopg.Connection, *, codes: list[str], since: date | None = None) -> int:
    """Mirror MIRRORED features for the given codes into feature_registry/feature_values (symbol <CODE>.JK, 1d,
    ts = the 16:00 WIB cut)."""
    with conn.cursor() as cur:
        for name, (col, family) in MIRRORED.items():
            cur.execute(
                """
                INSERT INTO feature_registry (feature_name, version, family, owner, transformer_ref, inputs, output_dtype,
                    symbols, intervals, pit_safe, publish_schedule, ffill_policy, max_ffill_age_hours, backfill_strategy, status,
                    created_by, updated_by)
                VALUES (%s, 1, %s, 'blackheart-ingest/idx', %s, %s::jsonb, 'numeric', NULL, ARRAY['1d'], true,
                        'daily 16:30 WIB', 'none', 0, 'idx features --publish', 'registered', 'idx', 'idx')
                ON CONFLICT DO NOTHING
                """,
                (name, family, f"blackheart_ingest.idx.features:{col}", json.dumps({"table": "idx.feature_daily", "column": col})),
            )
        cur.execute(
            "SELECT trade_date, code, {} FROM idx.feature_daily WHERE code = ANY(%s) {} ORDER BY code, trade_date".format(
                ", ".join(c for c, _ in MIRRORED.values()), "AND trade_date >= %s" if since else ""),
            (codes, since) if since else (codes,))
        rows = cur.fetchall()
        run_uuid = uuid.uuid4()
        out = []
        for row in rows:
            rr = row if isinstance(row, dict) else dict(zip(["trade_date", "code", *[c for c, _ in MIRRORED.values()]], row, strict=True))
            ts = cut_utc(rr["trade_date"])
            for name, (col, _) in MIRRORED.items():
                v = _nn(rr[col])
                if v is None:
                    continue
                out.append((name, 1, f"{rr['code']}.JK", "1d", ts, v, run_uuid))
        for i in range(0, len(out), 10000):
            cur.executemany(
                """
                INSERT INTO feature_values (feature_name, version, symbol, interval, ts, value, compute_run_id, created_by, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'idx', 'idx')
                ON CONFLICT (feature_name, version, symbol, interval, ts) DO UPDATE SET value = EXCLUDED.value,
                    compute_run_id = EXCLUDED.compute_run_id, updated_time = now()
                """,
                out[i:i + 10000])
    conn.commit()
    return len(out)
