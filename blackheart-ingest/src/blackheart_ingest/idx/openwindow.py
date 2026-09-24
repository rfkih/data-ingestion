"""The open window: the half hour when the live tape is worth streaming, and the only time it is.

Phase 3 of the strategies + alert-stream plan, and the operator's own boundary: *no live feed for tomorrow's buy list;
the live feed appears at the open, as a placement read for the names that already have a ticket.* So this runs from
08:55 to 09:30 WIB and does three things:

  08:55   subscribe today's open ticket names to the tick feed (``reason='ticket'``), on top of the standing liquid set
  09:00+  every few seconds, re-read the order book for each open line (``execwatch.read``) and put a ``kind='exec'``
          row on the bus when the placement read changes
  09:30   unsubscribe those names again, so the feed goes back to what it carries all day

What it does not do: decide anything. The ticket already carries the side, the lots and the limit; the only question
here is *where to put the order right now*, which study #99 answered - a buy that waits for the book to lean to the bid
filled 6 to 11 basis points better than one that took the offer immediately.

Three properties worth keeping:

* **One writer.** A Postgres advisory lock means two scheduler processes cannot both stream the window.
* **Quiet by default.** A row goes on the bus only when a line's read *changes* (and at most every ``MIN_REPEAT_S``),
  deduped on ``exec:{ticket}:{line}`` so a repeat updates in place. ``valid_until`` is a few seconds out: a placement
  read is true for about as long as the book holds still, and a screen drops it rather than showing a stale one.
* **It stops on its own.** A filled line, a halted book, a closed ticket, a dead feed or 09:30 all end it.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from . import book as bk
from . import execwatch, runlog, ticket
from .card import _rows
from .feed import store as fs

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")

SUBSCRIBE_AT = (8, 55)          # WIB: before the auction, so the book is already streaming when it matches
WINDOW_OPEN = (9, 0)
WINDOW_CLOSE = (9, 30)
POLL_S = 5.0                    # one read per line per this many seconds (study #99 works on the book, not on ticks)
MIN_REPEAT_S = 30.0             # the same unchanged read is not re-sent more often than this
VALID_S = 20                    # how long a placement read stays true on a screen
STALE_FEED_S = 120              # a feed quieter than this is not a live book; say so once and stop reading
LOCK_KEY = "idx-open-window"


def _hhmm(now: datetime) -> tuple[int, int]:
    n = now.astimezone(WIB)
    return (n.hour, n.minute)


def in_window(now: datetime | None = None) -> bool:
    """True inside 09:00-09:30 WIB on a weekday."""
    n = (now or datetime.now(WIB)).astimezone(WIB)
    return n.weekday() < 5 and WINDOW_OPEN <= _hhmm(n) < WINDOW_CLOSE


TICKET_LOOKBACK_DAYS = 7        # an issued ticket older than this with lines still open is stuck, not live


def open_tickets(conn: psycopg.Connection, d: date) -> list[dict[str, Any]]:
    """Issued tickets with at least one line still to work, for books that are not halted.

    Not "today's" tickets: a trend ticket is drafted after the close and carries the bar's date - yesterday's - because
    it is filled at the next open. Filtering on ticket_date = today found none of them (caught in review 2026-09-24).
    A gap-fade ticket is dated today; both belong in the window. The lookback only keeps a forgotten ticket from
    weeks ago out of the loop."""
    rows = _rows(conn, """
        SELECT t.id, t.book, t.mode FROM idx.ticket t
         WHERE t.status = 'issued' AND t.ticket_date BETWEEN %s AND %s
         ORDER BY t.id""", (d - timedelta(days=TICKET_LOOKBACK_DAYS), d), ["id", "book", "mode"])
    out = []
    for r in rows:
        try:
            b = bk.get_book(conn, r["book"])
        except Exception:
            continue
        if bk.is_halted(b):
            continue
        t = ticket.load(conn, r["id"])
        if t and any(ln["status"] in ("open", "partial") for ln in t["lines"]):
            out.append({"id": t["id"], "book": t["book"], "mode": r["mode"],
                        "codes": sorted({ln["code"] for ln in t["lines"] if ln["status"] in ("open", "partial")})})
    return out


def ensure_subscribed(conn: psycopg.Connection, codes: list[str]) -> int:
    """Put any ticket name not yet on the feed onto it. Called every pass, because a live ticket is issued by a person
    (two-key) and may only exist after 08:55 - without this its names would read "no book yet" all window long."""
    if not codes:
        return 0
    have = {r["code"] for r in _rows(conn, "SELECT code FROM idx.feed_symbol WHERE enabled AND code = ANY(%s)",
                                     (codes,), ["code"])}
    missing = sorted(set(codes) - have)
    if missing:
        fs.set_symbols(conn, missing, reason="ticket")
        logger.info("idx open window: subscribed %d late name(s): %s", len(missing), " ".join(missing))
    return len(missing)


def subscribe(conn: psycopg.Connection, d: date | None = None) -> dict[str, Any]:
    """Put today's ticket names on the tick feed. Additive: the standing liquid subscription is untouched."""
    d = d or datetime.now(WIB).date()
    tickets = open_tickets(conn, d)
    codes = sorted({c for t in tickets for c in t["codes"]})
    if codes:
        fs.set_symbols(conn, codes, reason="ticket")
    logger.info("idx open window: subscribed %d name(s) from %d ticket(s) for %s", len(codes), len(tickets), d)
    return {"date": str(d), "tickets": [t["id"] for t in tickets], "codes": codes}


def unsubscribe(conn: psycopg.Connection) -> int:
    """Take the ticket names off the feed again. Only the rows this loop added (reason='ticket') are touched, so a
    name that is also in the standing liquid set, or one the operator pinned by hand, keeps streaming."""
    codes = [r["code"] for r in _rows(conn, "SELECT code FROM idx.feed_symbol WHERE reason = 'ticket' AND enabled",
                                      (), ["code"])]
    n = fs.disable_symbols(conn, codes) if codes else 0
    if n:
        logger.info("idx open window: unsubscribed %d ticket name(s)", n)
    return n


@contextmanager
def _lock(conn: psycopg.Connection):
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS got", (LOCK_KEY,))
        row = cur.fetchone()
        got = bool(next(iter(row.values())) if isinstance(row, dict) else row[0])
    conn.commit()
    try:
        yield got
    finally:
        if got:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (LOCK_KEY,))
            conn.commit()


WHERE_WORDS = {"rest_bid": ("rest at the bid", "bid"), "take_offer": ("take the offer", "offer"),
               "rest_offer": ("rest at the offer", "offer"), "hit_bid": ("hit the bid", "bid"),
               "balanced": ("the book is balanced", None), "unknown": ("no book yet", None)}


def line_message(ln: dict[str, Any]) -> str:
    """What a person reads. Factual, never a call to trade: the ticket already decided that.

    The price shown is the side of the book the read points at - resting at the bid quotes the bid, taking the offer
    quotes the offer. Quoting the wrong one is worse than quoting none: it is a number somebody might type in."""
    place, which = WHERE_WORDS.get(ln.get("place") or "unknown", (ln.get("place") or "", None))
    px = ln.get(which) if which else None
    at = f" Rp {px:,.0f}" if px else ""
    return f"{ln['code']} {ln['side']}: {place}{at}"


def _emit(conn: psycopg.Connection, t: dict[str, Any], ln: dict[str, Any], strategy: str | None) -> int:
    payload = {k: ln.get(k) for k in ("code", "side", "lots", "limit", "bid", "offer", "last", "spread_bps",
                                      "obi1", "micro_ticks", "place", "act", "note")}
    payload["ticket"] = t["ticket"]
    payload["line"] = ln["id"]
    return runlog.alert(conn, "info", f"exec:{t['book']}", line_message(ln), kind="exec", strategy=strategy,
                        code=ln["code"], book=t["book"], payload=payload,
                        dedupe_key=f"exec:{t['ticket']}:{ln['id']}",
                        valid_until=datetime.now(UTC) + timedelta(seconds=VALID_S))


def _strategy_of(mode: str | None) -> str | None:
    """The registry key a ticket belongs to, so the strategy page can show its own window."""
    return {"trend": "trend_small", "gapfade": "gapfade", "rebalance": "value_strict",
            "annual": "value_strict"}.get(mode or "")


def tick_once(conn: psycopg.Connection, state: dict[int, dict[str, Any]], d: date | None = None,
              now: datetime | None = None) -> dict[str, Any]:
    """One pass over every open line of every open ticket. ``state`` carries the last read per line between passes,
    so an unchanged book stays off the bus. -> what happened, for the log."""
    now = now or datetime.now(UTC)
    d = d or now.astimezone(WIB).date()
    out = {"tickets": 0, "lines": 0, "emitted": 0, "stale_feed": False, "subscribed": 0}
    tickets = open_tickets(conn, d)
    try:
        out["subscribed"] = ensure_subscribed(conn, sorted({c for t in tickets for c in t["codes"]}))
    except Exception:
        logger.exception("idx open window: late subscribe failed; reading what the feed has")
    for t_meta in tickets:
        try:
            r = execwatch.read(conn, t_meta["id"], d)
        except Exception:
            logger.exception("idx open window: read failed for ticket %s", t_meta["id"])
            continue
        out["tickets"] += 1
        if not r["feed"]["live"] and (r["feed"]["stale_s"] is None or r["feed"]["stale_s"] > STALE_FEED_S):
            out["stale_feed"] = True
            continue                                                  # a quiet feed says nothing about the book
        strategy = _strategy_of(t_meta.get("mode"))
        for ln in r["lines"]:
            out["lines"] += 1
            prev = state.get(ln["id"])
            changed = prev is None or prev["place"] != ln["place"]
            due = prev is not None and (now - prev["at"]).total_seconds() >= MIN_REPEAT_S
            if not (changed or due):
                continue
            _emit(conn, r, ln, strategy)
            state[ln["id"]] = {"place": ln["place"], "at": now}
            out["emitted"] += 1
    return out


def run_window(conn: psycopg.Connection, *, until: datetime | None = None, poll_s: float = POLL_S,
               sleep=time.sleep, now_fn=lambda: datetime.now(UTC)) -> dict[str, Any]:
    """Stream placement reads until 09:30 WIB (or ``until``). Returns a summary; never raises on one bad pass."""
    state: dict[int, dict[str, Any]] = {}
    res = {"passes": 0, "emitted": 0, "lines": 0, "stale_feed_passes": 0, "stopped": None}
    with _lock(conn) as got:
        if not got:
            res["stopped"] = "another process holds the open-window lock"
            logger.info("idx open window: %s", res["stopped"])
            return res
        while True:
            now = now_fn()
            if until is not None and now >= until:
                res["stopped"] = "window closed"
                break
            if until is None and not in_window(now):
                res["stopped"] = "outside the window"
                break
            try:
                one = tick_once(conn, state, now=now)
                res["passes"] += 1
                res["emitted"] += one["emitted"]
                res["lines"] = one["lines"]
                res["stale_feed_passes"] += 1 if one["stale_feed"] else 0
                if one["tickets"] == 0:
                    res["stopped"] = "nothing left to work"
                    break
            except Exception:
                logger.exception("idx open window: pass failed; carrying on")
            sleep(poll_s)
    logger.info("idx open window: %s after %d pass(es), %d read(s) sent", res["stopped"], res["passes"], res["emitted"])
    return res
