"""idx migration runner — discovery/checksum logic offline, idempotence against a DB when reachable."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from blackheart_ingest.idx import migrate as mig


def test_discover_orders_and_hashes(tmp_path: Path) -> None:
    (tmp_path / "0002_b.sql").write_text("select 2;", encoding="utf-8")
    (tmp_path / "0001_a.sql").write_text("select 1;", encoding="utf-8")
    ms = mig.discover(tmp_path)
    assert [m.version for m in ms] == [1, 2]
    assert ms[0].sha256 != ms[1].sha256 and len(ms[0].sha256) == 64


def test_discover_rejects_bad_names_and_duplicates(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "0001_dup.sql").write_text("select 1;", encoding="utf-8")
    with pytest.raises(ValueError):
        mig.discover(tmp_path)
    (tmp_path / "0001_dup.sql").unlink()
    (tmp_path / "junk.sql").write_text("select 1;", encoding="utf-8")
    with pytest.raises(ValueError):
        mig.discover(tmp_path)


def test_shipped_migrations_parse() -> None:
    ms = mig.discover()
    assert ms and ms[0].version == 1 and "CREATE SCHEMA IF NOT EXISTS idx" in ms[0].sql


@pytest.fixture
def db_conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        conn = psycopg.connect(dsn, autocommit=False)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield conn
    conn.close()


def test_migrate_is_idempotent(db_conn) -> None:
    first = mig.migrate(db_conn)
    second = mig.migrate(db_conn)
    assert second == []
    states = {v: st for v, _, st in mig.status(db_conn)}
    assert all(st == "applied" for st in states.values())
    assert first == [] or first[0].version == 1
