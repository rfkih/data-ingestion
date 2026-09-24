"""The open window: only inside it, only for ticketed names, and only when the read changes."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from blackheart_ingest.idx import openwindow as ow


def _wib(h: int, m: int, day: int = 24) -> datetime:
    return datetime(2026, 9, day, h, m, tzinfo=ow.WIB)


def test_the_window_is_the_half_hour_after_the_open_on_a_weekday() -> None:
    assert ow.in_window(_wib(9, 0)) and ow.in_window(_wib(9, 29))
    assert not ow.in_window(_wib(8, 59)) and not ow.in_window(_wib(9, 30)) and not ow.in_window(_wib(14, 0))
    assert not ow.in_window(_wib(9, 15, day=26))                 # a Saturday
    assert ow.in_window(datetime(2026, 9, 24, 2, 10, tzinfo=UTC))  # 09:10 WIB expressed in UTC


def test_the_message_is_a_read_of_the_book_never_a_call_to_trade() -> None:
    msg = ow.line_message({"code": "BBCA", "side": "buy", "place": "rest_bid", "bid": 9125.0, "offer": 9150.0})
    assert msg == "BBCA buy: rest at the bid Rp 9,125"
    # the price quoted is the side of the book the read points at, never the other one
    assert ow.line_message({"code": "BBRI", "side": "buy", "place": "take_offer", "offer": 4500.0,
                            "bid": 4490.0}) == "BBRI buy: take the offer Rp 4,500"
    assert ow.line_message({"code": "BBRI", "side": "sell", "place": "hit_bid", "offer": 4500.0,
                            "bid": 4490.0}) == "BBRI sell: hit the bid Rp 4,490"
    assert ow.line_message({"code": "X", "side": "buy", "place": "balanced", "bid": 1.0, "offer": 2.0}) == "X buy: the book is balanced"
    assert ow.line_message({"code": "X", "side": "sell", "place": "unknown", "bid": None, "offer": None}) == "X sell: no book yet"
    for word in ("buy now", "sell now", "recommend", "should"):   # spec §03: a factual read, not a directive
        assert word not in msg.lower()


def test_a_ticket_maps_to_the_strategy_whose_page_shows_it() -> None:
    assert ow._strategy_of("trend") == "trend_small"
    assert ow._strategy_of("gapfade") == "gapfade"
    assert ow._strategy_of("rebalance") == "value_strict"
    assert ow._strategy_of(None) is None and ow._strategy_of("something new") is None


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


def test_only_a_changed_read_goes_on_the_bus(conn, monkeypatch) -> None:
    """The book is re-read every few seconds; the bus must not carry every one of those."""
    sent: list[dict] = []
    reads = {"place": "rest_bid"}

    def fake_open_tickets(_conn, _d):
        return [{"id": 41, "book": "paper_trend", "codes": ["BBCA"]}]

    def fake_read(_conn, _tid, _d):
        return {"ticket": 41, "book": "paper_trend", "status": "issued", "date": str(_d),
                "feed": {"live": True, "stale_s": 2, "last_at": None},
                "lines": [{"id": 900, "code": "BBCA", "side": "buy", "lots": "10", "limit": "9200",
                           "bid": 9125.0, "offer": 9150.0, "last": 9125.0, "spread_bps": 27.0, "obi1": 0.42,
                           "micro_ticks": 0.8, "place": reads["place"], "act": False, "in_feed": True,
                           "note": "the book leans to the bid"}]}

    monkeypatch.setattr(ow, "open_tickets", fake_open_tickets)
    monkeypatch.setattr(ow.execwatch, "read", fake_read)
    monkeypatch.setattr(ow.ticket, "load", lambda _c, _i: {"id": 41, "book": "paper_trend", "mode": "trend"})
    monkeypatch.setattr(ow.runlog, "alert", lambda *a, **k: (sent.append(k), len(sent))[1])

    state: dict[int, dict] = {}
    t0 = datetime(2026, 9, 24, 2, 5, tzinfo=UTC)
    first = ow.tick_once(conn, state, now=t0)
    assert first["emitted"] == 1 and first["lines"] == 1
    k = sent[0]
    assert k["kind"] == "exec" and k["code"] == "BBCA" and k["book"] == "paper_trend"
    assert k["strategy"] == "trend_small" and k["dedupe_key"] == "exec:41:900"
    assert k["payload"]["place"] == "rest_bid" and k["payload"]["obi1"] == 0.42
    assert k["valid_until"] > t0                                   # the read expires by itself

    # the same read five seconds later: nothing new to say
    assert ow.tick_once(conn, state, now=t0 + timedelta(seconds=5))["emitted"] == 0
    assert len(sent) == 1

    # the book turns: that is news
    reads["place"] = "take_offer"
    assert ow.tick_once(conn, state, now=t0 + timedelta(seconds=10))["emitted"] == 1
    assert sent[-1]["payload"]["place"] == "take_offer"

    # unchanged, but long enough that a screen should hear it is still true
    assert ow.tick_once(conn, state, now=t0 + timedelta(seconds=45))["emitted"] == 1
    assert len(sent) == 3


def test_a_stale_feed_says_nothing_about_the_book(conn, monkeypatch) -> None:
    sent: list[dict] = []
    monkeypatch.setattr(ow, "open_tickets", lambda _c, _d: [{"id": 7, "book": "paper_trend", "codes": ["BBCA"]}])
    monkeypatch.setattr(ow.execwatch, "read", lambda _c, _t, _d: {
        "ticket": 7, "book": "paper_trend", "status": "issued", "date": str(_d),
        "feed": {"live": False, "stale_s": 400, "last_at": None},
        "lines": [{"id": 1, "code": "BBCA", "side": "buy", "place": "rest_bid", "bid": 1.0, "offer": 2.0}]})
    monkeypatch.setattr(ow.runlog, "alert", lambda *a, **k: (sent.append(k), 1)[1])
    out = ow.tick_once(conn, {}, now=datetime(2026, 9, 24, 2, 5, tzinfo=UTC))
    assert out["stale_feed"] is True and out["emitted"] == 0 and not sent


def test_run_window_stops_at_the_close_and_only_one_process_streams(conn, monkeypatch) -> None:
    monkeypatch.setattr(ow, "tick_once", lambda *a, **k: {"tickets": 1, "lines": 1, "emitted": 1, "stale_feed": False})
    clock = {"t": datetime(2026, 9, 24, 2, 0, tzinfo=UTC)}          # 09:00 WIB

    def now_fn():
        return clock["t"]

    def sleep(_s):
        clock["t"] += timedelta(seconds=10)
    res = ow.run_window(conn, until=datetime(2026, 9, 24, 2, 0, 30, tzinfo=UTC), poll_s=0, sleep=sleep, now_fn=now_fn)
    assert res["stopped"] == "window closed" and res["passes"] == 3 and res["emitted"] == 3

    # a second process finds the lock held and does nothing rather than double-streaming
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as other, ow._lock(other) as got:
        assert got
        res2 = ow.run_window(conn, until=datetime(2026, 9, 24, 2, 0, 30, tzinfo=UTC), poll_s=0, sleep=sleep, now_fn=now_fn)
    assert res2["stopped"] == "another process holds the open-window lock" and res2["passes"] == 0


def test_run_window_stops_when_there_is_nothing_left_to_work(conn, monkeypatch) -> None:
    monkeypatch.setattr(ow, "tick_once", lambda *a, **k: {"tickets": 0, "lines": 0, "emitted": 0, "stale_feed": False})
    res = ow.run_window(conn, until=datetime(2099, 1, 1, tzinfo=UTC), poll_s=0, sleep=lambda _s: None,
                        now_fn=lambda: datetime(2026, 9, 24, 2, 5, tzinfo=UTC))
    assert res["stopped"] == "nothing left to work" and res["passes"] == 1
