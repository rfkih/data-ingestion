"""``index`` job — Ringkasan Indeks for one day → ``idx.index_daily`` (45 indices; no open)."""
from __future__ import annotations

import logging
from datetime import date, datetime

import psycopg

from .. import bronze, etl, runlog
from ..client import IdxClient

logger = logging.getLogger(__name__)
JOB = "index"

_SQL = """
INSERT INTO idx.index_daily (trade_date, index_code, previous, open, high, low, close, volume, value, bronze_id, fetched_at)
VALUES (%(trade_date)s, %(index_code)s, %(previous)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(value)s,
        %(bronze_id)s, %(fetched_at)s)
ON CONFLICT (trade_date, index_code) DO UPDATE SET
    previous = EXCLUDED.previous, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close,
    volume = EXCLUDED.volume, value = EXCLUDED.value, bronze_id = EXCLUDED.bronze_id, fetched_at = EXCLUDED.fetched_at
"""


def process(conn: psycopg.Connection, d: date, rows: list[dict], fetched_at: datetime, bronze_id: int | None,
            r: runlog.RunResult) -> None:
    out = [x for x in etl.index_rows(rows, fetched_at, bronze_id) if x["trade_date"] == d]
    r.rows_in = len(rows)
    if not out:
        r.detail["empty"] = True
        return
    with conn.cursor() as cur:
        cur.executemany(_SQL, out)
    conn.commit()
    r.rows_out = len(out)


def run(conn: psycopg.Connection, client: IdxClient, d: date) -> runlog.RunResult:
    r = runlog.RunResult(JOB, d.isoformat())
    if d.weekday() >= 5:
        r.status = "skipped"
        return r
    run_id = runlog.start(conn, JOB, r.run_key)
    try:
        res = client.index_summary(d)
        drift = bronze.drift(conn, res)
        bid = bronze.write(conn, res)
        if drift:
            r.warn(f"payload fingerprint drift: {drift[0]} -> {drift[1]}")
        process(conn, d, res.rows(), res.fetched_at, bid, r)
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx index %s failed", d)
    runlog.finish(conn, run_id, r)
    return r


def replay(conn: psycopg.Connection, d: date) -> runlog.RunResult:
    r = runlog.RunResult(JOB + ":replay", d.isoformat())
    row = bronze.latest(conn, "index_summary", d.isoformat())
    if row is None:
        r.status = "failed"
        r.error = "no bronze payload for this date"
        return r
    payload = bronze.read(None, row["path"])
    rows = payload.get("data") or [] if isinstance(payload, dict) else []
    run_id = runlog.start(conn, r.job, r.run_key)
    try:
        process(conn, d, rows, row["fetched_at"], row["id"], r)
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
    runlog.finish(conn, run_id, r)
    return r
