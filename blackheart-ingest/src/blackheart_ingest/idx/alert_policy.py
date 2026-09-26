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
FEED_ACTION_WORDS = ("down", "token", "expired", "expires", "missing")


def _prefix(job: str | None) -> str:
    return (job or "").split(":", 1)[0].strip().lower()


def actionable(row: dict[str, Any]) -> bool:
    """Pure: does this alert row ask a person to do something? (shown in the web panel)"""
    sev = (row.get("severity") or "").lower()
    kind = (row.get("kind") or "").lower()
    job = _prefix(row.get("job"))
    msg = (row.get("message") or "").strip().lower()
    if any(msg.startswith(p) for p in NOT_ACTION_PREFIXES):
        return False
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
