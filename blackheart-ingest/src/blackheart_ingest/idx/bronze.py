"""Bronze layer — immutable archive of every idx.co.id response.

Files: ``<bronze_dir>/<endpoint>/<key>/<fetched_at>.json.gz`` (raw bytes,
gzip). Rows: ``idx.bronze_index`` with sha256, size, HTTP status and the
payload fingerprint. Silver is a deterministic function of bronze; nothing
downstream ever needs the network again once a response is archived.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

from ..shared.settings import get_settings
from .client import FetchResult

logger = logging.getLogger(__name__)
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def bronze_dir() -> Path:
    return Path(get_settings().idx_bronze_dir)


def _rel_path(endpoint: str, key: str, fetched_at: datetime) -> Path:
    safe_key = _SAFE.sub("_", key) or "_"
    return Path(endpoint) / safe_key / (fetched_at.strftime("%Y%m%dT%H%M%S%fZ") + ".json.gz")


def write(conn: psycopg.Connection, res: FetchResult, *, directory: Path | None = None) -> int:
    """Archive one response; returns the ``idx.bronze_index.id``. Commits."""
    root = directory or bronze_dir()
    rel = _rel_path(res.endpoint, res.key, res.fetched_at)
    full = root / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(full, "wb") as f:
        f.write(res.body)
    sha = hashlib.sha256(res.body).hexdigest()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO idx.bronze_index (endpoint, key, fetched_at, path, sha256, bytes, http_status, fingerprint)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (res.endpoint, res.key, res.fetched_at, rel.as_posix(), sha, len(res.body), res.status, res.fingerprint),
        )
        row = cur.fetchone()
    conn.commit()
    bid = row[0] if isinstance(row, tuple) else row["id"]
    logger.debug("bronze wrote %s/%s -> %s (%d bytes)", res.endpoint, res.key, rel.as_posix(), len(res.body))
    return int(bid)


def read(directory: Path | None, rel_path: str) -> Any:
    root = directory or bronze_dir()
    with gzip.open(root / rel_path, "rb") as f:
        return json.loads(f.read())


def latest(conn: psycopg.Connection, endpoint: str, key: str) -> dict[str, Any] | None:
    """Most recent index row for (endpoint, key), or None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, endpoint, key, fetched_at, path, sha256, bytes, http_status, fingerprint
            FROM idx.bronze_index WHERE endpoint = %s AND key = %s
            ORDER BY fetched_at DESC LIMIT 1
            """,
            (endpoint, key),
        )
        row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    cols = ["id", "endpoint", "key", "fetched_at", "path", "sha256", "bytes", "http_status", "fingerprint"]
    return dict(zip(cols, row, strict=True))


def last_fingerprint(conn: psycopg.Connection, endpoint: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT fingerprint FROM idx.bronze_index WHERE endpoint = %s AND fingerprint IS NOT NULL "
            "ORDER BY fetched_at DESC LIMIT 1",
            (endpoint,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return row[0] if isinstance(row, tuple) else row["fingerprint"]


def drift(conn: psycopg.Connection, res: FetchResult) -> tuple[str | None, str | None] | None:
    """Return (previous, current) fingerprints if the row shape changed, else None."""
    prev = last_fingerprint(conn, res.endpoint)
    if prev is not None and res.fingerprint is not None and prev != res.fingerprint:
        return prev, res.fingerprint
    return None
