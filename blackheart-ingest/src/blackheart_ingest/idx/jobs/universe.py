"""``universe`` job — Daftar Saham snapshot → ``idx.listing`` + ``idx.listing_snapshot``.

Codes present today are ACTIVE (first_seen/last_seen maintained); codes that
were ACTIVE but are missing from a full snapshot become DELISTED. A snapshot
smaller than ``MIN_ROWS`` is treated as a partial payload and never used to
delist anything.
"""
from __future__ import annotations

import logging
from datetime import date

import psycopg

from .. import bronze, etl, runlog
from ..client import IdxClient

logger = logging.getLogger(__name__)
JOB = "universe"
MIN_ROWS = 800


def process(conn: psycopg.Connection, d: date, rows: list[dict], r: runlog.RunResult) -> None:
    listings = etl.listing_rows(rows)
    r.rows_in = len(rows)
    if not listings:
        r.status = "failed"
        r.error = "empty Daftar Saham payload"
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO idx.listing_snapshot (snapshot_date, code, name, listing_date, board, listed_shares)
            VALUES (%(d)s, %(code)s, %(name)s, %(listing_date)s, %(board)s, %(listed_shares)s)
            ON CONFLICT (snapshot_date, code) DO UPDATE SET
                name = EXCLUDED.name, listing_date = EXCLUDED.listing_date, board = EXCLUDED.board,
                listed_shares = EXCLUDED.listed_shares
            """,
            [{"d": d, **lst} for lst in listings],
        )
        cur.executemany(
            """
            INSERT INTO idx.listing (code, name, listing_date, board, listed_shares, status, first_seen, last_seen, updated_at)
            VALUES (%(code)s, %(name)s, %(listing_date)s, %(board)s, %(listed_shares)s, 'ACTIVE', %(d)s, %(d)s, now())
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name, listing_date = COALESCE(EXCLUDED.listing_date, idx.listing.listing_date),
                board = EXCLUDED.board, listed_shares = EXCLUDED.listed_shares, status = 'ACTIVE',
                first_seen = LEAST(idx.listing.first_seen, EXCLUDED.first_seen),
                last_seen = GREATEST(idx.listing.last_seen, EXCLUDED.last_seen), updated_at = now()
            """,
            [{"d": d, **lst} for lst in listings],
        )
        delisted = 0
        if len(listings) >= MIN_ROWS:
            cur.execute(
                "UPDATE idx.listing SET status = 'DELISTED', updated_at = now() "
                "WHERE status = 'ACTIVE' AND NOT (code = ANY(%s))",
                ([lst["code"] for lst in listings],),
            )
            delisted = cur.rowcount
        else:
            r.warn(f"snapshot has only {len(listings)} rows (< {MIN_ROWS}); delisting skipped")
    conn.commit()
    r.rows_out = len(listings)
    r.detail["delisted_now"] = delisted
    boards: dict[str, int] = {}
    for lst in listings:
        boards[lst["board"] or "?"] = boards.get(lst["board"] or "?", 0) + 1
    r.detail["boards"] = boards


def run(conn: psycopg.Connection, client: IdxClient, d: date) -> runlog.RunResult:
    r = runlog.RunResult(JOB, d.isoformat())
    run_id = runlog.start(conn, JOB, r.run_key)
    try:
        res = client.securities_stock()
        drift = bronze.drift(conn, res)
        bid = bronze.write(conn, res)
        if drift:
            r.warn(f"payload fingerprint drift: {drift[0]} -> {drift[1]}")
            runlog.alert(conn, "warning", JOB, f"securities_stock field drift: {drift[1]}")
        r.detail["bronze_id"] = bid
        process(conn, d, res.rows(), r)
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx universe failed")
    runlog.finish(conn, run_id, r)
    return r
