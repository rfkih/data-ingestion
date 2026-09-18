"""Single-instance scheduler lock and the per-book paper-fill lock (phase 0.1 of the open-research plan)."""
from __future__ import annotations

import os

import psycopg
import pytest

from blackheart_ingest.idx import scheduler, ticket


@pytest.fixture
def two_conns():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        a, b = psycopg.connect(dsn, connect_timeout=5), psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield a, b
    a.close()
    b.close()


def _held_elsewhere(conn, key: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (key,))
        got = cur.fetchone()[0]
        if got:
            cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (key,))
    conn.commit()
    return not got


def test_second_scheduler_is_refused_until_the_first_closes(two_conns) -> None:
    a, b = two_conns
    assert scheduler.try_singleton_lock(a) is True
    assert scheduler.try_singleton_lock(b) is False
    a.close()
    assert scheduler.try_singleton_lock(b) is True


def test_paper_fill_lock_is_held_for_the_duration_and_released_after(two_conns) -> None:
    a, b = two_conns
    key = "paper_fill:test_lock_book"
    assert not _held_elsewhere(b, key)
    with ticket._book_lock(a, key):
        assert _held_elsewhere(b, key)
        a.commit()                                    # commits inside the block must not release a session-level lock
        assert _held_elsewhere(b, key)
    assert not _held_elsewhere(b, key)


def test_paper_fill_lock_released_on_error(two_conns) -> None:
    a, b = two_conns
    key = "paper_fill:test_lock_book_err"
    with pytest.raises(RuntimeError):
        with ticket._book_lock(a, key):
            raise RuntimeError("boom")
    assert not _held_elsewhere(b, key)
