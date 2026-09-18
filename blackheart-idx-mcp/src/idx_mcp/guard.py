"""Pure guardrails applied on the agent side before a call reaches the ingest API.

Phase 0 keeps them here (client-side); phase 1 of the agent-desk plan moves the same rules server-side, where the
agent cannot skip them. The rules are deliberately few and legible:

* **two-key** — the ``live`` book's tickets are issued by the operator in the Blackridge app. The agent may build a draft and may
  cancel a draft, never set ``issued`` (nor ``closed``: closing is the operator's confirmation that the broker work is done).
* **paper is free** — the ``paper`` book (and any ``test_*`` book) is the agent's to build, issue, fill and close.
* **fills are facts** — a fill on the live book records what the broker actually did; the operator enters it. The
  agent records fills on paper/test books only (the server refuses live fills from the agent as well).
"""
from __future__ import annotations

LIVE_BOOKS = frozenset({"live"})     # informational; is_live() below is the rule
TWO_KEY = ("two-key: tickets on the live book are issued and closed by the operator in the Blackridge app (/ticket). "
           "The agent may only leave it as 'draft' or set 'cancelled' on its own draft; ask the operator to issue.")
FILL_PROVENANCE = ("live fills are entered by the operator (the Blackridge app /book or /ticket, or `idx book fill`): the agent never records "
                   "a fill on the live book. Paper fills are the scheduler's (paper_fill at the next open) or yours.")


class GuardError(ValueError):
    pass


def is_live(book: str) -> bool:
    """Every book that is not a paper or test book is live (live, trend_live, ...)."""
    b = book.strip().lower()
    return not (b.startswith("paper") or b.startswith("test"))


def check_status_change(book: str, status: str, actor: str = "agent") -> None:
    """Raise unless ``actor`` may move a ticket on ``book`` to ``status``."""
    if actor == "operator" or not is_live(book):
        return
    if status in ("issued", "closed"):
        raise GuardError(TWO_KEY)


def check_fill(book: str) -> None:
    if is_live(book):
        raise GuardError(FILL_PROVENANCE)
