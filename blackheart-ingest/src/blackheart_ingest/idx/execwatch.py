"""Live execution timing for the open lines of a ticket (research menu 28b / study #99): for a trade the operator has
already decided to make, the tick feed says whether to rest at the bid or take the offer right now. The one microstructure
edge that survived costs was execution timing - a buy that waits for the book to lean to the bid (OBI1 >= 0.3, microprice
above the mid) before taking the offer filled +6..+11 bps better than hitting immediately, both sessions, beyond a
random-wait placebo. This reads that lean per line and turns it into "where to place", never a decision to trade: the
ticket already carries the side, the lots and the limit; this only times the placement.

Read-only on the feed. No directive words in anything a person sees (spec §03): "book leaning up", "rest at the bid",
"take the offer", "balanced" - a factual read of the order book, not a call to buy or sell.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from . import gapfade, ticket

WIB = ZoneInfo("Asia/Jakarta")
OBI_THR = 0.3          # the book must lean this far before a taker's timing has an edge (study #99)


def tick(px: float) -> float:
    return 1.0 if px < 200 else 2.0 if px < 500 else 5.0 if px < 2000 else 10.0 if px < 5000 else 25.0


def lean(side: str, obi1: float | None, micro_ticks: float | None, thr: float = OBI_THR) -> str:
    """Where to place a line, from the book's lean. A buyer takes the offer when the book leans up (it is about to cost
    more) and rests at the bid when it leans down (the price is coming down to them); a seller mirrors it. 'balanced'
    when neither, so there is no timing edge either way. Pure, so the decision is unit-tested without the feed."""
    if obi1 is None:
        return "unknown"
    up = obi1 >= thr and (micro_ticks or 0) > 0
    down = obi1 <= -thr and (micro_ticks or 0) < 0
    if side == "buy":
        return "offer" if up else "bid" if down else "balanced"
    return "bid" if down else "offer" if up else "balanced"


def acts_now(side: str, place: str) -> bool:
    """Whether the read says to cross the spread now (take) rather than rest (post and wait)."""
    return (side == "buy" and place == "offer") or (side == "sell" and place == "bid")


def _note(side: str, place: str, obi1: float | None) -> str:
    if place == "unknown":
        return "Not in the live feed"
    if place == "balanced":
        return "Balanced book — either side, no timing edge"
    where = "the offer" if place == "offer" else "the bid"
    verb = "Take" if acts_now(side, place) else "Rest at"
    tilt = "leaning up" if (obi1 or 0) > 0 else "leaning down"
    return f"Book {tilt} — {verb.lower()} {where}"


def _books(conn: psycopg.Connection, codes: list[str], d: date) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    rows = gapfade._rows(conn, """SELECT DISTINCT ON (code) code, bid_px[1] AS bid, off_px[1] AS off, bid_vol[1] AS bv, off_vol[1] AS ov,
                                         ts AT TIME ZONE 'Asia/Jakarta' AS t
                                    FROM idx.feed_book WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code = ANY(%s)
                                    ORDER BY code, ts DESC""", (d, codes), ["code", "bid", "off", "bv", "ov", "t"])
    return {r["code"]: r for r in rows}


def _last_prices(conn: psycopg.Connection, codes: list[str], d: date) -> dict[str, float]:
    if not codes:
        return {}
    rows = gapfade._rows(conn, """SELECT DISTINCT ON (code) code, price FROM idx.feed_trade
                                   WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code = ANY(%s) ORDER BY code, ts DESC""",
                         (d, codes), ["code", "price"])
    return {r["code"]: float(r["price"]) for r in rows if r["price"]}


def market_lean(conn: psycopg.Connection, d: date) -> float | None:
    """The market's own book lean now: the mean top-of-book imbalance across every feed name's latest book today. A buy
    into a market whose flow is leaning down is the one the gate would hold (study #99)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT avg((bv - ov) / NULLIF(bv + ov, 0)) AS m FROM (
                           SELECT DISTINCT ON (code) bid_vol[1]::numeric AS bv, off_vol[1]::numeric AS ov FROM idx.feed_book
                           WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code <> 'IHSG'
                             AND bid_vol[1] > 0 AND off_vol[1] > 0 ORDER BY code, ts DESC) x""", (d,))
        r = cur.fetchone()
    return float(r["m"]) if r and r["m"] is not None else None


def read(conn: psycopg.Connection, ticket_id: int, d: date | None = None) -> dict[str, Any]:
    """Everything the live placement screen needs for one ticket, in one poll. Read-only."""
    now = datetime.now(WIB)
    d = d or now.date()
    t = ticket.load(conn, ticket_id)
    if t is None:
        raise ValueError(f"no ticket {ticket_id}")
    open_lines = [ln for ln in t["lines"] if ln["status"] in ("open", "partial")]
    codes = sorted({ln["code"] for ln in open_lines})
    books = _books(conn, codes, d)
    last = _last_prices(conn, codes, d)
    feed = gapfade._rows(conn, """SELECT max(ts) AS m FROM idx.feed_trade WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s""", (d,), ["m"])
    last_ts = feed[0]["m"] if feed else None
    stale = round((now - last_ts.astimezone(WIB)).total_seconds()) if last_ts else None
    mkt = market_lean(conn, d)
    lines = []
    for ln in open_lines:
        b = books.get(ln["code"])
        bid = float(b["bid"]) if b and b["bid"] else None
        off = float(b["off"]) if b and b["off"] else None
        bv = float(b["bv"]) if b and b["bv"] else 0.0
        ov = float(b["ov"]) if b and b["ov"] else 0.0
        obi = (bv - ov) / (bv + ov) if (bv + ov) > 0 else None
        mid = (bid + off) / 2 if bid and off else None
        micro = (bid * ov + off * bv) / (bv + ov) if (bid and off and (bv + ov) > 0) else None
        micro_ticks = (micro - mid) / tick(mid) if (micro is not None and mid) else None
        place = lean(ln["side"], obi, micro_ticks) if b else "unknown"
        lines.append({
            "id": ln["id"], "code": ln["code"], "name": ln.get("name"), "side": ln["side"],
            "lots": str(ln["lots"]), "limit": str(ln["limit_price"]) if ln.get("limit_price") is not None else None,
            "bid": bid, "offer": off, "last": last.get(ln["code"]),
            "spread_bps": round((off - bid) / mid * 1e4, 1) if (bid and off and mid) else None,
            "obi1": round(obi, 3) if obi is not None else None,
            "micro_ticks": round(micro_ticks, 2) if micro_ticks is not None else None,
            "place": place, "act": acts_now(ln["side"], place), "in_feed": b is not None,
            "note": _note(ln["side"], place, obi),
        })
    return {"ticket": t["id"], "book": t["book"], "status": t["status"], "date": str(d),
            "phase": gapfade.session_phase(now), "market_lean": round(mkt, 3) if mkt is not None else None,
            "feed": {"last_at": last_ts.astimezone(WIB).isoformat() if last_ts else None, "stale_s": stale,
                     "live": bool(stale is not None and stale <= 120 and gapfade.session_phase(now) in ("open", "pre-open", "closing"))},
            "lines": lines}
