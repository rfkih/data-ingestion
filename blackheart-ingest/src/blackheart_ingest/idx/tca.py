"""Weekly transaction-cost analysis of the live combined book (Track A5, operator 2026-09-26: "okay do track A").

The desk's biggest suspected leak is execution: the return lives in a few large trades (median trade negative), so a missed or
late line is not neutral. The nightly scorecard already measures it per line; this turns it into rupiah, per week, pushed to
the operator every Friday evening (and ``idx tca`` any time).

Per sleeve, for the week and since the book started:
  lines / filled / missed        fill rate (the kill rule `fills:<sleeve>` trips under 80 %)
  delay                          median hours from ticket to recorded fill (a proxy: when the fill was entered)
  slippage vs plan               fill vs the line's reference price, bps and rupiah (buys paying more = cost)
  vs paper twin                  fill vs the twin's fill on the same name / side / day, bps and rupiah - the pure execution cost
  missed but the twin traded     how many, and the twin's realised P&L on those round trips = the rupiah the misses cost
  vs the open                    fill vs that day's official open (``open_src = 'idx'`` only), bps and rupiah - what the
                                 backtests assume for the trend rule (fill at the next open; a day late costs Sharpe 1.31 -> 0.91)
  pre-open queue                 the line's shares as a share of the opposite side of the book at prices the fill could have
                                 taken, in the last feed snapshot of the pre-opening (08:45-09:00 WIB) - how much of the
                                 opening queue our order is (operator 2026-09-28: "catat slippage otomatis per fill")
The Friday job also covers the live trend books (``trend_live``); their lines carry no sleeve flag and report as ``trend``.
Nothing here trades or changes a setting.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import psycopg

from . import combo_book as cb
from . import killrules as kr
from .card import _rows

WIB = ZoneInfo("Asia/Jakarta")
LOT = 100


def _lines(conn: psycopg.Connection, book: str) -> list[dict[str, Any]]:
    return _rows(conn, """
        SELECT t.id AS ticket, t.ticket_date, t.created_at AS issued_at, l.code, l.side, l.ref_close, l.status, l.skip_reason, l.flags,
               l.filled_lots, f.price AS fill_price, f.created_at AS filled_at, f.trade_date AS fill_date,
               CASE WHEN b.open_src = 'idx' THEN b.open END AS day_open
          FROM idx.ticket t JOIN idx.ticket_line l ON l.ticket_id = t.id LEFT JOIN idx.fill f ON f.id = l.fill_id
          LEFT JOIN idx.bar b ON b.code = l.code AND b.trade_date = f.trade_date AND b.source = 'idx'
         WHERE t.book = %s AND t.status <> 'cancelled' ORDER BY t.id, l.seq""", (book,),
        ["ticket", "ticket_date", "issued_at", "code", "side", "ref_close", "status", "skip_reason", "flags", "filled_lots", "fill_price",
         "filled_at", "fill_date", "day_open"])


def depth_within(side: str, price: Decimal | float, px: list | None, vol: list | None) -> float | None:
    """Pure. Shares resting on the opposite side at prices a fill at ``price`` could have taken: offers at or below it for a
    buy, bids at or above it for a sell. None when the snapshot has no levels."""
    if not px or not vol:
        return None
    p = float(price)
    ok = (lambda q: q <= p) if side == "buy" else (lambda q: q >= p)
    return float(sum(v for q, v in zip(px, vol) if q is not None and v is not None and ok(float(q))))


def preopen_books(conn: psycopg.Connection, lines: list[dict[str, Any]]) -> dict[tuple, dict[str, Any]]:
    """(code, day) -> the last feed book snapshot of the pre-opening (08:45-09:00 WIB) for every filled line. The feed book
    exists from 2026-09-22; earlier fills simply have none."""
    keys = sorted({(r["code"], r["fill_date"]) for r in lines if r.get("fill_date") and r.get("fill_price")})
    out: dict[tuple, dict[str, Any]] = {}
    for code, d in keys:
        t0 = datetime(d.year, d.month, d.day, 8, 45, tzinfo=WIB)
        rows = _rows(conn, """SELECT bid_px, bid_vol, off_px, off_vol FROM idx.feed_book WHERE code = %s AND ts >= %s AND ts < %s
                               ORDER BY ts DESC LIMIT 1""", (code, t0, t0 + timedelta(minutes=15)), ["bid_px", "bid_vol", "off_px", "off_vol"])
        if rows:
            out[(code, d)] = rows[0]
    return out


def summarize(lines: list[dict[str, Any]], twin: dict[tuple, Decimal], twin_pnl: dict[tuple, float],
              since: date | None = None, books: dict[tuple, dict[str, Any]] | None = None,
              default_sleeve: str = "manual") -> dict[str, dict[str, Any]]:
    """Pure. Ticket lines (live book) -> per-sleeve TCA. ``twin``: (sleeve, code, side, day) -> twin fill price;
    ``twin_pnl``: (sleeve, code, entry day) -> the twin's realised P&L in rupiah on the round trip it opened that day;
    ``books``: (code, day) -> the pre-open feed snapshot (``preopen_books``); ``default_sleeve`` names lines without a sleeve
    flag (a trend book's lines -> "trend")."""
    books = books or {}
    out: dict[str, dict[str, Any]] = {}
    for r in lines:
        d = r["fill_date"] or r["ticket_date"]
        if since and d and d < since:
            continue
        s = cb.sleeve_of(r["flags"])
        if s == "manual":
            s = default_sleeve
        p = out.setdefault(s, {"lines": 0, "filled": 0, "missed": 0, "delay_h": [], "slip_bps": [], "slip_rp": 0.0,
                               "twin_bps": [], "twin_rp": 0.0, "missed_twin": 0, "missed_twin_rp": 0.0,
                               "open_bps": [], "open_rp": 0.0, "queue": []})
        p["lines"] += 1
        if r["status"] in ("filled", "partial") and r["fill_price"]:
            p["filled"] += 1
            fp, lots = Decimal(r["fill_price"]), Decimal(r["filled_lots"] or 0)
            notional = float(fp * lots * LOT)
            sign = 1 if r["side"] == "buy" else -1
            if r["ref_close"]:
                ref = Decimal(r["ref_close"])
                bps = float((fp / ref - 1) * sign) * 1e4
                p["slip_bps"].append(bps)
                p["slip_rp"] += bps / 1e4 * notional
            if r.get("day_open"):
                bps = float((fp / Decimal(r["day_open"]) - 1) * sign) * 1e4
                p["open_bps"].append(bps)
                p["open_rp"] += bps / 1e4 * notional
            snap_ = books.get((r["code"], r["fill_date"]))
            if snap_ and lots > 0:
                px, vol = (snap_["off_px"], snap_["off_vol"]) if r["side"] == "buy" else (snap_["bid_px"], snap_["bid_vol"])
                depth = depth_within(r["side"], fp, px, vol)
                if depth:
                    p["queue"].append(float(lots * LOT) / depth)
            tp = twin.get((s, r["code"], r["side"], r["fill_date"]))
            if tp:
                bps = cb.twin_gap_bps(r["side"], fp, tp)
                p["twin_bps"].append(bps)
                p["twin_rp"] += bps / 1e4 * notional
            if r["filled_at"] and r["issued_at"]:
                p["delay_h"].append((r["filled_at"] - r["issued_at"]).total_seconds() / 3600)
        elif r["status"] == "skipped" and (r["skip_reason"] or "").startswith("missed"):
            p["missed"] += 1
            if r["side"] == "buy" and (s, r["code"], r["ticket_date"]) in twin_pnl:
                p["missed_twin"] += 1
                p["missed_twin_rp"] += twin_pnl[(s, r["code"], r["ticket_date"])]
    for p in out.values():
        p["fill_rate"] = p["filled"] / p["lines"] if p["lines"] else None
        p["delay_h_median"] = float(np.median(p["delay_h"])) if p["delay_h"] else None
        p["slip_bps_mean"] = float(np.mean(p["slip_bps"])) if p["slip_bps"] else None
        p["twin_bps_mean"] = float(np.mean(p["twin_bps"])) if p["twin_bps"] else None
        p["open_bps_mean"] = float(np.mean(p["open_bps"])) if p["open_bps"] else None
        p["queue_median"] = float(np.median(p["queue"])) if p["queue"] else None
        for k in ("delay_h", "slip_bps", "twin_bps", "open_bps", "queue"):
            p[f"n_{k}"] = len(p.pop(k))
    return out


def twin_round_trips(conn: psycopg.Connection, twin: str) -> dict[tuple, float]:
    """The twin's closed round trips -> (sleeve, code, entry day): realised P&L in rupiah (fees in)."""
    if not twin:
        return {}
    out: dict[tuple, float] = {}
    fills = kr.book_fills(conn, twin)
    trades = kr.closed_trades(fills, cb.sleeve_of)
    cost = {}
    for f in fills:                                              # entry notional per (sleeve, code, day) to turn returns into rupiah
        if f["side"] == "buy":
            k = (cb.sleeve_of(f["flags"]), f["code"], f["trade_date"])
            cost[k] = cost.get(k, 0.0) + float(Decimal(f["lots"]) * LOT * Decimal(f["price"]))
    for t in trades:
        k = (t["sleeve"], t["code"], t["d_in"])
        out[k] = out.get(k, 0.0) + t["ret"] * cost.get(k, 0.0)
    return out


def report(conn: psycopg.Connection, book: str, end: date | None = None) -> dict[str, Any]:
    end = end or datetime.now(WIB).date()
    b = cb.bk.get_book(conn, book)
    twin = str((b.get("params") or {}).get("twin") or "")
    tw = cb.twin_fills(conn, twin)
    tp = twin_round_trips(conn, twin)
    lines = _lines(conn, book)
    books = preopen_books(conn, lines)
    dflt = "trend" if b.get("rule") == "trend" else "manual"
    return {"book": book, "twin": twin or None, "end": str(end),
            "week": summarize(lines, tw, tp, since=end - timedelta(days=6), books=books, default_sleeve=dflt),
            "all": summarize(lines, tw, tp, books=books, default_sleeve=dflt)}


def render(rep: dict[str, Any]) -> str:
    """The Friday push, in the operator's language."""
    def block(title: str, per: dict[str, dict[str, Any]]) -> list[str]:
        if not per:
            return [f"{title}: belum ada baris tiket."]
        o = [title]
        for s, p in sorted(per.items()):
            fr = f"{p['fill_rate'] * 100:.0f} %" if p["fill_rate"] is not None else "-"
            parts = [f"{s}: {p['filled']}/{p['lines']} terisi ({fr}), {p['missed']} miss"]
            if p["slip_bps_mean"] is not None:
                parts.append(f"slip {p['slip_bps_mean']:+.0f} bps (Rp {p['slip_rp']:,.0f})")
            if p["twin_bps_mean"] is not None:
                parts.append(f"vs twin {p['twin_bps_mean']:+.0f} bps (Rp {p['twin_rp']:,.0f})")
            if p["open_bps_mean"] is not None:
                parts.append(f"vs open {p['open_bps_mean']:+.0f} bps (Rp {p['open_rp']:,.0f}, n {p['n_open_bps']})")
            if p["queue_median"] is not None:
                parts.append(f"antrean pre-open median {p['queue_median'] * 100:.1f} %")
            if p["missed_twin"]:
                parts.append(f"{p['missed_twin']} miss yang twin eksekusi = Rp {p['missed_twin_rp']:,.0f}")
            if p["delay_h_median"] is not None:
                parts.append(f"telat median {p['delay_h_median']:.1f} jam")
            o.append("  " + ", ".join(parts))
        return o
    o = [f"[TCA mingguan] {rep['book']} s.d. {rep['end']}"]
    o += block("Minggu ini", rep["week"])
    o += block("Sejak awal", rep["all"])
    cost = sum(p["twin_rp"] + p["missed_twin_rp"] for p in rep["all"].values())
    if rep["all"]:
        o.append(f"Biaya eksekusi vs twin sejak awal: Rp {cost:,.0f} (positif = live lebih buruk dari paper).")
    return "\n".join(o)


def evidence_lines(conn: psycopg.Connection, book: str) -> list[str]:
    """The pre-registered confirmation status (killrules.confirm_check) of the live book and of the uncapped signal record."""
    out = ["Bukti edge (pre-registered 2026-09-26):"]
    books = [book] + [b for b in cb.combo_books(conn) if b != book and (cb.bk.get_book(conn, b).get("label") or "").startswith("Signal record")]
    for b in books:
        cs = kr.evaluate(conn, b).get("confirm") or []
        tag = "live" if cb.ticket.is_live(b) else "sinyal (paper)"
        out.append(f"  {tag}: " + "; ".join(f"{c['rule'].split(':')[1]} {c['status']} {c['n']}/{c['need']}"
                                            + (f" t {c['t']:.1f}" if c.get("t") is not None else "") for c in cs))
    return out


def weekly(conn: psycopg.Connection, book: str) -> str | None:
    """Friday job: push the report for a live combo book (paper books are the yardstick, not the subject)."""
    if not cb.ticket.is_live(book):
        return None
    text = "\n".join([render(report(conn, book)), *evidence_lines(conn, book)])
    cb._notify(conn, book, text, data={"route": f"/m/ticket?book={book}", "kind": "tca", "book": book})
    return text
