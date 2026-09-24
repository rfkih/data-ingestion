"""Per-person alert preferences: what a phone is allowed to interrupt someone with.

Part of the alert bus (phase 2). The bus writes every row; the consumers decide what leaves the building, and this is
the one place that answers "should this person hear about this". A mute is a row - no row means everything is
delivered, so a new account starts fully subscribed and nothing is hidden by a default nobody chose.

Two granularities, both optional and combinable: a `kind` ('exec', 'ara', …) and a `strategy` (a registry key). The
empty string is the wildcard, so ('', '') mutes everything and ('exec', '') mutes only the execution reads. Quiet hours
are stored on the same row and read in WIB, the desk's own clock; a window that crosses midnight (22:00 -> 07:00) is
handled as the wrap it looks like.

The stream deliberately ignores all of this. A browser tab that is open is somebody looking at the screen on purpose;
preferences exist to stop a phone buzzing at midnight, not to hide rows from a page they asked for.
"""
from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from .card import _rows

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
COLS = ["user_id", "kind", "strategy", "muted", "quiet_from", "quiet_to", "updated_at"]


def list_prefs(conn: psycopg.Connection, user_id: str) -> list[dict[str, Any]]:
    return _rows(conn, f"SELECT {', '.join(COLS)} FROM idx.alert_pref WHERE user_id = %s ORDER BY kind, strategy",
                 (user_id,), COLS)


def set_pref(conn: psycopg.Connection, user_id: str, *, kind: str = "", strategy: str = "", muted: bool = True,
             quiet_from: time | None = None, quiet_to: time | None = None) -> dict[str, Any]:
    """Mute (or unmute) one kind/strategy for one person. Unmuting with no quiet hours deletes the row: the absence of
    a preference is the default, and a table of `muted = false` rows would only be a way to get that default wrong."""
    with conn.cursor() as cur:
        if not muted and quiet_from is None and quiet_to is None:
            cur.execute("DELETE FROM idx.alert_pref WHERE user_id = %s AND kind = %s AND strategy = %s",
                        (user_id, kind, strategy))
        else:
            cur.execute("""INSERT INTO idx.alert_pref (user_id, kind, strategy, muted, quiet_from, quiet_to)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON CONFLICT (user_id, kind, strategy) DO UPDATE SET muted = EXCLUDED.muted,
                               quiet_from = EXCLUDED.quiet_from, quiet_to = EXCLUDED.quiet_to, updated_at = now()""",
                        (user_id, kind, strategy, muted, quiet_from, quiet_to))
    conn.commit()
    return {"user_id": user_id, "kind": kind, "strategy": strategy, "muted": muted,
            "quiet_from": quiet_from.isoformat() if quiet_from else None,
            "quiet_to": quiet_to.isoformat() if quiet_to else None}


def in_quiet_hours(row: dict[str, Any], now_wib: time) -> bool:
    """True inside [quiet_from, quiet_to) in WIB, including the usual window that wraps past midnight."""
    a, b = row.get("quiet_from"), row.get("quiet_to")
    if a is None or b is None:
        return False
    return (a <= now_wib < b) if a <= b else (now_wib >= a or now_wib < b)


def matches(row: dict[str, Any], kind: str | None, strategy: str | None) -> bool:
    """A preference row applies when each of its non-empty fields matches ('' is the wildcard)."""
    return ((not row["kind"] or row["kind"] == (kind or "")) and
            (not row["strategy"] or row["strategy"] == (strategy or "")))


def allows(conn: psycopg.Connection, user_id: str | None, kind: str | None, strategy: str | None = None,
           now: datetime | None = None) -> bool:
    """Should this person's phone be interrupted by this row? No preferences -> yes, always."""
    if not user_id:
        return True                                          # desk news has no owner to have muted it
    try:
        rows = list_prefs(conn, user_id)
    except Exception:                                        # a preference lookup must never swallow an alert
        logger.exception("idx prefs: lookup failed for %s; delivering", user_id)
        return True
    if not rows:
        return True
    hhmm = (now or datetime.now(WIB)).astimezone(WIB).time()
    for r in rows:
        if not matches(r, kind, strategy):
            continue
        if r["muted"] and r["quiet_from"] is None:
            return False                                     # a plain mute
        if in_quiet_hours(r, hhmm):
            return False
    return True
