"""Regression tests for the ``_get_max_ts_for_feature`` incremental-refresh bug.

Two stacked bugs made ``POST /compute/refresh?incremental=true`` fail on every
call (and silently degrade the whole refresh to ``status='partial'``, 0 rows):

  1. The query selected ``WHERE name = %(name)s`` — there is no ``name`` column
     on ``feature_values``; the key column is ``feature_name`` (PK is
     ``(feature_name, version, symbol, interval, ts)``). Every call raised
     ``psycopg.errors.UndefinedColumn``.
  2. ``shared.db.get_connection`` uses ``psycopg.rows.dict_row``, so
     ``cur.fetchone()`` returns a dict. The code then did ``row[0]`` which
     raises ``KeyError(0)`` — the identical bug class already fixed in
     ``persistence._count_persisted_for_run`` (2026-05-20).

These pin the fix at both levels: the SQL targets the real column with an
explicit ``MAX(ts) AS max_ts`` alias, and the Python access works under the
dict-row factory (with a tuple-row fallback for injected connections).
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any


def test_max_ts_sql_targets_feature_name_column_with_alias() -> None:
    """SQL must filter on ``feature_name`` (the real column) and alias the
    aggregate as ``max_ts`` so the dict-row factory yields a stable key."""
    from blackheart_ingest.api import compute

    src = inspect.getsource(compute._get_max_ts_for_feature)
    assert "feature_name = %(name)s" in src, (
        "_get_max_ts_for_feature no longer filters on the real ``feature_name`` "
        "column. The prior ``WHERE name=`` raised UndefinedColumn on every "
        "incremental refresh."
    )
    assert "name = %(name)s" not in src.replace("feature_name = %(name)s", ""), (
        "_get_max_ts_for_feature still references a bare ``name`` column."
    )
    assert "MAX(ts) AS max_ts" in src, (
        "_get_max_ts_for_feature must alias ``MAX(ts) AS max_ts`` for stable "
        "dict-row access."
    )


class _FakeDictCursor:
    """Minimal psycopg-cursor stand-in that returns dict-style rows."""

    def __init__(self, row: Any) -> None:
        self._row = row
        self.executed: tuple[str, Any] | None = None

    def __enter__(self) -> "_FakeDictCursor":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    def execute(self, sql: str, params: Any) -> None:
        self.executed = (sql, params)

    def fetchone(self) -> Any:
        return self._row


class _FakeConn:
    def __init__(self, row: Any) -> None:
        self._cursor = _FakeDictCursor(row)

    def cursor(self) -> _FakeDictCursor:
        return self._cursor


def test_max_ts_with_dict_row_returns_value() -> None:
    """The hot path: dict-row factory returns ``{"max_ts": <dt>}``; the
    function must return that datetime. Pre-fix this raised ``KeyError(0)``."""
    from blackheart_ingest.api.compute import _get_max_ts_for_feature

    dt = datetime(2026, 6, 1, 12, 0, 0)
    conn = _FakeConn({"max_ts": dt})
    assert _get_max_ts_for_feature(conn, "ofi_1h", symbol="BTCUSDT", interval="1h") == dt


def test_max_ts_with_tuple_row_falls_back() -> None:
    """Backward compat: a tuple-row connection still works via ``row[0]``."""
    from blackheart_ingest.api.compute import _get_max_ts_for_feature

    dt = datetime(2026, 6, 1, 12, 0, 0)
    conn = _FakeConn((dt,))
    assert _get_max_ts_for_feature(conn, "ofi_1h") == dt


def test_max_ts_strips_timezone_to_naive_utc() -> None:
    """A tz-aware result is normalised to naive UTC (project convention)."""
    from blackheart_ingest.api.compute import _get_max_ts_for_feature

    aware = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    conn = _FakeConn({"max_ts": aware})
    result = _get_max_ts_for_feature(conn, "ofi_1h")
    assert result == datetime(2026, 6, 1, 12, 0, 0)
    assert result.tzinfo is None


def test_max_ts_none_value_returns_none() -> None:
    """No prior rows: ``MAX(ts)`` is NULL → dict has ``{"max_ts": None}`` →
    return None so the caller falls back to a full backfill window."""
    from blackheart_ingest.api.compute import _get_max_ts_for_feature

    assert _get_max_ts_for_feature(_FakeConn({"max_ts": None}), "ofi_1h") is None


def test_max_ts_empty_row_returns_none() -> None:
    from blackheart_ingest.api.compute import _get_max_ts_for_feature

    assert _get_max_ts_for_feature(_FakeConn(None), "ofi_1h") is None
