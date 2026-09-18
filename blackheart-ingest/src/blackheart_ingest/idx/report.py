"""Performance report for a book over a period: NAV return against the IDX benchmarks (COMPOSITE, LQ45, IDXV30, IDX30 from
``idx.index_daily``), drawdown, and the contribution of every name - the daily P&L per position from the marks
(value today - value yesterday - the day's net buys + net sells) plus the dividends credited while held. Honest by
construction: it reads the same ``book_mark`` / ``book_nav`` rows the app shows, and the per-name P&L adds up to the NAV
change exactly. Known limit: a cash top-up or withdrawal on a live book (``idx book cash``) is not a dated flow - the marks
carry it only after ``mark --rebuild`` (which shifts the whole cash history); the report flags a cash setting that differs
from the last marked cash so the operator knows the return is not clean over such a period.

Periods: ``since`` (first NAV row), ``mtd``, ``ytd``, ``1m`` / ``3m`` / ``6m`` / ``1y`` (calendar), or ``YYYY-MM-DD:YYYY-MM-DD``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from . import book as bk
from .card import _rows

BENCHMARKS = ("COMPOSITE", "LQ45", "IDXV30", "IDX30")
LOT = 100


def period_bounds(period: str, first: date, last: date) -> tuple[date, date]:
    """Pure: the period's start (the NAV row on/before it is the base) and end, clamped to the book's NAV range."""
    p = (period or "since").lower().strip()
    if ":" in p:
        a, b = p.split(":", 1)
        return max(date.fromisoformat(a), first), min(date.fromisoformat(b), last)
    if p == "since":
        return first, last
    if p == "mtd":
        return max(last.replace(day=1), first), last
    if p == "ytd":
        return max(last.replace(month=1, day=1), first), last
    months = {"1m": 1, "3m": 3, "6m": 6, "1y": 12}.get(p)
    if months is None:
        raise ValueError("period must be since | mtd | ytd | 1m | 3m | 6m | 1y | YYYY-MM-DD:YYYY-MM-DD")
    m = last.month - months
    y = last.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    start = date(y, m, min(last.day, 28))
    return max(start, first), last


def contributions(marks: list[dict[str, Any]], fills: list[dict[str, Any]], divs: dict[str, Decimal]) -> dict[str, dict[str, Any]]:
    """Pure. ``marks`` rows {trade_date, code, value} for the period (the day before the start included as the base),
    ``fills`` rows {trade_date, code, side, lots, price, fee} inside the period, ``divs`` net dividends per code inside it.
    P&L per name = sum over days of (value_t - value_{t-1}) - buys_t + sells_t, + dividends."""
    days = sorted({m["trade_date"] for m in marks})
    by_day: dict[date, dict[str, Decimal]] = {d: {} for d in days}
    for m in marks:
        by_day[m["trade_date"]][m["code"]] = Decimal(m["value"] or 0)
    flow: dict[tuple[date, str], Decimal] = {}
    fee_by_code: dict[str, Decimal] = {}
    for f in fills:
        gross = Decimal(f["lots"]) * LOT * Decimal(f["price"])
        fee = Decimal(f["fee"] or 0)
        net = (gross + fee) if f["side"] == "buy" else -(gross - fee)              # cash that went INTO the name
        if f["side"] not in ("buy", "sell"):
            continue
        flow[(f["trade_date"], f["code"])] = flow.get((f["trade_date"], f["code"]), Decimal(0)) + net
        fee_by_code[f["code"]] = fee_by_code.get(f["code"], Decimal(0)) + fee
    codes = {m["code"] for m in marks} | {f["code"] for f in fills}
    out: dict[str, dict[str, Any]] = {}
    for c in sorted(codes):
        pnl, prev = Decimal(0), None
        for d in days:
            v = by_day[d].get(c, Decimal(0))
            if prev is not None:
                pnl += v - prev - flow.get((d, c), Decimal(0))
            prev = v
        pnl += divs.get(c, Decimal(0))
        out[c] = {"pnl": pnl, "dividends": divs.get(c, Decimal(0)), "fees": fee_by_code.get(c, Decimal(0)),
                  "value_end": by_day[days[-1]].get(c, Decimal(0)) if days else Decimal(0)}
    return out


def max_drawdown(navs: list[Decimal]) -> Decimal:
    peak, dd = None, Decimal(0)
    for v in navs:
        peak = v if peak is None or v > peak else peak
        if peak:
            dd = min(dd, (v - peak) / peak)
    return dd


def build(conn: psycopg.Connection, book: str, period: str = "since", as_of: date | None = None) -> dict[str, Any]:
    b = bk.get_book(conn, book)
    nav = _rows(conn, "SELECT trade_date, cash, positions, nav, n_positions, dividends FROM idx.book_nav WHERE book = %s AND (%s::date IS NULL OR trade_date <= %s) ORDER BY trade_date",
                (book, as_of, as_of), ["trade_date", "cash", "positions", "nav", "n_positions", "dividends"])
    if not nav:
        raise ValueError(f"book {book} has no NAV history yet (no fills, or not marked)")
    first, last = nav[0]["trade_date"], nav[-1]["trade_date"]
    start, end = period_bounds(period, first, last)
    win = [n for n in nav if start <= n["trade_date"] <= end]
    if len(win) < 1:
        raise ValueError(f"no NAV rows between {start} and {end}")
    base_row = next((n for n in reversed(nav) if n["trade_date"] < start), None) or win[0]   # the close before the window
    base_date = base_row["trade_date"]
    nav_start, nav_end = Decimal(base_row["nav"]), Decimal(win[-1]["nav"])
    ret = (nav_end / nav_start - 1) if nav_start else Decimal(0)
    bench: dict[str, Any] = {}
    for code in BENCHMARKS:
        pts = _rows(conn, """SELECT (SELECT close FROM idx.index_daily WHERE index_code = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1) AS a,
                                    (SELECT close FROM idx.index_daily WHERE index_code = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1) AS b""",
                    (code, base_date, code, end), ["a", "b"])[0]
        bench[code] = (Decimal(pts["b"]) / Decimal(pts["a"]) - 1) if pts["a"] and pts["b"] else None
    marks = _rows(conn, "SELECT trade_date, code, value FROM idx.book_mark WHERE book = %s AND trade_date BETWEEN %s AND %s ORDER BY trade_date, code",
                  (book, base_date, end), ["trade_date", "code", "value"])
    fills = _rows(conn, "SELECT trade_date, code, side, lots, price, fee FROM idx.fill WHERE book = %s AND trade_date > %s AND trade_date <= %s ORDER BY trade_date, id",
                  (book, base_date, end), ["trade_date", "code", "side", "lots", "price", "fee"])
    tax = Decimal(b["div_tax_pct"]) / 100
    divs: dict[str, Decimal] = {}
    for r in _rows(conn, """SELECT dv.code, dv.ex_date, dv.amount_per_share, m.lots FROM idx.dividend dv
                             JOIN idx.book_mark m ON m.book = %s AND m.code = dv.code AND m.trade_date = dv.ex_date
                            WHERE dv.kind = 'cash' AND dv.ex_date > %s AND dv.ex_date <= %s""", (book, base_date, end),
                   ["code", "ex_date", "dps", "lots"]):
        divs[r["code"]] = divs.get(r["code"], Decimal(0)) + Decimal(r["lots"]) * LOT * Decimal(r["dps"]) * (1 - tax)
    contrib = contributions(marks, fills, divs)
    names = [{"code": c, "pnl": v["pnl"], "contrib_pct": (v["pnl"] / nav_start * 100) if nav_start else Decimal(0), "dividends": v["dividends"],
              "fees": v["fees"], "value_end": v["value_end"], "held": v["value_end"] > 0,
              "weight_pct": (v["value_end"] / nav_end * 100) if nav_end else Decimal(0)} for c, v in contrib.items()]
    names.sort(key=lambda x: x["pnl"], reverse=True)
    explained = sum(n["pnl"] for n in names)
    cash_unmarked = Decimal(b["cash"]) - Decimal(nav[-1]["cash"])      # a top-up/withdrawal since the last mark (see module doc)
    return {"book": book, "period": period, "start": start, "end": end, "base_date": base_date, "nav_start": nav_start, "nav_end": nav_end,
            "ret_pct": ret * 100, "bench_pct": {k: (v * 100 if v is not None else None) for k, v in bench.items()},
            "excess_vs_composite_pct": (ret - bench["COMPOSITE"]) * 100 if bench.get("COMPOSITE") is not None else None,
            "max_drawdown_pct": max_drawdown([Decimal(n["nav"]) for n in win]) * 100, "days": len(win), "n_fills": len(fills),
            "fees": sum(Decimal(f["fee"] or 0) for f in fills), "dividends": sum(divs.values(), Decimal(0)),
            "pnl_explained": explained, "pnl_total": nav_end - nav_start, "cash_unmarked": cash_unmarked,
            "hit_rate_pct": (sum(1 for n in names if n["pnl"] > 0) / len(names) * 100) if names else None,
            "n_positions": win[-1]["n_positions"], "names": names}


def render(rep: dict[str, Any], top: int = 5) -> str:
    def pct(v: Any) -> str:
        return "-" if v is None else f"{float(v):+.2f} %"
    o = [f"{rep['book']} {rep['period']}: {rep['base_date']} -> {rep['end']}  NAV Rp {float(rep['nav_start']):,.0f} -> Rp {float(rep['nav_end']):,.0f}  "
         f"{pct(rep['ret_pct'])}  (max DD {pct(rep['max_drawdown_pct'])}, {rep['n_positions']} names, {rep['n_fills']} fills)",
         "bench: " + "  ".join(f"{k} {pct(v)}" for k, v in rep["bench_pct"].items()) + f"  | excess vs COMPOSITE {pct(rep['excess_vs_composite_pct'])}"]
    if rep["names"]:
        o.append("top:    " + ", ".join(f"{n['code']} {pct(n['contrib_pct'])}" for n in rep["names"][:top]))
        o.append("bottom: " + ", ".join(f"{n['code']} {pct(n['contrib_pct'])}" for n in rep["names"][-top:][::-1]))
        o.append(f"hit rate {float(rep['hit_rate_pct'] or 0):.0f} % | dividends Rp {float(rep['dividends']):,.0f} | fees Rp {float(rep['fees']):,.0f}")
    if abs(Decimal(rep["cash_unmarked"])) > 1:
        o.append(f"note: the book's cash setting is Rp {float(rep['cash_unmarked']):,.0f} off the last marked cash (top-up/withdrawal not in the "
                 "marks) - run `idx book mark --rebuild`; the return over a period spanning it is not clean")
    return "\n".join(o)
