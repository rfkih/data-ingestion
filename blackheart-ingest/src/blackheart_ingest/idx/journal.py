"""Decision journal (``idx.decision``): one row per action on the desk - who (agent | operator | scheduler), what, on which
book/name/ticket, and why. Written by the API routes, the scheduler and the ticket module; read by the app and the
agent (``GET /idx/decision``). The journal is append-only: nothing here updates or deletes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import psycopg
import psycopg.types.json

ACTORS = ("agent", "operator", "scheduler")


def record(conn: psycopg.Connection, book: str | None, actor: str, action: str, *, code: str | None = None, ticket_id: int | None = None,
           line_id: int | None = None, rationale: str | None = None, refs: dict[str, Any] | None = None, commit: bool = True,
           user_id: str | None = None) -> int:
    """``user_id`` = whose journal this is; left out, a row on a book belongs to the book's owner."""
    if actor not in ACTORS:
        raise ValueError(f"actor must be one of {ACTORS}")
    with conn.cursor() as cur:
        if user_id is None and book:
            cur.execute("SELECT owner_id FROM idx.book WHERE book = %s", (book,))
            r = cur.fetchone()
            v = (r["owner_id"] if isinstance(r, dict) else r[0]) if r else None
            user_id = str(v) if v else None
        cur.execute("""INSERT INTO idx.decision (book, actor, action, code, ticket_id, line_id, rationale, refs, user_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (book, actor, action, code.upper() if code else None, ticket_id, line_id, rationale,
                     psycopg.types.json.Jsonb(_plain(refs or {})), user_id))
        row = cur.fetchone()
    if commit:
        conn.commit()
    return int(next(iter(row.values())) if isinstance(row, dict) else row[0])


def recent(conn: psycopg.Connection, book: str | None = None, code: str | None = None, limit: int = 50,
           action: str | None = None, user_id: str | None = None) -> list[dict[str, Any]]:
    """Newest first; ``user_id`` narrows to one account's journal (its rows and rows on its books)."""
    cols = ["id", "ts", "book", "actor", "action", "code", "ticket_id", "line_id", "rationale", "refs"]
    with conn.cursor() as cur:
        cur.execute(f"""SELECT {', '.join('d.' + c for c in cols)} FROM idx.decision d
                         WHERE (%s::text IS NULL OR d.book = %s) AND (%s::text IS NULL OR d.code = %s) AND (%s::text IS NULL OR d.action = %s)
                           AND (%s::uuid IS NULL OR d.user_id = %s::uuid OR d.book IN (SELECT book FROM idx.book WHERE owner_id = %s::uuid))
                         ORDER BY d.ts DESC, d.id DESC LIMIT %s""",
                    (book, book, code.upper() if code else None, code.upper() if code else None, action, action, user_id, user_id, user_id,
                     min(max(limit, 1), 500)))
        rows = cur.fetchall()
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in rows]


def _plain(v: Any) -> Any:
    """JSON-safe copy: Decimals to str, dates to ISO."""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, list | tuple | set):
        return [_plain(x) for x in v]
    if isinstance(v, date | datetime):
        return v.isoformat()
    if isinstance(v, int | float | str | bool) or v is None:
        return v
    return str(v)
