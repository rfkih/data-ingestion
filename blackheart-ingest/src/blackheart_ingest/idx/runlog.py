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
import psycopg.types.json

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


KINDS = ("signal", "ticket", "exec", "regime", "ara", "risk", "feed", "ops")


def alert(conn: psycopg.Connection, severity: str, job: str | None, message: str, *, kind: str | None = None,
          strategy: str | None = None, code: str | None = None, book: str | None = None, user_id: str | None = None,
          payload: dict[str, Any] | None = None, dedupe_key: str | None = None,
          valid_until: datetime | None = None, notify_channels: bool = True) -> int:
    """Write one row on the bus and let the consumers have it. -> the alert id.

    A producer never picks a channel: the phone push, Telegram and the browser stream all read idx.alert. The typed
    fields are what lets them route and render without parsing the message - and every one of them is optional, so the
    free-text callers that predate the bus keep working exactly as they did.

    ``dedupe_key`` is the producer's name for "this same thing" (``exec:41:BBCA``): while an alert with that key is
    still open it is UPDATED in place rather than duplicated, which is what makes a five-second execution read safe to
    emit repeatedly. ``valid_until`` says when the row stops being true, so a screen can drop it without being told."""
    cols = {"severity": severity, "job": job, "message": message, "kind": kind, "strategy": strategy, "code": code,
            "book": book, "user_id": user_id, "valid_until": valid_until,
            "payload": psycopg.types.json.Jsonb(payload) if payload is not None else None, "dedupe_key": dedupe_key}
    names = list(cols)
    with conn.cursor() as cur:
        if dedupe_key:
            cur.execute("""INSERT INTO idx.alert (severity, job, message, kind, strategy, code, book, user_id, valid_until, payload, dedupe_key)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL AND acknowledged_at IS NULL
                           DO UPDATE SET severity = EXCLUDED.severity, job = EXCLUDED.job, message = EXCLUDED.message,
                               kind = EXCLUDED.kind, strategy = EXCLUDED.strategy, code = EXCLUDED.code,
                               book = EXCLUDED.book, user_id = EXCLUDED.user_id, valid_until = EXCLUDED.valid_until,
                               payload = EXCLUDED.payload, ts = now()
                           RETURNING id""", tuple(cols[n] for n in names))
        else:
            cur.execute(f"""INSERT INTO idx.alert ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))})
                            RETURNING id""", tuple(cols[n] for n in names))
        row = cur.fetchone()
        alert_id = int(next(iter(row.values())) if isinstance(row, dict) else row[0])
    conn.commit()
    level = {"critical": logging.CRITICAL, "warning": logging.WARNING}.get(severity, logging.INFO)
    logger.log(level, "idx alert [%s] %s: %s", severity, job, message)      # an info row is a diary line, not a warning
    if notify_channels:
        try:                                                               # warning/critical also go out (Telegram), best effort
            from . import notify
            notify.on_alert(severity, job, message, kind=kind, strategy=strategy, book=book, user_id=user_id)
        except Exception:                                                  # a notification must never fail the job
            logger.exception("idx alert: notify failed")
    return alert_id


def alert_once(conn: psycopg.Connection, severity: str, job: str | None, message: str, **kw: Any) -> bool:
    """``alert`` unless the same job+message is already open (unacknowledged). Returns whether it raised one - a caller
    that nags on a repeating schedule uses the False to send its own reminder without filling the alert table."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM idx.alert WHERE job = %s AND message = %s AND acknowledged_at IS NULL", (job, message))
        if cur.fetchone():
            return False
    alert(conn, severity, job, message, **kw)
    return True


def resolve(conn: psycopg.Connection, job: str, like: str | None = None) -> int:
    """Acknowledge the open alerts of ``job`` (optionally only those whose message matches the SQL ``like``) because
    the condition that raised them has cleared. Without this an alert lives until a human clicks it, so the desk drifts
    into a screen nobody reads - on 2026-09-24 it held 38 open alerts of which 29 were two incidents, repeated once per
    retry. Every nagging check should resolve what it raised. Returns how many rows were closed."""
    sql = "UPDATE idx.alert SET acknowledged_at = now() WHERE acknowledged_at IS NULL AND job = %s"
    params: list[Any] = [job]
    if like is not None:
        sql += " AND message LIKE %s"
        params.append(like)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        n = cur.rowcount
    conn.commit()
    if n:
        logger.info("idx alert: resolved %d open %s alert(s)", n, job)
    return n


def sweep_info(conn: psycopg.Connection, days: int = 3) -> int:
    """Acknowledge informational alerts older than ``days``. An 'info' row is a diary entry, not a fault - the ARA watch
    writes two every evening - and left open they bury the warnings that actually need somebody. Warnings and criticals
    are never swept: those close when their condition clears, or a person closes them."""
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.alert SET acknowledged_at = now() WHERE acknowledged_at IS NULL AND severity = 'info' "
                    "AND ts < now() - make_interval(days => %s)", (days,))
        n = cur.rowcount
    conn.commit()
    if n:
        logger.info("idx alert: swept %d info alert(s) older than %d days", n, days)
    return n


ALERT_COLS = ["id", "ts", "severity", "job", "message", "kind", "strategy", "code", "book", "user_id", "payload",
              "dedupe_key", "valid_until", "acknowledged_at"]

# A person sees the desk's own rows plus anything about their books or addressed to them - never another account's.
# The older ``book:X`` / ``ticket:X`` job convention is read too, so rows that predate the typed columns scope the
# same way. Done in SQL so LIMIT counts the rows the person may see, not the rows that exist (review 2026-09-24).
SCOPE_SQL = ("(user_id IS NULL OR user_id = %s) AND ("
             "COALESCE(book, CASE WHEN split_part(job, ':', 1) IN ('book', 'ticket') THEN split_part(job, ':', 2) END) IS NULL"
             " OR COALESCE(book, split_part(job, ':', 2)) = ANY(%s))")


def open_alerts(conn: psycopg.Connection, limit: int = 50, *, kind: str | None = None, strategy: str | None = None,
                code: str | None = None, since: int | None = None, include_expired: bool = False,
                user_id: str | None = None, books: list[str] | None = None) -> list[dict[str, Any]]:
    """Open (unacknowledged) alerts, newest first. An expired row (valid_until in the past) is left out unless asked
    for: an execution read that was true fifteen seconds ago is not news, it is clutter.

    ``since`` is an alert id - what a page asks for after a stream gap: rows newer than it by id, AND rows whose ``ts``
    is newer than that row's. A dedupe key updates a row in place and keeps its id, so ``id > since`` alone would miss
    an execution read that changed (review 2026-09-24). ``user_id`` scopes to a person, with ``books`` = their book
    ids; None is a service that sees everything."""
    where = ["acknowledged_at IS NULL"]
    params: list[Any] = []
    for col, val in (("kind", kind), ("strategy", strategy), ("code", code)):
        if val:
            where.append(f"{col} = %s")
            params.append(val)
    if since is not None:
        where.append("(id > %s OR ts > (SELECT a2.ts FROM idx.alert a2 WHERE a2.id = %s))")
        params.extend([since, since])
    if not include_expired:
        where.append("(valid_until IS NULL OR valid_until > now())")
    if user_id is not None:
        where.append(SCOPE_SQL)
        params.extend([user_id, list(books or [])])
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(ALERT_COLS)} FROM idx.alert WHERE {' AND '.join(where)} "
                    f"ORDER BY ts DESC LIMIT %s", params)
        rows = cur.fetchall()
    return [r if isinstance(r, dict) else dict(zip(ALERT_COLS, r, strict=True)) for r in rows]


def acknowledge(conn: psycopg.Connection, alert_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.alert SET acknowledged_at = now() WHERE id = %s AND acknowledged_at IS NULL", (alert_id,))
        n = cur.rowcount
    conn.commit()
    return n == 1
