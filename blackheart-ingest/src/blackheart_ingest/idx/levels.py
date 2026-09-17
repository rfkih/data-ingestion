"""Price levels per held name (migration 0024 ``idx.price_level``): a stop, a take-profit or an early warning the operator
wants to hear about. ``check`` runs after every mark in the daily chain: a stop / warn fires when the close is at or below
the level, a take-profit when it is at or above; the alert is critical (stop, take_profit) or warning (warn), goes out
through ``runlog.alert`` (Telegram when ``notify`` is configured) and the level is stamped ``triggered_at`` so it does not
fire again until ``reset``. A code that is an index (``idx.index_daily``) is read from there, so an IHSG level works too.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import psycopg

from . import runlog

logger = logging.getLogger(__name__)
KINDS = ("stop", "take_profit", "warn")
JOB = "levels"


def _rows(cur) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def set_level(conn: psycopg.Connection, book: str, code: str, kind: str, level: Decimal | float | str, note: str | None = None) -> dict[str, Any]:
    """Create or replace one level (re-arms it)."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.price_level (book, code, kind, level, note) VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (book, code, kind) DO UPDATE SET level = EXCLUDED.level, note = COALESCE(EXCLUDED.note, idx.price_level.note),
                           active = TRUE, triggered_at = NULL, triggered_px = NULL, created_at = now()
                       RETURNING id, book, code, kind, level, note, active""", (book, code.upper(), kind, Decimal(str(level)), note))
        row = _rows(cur)[0]
    conn.commit()
    return row


def clear(conn: psycopg.Connection, book: str, code: str, kind: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.price_level WHERE book = %s AND code = %s AND (%s::text IS NULL OR kind = %s)", (book, code.upper(), kind, kind))
        n = cur.rowcount
    conn.commit()
    return n


def reset(conn: psycopg.Connection, book: str, code: str, kind: str | None = None) -> int:
    """Re-arm triggered levels (after the operator acted, or decided not to)."""
    with conn.cursor() as cur:
        cur.execute("""UPDATE idx.price_level SET active = TRUE, triggered_at = NULL, triggered_px = NULL
                        WHERE book = %s AND code = %s AND (%s::text IS NULL OR kind = %s)""", (book, code.upper(), kind, kind))
        n = cur.rowcount
    conn.commit()
    return n


def levels(conn: psycopg.Connection, book: str | None = None, code: str | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT l.id, l.book, l.code, l.kind, l.level, l.note, l.active, l.created_at, l.triggered_at, l.triggered_px,
                              p.lots, p.avg_price
                         FROM idx.price_level l LEFT JOIN idx.position p ON p.book = l.book AND p.code = l.code
                        WHERE (%s::text IS NULL OR l.book = %s) AND (%s::text IS NULL OR l.code = %s)
                        ORDER BY l.book, l.code, l.kind""", (book, book, code, code))
        return _rows(cur)


def _closes(conn: psycopg.Connection, codes: list[str]) -> dict[str, tuple[Any, Decimal]]:
    """Latest close per code: idx.bar for a stock, idx.index_daily for an index code."""
    out: dict[str, tuple[Any, Decimal]] = {}
    if not codes:
        return out
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (code) code, trade_date, close FROM idx.bar
                        WHERE code = ANY(%s) AND source IN ('idx', 'yahoo') AND close IS NOT NULL ORDER BY code, trade_date DESC""", (codes,))
        for r in _rows(cur):
            out[r["code"]] = (r["trade_date"], Decimal(r["close"]))
        missing = [c for c in codes if c not in out]
        if missing:
            cur.execute("""SELECT DISTINCT ON (index_code) index_code AS code, trade_date, close FROM idx.index_daily
                            WHERE index_code = ANY(%s) ORDER BY index_code, trade_date DESC""", (missing,))
            for r in _rows(cur):
                out[r["code"]] = (r["trade_date"], Decimal(r["close"]))
    return out


def evaluate(level: dict[str, Any], close: Decimal) -> bool:
    """Pure: does this level fire at this close?"""
    lv = Decimal(level["level"])
    if level["kind"] in ("stop", "warn"):
        return close <= lv
    return close >= lv


def check(conn: psycopg.Connection, book: str) -> runlog.RunResult:
    """Fire every active, untriggered level whose close crossed it; stamp it; alert once."""
    r = runlog.RunResult(f"{JOB}:check", book)
    run_id = runlog.start(conn, f"{JOB}:check", book)
    try:
        act = [x for x in levels(conn, book) if x["active"] and x["triggered_at"] is None]
        px = _closes(conn, sorted({x["code"] for x in act}))
        r.rows_in = len(act)
        for x in act:
            if x["code"] not in px:
                continue
            d, close = px[x["code"]]
            if not evaluate(x, close):
                continue
            vs = ""
            if x["avg_price"]:
                vs = f" ({float(close / Decimal(x['avg_price']) - 1):+.1%} vs avg {float(x['avg_price']):,.0f}, {int(x['lots'])} lot)"
            head = {"stop": "STOP LOSS", "take_profit": "TAKE PROFIT", "warn": "WARNING LEVEL"}[x["kind"]]
            msg = f"{head} {x['code']}: close {float(close):,.0f} on {d} crossed {float(x['level']):,.0f}{vs}." + (f" Plan: {x['note']}" if x["note"] else "")
            runlog.alert(conn, "critical" if x["kind"] != "warn" else "warning", f"levels:{book}", msg)
            with conn.cursor() as cur:
                cur.execute("UPDATE idx.price_level SET triggered_at = %s, triggered_px = %s WHERE id = %s", (datetime.now(UTC), close, x["id"]))
            conn.commit()
            r.rows_out += 1
            logger.warning("idx levels %s: %s", book, msg)
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx levels check failed")
    runlog.finish(conn, run_id, r)
    return r


def render(rows: list[dict[str, Any]], closes: dict[str, tuple[Any, Decimal]] | None = None) -> str:
    L = [f"{'book':6s} {'code':9s} {'kind':11s} {'level':>10s} {'last':>10s} {'dist':>7s} {'avg':>8s} {'state':10s} note"]
    for x in rows:
        last = closes.get(x["code"], (None, None))[1] if closes else None
        dist = f"{float(last / Decimal(x['level']) - 1):+.1%}" if last else "-"
        state = f"HIT {str(x['triggered_at'])[:10]}" if x["triggered_at"] else ("armed" if x["active"] else "off")
        L.append(f"{x['book']:6s} {x['code']:9s} {x['kind']:11s} {float(x['level']):>10,.0f} {float(last) if last else 0:>10,.0f} {dist:>7s} "
                 f"{float(x['avg_price']) if x['avg_price'] else 0:>8,.0f} {state:10s} {x['note'] or ''}")
    return "\n".join(L)
