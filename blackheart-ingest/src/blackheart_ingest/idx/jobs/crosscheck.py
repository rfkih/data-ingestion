"""``crosscheck`` job - per-stock endpoint (GetTradingInfoSS) vs ``idx.bar`` for a sample of codes.

The day-dump and the per-stock history are two views of the same IDX table;
if they disagree on a close by more than ``TOL`` the feed changed under us
(restatement, late correction) and the day should be re-fetched.
"""
from __future__ import annotations

import logging
import random
from datetime import date, timedelta
from decimal import Decimal

import psycopg

from .. import bronze, etl, runlog
from ..client import IdxClient

logger = logging.getLogger(__name__)
JOB = "crosscheck"
TOL = Decimal("0.005")
LOOKBACK_DAYS = 45


def _sample_codes(conn: psycopg.Connection, sample: int, seed: int | None) -> list[str]:
    """Top names by recent traded value plus a rotating random slice of the rest."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT code FROM idx.bar WHERE trade_date >= %s AND source = 'idx'
             GROUP BY code ORDER BY sum(value) DESC NULLS LAST
            """,
            (date.today() - timedelta(days=30),),
        )
        ordered = [r[0] if isinstance(r, tuple) else r["code"] for r in cur.fetchall()]
    if not ordered:
        return []
    head = ordered[: sample // 2]
    rest = ordered[sample // 2:]
    random.Random(seed).shuffle(rest)
    return head + rest[: sample - len(head)]


def run(conn: psycopg.Connection, client: IdxClient, *, sample: int = 60, codes: list[str] | None = None,
        seed: int | None = None) -> runlog.RunResult:
    r = runlog.RunResult(JOB, date.today().isoformat())
    codes = codes or _sample_codes(conn, sample, seed)
    run_id = runlog.start(conn, JOB, r.run_key)
    since = date.today() - timedelta(days=LOOKBACK_DAYS)
    mism: list[str] = []
    checked = 0
    try:
        for code in codes:
            res = client.trading_info(code)
            bronze.write(conn, res)
            remote = {}
            for row in res.rows():
                s = etl.summary_row(row, res.fetched_at, None)
                if s and s["trade_date"] >= since and s["close"]:
                    remote[s["trade_date"]] = s["close"]
            with conn.cursor() as cur:
                cur.execute("SELECT trade_date, close FROM idx.bar WHERE code = %s AND source = 'idx' AND trade_date >= %s",
                            (code, since))
                local = {(x[0] if isinstance(x, tuple) else x["trade_date"]): (x[1] if isinstance(x, tuple) else x["close"])
                         for x in cur.fetchall()}
            bad = [d for d, c in remote.items() if d in local and abs(local[d] / c - 1) > TOL]
            missing = [d for d in remote if d not in local and d.weekday() < 5]
            checked += 1
            if bad or missing:
                mism.append(f"{code}: {len(bad)} closes differ, {len(missing)} days missing locally")
        r.rows_in = checked
        r.rows_out = len(mism)
        if mism:
            r.detail["mismatch_codes"] = len(mism)
            for m in mism[:20]:
                r.warn(m)
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx crosscheck failed")
    runlog.finish(conn, run_id, r)
    return r
