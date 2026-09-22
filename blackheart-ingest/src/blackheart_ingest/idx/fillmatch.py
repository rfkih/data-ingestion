"""What the tape says about an open ticket line - the one-tap fill (operator, 2026-09-22: "catat fill satu ketukan").

Recording fills by hand is the desk's largest daily chore and its commonest source of error: a trend ticket is worked most
evenings and every lot and price is typed back in. The tick feed now sees every print on the exchange, so for a line the
operator has worked we can say what the market actually traded inside its limit and offer a fill to confirm.

What this can and cannot know. It cannot know which prints were the operator's order - the feed carries no account. It can
know, exactly, at what prices and in what size the market traded within the line's limit while the ticket was open, and that
is enough for a proposal the operator confirms with one tap (or edits). Nothing here writes anything: the caller records the
fill through ``ticket.fill_line``, which keeps the two-key rule, the journal and the book mark.

The proposal, per open line:
  eligible prints   today's prints of that code at a price the line could have traded at - at or below the limit for a buy,
                    at or above it for a sell - from 09:00 (the ticket is worked from the open) to now.
  price             the volume-weighted average of those prints, snapped to the tick the conservative way (a buy rounds
                    up, a sell rounds down - the proposal never flatters the fill) and never worse than the line's limit.
  lots              the whole remaining lots when the eligible volume is at least ``COVER`` times the line's size (the order
                    would have been a small part of that flow); otherwise the lots that volume could plausibly have filled.
  confidence        high   the market traded >= 10x the line's size inside the limit
                    medium >= 3x (the COVER floor)
                    low    less than that, or the line's own size dominates the flow - the operator should check the broker
  A line with no eligible print at all comes back with ``lots`` 0 and a reason, never a guessed price.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg

from . import ticket
from .card import _rows

logger = logging.getLogger(__name__)
COVER = Decimal(3)                       # eligible volume must be this many times the line before a full fill is proposed
HIGH = Decimal(10)
SESSION_FROM = time(9, 0)


def eligible(prints: list[dict[str, Any]], side: str, limit: Decimal) -> list[dict[str, Any]]:
    """Pure. The prints a line could have traded at: at or below the limit for a buy, at or above it for a sell."""
    return [p for p in prints if (Decimal(p["price"]) <= limit) if side == "buy"] if side == "buy" \
        else [p for p in prints if Decimal(p["price"]) >= limit]


def propose(line: dict[str, Any], prints: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure. One open line plus today's prints of its code -> the fill to offer. ``prints``: {price, qty, at}."""
    remaining = Decimal(line["lots"]) - Decimal(line.get("filled_lots") or 0)
    limit = Decimal(line["limit_price"])
    out: dict[str, Any] = {"line_id": line["id"], "code": line["code"], "side": line["side"], "remaining": remaining,
                           "limit_price": limit, "lots": Decimal(0), "price": None, "confidence": "none",
                           "volume": Decimal(0), "n_prints": 0, "first": None, "last": None, "why": None}
    if remaining <= 0:
        out["why"] = "nothing left to fill"
        return out
    hits = eligible(prints, line["side"], limit)
    if not hits:
        out["why"] = f"no print at or {'below' if line['side'] == 'buy' else 'above'} {limit} today"
        return out
    vol = sum((Decimal(p["qty"]) for p in hits), Decimal(0))
    turnover = sum((Decimal(p["qty"]) * Decimal(p["price"]) for p in hits), Decimal(0))
    vwap = (turnover / vol) if vol else limit
    px = Decimal(ticket.snap(vwap, line["side"]))
    px = min(px, limit) if line["side"] == "buy" else max(px, limit)      # never propose a fill worse than the limit
    size = remaining * ticket.LOT
    if vol >= size * COVER:
        lots, conf = remaining, ("high" if vol >= size * HIGH else "medium")
    else:
        lots = (vol / ticket.LOT).to_integral_value(rounding=ROUND_HALF_UP)
        lots, conf = min(remaining, max(lots, Decimal(0))), "low"
    if lots <= 0:
        out.update({"why": "the market traded less than a lot inside the limit", "volume": vol, "n_prints": len(hits)})
        return out
    out.update({"lots": lots, "price": px, "confidence": conf, "volume": vol, "n_prints": len(hits),
                "first": min(p["at"] for p in hits), "last": max(p["at"] for p in hits), "vwap": vwap})
    return out


def prints_for(conn: psycopg.Connection, codes: list[str], d: date) -> dict[str, list[dict[str, Any]]]:
    """Today's prints per code from the tick feed, from the open onwards (a ticket is worked during the session)."""
    if not codes:
        return {}
    rows = _rows(conn, """SELECT code, price, qty, ts AT TIME ZONE 'Asia/Jakarta' AS at FROM idx.feed_trade
                           WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code = ANY(%s)
                             AND (ts AT TIME ZONE 'Asia/Jakarta')::time >= %s ORDER BY code, ts""",
                 (d, codes, SESSION_FROM), ["code", "price", "qty", "at"])
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["code"], []).append({"price": Decimal(str(r["price"])), "qty": Decimal(str(r["qty"])), "at": r["at"]})
    return out


def suggest(conn: psycopg.Connection, ticket_id: int, d: date | None = None) -> dict[str, Any]:
    """Every open line of a ticket with the fill the tape supports. Read-only."""
    t = ticket.load(conn, ticket_id)
    if t is None:
        raise ValueError(f"no ticket {ticket_id}")
    d = d or datetime.now(tz=None).date()
    if t["status"] != "issued":                                            # only an issued ticket is being worked at the
        return {"ticket": t["id"], "book": t["book"], "status": t["status"], "date": d, "lines": [],   # broker right now;
                "why": f"ticket is {t['status']}, not issued"}             # a draft is not placed and a closed/cancelled one is done
    open_lines = [ln for ln in t["lines"] if ln["status"] in ("open", "partial")]
    prints = prints_for(conn, sorted({ln["code"] for ln in open_lines}), d)
    return {"ticket": t["id"], "book": t["book"], "status": t["status"], "date": d,
            "lines": [propose(ln, prints.get(ln["code"], [])) for ln in open_lines]}


def render(s: dict[str, Any]) -> str:
    o = [f"# fills the tape supports - ticket #{s['ticket']} ({s['book']}, {s['status']}) on {s['date']}"]
    if s.get("why"):
        return o[0] + "\n  (" + str(s["why"]) + ")"
    for ln in s["lines"]:
        if ln["lots"] > 0:
            o.append(f"  {ln['side']:4s} {ln['code']:<6} {int(ln['lots']):>5} lot @ {float(ln['price']):>9,.0f}  "
                     f"[{ln['confidence']}] {int(ln['n_prints'])} prints, {float(ln['volume']):,.0f} shares inside the limit "
                     f"{float(ln['limit_price']):,.0f} ({ln['first']:%H:%M}-{ln['last']:%H:%M})")
        else:
            o.append(f"  {ln['side']:4s} {ln['code']:<6}     -              {ln['why']}")
    if not s["lines"]:
        o.append("  (no open line)")
    return "\n".join(o)
