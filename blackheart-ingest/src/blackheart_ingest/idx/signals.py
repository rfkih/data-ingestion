"""What each strategy said today — the record behind the ticket.

Part of the alert bus (phase 2). A ticket is the actionable subset of a night's thinking: the names that cleared every
check, fit the cash and were not already held. The strategy pages need the rest of it too - what signalled, what was
held back by the regime gate, what the rule wanted to sell - so ``idx.strategy_signal`` keeps one row per
(strategy, day, name, book) whether or not it became a ticket line.

Producers call ``record`` once with everything they saw. It writes the rows, then puts a single summary on the bus
(``kind='signal'``), deduped per strategy and day so a re-run updates rather than repeats.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import psycopg
import psycopg.types.json

from . import runlog
from .card import _rows

logger = logging.getLogger(__name__)
ACTIONS = ("buy", "sell", "hold", "hold_back", "watch")


def record(conn: psycopg.Connection, strategy: str, as_of: date, rows: list[dict[str, Any]], *, book: str = "",
           summary: str | None = None, user_id: str | None = None, alert: bool = True) -> dict[str, Any]:
    """Store what a strategy said on a day. ``rows``: {code, action, ref_price?, size_pct?, reason?, ticket_id?}.

    Re-running a night replaces that day's rows for the same (strategy, book) - a second run is a correction, not a
    second opinion. -> counts by action, plus the alert id when one was raised."""
    kept = [r for r in rows if r.get("code") and r.get("action") in ACTIONS]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.strategy_signal WHERE strategy = %s AND as_of = %s AND book = %s",
                    (strategy, as_of, book))
        cur.executemany("""INSERT INTO idx.strategy_signal (strategy, as_of, code, action, ref_price, size_pct, reason, book, ticket_id)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        [(strategy, as_of, r["code"].upper(), r["action"], r.get("ref_price"), r.get("size_pct"),
                          psycopg.types.json.Jsonb(r.get("reason") or {}), book, r.get("ticket_id")) for r in kept])
    conn.commit()
    by_action: dict[str, int] = {}
    for r in kept:
        by_action[r["action"]] = by_action.get(r["action"], 0) + 1
    out: dict[str, Any] = {"strategy": strategy, "as_of": str(as_of), "book": book or None, "rows": len(kept),
                           "by_action": by_action, "alert": None}
    if alert and kept:
        text = summary or _summarise(by_action, kept)
        out["alert"] = runlog.alert(
            conn, "info", f"signal:{strategy}", text, kind="signal", strategy=strategy, book=book or None,
            user_id=user_id, payload={"as_of": str(as_of), "by_action": by_action,
                                      "codes": {a: [r["code"] for r in kept if r["action"] == a][:12] for a in by_action}},
            dedupe_key=f"signal:{strategy}:{as_of}:{book}")
    return out


def _summarise(by_action: dict[str, int], rows: list[dict[str, Any]]) -> str:
    parts = [f"{n} to {a.replace('_', ' ')}" for a, n in sorted(by_action.items())]
    names = ", ".join(r["code"] for r in rows[:6]) + ("…" if len(rows) > 6 else "")
    return f"{'; '.join(parts)} — {names}"


SIGNAL_COLS = ["strategy", "as_of", "code", "action", "ref_price", "size_pct", "reason", "book", "ticket_id", "created_at"]


def latest(conn: psycopg.Connection, strategy: str, *, limit: int = 60, as_of: date | None = None) -> list[dict[str, Any]]:
    """The most recent signals of one strategy (or those of one day)."""
    if as_of is not None:
        return _rows(conn, f"SELECT {', '.join(SIGNAL_COLS)} FROM idx.strategy_signal WHERE strategy = %s AND as_of = %s "
                           f"ORDER BY action, code LIMIT %s", (strategy, as_of, limit), SIGNAL_COLS)
    return _rows(conn, f"SELECT {', '.join(SIGNAL_COLS)} FROM idx.strategy_signal WHERE strategy = %s "
                       f"ORDER BY as_of DESC, action, code LIMIT %s", (strategy, limit), SIGNAL_COLS)
