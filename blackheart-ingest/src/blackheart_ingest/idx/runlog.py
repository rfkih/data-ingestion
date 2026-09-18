"""``idx.ingest_run`` + ``idx.alert`` helpers — every job records itself here,
and every operator-visible problem is an alert row (the app renders them;
there is no Telegram/email)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    job: str
    run_key: str | None
    status: str = "ok"                 # ok | partial | failed | skipped
    rows_in: int = 0
    rows_out: int = 0
    rows_rejected_pit: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.warning("idx %s %s: %s", self.job, self.run_key, msg)


def start(conn: psycopg.Connection, job: str, run_key: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO idx.ingest_run (job, run_key, status) VALUES (%s, %s, 'running') RETURNING id",
            (job, run_key),
        )
        row = cur.fetchone()
    conn.commit()
    return int(row[0] if isinstance(row, tuple) else row["id"])


def finish(conn: psycopg.Connection, run_id: int, r: RunResult) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE idx.ingest_run
               SET finished_at = %s, status = %s, rows_in = %s, rows_out = %s,
                   rows_rejected_pit = %s, warnings = %s::jsonb, error = %s
             WHERE id = %s
            """,
            (datetime.now(UTC), r.status, r.rows_in, r.rows_out, r.rows_rejected_pit,
             json.dumps(r.warnings), r.error, run_id),
        )
    conn.commit()


def alert(conn: psycopg.Connection, severity: str, job: str | None, message: str) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO idx.alert (severity, job, message) VALUES (%s, %s, %s)", (severity, job, message))
    conn.commit()
    logger.log(logging.CRITICAL if severity == "critical" else logging.WARNING, "idx alert [%s] %s: %s", severity, job, message)
    try:                                                                   # warning/critical also go out (Telegram), best effort
        from . import notify
        notify.on_alert(severity, job, message)
    except Exception:                                                      # a notification must never fail the job
        logger.exception("idx alert: notify failed")


def open_alerts(conn: psycopg.Connection, limit: int = 50) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, ts, severity, job, message FROM idx.alert WHERE acknowledged_at IS NULL "
            "ORDER BY ts DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
    cols = ["id", "ts", "severity", "job", "message"]
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in rows]


def acknowledge(conn: psycopg.Connection, alert_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.alert SET acknowledged_at = now() WHERE id = %s AND acknowledged_at IS NULL", (alert_id,))
        n = cur.rowcount
    conn.commit()
    return n == 1
