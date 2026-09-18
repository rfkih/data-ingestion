"""Outbound notifications for the desk, fanned out to every configured channel:

* the Blackridge Android app (push through Firebase, ``push.py``; ``IDX_FCM_SERVICE_ACCOUNT`` on the server) - the operator's
  chosen channel;
* Telegram (``IDX_TELEGRAM_TOKEN`` / ``IDX_TELEGRAM_CHAT``) - kept as an optional second channel, off unless configured.

Best-effort by design - a notification that cannot be sent is logged, never raised into the job that produced it; with
nothing configured every call is a no-op that reports ``sent=False``.

What goes out: every alert of severity warning/critical the moment it is raised (``runlog.alert`` calls ``on_alert``), a
live ticket when it is drafted (``format_ticket``), and whatever the operator or the agent sends through ``POST /idx/notify``.
Plain text only. A message's first line is the push title; ``data`` (a route to open, a ticket id) rides along so a tap on
the phone lands on the right screen.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from . import push

logger = logging.getLogger(__name__)
TOKEN_ENV, CHAT_ENV = "IDX_TELEGRAM_TOKEN", "IDX_TELEGRAM_CHAT"
OPS_ENV = "IDX_OPS_NOTIFY_EMAIL"         # the account whose phones get the desk's own alerts (ingest failures, no bar); unset = nobody
PUSH_SEVERITIES = ("warning", "critical")
MAX_LEN = 4096
Sender = Callable[[str, dict[str, Any]], dict[str, Any]]


def telegram_configured() -> bool:
    return bool(os.environ.get(TOKEN_ENV) and os.environ.get(CHAT_ENV))


def channels() -> list[str]:
    return [c for c, on in (("app", push.configured()), ("telegram", telegram_configured())) if on]


def configured() -> bool:
    """Whether at least one channel can carry a message."""
    return bool(channels())


def _post(url: str, payload: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _telegram(text: str, *, sender: Sender | None = None) -> bool:
    text = text if len(text) <= MAX_LEN else text[: MAX_LEN - 2] + " …"
    url = f"https://api.telegram.org/bot{os.environ[TOKEN_ENV]}/sendMessage"
    payload = {"chat_id": os.environ[CHAT_ENV], "text": text, "disable_web_page_preview": True}
    try:
        res = (sender or _post)(url, payload)
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.warning("idx notify: telegram send failed: %s: %s", type(e).__name__, e)
        return False
    ok = bool(res.get("ok", True))
    if not ok:
        logger.warning("idx notify: telegram refused: %s", res)
    return ok


def split_title(text: str, title: str | None = None) -> tuple[str, str]:
    """Pure: (title, body) for the phone - the first line is the title unless one is given; a one-liner is its own body."""
    text = (text or "").strip()
    if title:
        return title.strip()[:120], text
    head, _, rest = text.partition("\n")
    return head[:120], (rest.strip() or head)


def ops_user_id() -> str | None:
    """The account behind ``IDX_OPS_NOTIFY_EMAIL``, if it exists."""
    email = (os.environ.get(OPS_ENV) or "").strip().lower()
    if not email:
        return None
    try:
        from ..shared.db import get_connection
        from . import accounts
        with get_connection() as conn:
            u = accounts.get_user(conn, email)
        return str(u["id"]) if u else None
    except Exception:                                                   # no database: no ops phone
        return None


def owner_of(book: str | None) -> str | None:
    if not book:
        return None
    try:
        from ..shared.db import get_connection
        from . import book as bk
        with get_connection() as conn:
            return bk.owner_of(conn, book)
    except Exception:
        return None


def send(text: str, *, title: str | None = None, data: dict[str, Any] | None = None, sender: Sender | None = None,
         push_sender: push.Sender | None = None, user_id: str | None = None, book: str | None = None) -> bool:
    """Send one message on every configured channel. The phone channel needs a person: ``user_id``, else the owner of
    ``book``, else the ops account; with none of these the push is dropped (Telegram, a single operator channel, still
    goes). Returns whether it went out anywhere; never raises."""
    if not configured():
        logger.info("idx notify: no channel configured (%s or telegram); dropped: %s", push.SA_ENV, text[:120])
        return False
    sent = False
    if push.configured():
        target = user_id or owner_of(book) or ops_user_id()
        if target:
            t, b = split_title(text, title)
            r = push.broadcast(t, b, data or {"route": "/m"}, sender=push_sender, user_id=target)
            sent = sent or r.get("sent", 0) > 0
        else:
            logger.info("idx notify: no account to push to (book=%s, %s unset); dropped: %s", book, OPS_ENV, text[:80])
    if telegram_configured():
        sent = _telegram(text, sender=sender) or sent
    return sent


def on_alert(severity: str, job: str | None, message: str, *, sender: Sender | None = None, push_sender: push.Sender | None = None) -> bool:
    """Called by ``runlog.alert``: push the alerts that need a human, drop the rest. A ``book:X`` / ``ticket:X`` alert goes
    to X's owner (and opens that book); a desk alert goes to the ops account."""
    if severity not in PUSH_SEVERITIES or not configured():
        return False
    book = job.split(":", 1)[1] if job and job.split(":", 1)[0] in ("book", "ticket") and ":" in job else None
    route = f"/m/book?book={book}" if book else "/m/more"
    return send(f"[{severity.upper()}] {job or 'idx'}\n{message}", data={"route": route, "kind": "alert", "severity": severity, "job": job or ""},
                sender=sender, push_sender=push_sender, book=book)


def ticket_data(t: dict[str, Any]) -> dict[str, Any]:
    """The push payload for a ticket: tapping it opens that book's ticket screen in the app."""
    return {"route": f"/m/ticket?book={t['book']}", "kind": "ticket", "book": t["book"], "ticket": t["id"]}


def format_ticket(t: dict[str, Any], checks: dict[str, Any] | None = None) -> str:
    """Pure: a ticket as a plain-text message the operator can work from at the broker."""
    head = f"Ticket #{t['id']} {t['book']} {t['mode']} ({t['status']}) - prices as of {t['ticket_date']}"
    lines = [head]
    if checks is not None:
        lines.append("guardrails: OK" if checks.get("ok") else "guardrails: " + "; ".join(
            f"{x['kind']}" + (f" {x['code']}" if x.get("code") else "") for x in checks.get("breaches") or []))
    for ln in t.get("lines") or []:
        flags = " ".join(ln.get("flags") or [])
        lines.append(f"{ln['side'].upper():4} {ln['code']:<5} {int(float(ln['lots'])):>5} lot @ {float(ln['limit_price']):,.0f}"
                     + (f"  [{flags}]" if flags else ""))
    cash_after = (t.get("params") or {}).get("cash_after")
    if cash_after is not None:
        lines.append(f"cash after (est.) Rp {float(cash_after):,.0f}")
    return "\n".join(lines)
