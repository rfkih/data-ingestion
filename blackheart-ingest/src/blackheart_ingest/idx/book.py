"""Position book — the operator's real holdings (``live``, fills entered by hand from the broker) and the paper track
(``paper``, hypothetical fills at the next open). Positions are rebuilt from fills (average cost, fees in the basis);
marks and NAV are derived per trading day from ``idx.bar`` with net dividends credited on the ex-date; corporate actions
become ``split`` fills so lots and cost stay consistent. ``check`` raises deduplicated ``idx.alert`` rows for held names:
material disclosures, a new report breaking the book rule, a drawdown past the threshold, liquidity gone.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from . import runlog
from .card import _pct, _rows, _t
from .metrics import LIQ, fundamentals_asof

logger = logging.getLogger(__name__)
LOT = 100
TREND_TRAIL = Decimal("0.10")               # the trend rule sells 10 % under the peak close since entry (see trend_book.TRAIL)
WIB = ZoneInfo("Asia/Jakarta")
DRAWDOWN_ALERT = Decimal("0.25")
ALERT_KINDS = ("exchange_query", "suspension", "rights", "control_change", "legal", "auditor", "affiliated_tx", "material_info",
               "corporate_action", "buyback", "management")
Q2 = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(Q2, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# pure: fills -> positions
# ---------------------------------------------------------------------------
def apply_fill(pos: dict[str, Any] | None, f: dict[str, Any]) -> dict[str, Any] | None:
    """Average-cost bookkeeping. pos = {lots, avg_price, cost_basis, realized_pnl, dividends, opened_at, last_fill_at} or None."""
    lots, price, fee = Decimal(f["lots"]), Decimal(f["price"]), Decimal(f.get("fee") or 0)
    d = f["trade_date"]
    if f["side"] == "split":                        # new lot count and new average, value unchanged
        if not pos:
            return None
        return {**pos, "lots": lots, "avg_price": price, "last_fill_at": d}
    if f["side"] == "buy":
        if not pos or pos["lots"] == 0:
            cost = lots * LOT * price + fee
            return {"lots": lots, "avg_price": cost / (lots * LOT), "cost_basis": cost, "realized_pnl": Decimal(pos["realized_pnl"]) if pos else Decimal(0),
                    "dividends": Decimal(pos["dividends"]) if pos else Decimal(0), "opened_at": d, "last_fill_at": d}
        cost = Decimal(pos["cost_basis"]) + lots * LOT * price + fee
        new_lots = Decimal(pos["lots"]) + lots
        return {**pos, "lots": new_lots, "avg_price": cost / (new_lots * LOT), "cost_basis": cost, "last_fill_at": d}
    if f["side"] == "sell":
        if not pos or Decimal(pos["lots"]) < lots:
            raise ValueError(f"sell {lots} lots of {f['code']} on {d}: only {pos['lots'] if pos else 0} held")
        avg = Decimal(pos["avg_price"])
        proceeds = lots * LOT * price - fee
        realized = proceeds - lots * LOT * avg
        new_lots = Decimal(pos["lots"]) - lots
        return {**pos, "lots": new_lots, "cost_basis": new_lots * LOT * avg, "realized_pnl": Decimal(pos["realized_pnl"]) + realized,
                "last_fill_at": d}
    raise ValueError(f"unknown side {f['side']!r}")


def positions_from(fills: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for f in sorted(fills, key=lambda x: (x["trade_date"], x["id"] if "id" in x else 0)):
        p = apply_fill(out.get(f["code"]), f)
        if p is None:
            continue
        out[f["code"]] = p
    return out


def default_fee(gross: Decimal, side: str, book: dict[str, Any]) -> Decimal:
    pct = Decimal(book["fee_buy_pct"] if side == "buy" else book["fee_sell_pct"])
    return _q(gross * pct / 100)


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------
LIMIT_FIELDS = ("max_weight_pct", "max_sector_pct", "max_turnover_pct", "min_v60")
SETTABLE_FIELDS = ("cash", "fee_buy_pct", "fee_sell_pct", "div_tax_pct", "broker", "note", "strategy", "max_names", "regime_filter", "entry_gate",
                   "take_profit_pct", "trend_exit", "cash_floor_pct", "stress_cash_pct", "stress_rule", "label", "rule", "trend_variant", "params",
                   *LIMIT_FIELDS)
RULES = ("annual", "trend", "gapfade", "combo")   # annual = the value list rebalanced in May; trend = breakout + trailing stop, daily;
                                           # gapfade = buy the opening gap-down, sell into the same close (intraday, paper only)
                                           # combo = one cash pool, three sleeves (gap-fade, trend, ML) sized from book.params (combo_book.py)
KINDS = ("paper", "live")
AGENT_SETTABLE_FIELDS = ("note",)          # everything else on a book is the operator's (strategy, size, cash, fees, overlays, limits)


def get_book(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    rows = _rows(conn, "SELECT book, cash, fee_buy_pct, fee_sell_pct, div_tax_pct, broker, note, strategy, max_names, regime_filter, entry_gate, "
                       "take_profit_pct, trend_exit, cash_floor_pct, stress_cash_pct, stress_rule, status, halted_at, halt_reason, "
                       "max_weight_pct, max_sector_pct, max_turnover_pct, min_v60, owner_id, label, rule, trend_variant, archived_at, created_at, params "
                       "FROM idx.book WHERE book = %s",
                 (book,), ["book", "cash", "fee_buy_pct", "fee_sell_pct", "div_tax_pct", "broker", "note", "strategy", "max_names", "regime_filter", "entry_gate",
                           "take_profit_pct", "trend_exit", "cash_floor_pct", "stress_cash_pct", "stress_rule", "status", "halted_at", "halt_reason",
                           "max_weight_pct", "max_sector_pct", "max_turnover_pct", "min_v60", "owner_id", "label", "rule", "trend_variant", "archived_at",
                           "created_at", "params"])
    if rows and rows[0].get("owner_id") is not None:
        rows[0]["owner_id"] = str(rows[0]["owner_id"])
    if not rows:
        raise ValueError(f"no book {book!r}")
    return rows[0]


def ensure_book(conn: psycopg.Connection, book: str, **fields: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO idx.book (book) VALUES (%s) ON CONFLICT (book) DO NOTHING", (book,))
        if cur.rowcount == 1 and "strategy" not in fields:                # a new book follows the deployed strategy
            from .strategies import deployed
            cur.execute("UPDATE idx.book SET strategy = %s WHERE book = %s", (deployed(), book))
        for k, v in fields.items():
            if k in SETTABLE_FIELDS:
                if k in ("cash_floor_pct", "stress_cash_pct") and v is not None and not 0 <= Decimal(str(v)) <= 80:
                    raise ValueError(f"{k} must be between 0 and 80")
                if k in LIMIT_FIELDS:
                    v = Decimal(str(v))
                    if k != "min_v60" and not 0 < v <= 100:
                        raise ValueError(f"{k} must be a percent in (0, 100]")
                    if k == "min_v60" and v < 0:
                        raise ValueError("min_v60 must be >= 0")
                if k == "stress_rule" and v not in ("ma", "any2"):
                    raise ValueError("stress_rule must be 'ma' or 'any2'")
                if k == "take_profit_pct":
                    v = None if v in (None, "", 0, "0") else Decimal(str(v))
                    if v is not None and v <= 0:
                        raise ValueError("take_profit_pct must be positive, or empty to switch it off")
                if k in ("regime_filter", "entry_gate", "trend_exit"):
                    v = v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "t", "yes", "on")
                if k == "strategy":
                    from .strategies import get as _get_strategy
                    _get_strategy(str(v))                                # ValueError on an unknown key
                if k == "max_names":
                    v = int(v) if v not in (None, "", 0, "0") else None
                if k == "rule" and v not in RULES:
                    raise ValueError(f"rule must be one of {RULES}")
                if k == "trend_variant":
                    v = (str(v).strip().lower() or None) if v is not None else None
                    if v is not None and v not in ("small", "all"):
                        raise ValueError("trend_variant must be 'small' or 'all'")
                if k == "label":
                    v = (str(v).strip()[:60] or None) if v is not None else None
                if k == "params":
                    if isinstance(v, str):
                        v = json.loads(v) if v.strip() else {}
                    if not isinstance(v, dict):
                        raise ValueError("params must be a JSON object")
                    v = psycopg.types.json.Jsonb(v)
                cur.execute(f"UPDATE idx.book SET {k} = %s, updated_at = now() WHERE book = %s", (v, book))
    conn.commit()


def create_book(conn: psycopg.Connection, owner_id: str | None, kind: str, label: str, **fields: Any) -> str:
    """A new book for an account: id ``<kind>-<6 hex>`` (the kind prefix is what ``ticket.is_live`` keys off), the label is
    what its owner sees. Returns the id."""
    import secrets
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not (label or "").strip():
        raise ValueError("label is required")
    with conn.cursor() as cur:
        for _ in range(20):
            book = f"{kind}-{secrets.token_hex(3)}"
            cur.execute("INSERT INTO idx.book (book, owner_id, label) VALUES (%s, %s, %s) ON CONFLICT (book) DO NOTHING", (book, owner_id, label.strip()[:60]))
            if cur.rowcount == 1:
                break
        else:                                                              # pragma: no cover - 16 M ids per kind
            raise RuntimeError("could not allocate a book id")
    conn.commit()
    ensure_book(conn, book, **fields)
    return book


def list_books(conn: psycopg.Connection, owner_id: str | None = None, *, include_archived: bool = False, include_test: bool = False) -> list[str]:
    """Book ids, an owner's or everyone's (owner_id None), live first then by label."""
    with conn.cursor() as cur:
        cur.execute("""SELECT book FROM idx.book
                        WHERE (%s::uuid IS NULL OR owner_id = %s::uuid) AND (%s OR archived_at IS NULL) AND (%s OR book NOT LIKE 'test%%')
                        ORDER BY (book LIKE 'paper%%'), rule, label NULLS LAST, book""",
                    (owner_id, owner_id, include_archived, include_test))
        return [r["book"] if isinstance(r, dict) else r[0] for r in cur.fetchall()]


def owner_of(conn: psycopg.Connection, book: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT owner_id FROM idx.book WHERE book = %s", (book,))
        r = cur.fetchone()
    if not r:
        return None
    v = r["owner_id"] if isinstance(r, dict) else r[0]
    return str(v) if v else None


def archive(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    """Close a book: it keeps its history but leaves every list and every nightly job."""
    b = get_book(conn, book)
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.book SET archived_at = now(), updated_at = now() WHERE book = %s AND archived_at IS NULL", (book,))
        cur.execute("UPDATE idx.ticket SET status = 'cancelled' WHERE book = %s AND status IN ('draft', 'issued')", (book,))
    conn.commit()
    return {**b, "archived_at": datetime.now(UTC)}


def unarchive(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    """Reopen an archived book: it rejoins every list and every nightly job (marks, checks, price levels). Tickets that
    ``archive`` cancelled stay cancelled - a reopened book drafts fresh ones. Added 2026-09-23 after the IPOT book was
    archived by a mis-tap on 09-18 and its stop/take-profit levels went unwatched for five sessions."""
    b = get_book(conn, book)
    if b.get("archived_at") is None:
        return b
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.book SET archived_at = NULL, updated_at = now() WHERE book = %s AND archived_at IS NOT NULL", (book,))
    conn.commit()
    return {**b, "archived_at": None}


def is_halted(b: dict[str, Any]) -> bool:
    return (b.get("status") or "active") == "halted"


def halt(conn: psycopg.Connection, book: str, reason: str) -> dict[str, Any]:
    """Kill switch: no ticket is built or issued and no paper fill runs on a halted book until ``resume``. Fills entered by
    hand still record (they are facts about the broker account, not decisions)."""
    get_book(conn, book)
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.book SET status = 'halted', halted_at = now(), halt_reason = %s, updated_at = now() WHERE book = %s", (reason, book))
    conn.commit()
    return get_book(conn, book)


def resume(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    get_book(conn, book)
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.book SET status = 'active', halted_at = NULL, halt_reason = NULL, updated_at = now() WHERE book = %s", (book,))
    conn.commit()
    return get_book(conn, book)


def add_fill(conn: psycopg.Connection, book: str, trade_date: date, code: str, side: str, lots: Decimal, price: Decimal,
             fee: Decimal | None = None, source: str = "manual", note: str | None = None, adjust_cash: bool = True) -> int:
    b = get_book(conn, book)
    code, side = code.upper(), side.lower()
    gross = Decimal(lots) * LOT * Decimal(price)
    if fee is None:
        fee = default_fee(gross, side, b) if side in ("buy", "sell") else Decimal(0)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.fill (book, trade_date, code, side, lots, price, fee, source, note)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (book, trade_date, code, side, lots, price, fee, source, note))
        row = cur.fetchone()
        fid = int(next(iter(row.values())) if isinstance(row, dict) else row[0])
    conn.commit()
    if adjust_cash and side in ("buy", "sell"):
        delta = -(gross + fee) if side == "buy" else (gross - fee)
        with conn.cursor() as cur:
            cur.execute("UPDATE idx.book SET cash = cash + %s, updated_at = now() WHERE book = %s", (delta, book))
        conn.commit()
    rebuild_positions(conn, book)
    return fid


def rebuild_positions(conn: psycopg.Connection, book: str) -> dict[str, dict[str, Any]]:
    fills = _rows(conn, "SELECT id, trade_date, code, side, lots, price, fee FROM idx.fill WHERE book = %s ORDER BY trade_date, id", (book,),
                  ["id", "trade_date", "code", "side", "lots", "price", "fee"])
    divs = _rows(conn, "SELECT code, sum(dividends) AS d FROM idx.position WHERE book = %s GROUP BY code", (book,), ["code", "d"])
    kept = {d["code"]: Decimal(d["d"]) for d in divs}
    pos = positions_from(fills)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.position WHERE book = %s", (book,))
        for code, p in pos.items():
            if p["lots"] <= 0 and p["realized_pnl"] == 0:
                continue
            cur.execute("""INSERT INTO idx.position (book, code, lots, avg_price, cost_basis, realized_pnl, dividends, opened_at, last_fill_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (book, code, p["lots"], _q(Decimal(p["avg_price"])), _q(Decimal(p["cost_basis"])), _q(Decimal(p["realized_pnl"])),
                         kept.get(code, Decimal(0)), p["opened_at"], p["last_fill_at"]))
    conn.commit()
    return pos


def positions_asof(conn: psycopg.Connection, book: str, d: date) -> dict[str, dict[str, Any]]:
    """Positions from the fills dated on or before ``d`` - what the book held at that day's close (marks must use this,
    not the current ``idx.position``, or a re-mark after back-dated fills paints today's book over the past)."""
    fills = _rows(conn, "SELECT id, trade_date, code, side, lots, price, fee FROM idx.fill WHERE book = %s AND trade_date <= %s ORDER BY trade_date, id",
                  (book, d), ["id", "trade_date", "code", "side", "lots", "price", "fee"])
    return positions_from(fills)


def import_csv(conn: psycopg.Connection, book: str, path: str | Path) -> int:
    """The research ledger format: date,code,side,lots,price,fee_pct,note (fee_pct optional -> book default)."""
    n = 0
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            gross = Decimal(r["lots"]) * LOT * Decimal(r["price"])
            fee = _q(gross * Decimal(r["fee_pct"]) / 100) if r.get("fee_pct") else None
            add_fill(conn, book, date.fromisoformat(r["date"]), r["code"], r["side"], Decimal(r["lots"]), Decimal(r["price"]), fee,
                     source="import", note=r.get("note") or None)
            n += 1
    return n


# ---------------------------------------------------------------------------
# marks, NAV, corporate actions, dividends
# ---------------------------------------------------------------------------
def _trading_days(conn: psycopg.Connection, start: date, end: date) -> list[date]:
    return [r["d"] for r in _rows(conn, "SELECT DISTINCT trade_date FROM idx.bar WHERE source IN ('idx', 'yahoo') AND trade_date BETWEEN %s AND %s ORDER BY 1",
                                  (start, end), ["d"])]


def _fill_cash_deltas(conn: psycopg.Connection, book: str) -> dict[date, Decimal]:
    out: dict[date, Decimal] = {}
    for f in _rows(conn, "SELECT trade_date, side, lots, price, fee FROM idx.fill WHERE book = %s AND side IN ('buy', 'sell')", (book,),
                   ["d", "side", "lots", "price", "fee"]):
        gross = Decimal(f["lots"]) * LOT * Decimal(f["price"])
        delta = -(gross + Decimal(f["fee"])) if f["side"] == "buy" else gross - Decimal(f["fee"])
        out[f["d"]] = out.get(f["d"], Decimal(0)) + delta
    return out


def reset_marks(conn: psycopg.Connection, book: str) -> None:
    """Drop marks/NAV and the dividends they credited (so a re-mark starts clean); fills and positions stay."""
    with conn.cursor() as cur:
        cur.execute("SELECT coalesce(sum(dividends), 0) FROM idx.book_nav WHERE book = %s", (book,))
        row = cur.fetchone()
        credited = Decimal(next(iter(row.values())) if isinstance(row, dict) else row[0])
        cur.execute("UPDATE idx.book SET cash = cash - %s, updated_at = now() WHERE book = %s", (credited, book))
        cur.execute("UPDATE idx.position SET dividends = 0 WHERE book = %s", (book,))
        cur.execute("DELETE FROM idx.book_mark WHERE book = %s", (book,))
        cur.execute("DELETE FROM idx.book_nav WHERE book = %s", (book,))
        cur.execute("DELETE FROM idx.fill WHERE book = %s AND source = 'corporate_action'", (book,))
    conn.commit()
    rebuild_positions(conn, book)


def mark(conn: psycopg.Connection, book: str, as_of: date | None = None, rebuild: bool = False) -> runlog.RunResult:
    """Mark every trading day from the day after the last mark (or the first fill) to as_of: splits -> fills, dividends ->
    cash, a mark per position, a NAV row. Cash on a day = the day before + that day's fill deltas + net dividends, anchored
    on the live book.cash (which already reflects every fill). ``rebuild`` recomputes from the first fill."""
    r = runlog.RunResult("book:mark", book)
    run_id = runlog.start(conn, "book:mark", book)
    try:
        if rebuild:
            reset_marks(conn, book)
        b = get_book(conn, book)
        first = _rows(conn, "SELECT min(trade_date) FROM idx.fill WHERE book = %s", (book,), ["d"])[0]["d"]
        last_bar = _rows(conn, "SELECT max(trade_date) FROM idx.bar WHERE source IN ('idx', 'yahoo') AND (%s::date IS NULL OR trade_date <= %s)",
                         (as_of, as_of), ["d"])[0]["d"]
        if first is None or last_bar is None:
            r.status = "skipped"
            r.detail["reason"] = "no fills"
            runlog.finish(conn, run_id, r)
            return r
        last = _rows(conn, "SELECT trade_date, cash FROM idx.book_nav WHERE book = %s ORDER BY trade_date DESC LIMIT 1", (book,), ["d", "cash"])
        deltas = _fill_cash_deltas(conn, book)
        credited = _rows(conn, "SELECT coalesce(sum(dividends), 0) AS s FROM idx.book_nav WHERE book = %s", (book,), ["s"])[0]["s"]
        if last:
            start, cash = last[0]["d"] + timedelta(days=1), Decimal(last[0]["cash"])     # fills dated before this need --rebuild
        else:
            start, cash = first, Decimal(b["cash"]) - sum(deltas.values(), Decimal(0)) - Decimal(credited)
        days = _trading_days(conn, start, last_bar)
        tax = Decimal(b["div_tax_pct"]) / 100
        n_days = 0
        splits_added = False
        prev_d = start - timedelta(days=1)
        for d in days:
            cash += sum((v for k, v in deltas.items() if prev_d < k <= d), Decimal(0))   # fills dated on a holiday/weekend land on the next bar
            prev_d = d
            pos = positions_asof(conn, book, d)
            held = {c: p for c, p in pos.items() if p["lots"] > 0}
            if held:
                acts = _rows(conn, "SELECT code, kind, factor FROM idx.corporate_action WHERE ex_date = %s AND code = ANY(%s) AND kind IN ('split', 'reverse_split')",
                             (d, list(held)), ["code", "kind", "factor"])
                for a in acts:
                    p = held[a["code"]]
                    factor = Decimal(a["factor"])
                    new_lots = (Decimal(p["lots"]) / factor).quantize(Q2, rounding=ROUND_HALF_UP)
                    add_fill(conn, book, d, a["code"], "split", new_lots, _q(Decimal(p["avg_price"]) * factor), Decimal(0),
                             source="corporate_action", note=f"{a['kind']} factor {factor}", adjust_cash=False)
                if acts:
                    splits_added = True
                    pos = positions_asof(conn, book, d)
                    held = {c: p for c, p in pos.items() if p["lots"] > 0}
            div_cash = Decimal(0)
            if held:
                for x in _rows(conn, "SELECT code, amount_per_share FROM idx.dividend WHERE ex_date = %s AND code = ANY(%s) AND kind = 'cash'",
                               (d, list(held)), ["code", "dps"]):
                    net = _q(Decimal(held[x["code"]]["lots"]) * LOT * Decimal(x["dps"]) * (1 - tax))
                    div_cash += net
                    with conn.cursor() as cur:
                        cur.execute("UPDATE idx.position SET dividends = dividends + %s WHERE book = %s AND code = %s", (net, book, x["code"]))
            cash += div_cash
            closes = {c["code"]: Decimal(c["close"]) for c in _rows(conn, "SELECT code, close FROM idx.bar WHERE trade_date = %s AND code = ANY(%s) AND source IN ('idx', 'yahoo')",
                                                                   (d, list(held)), ["code", "close"])} if held else {}
            total = Decimal(0)
            with conn.cursor() as cur:
                for code, p in held.items():
                    px = closes.get(code)
                    if px is None:                          # no bar (suspended, or not traded): carry the last mark
                        prev = _rows(conn, "SELECT close FROM idx.book_mark WHERE book = %s AND code = %s AND trade_date < %s ORDER BY trade_date DESC LIMIT 1",
                                     (book, code, d), ["close"])
                        px = Decimal(prev[0]["close"]) if prev and prev[0]["close"] is not None else Decimal(p["avg_price"])
                    val = _q(Decimal(p["lots"]) * LOT * px)
                    total += val
                    cost = _q(Decimal(p["cost_basis"]))
                    cur.execute("""INSERT INTO idx.book_mark (book, trade_date, code, lots, close, value, cost_basis, unrealized)
                                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                   ON CONFLICT (book, trade_date, code) DO UPDATE SET lots = EXCLUDED.lots, close = EXCLUDED.close,
                                       value = EXCLUDED.value, cost_basis = EXCLUDED.cost_basis, unrealized = EXCLUDED.unrealized""",
                                (book, d, code, p["lots"], px, val, cost, val - cost))
                cur.execute("""INSERT INTO idx.book_nav (book, trade_date, cash, positions, nav, n_positions, dividends)
                               VALUES (%s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (book, trade_date) DO UPDATE SET cash = EXCLUDED.cash, positions = EXCLUDED.positions,
                                   nav = EXCLUDED.nav, n_positions = EXCLUDED.n_positions, dividends = EXCLUDED.dividends""",
                            (book, d, cash, total, cash + total, len(held), div_cash))
                if div_cash:
                    cur.execute("UPDATE idx.book SET cash = cash + %s, updated_at = now() WHERE book = %s", (div_cash, book))
            conn.commit()
            n_days += 1
        if splits_added:                                     # the split fills changed today's lots/avg: refresh idx.position
            rebuild_positions(conn, book)
        r.rows_out = n_days
        r.detail = {"from": str(days[0]) if days else None, "to": str(days[-1]) if days else None}
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx book mark failed")
    runlog.finish(conn, run_id, r)
    return r


def capital(conn: psycopg.Connection, book: str) -> Decimal:
    """What was put into the book, reconstructed from the cash it holds now. Cash only ever moves by a fill
    (buy -(gross+fee), sell +(gross-fee)) and by a credited dividend, so undoing both gives the starting cash.
    The first NAV point is NOT the capital: it is already after the first day's fills and marks."""
    row = _rows(conn, """
        SELECT b.cash
             + coalesce((SELECT sum(CASE WHEN f.side = 'buy' THEN f.lots * 100 * f.price + f.fee
                                         WHEN f.side = 'sell' THEN -(f.lots * 100 * f.price - f.fee) ELSE 0 END)
                           FROM idx.fill f WHERE f.book = b.book), 0)
             - coalesce((SELECT sum(n.dividends) FROM idx.book_nav n WHERE n.book = b.book), 0) AS capital
          FROM idx.book b WHERE b.book = %s""", (book,), ["capital"])
    return Decimal(row[0]["capital"]) if row and row[0]["capital"] is not None else Decimal(0)


def snapshot(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    b = get_book(conn, book)
    pos = _rows(conn, """
        SELECT p.code, l.name, p.lots, p.avg_price, p.cost_basis, p.realized_pnl, p.dividends, p.opened_at,
               m.trade_date AS mark_date, m.close, m.value, m.unrealized,
               (SELECT max(bb.close) FROM idx.bar bb WHERE bb.code = p.code AND bb.source = 'idx' AND bb.trade_date >= p.opened_at) AS peak
          FROM idx.position p LEFT JOIN idx.listing l USING (code)
          LEFT JOIN LATERAL (SELECT trade_date, close, value, unrealized FROM idx.book_mark WHERE book = p.book AND code = p.code
                             ORDER BY trade_date DESC LIMIT 1) m ON true
         WHERE p.book = %s AND p.lots > 0 ORDER BY m.value DESC NULLS LAST, p.code""", (book,),
        ["code", "name", "lots", "avg_price", "cost_basis", "realized_pnl", "dividends", "opened_at", "mark_date", "close", "value", "unrealized", "peak"])
    closed = _rows(conn, "SELECT code, realized_pnl, dividends FROM idx.position WHERE book = %s AND lots = 0", (book,), ["code", "realized_pnl", "dividends"])
    nav = _rows(conn, "SELECT trade_date, cash, positions, nav, n_positions, dividends FROM idx.book_nav WHERE book = %s ORDER BY trade_date DESC LIMIT 260",
                (book,), ["trade_date", "cash", "positions", "nav", "n_positions", "dividends"])
    nav.reverse()
    cand = {c["code"]: c for c in _rows(conn, """
        SELECT code, rank, selected FROM idx.candidate WHERE run_date = (SELECT max(run_date) FROM idx.candidate)""", (), ["code", "rank", "selected"])}
    for p in pos:
        p["candidate_rank"] = cand.get(p["code"], {}).get("rank")
        p["candidate_selected"] = bool(cand.get(p["code"], {}).get("selected"))
        p["pnl_pct"] = (Decimal(p["unrealized"]) / Decimal(p["cost_basis"])) if p["unrealized"] is not None and Decimal(p["cost_basis"]) else None
        # trailing-stop gauge (the trend rule's 10 % under the peak close since entry; meaningful for trend books,
        # computed for all): high-water peak, the stop it implies, and how far the last close sits above it
        peak = Decimal(p["peak"]) if p.get("peak") is not None else None
        close = Decimal(p["close"]) if p["close"] is not None else None
        p["high"] = peak
        p["stop"] = (peak * (Decimal(1) - TREND_TRAIL)) if peak is not None else None
        p["dist_to_stop"] = ((close - p["stop"]) / close) if (close and p["stop"] is not None) else None
    total_val = sum(Decimal(p["value"] or 0) for p in pos)
    for p in pos:
        p["weight"] = (Decimal(p["value"] or 0) / (total_val + Decimal(b["cash"]))) if (total_val + Decimal(b["cash"])) else None
    return {"book": b, "positions": pos, "closed": closed, "nav": nav, "positions_value": total_val,
            "nav_now": total_val + Decimal(b["cash"]), "first_nav": Decimal(nav[0]["nav"]) if nav else None}


def render(s: dict[str, Any]) -> str:
    b = s["book"]
    o = [f"# Book {b['book']}  |  cash Rp {float(b['cash']):,.0f}  |  positions Rp {float(s['positions_value']):,.0f}  |  NAV Rp {float(s['nav_now']):,.0f}"]
    if s["first_nav"]:
        o.append(f"since {s['nav'][0]['trade_date']}: {_pct(s['nav_now'] / s['first_nav'] - 1)} | fees buy {b['fee_buy_pct']}% sell {b['fee_sell_pct']}% | div tax {b['div_tax_pct']}%")
    o += ["", "| code | lots | avg | last | value | weight | P&L | P&L % | div (net) | since | cand. |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in s["positions"]:
        cand = f"#{p['candidate_rank']}{'*' if p['candidate_selected'] else ''}" if p["candidate_rank"] else "-"
        last = f"{float(p['close']):,.0f}" if p["close"] is not None else "-"
        o.append(f"| {p['code']} | {float(p['lots']):g} | {float(p['avg_price']):,.0f} | {last} | "
                 f"{float(p['value'] or 0):,.0f} | {_pct(p['weight'], 1)} | {float(p['unrealized'] or 0):+,.0f} | {_pct(p['pnl_pct'])} | "
                 f"{float(p['dividends']):,.0f} | {p['opened_at']} | {cand} |")
    if s["closed"]:
        o += ["", "closed: " + ", ".join(f"{c['code']} {float(c['realized_pnl']):+,.0f}" for c in s["closed"])]
    return "\n".join(o)


# ---------------------------------------------------------------------------
# paper track
# ---------------------------------------------------------------------------
def paper_seed(conn: psycopg.Connection, book: str, run_date: date, cash: Decimal, fill: str = "next_open") -> list[dict[str, Any]]:
    """Buy the selected candidates of ``run_date`` equal-weight (whole lots) at the next open (or that close)."""
    ensure_book(conn, book, cash=cash)
    sel = [c["code"] for c in _rows(conn, "SELECT code FROM idx.candidate WHERE run_date = %s AND selected ORDER BY rank", (run_date,), ["code"])]
    if not sel:
        raise ValueError(f"no selected candidates for {run_date}; run `idx candidates --as-of {run_date}` first")
    if fill == "next_open":
        nxt = _rows(conn, "SELECT min(trade_date) FROM idx.bar WHERE source IN ('idx', 'yahoo') AND trade_date > %s", (run_date,), ["d"])[0]["d"]
        px = {p["code"]: (p["open"] if p["open"] else p["close"]) for p in _rows(conn, "SELECT code, open, close FROM idx.bar WHERE trade_date = %s AND code = ANY(%s) AND source IN ('idx', 'yahoo')",
                                                                                     (nxt, sel), ["code", "open", "close"])}
        d = nxt
    else:
        px = {p["code"]: p["close"] for p in _rows(conn, "SELECT code, close FROM idx.bar WHERE trade_date = %s AND code = ANY(%s) AND source IN ('idx', 'yahoo')",
                                                   (run_date, sel), ["code", "close"])}
        d = run_date
    b = get_book(conn, book)
    per_name = Decimal(cash) / len(sel)
    fills = []
    for code in sel:
        p = Decimal(px[code]) if px.get(code) else None
        if not p:
            continue
        lots = int((per_name / (1 + Decimal(b["fee_buy_pct"]) / 100)) // (p * LOT))
        if lots <= 0:
            continue
        add_fill(conn, book, d, code, "buy", Decimal(lots), p, None, source="paper", note=f"paper seed from candidates {run_date}")
        fills.append({"code": code, "lots": lots, "price": p, "date": d})
    return fills


# ---------------------------------------------------------------------------
# holding alerts
# ---------------------------------------------------------------------------
def _alert_once(conn: psycopg.Connection, severity: str, job: str, message: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM idx.alert WHERE job = %s AND message = %s AND acknowledged_at IS NULL", (job, message))
        if cur.fetchone():
            return False
    runlog.alert(conn, severity, job, message)
    return True


def check(conn: psycopg.Connection, book: str, since_days: int = 3) -> runlog.RunResult:
    """Raise alerts for held names: material disclosures in the last ``since_days``, a new report breaking the book rule or
    with thesis-break warnings, unrealized loss beyond DRAWDOWN_ALERT, liquidity below the universe floor."""
    r = runlog.RunResult("book:check", book)
    run_id = runlog.start(conn, "book:check", book)
    try:
        s = snapshot(conn, book)
        held = [p["code"] for p in s["positions"]]
        job = f"book:{book}"
        n = 0
        if held:
            D = s["positions"][0]["mark_date"] or date.today()
            since = datetime.combine(D - timedelta(days=since_days), datetime.min.time(), tzinfo=WIB)
            for a in _rows(conn, """SELECT code, kind, title, published_at FROM idx.announcement WHERE code = ANY(%s) AND published_at > %s AND kind = ANY(%s)
                                    ORDER BY published_at DESC""", (held, since, list(ALERT_KINDS)), ["code", "kind", "title", "pub"]):
                n += _alert_once(conn, "warning" if a["kind"] in ("exchange_query", "suspension", "legal", "auditor", "control_change") else "info", job,
                                 f"held {a['code']}: [{a['kind']}] {a['pub'].astimezone(WIB).date()} {(a['title'] or '')[:120]}")
            fund = fundamentals_asof(conn, D, held)
            for code, m in fund.items():
                newest = max(x for x in (m.get("annual_pub"), m.get("quarter_pub")) if x)
                if newest < D - timedelta(days=since_days):
                    continue
                if not m["gate_loose"]:
                    n += _alert_once(conn, "warning", job, f"held {code}: new report {newest} breaks the book rule ({', '.join(m['strict_fails'])})")
                elif m["warnings"]:
                    n += _alert_once(conn, "warning", job, f"held {code}: new report {newest} warnings {', '.join(m['warnings'])}")
            liq = {x["code"]: x["v60"] for x in _rows(conn, "SELECT code, value_60d_median AS v60 FROM idx.feature_daily WHERE trade_date = %s AND code = ANY(%s)",
                                                       (D, held), ["code", "v60"])}
            for p in s["positions"]:
                if p["pnl_pct"] is not None and p["pnl_pct"] <= -DRAWDOWN_ALERT:
                    n += _alert_once(conn, "warning", job, f"held {p['code']}: {_pct(p['pnl_pct'])} vs average cost {float(p['avg_price']):,.0f}")
                v = liq.get(p["code"])
                if v is not None and Decimal(v) < LIQ / 2:
                    n += _alert_once(conn, "info", job, f"held {p['code']}: 60-day median value Rp {_t(v, 1e9, 1)} bn/day, below half the universe floor")
        r.rows_in, r.rows_out = len(held), n
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx book check failed")
    runlog.finish(conn, run_id, r)
    return r
