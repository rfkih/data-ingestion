"""Phase 2 of the agent-desk plan: Telegram notify (pure formatting + injected sender), broker-CSV reconcile (pure parse/diff
+ a DB round trip), quotes (DB)."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from blackheart_ingest.idx import book, journal, notify, quote, reconcile, runlog

# ---------------------------------------------------------------------------------------------------------------- notify


def test_notify_is_a_noop_when_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv(notify.TOKEN_ENV, raising=False)
    monkeypatch.delenv(notify.CHAT_ENV, raising=False)
    monkeypatch.delenv(notify.push.SA_ENV, raising=False)
    assert not notify.configured() and notify.channels() == [] and notify.send("x") is False and notify.on_alert("critical", "j", "m") is False


def test_notify_sends_and_pushes_only_warning_and_critical(monkeypatch) -> None:
    monkeypatch.delenv(notify.push.SA_ENV, raising=False)               # telegram only here; the app channel has its own tests
    monkeypatch.setenv(notify.TOKEN_ENV, "123:abc")
    monkeypatch.setenv(notify.CHAT_ENV, "42")
    sent = []

    def sender(url, payload):
        sent.append((url, payload))
        return {"ok": True}

    assert notify.send("hello", sender=sender) and sent[-1][0].endswith("/bot123:abc/sendMessage") and sent[-1][1]["chat_id"] == "42"
    assert notify.on_alert("info", "book:paper", "quiet", sender=sender) is False and len(sent) == 1
    assert notify.on_alert("warning", "book:paper", "held X broke the gate", sender=sender) and sent[-1][1]["text"] == "[WARNING] book:paper\nheld X broke the gate"
    assert notify.send("y" * 5000, sender=sender) and len(sent[-1][1]["text"]) <= notify.MAX_LEN

    def failing(url, payload):
        raise OSError("down")

    assert notify.send("z", sender=failing) is False                    # never raises
    assert notify.send("z", sender=lambda u, p: {"ok": False, "description": "chat not found"}) is False


def test_format_ticket() -> None:
    t = {"id": 7, "book": "live", "mode": "rebalance", "status": "draft", "ticket_date": date(2026, 9, 16), "params": {"cash_after": "1234567"},
         "lines": [{"side": "sell", "code": "AAAA", "lots": Decimal(10), "limit_price": Decimal(1000), "flags": []},
                   {"side": "buy", "code": "BBBB", "lots": Decimal("25"), "limit_price": Decimal("2050"), "flags": ["strict:der", "pack:buy"]}]}
    s = notify.format_ticket(t, {"ok": False, "breaches": [{"kind": "max_weight", "code": "BBBB"}]})
    assert s.splitlines() == ["Ticket #7 live rebalance (draft) - prices as of 2026-09-16", "guardrails: max_weight BBBB",
                              "SELL AAAA     10 lot @ 1,000", "BUY  BBBB     25 lot @ 2,050  [strict:der pack:buy]", "cash after (est.) Rp 1,234,567"]
    assert "guardrails: OK" in notify.format_ticket(t, {"ok": True, "breaches": []})


# ------------------------------------------------------------------------------------------------------------- reconcile


@pytest.mark.parametrize("raw,val", [("1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("1.500", "1500"), ("3.5", "3.5"), ("1,500", "1500"),
                                     ("2,5", "2.5"), ("Rp 12.345", "12345"), ("", None), ("-", None), ("abc", None), (1500, "1500")])
def test_parse_number(raw, val) -> None:
    got = reconcile.parse_number(raw)
    assert (None if val is None else Decimal(val)) == got


def test_parse_csv_handles_indonesian_export_shapes() -> None:
    stockbit = "Account: 123\n\nSymbol;Lot;Avg Price;Market Price;Gain\nBBCA;10;9.850,00;10.000;+1,5%\nGJTL.JK;25;1.350;1.400;\n;;;;\nTotal;;;;\n"
    rows = reconcile.parse_csv(stockbit)
    assert [(r["code"], r["lots"], r["avg"]) for r in rows] == [("BBCA", Decimal(10), Decimal("9850.00")), ("GJTL", Decimal(25), Decimal(1350))]
    ipot = "﻿Stock Code,Shares,Average\nASII,9100,4910.5\nUNTR,0,26400\n"
    rows = reconcile.parse_csv(ipot)
    assert [(r["code"], r["lots"], r["avg"]) for r in rows] == [("ASII", Decimal(91), Decimal("4910.5"))]
    assert reconcile.parse_csv("kode,jumlah lot\nSRTG,3\n") == [{"code": "SRTG", "lots": Decimal(3), "avg": None}]
    with pytest.raises(ValueError, match="no usable header"):
        reconcile.parse_csv("foo,bar\n1,2\n")
    assert reconcile.parse_csv("") == []


def test_diff() -> None:
    book_pos = {"AAAA": {"lots": Decimal(10), "avg_price": Decimal(1000)}, "BBBB": {"lots": Decimal(5), "avg_price": Decimal(2000)},
                "CCCC": {"lots": Decimal(7), "avg_price": Decimal(500)}}
    broker = [{"code": "AAAA", "lots": Decimal(10), "avg": Decimal("1005")}, {"code": "BBBB", "lots": Decimal(6), "avg": Decimal(2000)},
              {"code": "DDDD", "lots": Decimal(1), "avg": None}]
    d = reconcile.diff(book_pos, broker)
    assert not d["ok"] and d["matched"] == ["AAAA"] and d["only_book"] == ["CCCC"] and d["only_broker"] == ["DDDD"]
    assert d["lots_mismatch"] == [{"code": "BBBB", "book_lots": "5", "broker_lots": "6", "diff_lots": "1"}] and d["avg_mismatch"] == []
    d = reconcile.diff({"AAAA": {"lots": 10, "avg_price": 1000}}, [{"code": "AAAA", "lots": 10, "avg": 1030}])
    assert d["ok"] and d["matched"] == [] and d["avg_mismatch"][0]["gap_pct"] == "3.00"     # lots agree (ok), avg flagged
    assert reconcile.diff({}, [])["ok"]


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


def test_reconcile_round_trip_and_alert_push(conn, monkeypatch) -> None:
    bk = "test_recon"
    _clean(conn, bk)
    try:
        book.ensure_book(conn, bk, cash=Decimal(50_000_000))
        book.add_fill(conn, bk, date(2026, 9, 11), "GJTL", "buy", Decimal(10), Decimal(1350))
        rep = reconcile.reconcile(conn, bk, reconcile.parse_csv("Symbol;Lot;Avg Price\nGJTL;10;1.352\n"), source="test.csv")
        assert rep["ok"] and rep["matched"] == ["GJTL"] and rep["source"] == "test.csv"
        rep = reconcile.reconcile(conn, bk, [{"code": "GJTL", "lots": Decimal(12), "avg": None}], actor="agent")
        assert not rep["ok"] and rep["lots_mismatch"][0]["diff_lots"] == "2"
        rows = journal.recent(conn, bk, action="reconcile")
        assert [r["actor"] for r in rows] == ["agent", "operator"] and rows[0]["refs"]["ok"] is False and "1 lot mismatches" in rows[0]["rationale"]
        assert "DIFFERENCES" in reconcile.render(rep) and "lots GJTL: book 10 vs broker 12" in reconcile.render(rep)

        # an alert raised anywhere goes out through notify when configured (warning+), not for info
        monkeypatch.delenv(notify.push.SA_ENV, raising=False)
        monkeypatch.setenv(notify.TOKEN_ENV, "t")
        monkeypatch.setenv(notify.CHAT_ENV, "c")
        sent = []
        monkeypatch.setattr(notify, "_post", lambda url, payload, timeout=15.0: sent.append(payload) or {"ok": True})
        runlog.alert(conn, "info", f"book:{bk}", "nothing")
        runlog.alert(conn, "warning", f"book:{bk}", "something")
        assert len(sent) == 1 and sent[0]["text"].startswith("[WARNING] book:test_recon")
    finally:
        _clean(conn, bk)


def test_quote(conn) -> None:
    rows = quote.latest(conn, ["bbca", "ZZZZ"])
    q = {r["code"]: r for r in rows}
    assert q["ZZZZ"]["error"] == "no bar" and q["BBCA"]["close"] > 0 and q["BBCA"]["band_lo"] < q["BBCA"]["close"] < q["BBCA"]["band_hi"]
    assert q["BBCA"]["tick"] in (1, 2, 5, 10, 25) and q["BBCA"]["trade_date"] >= date(2026, 9, 1)
    assert quote.latest(conn, []) == []
