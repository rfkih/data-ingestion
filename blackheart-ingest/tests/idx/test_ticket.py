"""Rebalance ticket: IDX price rules and the plan (pure), plus build -> store -> fill round trip (needs the local DB)."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from blackheart_ingest.idx import book, ticket

BOOK = {"fee_buy_pct": Decimal("0.15"), "fee_sell_pct": Decimal("0.25")}


def test_tick_sizes_and_snapping() -> None:
    assert [ticket.tick_size(Decimal(p)) for p in (150, 200, 499, 500, 1999, 2000, 4999, 5000, 26300)] == [1, 2, 2, 5, 5, 10, 10, 25, 25]
    assert ticket.snap(Decimal(613), "buy") == 615 and ticket.snap(Decimal(613), "sell") == 610
    assert ticket.snap(Decimal(4915), "buy") == 4920 and ticket.snap(Decimal(4915), "sell") == 4910
    assert ticket.snap(Decimal(201), "sell") == 200                        # tick 2 above 200


def test_auto_rejection_band_and_limits() -> None:
    lo, hi = ticket.reject_band(Decimal(1000))                            # 25 % band
    assert lo == 750 and hi == 1250
    lo, hi = ticket.reject_band(Decimal(100))                             # 35 % band, floor Rp 50
    assert lo == 65 and hi == 135
    assert ticket.reject_band(Decimal(60))[0] == 50
    assert ticket.limit_price(Decimal(595), "sell") == 590 and ticket.limit_price(Decimal(595), "buy") == 600
    assert ticket.limit_price(Decimal(8600), "sell") == 8575 and ticket.limit_price(Decimal(105), "buy") == 106
    assert ticket.limit_price(Decimal(1000), "buy", ticks_through=100) == 1250      # clamped to the band


def test_plan_rebalance_sells_exits_trims_and_buys_within_cash() -> None:
    held = {"OLD": {"lots": Decimal(100), "avg_price": Decimal(900)},        # 10 M, not a target -> sell all
            "FAT": {"lots": Decimal(300), "avg_price": Decimal(900)},        # 30 M, target ~ 19.8 M -> trim
            "OK": {"lots": Decimal(200), "avg_price": Decimal(1000)}}        # 20 M, on target -> nothing
    prices = {"OLD": Decimal(1000), "FAT": Decimal(1000), "OK": Decimal(1000), "NEW": Decimal(2000), "NEW2": Decimal(500)}
    res = ticket.plan(["FAT", "OK", "NEW", "NEW2"], held, prices, Decimal(20_000_000), book=BOOK)
    assert res["nav"] == Decimal(80_000_000)
    by = {(ln["code"], ln["side"]): ln for ln in res["lines"]}
    assert by[("OLD", "sell")]["lots"] == 100 and by[("OLD", "sell")]["limit_price"] == 995
    assert by[("FAT", "sell")]["lots"] == Decimal(103)                     # 30 M -> 19.8 M target: 10.2 M / (995 x 100) = 102.5 -> 103
    assert ("OK", "buy") not in by and ("OK", "sell") not in by
    assert by[("NEW", "buy")]["lots"] > 0 and by[("NEW2", "buy")]["limit_price"] == 505      # tick 5 from Rp 500
    need = sum(ln["notional"] for ln in res["lines"] if ln["side"] == "buy")
    assert need <= res["cash"] + sum(ln["notional"] for ln in res["lines"] if ln["side"] == "sell")
    assert res["cash_after"] >= 0


def test_plan_trim_size() -> None:
    held = {"FAT": {"lots": Decimal(300), "avg_price": Decimal(900)}}
    res = ticket.plan(["FAT", "X"], held, {"FAT": Decimal(1000), "X": Decimal(1000)}, Decimal(10_000_000), book=BOOK)
    # NAV 40 M, target 19.8 M each; FAT holds 30 M -> sell ceil(10.2 M / 99,500) = 103 lots
    trim = next(ln for ln in res["lines"] if ln["code"] == "FAT")
    assert trim["side"] == "sell" and trim["lots"] == 103 and "trim" in trim["reason"]


def test_plan_cash_limited_and_exits_mode() -> None:
    res = ticket.plan(["A", "B"], {}, {"A": Decimal(1000), "B": Decimal(1000)}, Decimal(1_000_000), book=BOOK)
    assert all("cash-limited" not in ln["flags"] for ln in res["lines"])        # sizing already fits the cash
    held = {"A": {"lots": Decimal(50), "avg_price": Decimal(1000)}}
    res = ticket.plan([], held, {"A": Decimal(1000)}, Decimal(0), book=BOOK, mode="exits", exits={"A": "pack: sell"})
    assert len(res["lines"]) == 1 and res["lines"][0]["side"] == "sell" and res["lines"][0]["lots"] == 50


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
        cur.execute("DELETE FROM idx.ticket WHERE book = %s", (bk,))
        for t in ("book_mark", "book_nav", "position", "fill"):
            cur.execute(f"DELETE FROM idx.{t} WHERE book = %s", (bk,))
        cur.execute("DELETE FROM idx.alert WHERE job = %s", (f"book:{bk}",))
        cur.execute("DELETE FROM idx.book WHERE book = %s", (bk,))
    conn.commit()


def test_round_trip(conn) -> None:
    bk = "test_ticket"
    _clean(conn, bk)
    try:
        book.ensure_book(conn, bk, cash=Decimal(200_000_000))
        res = ticket.build(conn, bk, run_date=date(2026, 9, 11), max_names=5)
        assert res["run_date"] == date(2026, 9, 11) and len(res["targets"]) == 5
        assert len(res["lines"]) == 5 and all(ln["side"] == "buy" for ln in res["lines"])
        tid = ticket.store(conn, res, notes="test")
        t = ticket.load(conn, tid)
        assert t["status"] == "draft" and len(t["lines"]) == 5 and t["lines"][0]["seq"] == 1
        ticket.set_status(conn, tid, "issued")
        line = t["lines"][0]
        r = ticket.fill_line(conn, line["id"], Decimal(line["lots"]), line["limit_price"], trade_date=date(2026, 9, 11))
        assert r["status"] == "filled"
        r2 = ticket.fill_line(conn, t["lines"][1]["id"], Decimal(1), t["lines"][1]["limit_price"], trade_date=date(2026, 9, 11))
        assert r2["status"] == "partial"
        ticket.skip_line(conn, t["lines"][2]["id"], "not convinced")
        t = ticket.load(conn, tid)
        assert [ln["status"] for ln in t["lines"][:3]] == ["filled", "partial", "skipped"] and t["status"] == "issued"
        s = book.snapshot(conn, bk)
        assert {p["code"] for p in s["positions"]} == {line["code"], t["lines"][1]["code"]}
        assert ticket.load(conn, None, bk)["id"] == tid
    finally:
        _clean(conn, bk)
