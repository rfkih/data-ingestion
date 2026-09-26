"""``index-open`` job - the COMPOSITE's opening level, which IDX does not publish, from Yahoo's ^JKSE series.

IDX's index summary carries previous / high / low / close and no open, so a normal open-high-low-close bar cannot be drawn
from it. Yahoo's ^JKSE closes agree with IDX's to 1e-8, and its open lies inside IDX's high-low range on 93 % of days
(2020-2026). On the rest it sits a hair outside (median 0.06 %, at most 0.81 %) and equals the previous close: Yahoo
records the level before the first trade. So the open is taken from Yahoo and bounded by IDX's own high and low; a value
further than MAX_OUTSIDE outside that range is not trusted and the day keeps no open. `open_src` says where it came from.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import psycopg

from .. import runlog

logger = logging.getLogger(__name__)
JOB = "index_open"
YAHOO_SYMBOL = "^JKSE"
MAX_OUTSIDE = 0.01                      # a Yahoo open more than 1 % outside IDX's high-low range is not used


def fetch_yahoo_opens(start: date, end: date, symbol: str = YAHOO_SYMBOL) -> dict[date, float]:
    import yfinance as yf
    df = yf.download(symbol, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), progress=False,
                     auto_adjust=False, multi_level_index=False)
    return {i.date(): float(v) for i, v in df["Open"].items() if v == v}  # v == v drops NaN


def bounded_open(raw: float, low: float, high: float) -> float | None:
    """Yahoo's open inside IDX's range for the day; None when it is too far outside to be the same day's level."""
    span_ref = max(abs(high), 1e-9)
    if raw < low - MAX_OUTSIDE * span_ref or raw > high + MAX_OUTSIDE * span_ref:
        return None
    return min(max(raw, low), high)


def run(conn: psycopg.Connection, *, since: date | None = None, index_code: str = "COMPOSITE",
        fetch: Callable[[date, date], dict[date, float]] = fetch_yahoo_opens) -> runlog.RunResult:
    """Fill `open` on the index rows that have none (since `since`, or all of them)."""
    r = runlog.RunResult(JOB, (since or date(1990, 1, 1)).isoformat())
    run_id = runlog.start(conn, JOB, r.run_key)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT trade_date, low, high FROM idx.index_daily
                            WHERE index_code = %s AND open IS NULL AND low IS NOT NULL AND high IS NOT NULL
                              AND (%s::date IS NULL OR trade_date >= %s::date) ORDER BY trade_date""",
                        (index_code, since, since))
            rows = [(t[0], float(t[1]), float(t[2])) if not isinstance(t, dict) else (t["trade_date"], float(t["low"]), float(t["high"]))
                    for t in cur.fetchall()]
        r.rows_in = len(rows)
        if not rows:
            r.status = "ok"
            runlog.finish(conn, run_id, r)
            return r
        opens = fetch(rows[0][0], rows[-1][0])
        filled = skipped = missing = 0
        with conn.cursor() as cur:
            for d, low, high in rows:
                raw = opens.get(d)
                if raw is None:
                    missing += 1
                    continue
                o = bounded_open(raw, low, high)
                if o is None:
                    skipped += 1
                    continue
                cur.execute("UPDATE idx.index_daily SET open = %s, open_src = 'yahoo' WHERE trade_date = %s AND index_code = %s AND open IS NULL",
                            (Decimal(str(round(o, 4))), d, index_code))
                filled += cur.rowcount
        conn.commit()
        r.rows_out = filled
        r.detail.update({"filled": filled, "not_on_yahoo": missing, "too_far_outside": skipped})
        r.status = "ok"
        logger.info("index opens %s: filled %s, not on Yahoo %s, too far outside %s", index_code, filled, missing, skipped)
    except Exception as e:  # recorded on the run row; the chain goes on without opens
        conn.rollback()
        r.status, r.error = "failed", str(e)[:500]
        logger.warning("index opens failed: %s", e)
    runlog.finish(conn, run_id, r)
    return r
