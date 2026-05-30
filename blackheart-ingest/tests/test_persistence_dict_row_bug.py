"""Regression tests for the 2026-05-20 ``_count_persisted_for_run`` bug.

Background: ``shared.db.get_connection`` uses ``psycopg.rows.dict_row``
as the row_factory, so ``cur.fetchone()`` returns a dict-like row.
The original ``_count_persisted_for_run`` did ``row[0]`` (tuple-style
indexing) which raised ``KeyError(0)`` on every call. The exception
propagated up through ``finish_run`` and caused EVERY feature compute
to fail post-persist — the audit row got marked failed, even though
``write_values`` had already committed N rows.

The silent failure mode: callers see ``FAIL persist: 0`` (the str of
``KeyError(0)``) and the operator interprets it as "wrote zero rows",
when in reality N rows landed but the audit row mis-counts them. After
the V84 TimescaleDB hypertable migration on 2026-05-17, this bug was
the root cause of feature_values appearing empty despite successful
upsert log lines.

These tests pin the fix at two levels:
  1. SQL must use an explicit alias (``AS n``) — the dict-row factory
     can pick a stable key vs whatever pg generates for unaliased
     COUNT(*).
  2. The Python access pattern works under dict-row factory.
"""
from __future__ import annotations

import inspect
import uuid
from typing import Any

import pytest


def test_count_persisted_sql_uses_explicit_alias() -> None:
    """The SQL in _count_persisted_for_run must use ``COUNT(*) AS n``
    so the dict-row factory yields a stable key. Bare ``COUNT(*)``
    gives an implementation-defined column name in pg and risks
    silent breakage on row_factory changes."""
    from blackheart_ingest.features import persistence

    src = inspect.getsource(persistence._count_persisted_for_run)
    assert "COUNT(*) AS n" in src, (
        "_count_persisted_for_run no longer SELECTs ``COUNT(*) AS n``. "
        "Without the explicit alias, dict-row factory yields an "
        "implementation-defined column name and reads break. See "
        "the 2026-05-20 silent-KeyError bug for context."
    )


class _FakeDictCursor:
    """Minimal psycopg-cursor stand-in that returns dict-style rows."""

    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def __enter__(self) -> "_FakeDictCursor":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    def execute(self, sql: str, params: Any) -> None:
        self._executed = (sql, params)

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _FakeConn:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def cursor(self) -> _FakeDictCursor:
        return _FakeDictCursor(self._row)


def test_count_persisted_with_dict_row_returns_int() -> None:
    """The hot path: dict-row factory returns ``{"n": 143}``; the
    function must return 143 as an int. Pre-fix this raised
    ``KeyError(0)``."""
    from blackheart_ingest.features.persistence import _count_persisted_for_run

    conn = _FakeConn({"n": 143})
    result = _count_persisted_for_run(uuid.uuid4(), conn=conn)
    assert result == 143


def test_count_persisted_with_tuple_row_falls_back() -> None:
    """Backward compat: if a caller injects a connection with the
    default tuple-row factory, the function should still work via the
    ``row[0]`` fallback."""
    from blackheart_ingest.features.persistence import _count_persisted_for_run

    # psycopg tuple rows are real tuples, not dicts.
    conn = _FakeConn((57,))
    result = _count_persisted_for_run(uuid.uuid4(), conn=conn)
    assert result == 57


def test_count_persisted_empty_returns_zero() -> None:
    """``fetchone() -> None`` (no rows somehow) returns 0 instead of
    raising. Defensive — COUNT(*) on a table always returns one row,
    so this shouldn't fire in production; but mocked tests need it."""
    from blackheart_ingest.features.persistence import _count_persisted_for_run

    conn = _FakeConn(None)
    assert _count_persisted_for_run(uuid.uuid4(), conn=conn) == 0
