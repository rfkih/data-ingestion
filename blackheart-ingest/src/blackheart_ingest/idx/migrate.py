"""Migration runner for the ``idx`` schema.

Plain SQL files in ``idx/migrations/NNNN_name.sql`` applied in order inside
one transaction each and recorded in ``idx.schema_history`` with a sha256.
A file whose checksum no longer matches its recorded row aborts the run —
edit history by adding a new file, never by changing an applied one.

The ``idx`` schema is owned by the ingest worker (not the trading JVM's
Flyway) so the data plane can change without a Java build.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_NAME_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    sql: str
    sha256: str


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    out: list[Migration] = []
    for p in sorted(directory.glob("*.sql")):
        m = _NAME_RE.match(p.name)
        if not m:
            raise ValueError(f"bad migration filename: {p.name} (want NNNN_name.sql)")
        sql = p.read_text(encoding="utf-8")
        out.append(Migration(int(m.group(1)), m.group(2), p, sql, hashlib.sha256(sql.encode("utf-8")).hexdigest()))
    versions = [m.version for m in out]
    if len(set(versions)) != len(versions):
        raise ValueError(f"duplicate migration versions: {versions}")
    return out


def _ensure_history(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS idx")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS idx.schema_history (
                version    INTEGER PRIMARY KEY,
                name       TEXT NOT NULL,
                sha256     TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def applied(conn: psycopg.Connection) -> dict[int, tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT version, name, sha256 FROM idx.schema_history ORDER BY version")
        rows = cur.fetchall()
    out: dict[int, tuple[str, str]] = {}
    for r in rows:
        if isinstance(r, dict):
            out[int(r["version"])] = (r["name"], r["sha256"])
        else:
            out[int(r[0])] = (r[1], r[2])
    return out


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Apply pending migrations. Returns the ones applied in this call."""
    _ensure_history(conn)
    done = applied(conn)
    ran: list[Migration] = []
    for m in discover(directory):
        if m.version in done:
            _, sha = done[m.version]
            if sha != m.sha256:
                raise RuntimeError(
                    f"migration {m.version:04d}_{m.name} changed after being applied "
                    f"(recorded {sha[:12]}, file {m.sha256[:12]}) — add a new migration instead"
                )
            continue
        logger.info("idx migrate: applying %04d_%s", m.version, m.name)
        try:
            with conn.cursor() as cur:
                cur.execute(m.sql)
                cur.execute(
                    "INSERT INTO idx.schema_history (version, name, sha256) VALUES (%s, %s, %s)",
                    (m.version, m.name, m.sha256),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        ran.append(m)
    return ran


def status(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[tuple[int, str, str]]:
    """(version, name, state) for every discovered migration."""
    _ensure_history(conn)
    done = applied(conn)
    out = []
    for m in discover(directory):
        if m.version not in done:
            state = "pending"
        elif done[m.version][1] != m.sha256:
            state = "DRIFT"
        else:
            state = "applied"
        out.append((m.version, m.name, state))
    return out
