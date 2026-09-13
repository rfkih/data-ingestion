"""Book-level overlays on top of the strategy (research/IDX_TREND_OVERLAY_2026-09-13.md), both off by default:

  regime_filter  the book sits in cash while the COMPOSITE is under its 200-day average. Checked on the first trading
                 day of each month after the close: when the regime turns off a "cash" ticket sells everything; when it
                 turns on a "rebalance" ticket buys the book's list back. An annual rebalance while the regime is off
                 becomes a cash ticket.
  entry_gate     at a rebalance, a listed name under its own 200-day average is not bought (held back, its slot stays in
                 cash); at each monthly check the held-back names that have crossed above are bought, one slot each,
                 with an "entry" ticket. Never sells on trend.

The rules themselves are pure (``regime_from_closes``, ``gate``); the rest reads the tables and builds tickets, which the
operator (live) or the paper fill (paper) then works. Every check is recorded in idx.regime_check.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import psycopg.types.json

from . import book as bk
from . import runlog

SMA_DAYS = 200
INDEX = "COMPOSITE"


def _rows(conn: psycopg.Connection, sql: str, params: tuple, cols: list[str]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        out = cur.fetchall()
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in out]


# ---------------------------------------------------------------------------
# pure rules
# ---------------------------------------------------------------------------
def regime_from_closes(closes: list[Any], days: int = SMA_DAYS) -> dict[str, Any]:
    """Oldest-first closes -> {close, sma, on}. Without ``days`` closes there is no average and the regime is on (no
    history is not a reason to sit out)."""
    if not closes:
        raise ValueError("no closes")
    last = Decimal(str(closes[-1]))
    if len(closes) < days:
        return {"close": last, "sma": None, "on": True, "n": len(closes)}
    window = [Decimal(str(c)) for c in closes[-days:]]
    sma = sum(window, Decimal(0)) / len(window)
    return {"close": last, "sma": sma, "on": last > sma, "n": len(closes)}


def take_profit_hits(positions: list[dict[str, Any]], prices: dict[str, Any], pct: Any) -> dict[str, str]:
    """Pure. Held names whose last close is at least ``pct`` % above their average purchase price -> {code: reason}."""
    if pct is None:
        return {}
    bar = Decimal(str(pct)) / 100
    out = {}
    for p in positions:
        c, avg = p["code"], p.get("avg_price")
        px = prices.get(c)
        if avg is None or px is None or Decimal(str(avg)) <= 0:
            continue
        gain = Decimal(str(px)) / Decimal(str(avg)) - 1
        if gain >= bar:
            out[c] = f"take profit: +{100 * gain:.0f} % over the purchase price (rule +{Decimal(str(pct)):.0f} %)"
    return out


def gate(targets: dict[str, Any], trend: dict[str, dict[str, Any]], held: set[str]) -> list[str]:
    """Pure. The names to hold back at a rebalance: listed, not already held, and under their 200-day average. A name
    without an average (young listing) is bought."""
    return [c for c in targets if c not in held and (t := trend.get(c)) is not None and t["sma"] is not None and not t["on"]]


# ---------------------------------------------------------------------------
# signals from the tables
# ---------------------------------------------------------------------------
def index_regime(conn: psycopg.Connection, D: date) -> dict[str, Any]:
    rows = _rows(conn, "SELECT trade_date AS d, close FROM idx.index_daily WHERE index_code = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT %s",
                 (INDEX, D, SMA_DAYS), ["d", "close"])
    if not rows:
        raise ValueError(f"no {INDEX} history on or before {D}")
    rows.reverse()
    r = regime_from_closes([x["close"] for x in rows])
    r.update({"check_date": rows[-1]["d"], "index_code": INDEX})
    return r


def name_trend(conn: psycopg.Connection, D: date, codes: list[str]) -> dict[str, dict[str, Any]]:
    """Per code: {close, sma, on} on the adjusted close series, as of D."""
    if not codes:
        return {}
    rows = _rows(conn, """
        SELECT code, trade_date AS d, c FROM (
            SELECT code, trade_date, close * adj_factor AS c, row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
              FROM idx.bar WHERE source = 'idx' AND code = ANY(%s) AND trade_date <= %s AND close IS NOT NULL) t
         WHERE rn <= %s ORDER BY code, trade_date""", (list(codes), D, SMA_DAYS), ["code", "d", "c"])
    by: dict[str, list[Any]] = {}
    for r in rows:
        by.setdefault(r["code"], []).append(r["c"])
    return {c: regime_from_closes(v) for c, v in by.items() if v}


def first_trading_day_of_month(conn: psycopg.Connection, D: date) -> bool:
    rows = _rows(conn, "SELECT min(trade_date) AS d FROM idx.bar WHERE source = 'idx' AND trade_date >= %s AND trade_date <= %s",
                 (D.replace(day=1), D), ["d"])
    return bool(rows and rows[0]["d"] == D)


# ---------------------------------------------------------------------------
# the record of checks
# ---------------------------------------------------------------------------
COLS = ["check_date", "index_code", "close", "sma", "regime_on", "detail", "created_at"]


def record(conn: psycopg.Connection, r: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.regime_check (check_date, index_code, close, sma, regime_on, detail)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (check_date) DO UPDATE SET close = EXCLUDED.close, sma = EXCLUDED.sma, regime_on = EXCLUDED.regime_on,
                           detail = EXCLUDED.detail""",
                    (r["check_date"], r["index_code"], r["close"], r["sma"], r["on"], psycopg.types.json.Jsonb({"n": r.get("n")})))
    conn.commit()


def _to_regime(row: dict[str, Any]) -> dict[str, Any]:
    return {"check_date": row["check_date"], "index_code": row["index_code"], "close": row["close"], "sma": row["sma"], "on": bool(row["regime_on"])}


def latest(conn: psycopg.Connection, before: date | None = None) -> dict[str, Any] | None:
    rows = _rows(conn, "SELECT check_date, index_code, close, sma, regime_on, detail, created_at FROM idx.regime_check "
                       "WHERE (%s::date IS NULL OR check_date < %s) ORDER BY check_date DESC LIMIT 1", (before, before), COLS)
    return _to_regime(rows[0]) if rows else None


def history(conn: psycopg.Connection, limit: int = 24) -> list[dict[str, Any]]:
    rows = _rows(conn, "SELECT check_date, index_code, close, sma, regime_on, detail, created_at FROM idx.regime_check ORDER BY check_date DESC LIMIT %s",
                 (limit,), COLS)
    return [_to_regime(r) for r in rows]


def current_list(conn: psycopg.Connection, book: str) -> dict[str, Any] | None:
    """The book's list: the latest rebalance ticket that was not cancelled (its weights and what was held back)."""
    rows = _rows(conn, "SELECT id, run_date, params FROM idx.ticket WHERE book = %s AND mode = 'rebalance' AND status <> 'cancelled' ORDER BY id DESC LIMIT 1",
                 (book,), ["id", "run_date", "params"])
    if not rows:
        return None
    p = rows[0]["params"] or {}
    return {"ticket_id": rows[0]["id"], "run_date": rows[0]["run_date"], "weights": p.get("weights") or {}, "targets": p.get("targets") or [],
            "held_back": p.get("held_back") or []}


# ---------------------------------------------------------------------------
# the monthly check
# ---------------------------------------------------------------------------
def monthly_check(conn: psycopg.Connection, D: date, build: bool = True) -> dict[str, Any]:
    """Record the regime as of D and, for every book with an overlay on, build the ticket it calls for. ``build=False``
    only reports. One report per book: action in {None, 'cash', 're-entry', 'entry'}."""
    from . import ticket as tk

    r = index_regime(conn, D)
    prev = latest(conn, r["check_date"])
    if build:
        record(conn, r)
    report: dict[str, Any] = {"regime": r, "previous_on": prev["on"] if prev else None, "books": []}
    for row in _rows(conn, "SELECT book FROM idx.book ORDER BY book", (), ["book"]):
        b = row["book"]
        meta = bk.get_book(conn, b)
        if not (meta.get("regime_filter") or meta.get("entry_gate") or meta.get("take_profit_pct")):
            continue
        positions = bk.snapshot(conn, b)["positions"]
        held = {p["code"] for p in positions}
        entry: dict[str, Any] = {"book": b, "action": None, "ticket": None, "names": []}
        report["books"].append(entry)
        if meta.get("regime_filter"):
            if not r["on"] and held:
                entry["action"] = "cash"
                if build:
                    res = tk.build(conn, b, mode="cash", run_date=D)
                    entry["ticket"] = tk.store(conn, res, notes=f"regime off on {r['check_date']}: to cash")
                    runlog.alert(conn, "warning", f"ticket:{b}", f"regime OFF ({INDEX} {r['close']:.0f} under its 200-day average "
                                 f"{r['sma']:.0f}): ticket #{entry['ticket']} sells the {b} book to cash")
            elif r["on"] and not held and prev is not None and not prev["on"]:
                entry["action"] = "re-entry"
                if build:
                    res = tk.build(conn, b, mode="rebalance", run_date=D)
                    entry["ticket"] = tk.store(conn, res, notes=f"regime on again on {r['check_date']}: back into the list")
                    runlog.alert(conn, "info", f"ticket:{b}", f"regime ON ({INDEX} {r['close']:.0f} above its 200-day average "
                                 f"{r['sma']:.0f}): ticket #{entry['ticket']} buys the {b} book back")
            if not r["on"]:
                continue
        if meta.get("take_profit_pct") and held:
            px = {r["code"]: r["close"] for r in _rows(conn, """SELECT DISTINCT ON (code) code, close FROM idx.bar
                       WHERE code = ANY(%s) AND source = 'idx' AND trade_date <= %s ORDER BY code, trade_date DESC""", (sorted(held), D), ["code", "close"])}
            hits = take_profit_hits(positions, px, meta["take_profit_pct"])
            if hits:
                entry["action"] = (entry["action"] + "+" if entry["action"] else "") + "take-profit"
                entry["names"] = entry["names"] + sorted(hits)
                if build:
                    res = tk.build(conn, b, mode="exits", run_date=D, exits=hits)
                    tid = tk.store(conn, res, notes=f"take profit on {r['check_date']}: {', '.join(sorted(hits))}")
                    entry["ticket"] = tid if entry["ticket"] is None else entry["ticket"]
                    runlog.alert(conn, "info", f"ticket:{b}", f"take profit: {', '.join(sorted(hits))} at least {meta['take_profit_pct']:.0f} % over "
                                 f"their purchase price; ticket #{tid} sells them from the {b} book")
        if meta.get("entry_gate"):
            cur = current_list(conn, b)
            back = [c for c in (cur or {}).get("held_back", []) if c not in held]
            if back:
                trend = name_trend(conn, D, back)
                ready = [c for c in back if c in trend and trend[c]["on"]]
                if ready:
                    entry["action"], entry["names"] = "entry", ready
                    if build:
                        res = tk.build(conn, b, mode="entry", run_date=D, entrants=ready)
                        entry["ticket"] = tk.store(conn, res, notes=f"entry gate on {r['check_date']}: {', '.join(ready)} crossed above their 200-day average")
                        runlog.alert(conn, "info", f"ticket:{b}", f"entry gate: {', '.join(ready)} crossed above their 200-day average; "
                                     f"ticket #{entry['ticket']} buys them into the {b} book")
    return report


def render(report: dict[str, Any]) -> str:
    r = report["regime"]
    sma = f"{r['sma']:,.0f}" if r["sma"] is not None else "n/a"
    o = [f"# regime check {r['check_date']}: {INDEX} {r['close']:,.0f} vs 200-day average {sma} -> {'ON (invested)' if r['on'] else 'OFF (cash)'}"
         + (f"  (previous check: {'on' if report['previous_on'] else 'off'})" if report["previous_on"] is not None else "")]
    for b in report["books"]:
        what = b["action"] or "nothing to do"
        if b["names"]:
            what += ": " + ", ".join(b["names"])
        if b["ticket"]:
            what += f" -> ticket #{b['ticket']}"
        o.append(f"  {b['book']:6s} {what}")
    if not report["books"]:
        o.append("  (no book has an overlay on)")
    return "\n".join(o)
