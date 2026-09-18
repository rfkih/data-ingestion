"""Who is calling the desk API, and which desk is theirs.

Three kinds of caller reach ``/idx/*``:

* **a signed-in person** through the app's proxy: ``Authorization: Bearer <session JWT>`` (the token this service issued in
  ``accounts``). Everything they touch is scoped to their account - their books, tickets, journal, watchlist, phones. The
  actor is ``operator`` (a human) unless ``X-Idx-Actor`` says otherwise.
* **a service** holding the ingest token (``X-Ingest-Token``): the nightly agent, the scheduler over HTTP, the CLI. Unscoped
  by default (every book), or scoped to one account with ``X-Idx-User: <email>`` - what the agent sends (``IDX_AGENT_USER``)
  so it only ever works one person's desk.
* **nobody** (no token at all): fine for the shared research reads; a 401 on anything that is somebody's. When no ingest
  token is configured at all (tests, a bare dev box) a caller without credentials counts as an unscoped service, as
  ``require_token`` has always treated it.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

import psycopg
from fastapi import Header, HTTPException, Request

from ..shared.settings import get_settings
from . import accounts, journal

ACTORS = journal.ACTORS


@dataclass(frozen=True)
class Caller:
    actor: str                    # agent | operator | scheduler
    user_id: str | None           # the account this call is scoped to; None = every book (service on the box)
    email: str | None
    service: bool                 # holds the ingest token (or none is configured)

    @property
    def scoped(self) -> bool:
        return self.user_id is not None


def _service(request: Request) -> bool:
    expected = get_settings().auth_token.get_secret_value()
    if not expected:
        return True
    provided = request.headers.get("X-Ingest-Token", "")
    return secrets.compare_digest(provided.encode(), expected.encode())


def caller_of(request: Request, x_idx_actor: str | None = Header(default=None), x_idx_user: str | None = Header(default=None),
              authorization: str | None = Header(default=None)) -> Caller:
    actor = (x_idx_actor or "operator").strip().lower()
    if actor not in ACTORS:
        raise HTTPException(status_code=400, detail=f"X-Idx-Actor must be one of {ACTORS}")
    service = _service(request)
    bearer = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    if bearer:
        claims = accounts.read_token(bearer, accounts.secret())
        if not claims or not claims.get("userId"):
            raise HTTPException(status_code=401, detail="session expired or invalid; sign in again")
        return Caller(actor=actor, user_id=str(claims["userId"]), email=str(claims.get("sub") or "").lower() or None, service=service)
    if not service:
        raise HTTPException(status_code=401, detail="missing/invalid X-Ingest-Token")
    if x_idx_user:
        from ..shared.db import get_connection
        with get_connection() as conn:
            u = accounts.get_user(conn, x_idx_user.strip().lower())
        if not u:
            raise HTTPException(status_code=401, detail=f"X-Idx-User {x_idx_user!r} is not an account on this desk")
        return Caller(actor=actor, user_id=str(u["id"]), email=u["email"], service=True)
    return Caller(actor=actor, user_id=None, email=None, service=True)


def need_user(c: Caller, what: str = "this") -> str:
    """The account id a personal thing belongs to; 401 for an unscoped service caller."""
    if not c.scoped:
        raise HTTPException(status_code=401, detail=f"{what} needs a signed-in account (or X-Idx-User for a service caller)")
    return str(c.user_id)


def own_book(conn: psycopg.Connection, book: str, c: Caller) -> dict[str, Any]:
    """The book row when the caller may work it: their own, or any book for an unscoped service. 404 otherwise (a book that
    is not yours does not exist as far as you are concerned)."""
    from . import book as bk
    try:
        b = bk.get_book(conn, book)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    if c.scoped and (b.get("owner_id") is None or str(b["owner_id"]) != c.user_id):
        raise HTTPException(status_code=404, detail=f"no book {book!r}")
    return b


def own_ticket(conn: psycopg.Connection, ticket_id: int, c: Caller) -> dict[str, Any]:
    from . import ticket
    t = ticket.load(conn, ticket_id)
    if t is None:
        raise HTTPException(status_code=404, detail="no ticket")
    own_book(conn, t["book"], c)
    return t


def own_line(conn: psycopg.Connection, line_id: int, c: Caller) -> dict[str, Any]:
    from . import ticket
    ln = ticket.line_book(conn, line_id)
    if ln is None:
        raise HTTPException(status_code=404, detail=f"no ticket line {line_id}")
    own_book(conn, ln["book"], c)
    return ln


def service_only(c: Caller, what: str) -> None:
    """Shared research is written from the box (CLI, the nightly agent), never from an account in the app."""
    if c.scoped and c.actor == "operator":
        raise HTTPException(status_code=403, detail=f"{what} is run from the desk's own tools, not from an account")
