"""Phase 3: the performance report - pure period/contribution/drawdown maths, then a DB round trip on a scratch book whose
per-name P&L must add up exactly to the NAV change."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from blackheart_ingest.idx import book, report


def test_period_bounds() -> None:
    first, last = date(2026, 5, 5), date(2026, 9, 16)
    assert report.period_bounds("since", first, last) == (first, last)
    assert report.period_bounds("mtd", first, last) == (date(2026, 9, 1), last)
    assert report.period_bounds("ytd", first, last) == (first, last)                         # clamped to the first NAV
    assert report.period_bounds("3m", first, last) == (date(2026, 6, 16), last)
    assert report.period_bounds("1y", first, last) == (first, last)
    assert report.period_bounds("2026-06-01:2026-06-30", first, last) == (date(2026, 6, 1), date(2026, 6, 30))
    assert report.period_bounds("1m", date(2026, 1, 31), date(2026, 3, 31)) == (date(2026, 2, 28), date(2026, 3, 31))
    with pytest.raises(ValueError, match="period must be"):
        report.period_bounds("2w", first, last)


def test_contributions_and_drawdown() -> None:
    d1, d2, d3 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)
    marks = [{"trade_date": d1, "code": "A", "value": Decimal(1000)},
             {"trade_date": d2, "code": "A", "value": Decimal(1100)}, {"trade_date": d2, "code": "B", "value": Decimal(500)},
             {"trade_date": d3, "code": "B", "value": Decimal(450)}]                            # A sold on d3, B bought d2
    fills = [{"trade_date": d2, "code": "B", "side": "buy", "lots": Decimal(1), "price": Decimal(5), "fee": Decimal(2)},   # cost 502
             {"trade_date": d3, "code": "A", "side": "sell", "lots": Decimal(1), "price": Decimal("11.2"), "fee": Decimal(3)}]  # proceeds 1117
    c = report.contributions(marks, fills, {"A": Decimal(10)})
    assert c["A"]["pnl"] == Decimal(1100) - 1000 + (0 - 1100 + 1117) + 10 and c["A"]["dividends"] == Decimal(10) and c["A"]["fees"] == Decimal(3)
    assert c["B"]["pnl"] == Decimal(500) - 502 + (450 - 500) and c["B"]["value_end"] == Decimal(450) and c["A"]["value_end"] == 0
    assert report.max_drawdown([Decimal(100), Decimal(120), Decimal(90), Decimal(110)]) == Decimal(-30) / 120
    assert report.max_drawdown([]) == 0


@pytest.fixture(scope="module")
def conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        c = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield c
    c.close()


def _clean(conn, bk):
    with conn.cursor() as cur:
        for t in ("book_mark", "book_nav", "position", "fill", "decision"):
            cur.execute(f"DELETE FROM idx.{t} WHERE book = %s", (bk,))
        cur.execute("DELETE FROM idx.alert WHERE job = %s", (f"book:{bk}",))
        cur.execute("DELETE FROM idx.book WHERE book = %s", (bk,))
    conn.commit()


def test_report_round_trip_adds_up(conn) -> None:
    bk = "test_report"
    _clean(conn, bk)
    try:
        book.ensure_book(conn, bk, cash=Decimal(100_000_000))
        book.add_fill(conn, bk, date(2026, 6, 1), "GJTL", "buy", Decimal(100), Decimal(1200))
        book.add_fill(conn, bk, date(2026, 6, 1), "BBCA", "buy", Decimal(10), Decimal(9000))
        book.add_fill(conn, bk, date(2026, 7, 1), "GJTL", "sell", Decimal(50), Decimal(1300))
        book.add_fill(conn, bk, date(2026, 8, 3), "ASII", "buy", Decimal(20), Decimal(4800))
        assert book.mark(conn, bk, date(2026, 9, 16)).status == "ok"
        for period in ("since", "mtd", "3m", "2026-06-15:2026-08-15"):
            rep = report.build(conn, bk, period)
            assert rep["pnl_explained"] == rep["pnl_total"], period
            assert rep["cash_unmarked"] == 0 and rep["days"] >= 1 and rep["bench_pct"]["COMPOSITE"] is not None
            assert set(n["code"] for n in rep["names"]) <= {"GJTL", "BBCA", "ASII"} and all(-100 < float(n["contrib_pct"]) < 100 for n in rep["names"])
            text = report.render(rep)
            assert text.startswith(f"{bk} {period}:") and "bench: COMPOSITE" in text
        rep = report.build(conn, bk, "since")
        assert rep["n_fills"] == 2 and {n["code"] for n in rep["names"] if n["held"]} == {"GJTL", "BBCA", "ASII"}     # day-1 fills are the base
        # a cash top-up outside fills is flagged (the marks do not carry dated cash flows), never hidden in a name
        book.ensure_book(conn, bk, cash=Decimal(book.get_book(conn, bk)["cash"]) + Decimal(5_000_000))
        rep = report.build(conn, bk, "since")
        assert rep["cash_unmarked"] == Decimal(5_000_000) and "cash setting is Rp 5,000,000 off" in report.render(rep)
        assert rep["pnl_explained"] == rep["pnl_total"]
        with pytest.raises(ValueError, match="no NAV rows"):
            report.build(conn, bk, "2025-01-01:2025-02-01")
    finally:
        _clean(conn, bk)
