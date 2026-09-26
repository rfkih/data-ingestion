"""Which alerts deserve a person's attention - the one rule the phone push, the web panel and the stream all read.

Operator, 2026-09-26: notify only for STOCK ACTIONS or SYSTEM ERRORS THAT NEED AN ACTION; nothing else. The bus
(``idx.alert``) still records everything - a diary row is useful in ``/idx/alerts`` and in a post-mortem - but only an
``actionable`` row reaches the web panel, and only a ``push_now`` row buzzes a phone.

Actionable:
  * stock actions: tickets and execution reads, risk breaches, price levels hit, order intents, gap-fade / combo trade
    problems, a held name at ARA, a warning on a held name (drawdown, disclosure, a report that breaks the book rule), a
    take-profit hit;
  * system errors a person must fix: the feed down or its session token missing/expiring, and a job that FAILED
    (critical). A failed job is usually retried by the scheduler (the daily chain every 15 minutes to 20:00), so it is
    shown in the web at once but pushed only by the evening digest if it is still open then (``push_now`` = False).
Not actionable: every info row (signals, ML runs, the ARA watch list, regime ON, entry gate...), a regime change (the
trend gate acts on its own), research-data warnings (ML/score/macro/crosscheck/dividends/broker/field drift), a missing
bar that is still being retried, feed coverage, and "no gap-fade scan" (the feed-down alert already says why).
"""
from __future__ import annotations

from typing import Any

STOCK_JOBS = ("ticket", "levels", "risk", "intents", "gapfade", "combo", "book", "exec")
STOCK_KINDS = ("ticket", "exec", "risk")
NOT_ACTION_PREFIXES = ("regime on", "regime off", "entry gate", "no gap-fade scan")
NOT_ACTION_WORDS = ("were swept at today's open",)                     # the runner already sold them: a report
FEED_ACTION_WORDS = ("down", "token", "expired", "expires", "missing")
# a disclosure on a held name: only an actual trading FREEZE is an action (operator 2026-09-24: a UMA flag or an exchange
# query is not a reason to sell); the book monitor tags them "[<kind>]" in the message
DISCLOSURE_ACTION = ("[suspension]",)
DISCLOSURE_TAGS = ("[exchange_query]", "[legal]", "[auditor]", "[control_change]", "[affiliated_tx]", "[uma]")


def _prefix(job: str | None) -> str:
    return (job or "").split(":", 1)[0].strip().lower()


def book_of(row: dict[str, Any]) -> str | None:
    """The book an alert is about: the typed field, else the ``<prefix>:<book>`` job convention of the stock jobs."""
    if row.get("book"):
        return str(row["book"])
    job = row.get("job") or ""
    if ":" in job and _prefix(job) in STOCK_JOBS:
        return job.split(":", 1)[1].strip() or None
    return None


def paper_book(book: str | None) -> bool:
    """A paper or test book fills itself - nothing about it needs a person (same test as ticket.is_live)."""
    b = (book or "").lower()
    return bool(b) and (b.startswith("paper") or b.startswith("test"))


def actionable(row: dict[str, Any]) -> bool:
    """Pure: does this alert row ask a person to do something? (shown in the web panel)"""
    sev = (row.get("severity") or "").lower()
    kind = (row.get("kind") or "").lower()
    job = _prefix(row.get("job"))
    msg = (row.get("message") or "").strip().lower()
    if paper_book(book_of(row)):
        return False
    if any(msg.startswith(p) for p in NOT_ACTION_PREFIXES) or any(w in msg for w in NOT_ACTION_WORDS):
        return False
    if job == "book" and any(t in msg for t in DISCLOSURE_TAGS + DISCLOSURE_ACTION):
        return any(t in msg for t in DISCLOSURE_ACTION)
    if kind == "exec":
        return True
    if job == "ticket" and msg.startswith("take profit"):
        return True
    if sev not in ("warning", "critical"):
        return False
    if kind in STOCK_KINDS or job in STOCK_JOBS:
        return True
    if kind == "ara":
        return (row.get("strategy") or "") == "ara_sell"            # a held name at ARA; a failed watch run is not
    if job == "feed" or kind == "feed":
        return sev == "critical" or any(w in msg for w in FEED_ACTION_WORDS)
    return sev == "critical"                                       # a job that failed (retried; see push_now)


def deferred(row: dict[str, Any]) -> bool:
    """A failed background job: shown now, pushed only if still open at the evening digest."""
    job, kind = _prefix(row.get("job")), (row.get("kind") or "").lower()
    return (actionable(row) and (row.get("severity") or "").lower() == "critical"
            and job not in STOCK_JOBS and kind not in STOCK_KINDS and job != "feed" and kind != "feed")


def push_now(row: dict[str, Any]) -> bool:
    """Pure: should this alert buzz a phone the moment it is raised? Execution reads never do (true for seconds)."""
    if (row.get("kind") or "").lower() == "exec":
        return False
    return actionable(row) and not deferred(row)


def tag(row: dict[str, Any]) -> dict[str, Any]:
    """The row with ``actionable`` set - what the web reads."""
    row["actionable"] = actionable(row)
    return row
