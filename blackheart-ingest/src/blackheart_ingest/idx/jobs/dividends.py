"""``dividends`` job — dated cash dividends per share -> ``idx.dividend``.

Primary IDX data carries amounts *paid* per fiscal year (cash-flow statement) but not ex-dates; the
disclosure feed carries the schedule announcements but the amount sits in a PDF. For the total-return
series the research needs (ex_date, amount), so this job takes Yahoo's dividend events (``events=div``,
split-adjusted amounts) and stores them with ``source='yahoo'``. ``crosscheck_paid`` compares each
fiscal year's Yahoo total x shares against the parsed ``dividends_paid`` where available.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import psycopg

from .. import runlog

logger = logging.getLogger(__name__)
JOB = "dividends"
UA = "Mozilla/5.0"


def fetch_yahoo(code: str, range_: str = "10y") -> list[tuple[date, Decimal]]:
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(code + ".JK")
           + f"?interval=1d&range={range_}&events=div")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)["chart"]["result"][0]
    divs = (d.get("events") or {}).get("dividends") or {}
    out = []
    for v in divs.values():
        try:
            out.append((datetime.fromtimestamp(int(v["date"]), tz=UTC).date(), Decimal(str(v["amount"]))))
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(out)


def run(conn: psycopg.Connection, codes: list[str], *, sleep_s: float = 1.2) -> runlog.RunResult:
    import time
    r = runlog.RunResult(JOB, f"{len(codes)} codes")
    run_id = runlog.start(conn, JOB, r.run_key)
    n_rows = n_fail = 0
    try:
        for i, code in enumerate(codes, 1):
            try:
                evs = fetch_yahoo(code)
            except Exception as e:
                n_fail += 1
                if n_fail <= 10:
                    r.warn(f"{code}: {type(e).__name__}: {str(e)[:80]}")
                time.sleep(sleep_s)
                continue
            if evs:
                with conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO idx.dividend (code, ex_date, kind, amount_per_share, currency, source)
                        VALUES (%s, %s, 'cash', %s, 'IDR', 'yahoo')
                        ON CONFLICT (code, ex_date, kind) DO UPDATE SET amount_per_share = EXCLUDED.amount_per_share
                        """, [(code, d, a) for d, a in evs])
                conn.commit()
                n_rows += len(evs)
            if i % 50 == 0:
                logger.info("idx dividends %d/%d rows=%d fail=%d", i, len(codes), n_rows, n_fail)
            time.sleep(sleep_s)
        r.rows_in = len(codes)
        r.rows_out = n_rows
        r.detail["failed_codes"] = n_fail
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
    runlog.finish(conn, run_id, r)
    return r


def crosscheck_paid(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Per (code, fiscal year): Yahoo DPS sum x shares_out vs primary dividends_paid (audited cash flow)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH y AS (
              SELECT code, extract(year FROM ex_date)::int AS yr, sum(amount_per_share) AS dps
                FROM idx.dividend WHERE source = 'yahoo' GROUP BY 1, 2)
            SELECT f.code, extract(year FROM f.period_end)::int AS fy, f.dividends_paid, f.shares_out, y.dps,
                   CASE WHEN f.shares_out > 0 AND y.dps IS NOT NULL THEN y.dps * f.shares_out END AS yahoo_paid_est
              FROM idx.fundamental f LEFT JOIN y ON y.code = f.code AND y.yr = extract(year FROM f.period_end)::int + 1
             WHERE f.period_label = 'TAHUNAN' AND f.dividends_paid > 0
            """)
        rows = cur.fetchall()
    cols = ["code", "fy", "dividends_paid", "shares_out", "dps", "yahoo_paid_est"]
    return [x if isinstance(x, dict) else dict(zip(cols, x, strict=True)) for x in rows]
