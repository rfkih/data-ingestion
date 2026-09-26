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
    ``book``, else the ops account. A *desk* message (neither given) that the ops account cannot receive falls back to
    every phone on the desk - see ``_desk_fallback``. A message about one book stays with that book's owner: it is
    somebody's position, not desk news, so an unreachable owner is logged and dropped, never fanned out.
    Returns whether it went out anywhere; never raises."""
    if not configured():
        logger.info("idx notify: no channel configured (%s or telegram); dropped: %s", push.SA_ENV, text[:120])
        return False
    from .alert_policy import paper_book
    if paper_book(book):                                                   # a paper/test book fills itself: nobody to act
        logger.info("idx notify: paper book %s, not pushed: %s", book, text[:80])
        return False
    sent = False
    if push.configured():
        desk = user_id is None and book is None
        target = user_id or owner_of(book) or ops_user_id()
        t, b = split_title(text, title)
        payload = data or {"route": "/m"}
        if target:
            r = push.broadcast(t, b, payload, sender=push_sender, user_id=target)
            if desk and r.get("devices") == 0 and not r.get("error"):       # that account has no phone (not a db hiccup)
                r = _desk_fallback(t, b, payload, push_sender, why=f"the ops account ({os.environ.get(OPS_ENV)}) has no phone registered")
            sent = sent or r.get("sent", 0) > 0
        elif desk:
            r = _desk_fallback(t, b, payload, push_sender, why=f"{OPS_ENV} names no account on this desk")
            sent = sent or r.get("sent", 0) > 0
        else:
            logger.info("idx notify: no account to push to (book=%s, %s unset); dropped: %s", book, OPS_ENV, text[:80])
    if telegram_configured():
        sent = _telegram(text, sender=sender) or sent
    return sent


def _desk_fallback(title: str, body: str, data: dict[str, Any], push_sender: push.Sender | None, *, why: str) -> dict[str, Any]:
    """Desk news (a dead feed, a failed job) with no reachable ops phone: send it to every phone on the desk instead.
    On 2026-09-24 the feed was down from 08:58 to 09:39 and raised twelve alerts; every push was dropped in silence
    because the one registered phone was signed in as a second account, so the desk found out by reading the table."""
    logger.warning("idx notify: desk push to every phone - %s: %s", why, title)
    return push.broadcast(title, body, data, sender=push_sender, user_id=None)


def on_alert(severity: str, job: str | None, message: str, *, sender: Sender | None = None, push_sender: push.Sender | None = None,
             kind: str | None = None, strategy: str | None = None, book: str | None = None, user_id: str | None = None) -> bool:
    """Called by ``runlog.alert``: push the alerts that need a human, drop the rest. The typed fields win when the bus
    supplies them (``book``, ``user_id``); otherwise the older ``book:X`` / ``ticket:X`` job convention is read as before.
    An execution read is never pushed - it is true for fifteen seconds, which is useless as a notification and would
    buzz a pocket every five seconds through the open - and the person's own mutes and quiet hours are honoured here,
    at the channel, never by dropping the row from the bus."""
    if not configured():
        return False
    from .alert_policy import push_now  # stock actions + system errors that need a person
    if not push_now({"severity": severity, "job": job, "message": message, "kind": kind, "strategy": strategy}):
        logger.info("idx notify: not actionable, not pushed: [%s] %s", severity, job)
        return False
    if book is None and job and job.split(":", 1)[0] in ("book", "ticket") and ":" in job:
        book = job.split(":", 1)[1]
    route = f"/m/book?book={book}" if book else "/m/more"
    if kind and strategy:
        route = f"/m/strategies/{strategy}"
    target = user_id or owner_of(book)
    if target and not _wanted(target, kind, strategy):
        logger.info("idx notify: %s muted %s/%s; not pushed", target, kind, strategy)
        return False
    data = {"route": route, "kind": kind or "alert", "severity": severity}
    if strategy:
        data["strategy"] = strategy
    return send(f"[{severity.upper()}] {job or 'idx'}\n{message}", data=data,
                sender=sender, push_sender=push_sender, book=book, user_id=user_id)


def _wanted(user_id: str, kind: str | None, strategy: str | None) -> bool:
    """The person's own preferences, read at the channel. Any failure delivers - a mute must never become a black hole."""
    try:
        from ..shared.db import get_connection
        from . import prefs
        with get_connection() as conn:
            return prefs.allows(conn, user_id, kind, strategy)
    except Exception:
        logger.exception("idx notify: preference check failed; delivering")
        return True


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
