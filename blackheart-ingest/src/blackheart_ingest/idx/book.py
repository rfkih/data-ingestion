"""Position book — the operator's real holdings (``live``, fills entered by hand from the broker) and the paper track
(``paper``, hypothetical fills at the next open). Positions are rebuilt from fills (average cost, fees in the basis);
marks and NAV are derived per trading day from ``idx.bar`` with net dividends credited on the ex-date; corporate actions
become ``split`` fills so lots and cost stay consistent. ``check`` raises deduplicated ``idx.alert`` rows for held names:
material disclosures, a new report breaking the book rule, a drawdown past the threshold, liquidity gone.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime, timedelta
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
def get_book(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    rows = _rows(conn, "SELECT book, cash, fee_buy_pct, fee_sell_pct, div_tax_pct, broker, note FROM idx.book WHERE book = %s", (book,),
                 ["book", "cash", "fee_buy_pct", "fee_sell_pct", "div_tax_pct", "broker", "note"])
    if not rows:
        raise ValueError(f"no book {book!r}")
    return rows[0]


def ensure_book(conn: psycopg.Connection, book: str, **fields: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO idx.book (book) VALUES (%s) ON CONFLICT (book) DO NOTHING", (book,))
        for k, v in fields.items():
            if k in ("cash", "fee_buy_pct", "fee_sell_pct", "div_tax_pct", "broker", "note"):
                cur.execute(f"UPDATE idx.book SET {k} = %s, updated_at = now() WHERE book = %s", (v, book))
    conn.commit()


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
    return [r["d"] for r in _rows(conn, "SELECT DISTINCT trade_date FROM idx.bar WHERE source = 'idx' AND trade_date BETWEEN %s AND %s ORDER BY 1",
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
        last_bar = _rows(conn, "SELECT max(trade_date) FROM idx.bar WHERE source = 'idx' AND (%s::date IS NULL OR trade_date <= %s)",
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
        for d in days:
            cash += deltas.get(d, Decimal(0))
            pos = rebuild_positions(conn, book)
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
                    pos = rebuild_positions(conn, book)
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
            closes = {c["code"]: Decimal(c["close"]) for c in _rows(conn, "SELECT code, close FROM idx.bar WHERE trade_date = %s AND code = ANY(%s) AND source = 'idx'",
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
        r.rows_out = n_days
        r.detail = {"from": str(days[0]) if days else None, "to": str(days[-1]) if days else None}
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx book mark failed")
    runlog.finish(conn, run_id, r)
    return r


def snapshot(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    b = get_book(conn, book)
    pos = _rows(conn, """
        SELECT p.code, l.name, p.lots, p.avg_price, p.cost_basis, p.realized_pnl, p.dividends, p.opened_at,
               m.trade_date AS mark_date, m.close, m.value, m.unrealized
          FROM idx.position p LEFT JOIN idx.listing l USING (code)
          LEFT JOIN LATERAL (SELECT trade_date, close, value, unrealized FROM idx.book_mark WHERE book = p.book AND code = p.code
                             ORDER BY trade_date DESC LIMIT 1) m ON true
         WHERE p.book = %s AND p.lots > 0 ORDER BY m.value DESC NULLS LAST, p.code""", (book,),
        ["code", "name", "lots", "avg_price", "cost_basis", "realized_pnl", "dividends", "opened_at", "mark_date", "close", "value", "unrealized"])
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
        nxt = _rows(conn, "SELECT min(trade_date) FROM idx.bar WHERE source = 'idx' AND trade_date > %s", (run_date,), ["d"])[0]["d"]
        px = {p["code"]: (p["open"] if p["open"] else p["close"]) for p in _rows(conn, "SELECT code, open, close FROM idx.bar WHERE trade_date = %s AND code = ANY(%s) AND source = 'idx'",
                                                                                     (nxt, sel), ["code", "open", "close"])}
        d = nxt
    else:
        px = {p["code"]: p["close"] for p in _rows(conn, "SELECT code, close FROM idx.bar WHERE trade_date = %s AND code = ANY(%s) AND source = 'idx'",
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
