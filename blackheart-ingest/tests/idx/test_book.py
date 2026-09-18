"""Position book: average-cost bookkeeping (pure) and the fill -> mark -> NAV -> check round trip (needs the local DB)."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from blackheart_ingest.idx import book


def _f(d, code, side, lots, price, fee=0, **kw):
    return {"trade_date": date.fromisoformat(d), "code": code, "side": side, "lots": Decimal(lots), "price": Decimal(price), "fee": Decimal(fee), **kw}


def test_average_cost_with_fees_and_partial_sell() -> None:
    p = book.apply_fill(None, _f("2026-05-05", "GJTL", "buy", 10, 1000, fee=1500))        # 1,000,000 + 1,500
    assert p["lots"] == 10 and p["cost_basis"] == Decimal(1_001_500) and p["avg_price"] == Decimal("1001.5")
    p = book.apply_fill(p, _f("2026-06-01", "GJTL", "buy", 10, 1200, fee=1800))            # + 1,200,000 + 1,800
    assert p["lots"] == 20 and p["avg_price"] == Decimal("1101.65")
    p = book.apply_fill(p, _f("2026-07-01", "GJTL", "sell", 5, 1300, fee=1625))            # proceeds 650,000 - 1,625
    assert p["lots"] == 15 and p["realized_pnl"] == Decimal(648_375) - 5 * 100 * Decimal("1101.65")
    assert p["cost_basis"] == 15 * 100 * Decimal("1101.65") and p["avg_price"] == Decimal("1101.65")
    with pytest.raises(ValueError, match="only 15 held"):
        book.apply_fill(p, _f("2026-07-02", "GJTL", "sell", 16, 1300))


def test_split_keeps_value() -> None:
    p = book.apply_fill(None, _f("2026-05-05", "RAJA", "buy", 10, 5000))
    q = book.apply_fill(p, _f("2026-07-16", "RAJA", "split", 50, 1000))                    # 1:5 split
    assert q["lots"] == 50 and q["avg_price"] == 1000 and q["cost_basis"] == p["cost_basis"]


def test_positions_from_orders_by_date_then_id() -> None:
    fills = [dict(_f("2026-05-06", "A", "sell", 5, 110), id=2), dict(_f("2026-05-05", "A", "buy", 5, 100), id=1)]
    pos = book.positions_from(fills)
    assert pos["A"]["lots"] == 0 and pos["A"]["realized_pnl"] == 5 * 100 * 10


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


def test_round_trip(conn) -> None:
    bk = "test_book"
    with conn.cursor() as cur:
        for t in ("book_mark", "book_nav", "position", "fill"):
            cur.execute(f"DELETE FROM idx.{t} WHERE book = %s", (bk,))
        cur.execute("DELETE FROM idx.alert WHERE job = %s", (f"book:{bk}",))
        cur.execute("DELETE FROM idx.book WHERE book = %s", (bk,))
    conn.commit()
    try:
        book.ensure_book(conn, bk, cash=Decimal(100_000_000), fee_buy_pct=Decimal("0.15"))
        fid = book.add_fill(conn, bk, date(2026, 5, 5), "GJTL", "buy", Decimal(100), Decimal(1200))
        assert fid > 0
        b = book.get_book(conn, bk)
        assert Decimal(b["cash"]) == Decimal(100_000_000) - Decimal(12_000_000) - Decimal("18000")      # fee 0.15 %
        r = book.mark(conn, bk, date(2026, 5, 8))
        assert r.status == "ok" and r.rows_out == 4                                                # 5,6,7,8 May
        s = book.snapshot(conn, bk)
        assert [p["code"] for p in s["positions"]] == ["GJTL"] and s["nav"][0]["trade_date"] == date(2026, 5, 5)
        assert Decimal(s["nav"][0]["cash"]) == Decimal(b["cash"])                                 # anchored on live cash
        assert s["positions"][0]["mark_date"] == date(2026, 5, 8) and s["positions"][0]["value"] > 0
        # incremental mark continues from the last NAV row; rebuild recomputes identically
        r2 = book.mark(conn, bk, date(2026, 5, 12))
        assert r2.status == "ok" and r2.detail["from"] == "2026-05-11"
        nav_before = {n["trade_date"]: n["nav"] for n in book.snapshot(conn, bk)["nav"]}
        book.mark(conn, bk, date(2026, 5, 12), rebuild=True)
        nav_after = {n["trade_date"]: n["nav"] for n in book.snapshot(conn, bk)["nav"]}
        assert nav_before == nav_after
        rc = book.check(conn, bk)
        assert rc.status == "ok" and rc.rows_in == 1
        # a sell closes the position and books realized P&L
        book.add_fill(conn, bk, date(2026, 5, 13), "GJTL", "sell", Decimal(100), Decimal(1300))
        s = book.snapshot(conn, bk)
        assert s["positions"] == [] and s["closed"][0]["code"] == "GJTL" and Decimal(s["closed"][0]["realized_pnl"]) > 0
    finally:
        with conn.cursor() as cur:
            for t in ("book_mark", "book_nav", "position", "fill"):
                cur.execute(f"DELETE FROM idx.{t} WHERE book = %s", (bk,))
            cur.execute("DELETE FROM idx.alert WHERE job = %s", (f"book:{bk}",))
            cur.execute("DELETE FROM idx.book WHERE book = %s", (bk,))
        conn.commit()


def test_rebuild_after_backdated_fills_marks_each_day_with_that_days_positions(conn) -> None:
    """Regression (found 2026-09-17): mark used the CURRENT positions for every past day, so a --rebuild after back-dated
    fills painted today's book over the whole history."""
    bk = "test_book_bd"
    with conn.cursor() as cur:
        for t in ("book_mark", "book_nav", "position", "fill", "decision"):
            cur.execute(f"DELETE FROM idx.{t} WHERE book = %s", (bk,))
        cur.execute("DELETE FROM idx.book WHERE book = %s", (bk,))
    conn.commit()
    try:
        book.ensure_book(conn, bk, cash=Decimal(100_000_000))
        book.add_fill(conn, bk, date(2026, 5, 5), "GJTL", "buy", Decimal(100), Decimal(1200))
        assert book.mark(conn, bk, date(2026, 5, 12)).status == "ok"
        # a fill dated in the past, entered late: sell GJTL and buy BBCA on May 8
        book.add_fill(conn, bk, date(2026, 5, 8), "GJTL", "sell", Decimal(100), Decimal(1250))
        book.add_fill(conn, bk, date(2026, 5, 8), "BBCA", "buy", Decimal(10), Decimal(9000))
        assert book.mark(conn, bk, date(2026, 5, 12), rebuild=True).status == "ok"
        with conn.cursor() as cur:
            cur.execute("SELECT trade_date, string_agg(code, ',' ORDER BY code) FROM idx.book_mark WHERE book = %s GROUP BY 1 ORDER BY 1", (bk,))
            marks = {str(d): codes for d, codes in cur.fetchall()}
        assert marks["2026-05-05"] == "GJTL" and marks["2026-05-07"] == "GJTL" and marks["2026-05-08"] == "BBCA" and marks["2026-05-12"] == "BBCA"
        assert [p["code"] for p in book.snapshot(conn, bk)["positions"]] == ["BBCA"]
    finally:
        with conn.cursor() as cur:
            for t in ("book_mark", "book_nav", "position", "fill", "decision"):
                cur.execute(f"DELETE FROM idx.{t} WHERE book = %s", (bk,))
            cur.execute("DELETE FROM idx.alert WHERE job = %s", (f"book:{bk}",))
            cur.execute("DELETE FROM idx.book WHERE book = %s", (bk,))
        conn.commit()
