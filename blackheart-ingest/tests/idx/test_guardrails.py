"""Guardrails (plan 2026-09-17 phase 1): the pure validator, then the kill switch / two-key / issue gate / journal on a test book."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from blackheart_ingest.idx import book, journal, ticket

BOOK = {"fee_buy_pct": Decimal("0.15"), "fee_sell_pct": Decimal("0.25"), "max_weight_pct": Decimal(12), "max_sector_pct": Decimal(35),
        "max_turnover_pct": Decimal(40), "min_v60": Decimal(5_000_000_000), "status": "active"}
HELD = {"AAAA": {"lots": Decimal(100), "avg_price": Decimal(1000)}}                       # Rp 10 M
PX = {"AAAA": Decimal(1000), "BBBB": Decimal(2000), "CCCC": Decimal(500)}
CASH = Decimal(90_000_000)                                                                  # NAV 100 M
SECTORS = {"AAAA": "Banks", "BBBB": "Banks", "CCCC": "Energy"}
V60 = {"AAAA": Decimal(6_000_000_000), "BBBB": Decimal(8_000_000_000), "CCCC": Decimal(1_000_000_000)}
ALLOWED = {"AAAA", "BBBB", "CCCC"}
D = date(2026, 9, 12)                                                                       # outside May 1-10


def _line(code, side, lots, limit, ref=None, status="open", filled=0):
    return {"code": code, "side": side, "lots": Decimal(lots), "limit_price": Decimal(limit), "ref_close": Decimal(ref if ref is not None else limit),
            "status": status, "filled_lots": Decimal(filled)}


def _v(lines, actor="agent", mode="rebalance", d=D, held=HELD, cash=CASH, **book_over):
    b = {**BOOK, **book_over}
    return ticket.validate_lines(lines, held, PX, cash, book=b, sectors=SECTORS, v60=V60, allowed_buys=ALLOWED, ticket_date=d, mode=mode, actor=actor)


def kinds(v):
    return [x["kind"] for x in v["breaches"]]


def test_clean_ticket_passes_and_reports_post_state() -> None:
    v = _v([_line("BBBB", "buy", 50, 2000)])                              # Rp 10 M = 10 % of NAV
    assert v["ok"] and v["n_lines"] == 1 and v["nav"] == Decimal(100_000_000)
    assert v["weights"] == {"AAAA": "0.1", "BBBB": "0.1"} and v["sectors"] == {"Banks": "0.2"}
    assert v["cash_after"] == CASH - Decimal(10_000_000) * Decimal("1.0015") and v["turnover"] == Decimal("0.1")


def test_max_weight_and_sector_apply_to_buys_only() -> None:
    assert kinds(_v([_line("BBBB", "buy", 70, 2000)])) == ["max_weight"]                     # 14 % > 12 %
    assert kinds(_v([_line("BBBB", "buy", 50, 2000)], max_sector_pct=15)) == ["max_sector"]   # Banks 20 % > 15 %
    # a sell never breaches even when the rest of the book is concentrated
    assert _v([_line("AAAA", "sell", 50, 1000)], max_weight_pct=1, max_sector_pct=1)["ok"]


def test_liquidity_candidates_band_cash_and_lots() -> None:
    assert kinds(_v([_line("CCCC", "buy", 20, 500)])) == ["liquidity"]
    v = _v([_line("DDDD", "buy", 10, 1000)])
    assert kinds(v) == ["not_in_candidates", "liquidity_unknown"]
    assert kinds(_v([_line("BBBB", "buy", 10, 3000, ref=2000)])) == ["band"]                 # 25 % band: 1,500-2,500
    assert "cash_negative" in kinds(_v([_line("BBBB", "buy", 50, 2000)], cash=Decimal(1_000_000)))   # (and weight: NAV is tiny)
    assert kinds(_v([_line("BBBB", "buy", 10, 2000, filled=10)])) == ["lot"]                 # nothing left to trade
    assert _v([_line("BBBB", "buy", 400, 2000, status="skipped"), _line("BBBB", "sell", 400, 2000, status="filled")])["ok"]


def test_turnover_is_the_agents_anti_churn_rule_only() -> None:
    lines = [_line("AAAA", "sell", 100, 1000), _line("BBBB", "buy", 50, 2000)]             # 20 % of NAV
    assert _v(lines)["ok"]
    assert kinds(_v(lines, max_turnover_pct=15)) == ["turnover"]
    assert _v(lines, actor="operator", max_turnover_pct=15)["ok"]                           # operator: exempt
    assert _v(lines, actor="scheduler", max_turnover_pct=15)["ok"]
    assert _v(lines, d=date(2026, 5, 5), max_turnover_pct=15)["ok"]                        # the annual window
    assert _v(lines, mode="exits", max_turnover_pct=15)["ok"]                               # thesis-break exits
    assert ticket.in_rebalance_window(date(2027, 5, 10)) and not ticket.in_rebalance_window(date(2027, 5, 11))


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
        for t in ("book_mark", "book_nav", "position", "fill", "decision"):
            cur.execute(f"DELETE FROM idx.{t} WHERE book = %s", (bk,))
        cur.execute("DELETE FROM idx.alert WHERE job IN (%s, %s)", (f"book:{bk}", f"ticket:{bk}"))
        cur.execute("DELETE FROM idx.book WHERE book = %s", (bk,))
    conn.commit()


def test_round_trip_kill_switch_two_key_and_issue_gate(conn, monkeypatch) -> None:
    bk = "test_guard"
    _clean(conn, bk)
    try:
        book.ensure_book(conn, bk, cash=Decimal(200_000_000), max_weight_pct=25, max_sector_pct=60)
        b = book.get_book(conn, bk)
        assert b["status"] == "active" and b["max_weight_pct"] == Decimal(25) and b["max_turnover_pct"] == Decimal(40)
        with pytest.raises(ValueError, match="percent"):
            book.ensure_book(conn, bk, max_weight_pct=150)

        # an agent-built full rebalance outside May: turnover ~100 % of NAV -> cannot be issued by anyone; operator raises the limit
        res = ticket.build(conn, bk, run_date=date(2026, 9, 11), max_names=5)
        tid = ticket.store(conn, res, actor="agent")
        assert ticket.load(conn, tid)["params"]["actor"] == "agent"
        v = ticket.validate(conn, tid)
        assert not v["ok"] and kinds(v) == ["turnover"] and v["actor"] == "agent" and v["book_status"] == "active"
        with pytest.raises(ValueError, match="turnover"):
            ticket.set_status(conn, tid, "issued", actor="agent")
        assert ticket.load(conn, tid)["status"] == "draft"
        book.ensure_book(conn, bk, max_turnover_pct=100)
        assert ticket.validate(conn, tid)["ok"]

        # kill switch
        book.halt(conn, bk, "test halt")
        assert book.get_book(conn, bk)["status"] == "halted"
        with pytest.raises(ValueError, match="halted"):
            ticket.build(conn, bk, run_date=date(2026, 9, 11), max_names=5)
        assert kinds(ticket.validate(conn, tid)) == ["halted"]
        with pytest.raises(ValueError, match="halted"):
            ticket.set_status(conn, tid, "issued", actor="operator")
        book.resume(conn, bk)

        # two-key: make this test book "live" for a moment
        monkeypatch.setattr(ticket, "is_live", lambda b: b in ("live", bk))
        with pytest.raises(PermissionError, match="two-key"):
            ticket.set_status(conn, tid, "issued", actor="agent")
        ticket.set_status(conn, tid, "cancelled", actor="agent")                             # its own draft: fine
        ticket.set_status(conn, tid, "draft", actor="operator")
        r = ticket.set_status(conn, tid, "issued", actor="operator", rationale="operator issues")
        assert r["status"] == "issued" and r["checks"]["ok"]
        monkeypatch.setattr(ticket, "is_live", lambda b: b == "live")

        # journal: halt/resume are journaled by the routes/CLI; status changes by the module itself
        rows = journal.recent(conn, bk)
        assert [r["action"] for r in rows] == ["ticket_status"] * 3                       # refused changes are not journaled
        assert rows[0]["actor"] == "operator" and rows[0]["refs"]["to"] == "issued" and rows[0]["rationale"] == "operator issues"
        assert rows[-1]["actor"] == "agent" and rows[-1]["refs"] == {**rows[-1]["refs"], "from": "draft", "to": "cancelled"}
        did = journal.record(conn, bk, "agent", "note", code="bbca", rationale="why", refs={"x": Decimal("1.5"), "d": date(2026, 1, 2)})
        got = next(r for r in journal.recent(conn, bk, "BBCA") if r["id"] == did)
        assert got["code"] == "BBCA" and got["refs"] == {"x": "1.5", "d": "2026-01-02"}
        with pytest.raises(ValueError, match="actor"):
            journal.record(conn, bk, "nobody", "note")
    finally:
        _clean(conn, bk)
