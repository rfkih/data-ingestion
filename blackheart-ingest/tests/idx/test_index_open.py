"""jobs/index_open: Yahoo's ^JKSE open bounded by IDX's high and low; far-off values and days Yahoo lacks stay without one."""
from __future__ import annotations

import os
from datetime import date

import psycopg
import pytest

from blackheart_ingest.idx.jobs import index_open as io


def test_bounded_open():
    assert io.bounded_open(105.0, 100.0, 110.0) == 105.0          # inside: as Yahoo has it
    assert io.bounded_open(110.5, 100.0, 110.0) == 110.0          # a hair above the high: bounded to it
    assert io.bounded_open(99.5, 100.0, 110.0) == 100.0
    assert io.bounded_open(125.0, 100.0, 110.0) is None           # more than 1 % outside: not the same day's level


@pytest.fixture
def conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        c = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield c
    c.close()


CODE = "TEST_INDEX_OPEN"


def test_run_fills_only_what_it_can_trust(conn):
    days = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    try:
        with conn.cursor() as cur:
            for d in days:
                cur.execute("""INSERT INTO idx.index_daily (trade_date, index_code, high, low, close, fetched_at)
                               VALUES (%s, %s, 110, 100, 105, now())""", (d, CODE))
        conn.commit()
        fake = {days[0]: 104.0, days[1]: 150.0}                       # day 2 far outside, day 3 not on Yahoo
        r = io.run(conn, index_code=CODE, fetch=lambda a, b: fake)
        assert r.status == "ok" and r.detail == {"filled": 1, "not_on_yahoo": 1, "too_far_outside": 1}
        with conn.cursor() as cur:
            cur.execute("SELECT trade_date, open, open_src FROM idx.index_daily WHERE index_code = %s ORDER BY trade_date", (CODE,))
            got = cur.fetchall()
        assert [(float(o) if o is not None else None, s) for _, o, s in got] == [(104.0, "yahoo"), (None, None), (None, None)]
        assert io.run(conn, index_code=CODE, fetch=lambda a, b: {days[0]: 90.0}).rows_out == 0   # a filled open is not rewritten
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM idx.index_daily WHERE index_code = %s", (CODE,))
            cur.execute("DELETE FROM idx.ingest_run WHERE job = %s AND run_key = %s", (io.JOB, "1990-01-01"))
        conn.commit()
