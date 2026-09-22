"""Pure transforms from decoded feed messages to rows: order-book bodies to level arrays, liveprice messages to prints."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

WIB = timezone(timedelta(hours=7))
TOP = 10


@dataclass
class Side:
    px: list[int] = field(default_factory=list)
    vol: list[int] = field(default_factory=list)
    n: list[int] = field(default_factory=list)
    total: int = 0
    levels: int = 0

    def top(self, k: int = TOP) -> tuple[list[int], list[int], list[int]]:
        return self.px[:k], self.vol[:k], self.n[:k]


def parse_book_body(body: str) -> tuple[str, str, Side] | None:
    """``#O|BMRI|BID|4210;1522;4476200|4200;4550;16042600|...`` -> (code, side, levels). Level = price;orders;volume (shares).
    Returns None for bodies that are not order-book lines."""
    parts = body.strip().split("|")
    if len(parts) < 3 or parts[0] != "#O":
        return None
    code, side = parts[1], parts[2].upper()
    if side not in ("BID", "OFFER"):
        return None
    s = Side()
    for lvl in parts[3:]:
        if not lvl:
            continue
        bits = lvl.split(";")
        if len(bits) < 3:
            continue
        try:
            px, n, vol = int(float(bits[0])), int(float(bits[1])), int(float(bits[2]))
        except ValueError:
            continue
        if px <= 0:
            continue
        s.px.append(px)
        s.n.append(n)
        s.vol.append(vol)
    s.levels = len(s.px)
    s.total = sum(s.vol)
    return code, side, s


def parse_ts(s: str | None, fallback: datetime | None = None) -> datetime:
    """Feed timestamps are ISO 8601 with an offset (``2026-09-21T14:59:11.076279+07:00``); a bare ``HH:MM:SS`` or a
    naive stamp is read as WIB. Falls back to ``fallback`` (or now) when unparsable."""
    now = fallback or datetime.now(UTC)
    if not s:
        return now
    s = s.strip()
    try:
        if len(s) == 8 and s[2] == ":" and s[5] == ":":
            d = now.astimezone(WIB)
            return d.replace(hour=int(s[:2]), minute=int(s[3:5]), second=int(s[6:8]), microsecond=0)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=WIB)
        return d
    except ValueError:
        return now


def trade_row(msg: dict[str, Any], recv: datetime) -> dict[str, Any] | None:
    """A liveprice message -> one print, or None when it carries no match (index rows, snapshots without quantity)."""
    code = msg.get("stock_code")
    price = msg.get("lastprice")
    qty = msg.get("quantity")
    if not code or price is None or price <= 0:
        return None
    if not qty:
        tt = msg.get("trade_trigger") or {}
        qty = tt.get("quantity") or 0
    if not qty:
        return None
    ts = parse_ts(msg.get("itch_incoming_time") or msg.get("date"), recv)
    verb = (msg.get("order_verb") or "").strip().upper()[:1] or None
    cum_vol = msg.get("volume")
    cum_val = msg.get("value")
    cum_frq = msg.get("frequency")
    return {"ts": ts, "code": code, "seq": int(msg.get("sequence_number") or 0), "price": round(price), "qty": int(qty),
            "verb": verb, "board": str(msg.get("board")) if msg.get("board") is not None else None,
            "cum_volume": int(cum_vol) if cum_vol is not None else None, "cum_value": int(cum_val) if cum_val is not None else None,
            "cum_freq": int(cum_frq) if cum_frq is not None else None, "recv_at": recv}


def book_row(code: str, ts: datetime, seq: int, bid: Side, offer: Side, n_updates: int) -> dict[str, Any]:
    bpx, bvol, bn = bid.top()
    opx, ovol, on = offer.top()
    return {"ts": ts, "code": code, "seq": seq, "bid_px": bpx, "bid_vol": bvol, "bid_n": bn, "off_px": opx, "off_vol": ovol, "off_n": on,
            "bid_total": bid.total, "off_total": offer.total, "bid_levels": bid.levels, "off_levels": offer.levels, "n_updates": n_updates}


def book_key(bid: Side, offer: Side) -> tuple:
    """What "the book changed" means for sampling: any of the top levels or the totals moved."""
    return (tuple(bid.px[:TOP]), tuple(bid.vol[:TOP]), tuple(offer.px[:TOP]), tuple(offer.vol[:TOP]), bid.total, offer.total)
