"""The session rule engine (idx/intents.py): triggers and windows, the ML-stop plan, the intent life cycle with its events, and
one tick end to end (tickets, prices and positions faked - only idx.order_intent is written, under a test book, and removed)."""
from __future__ import annotations

import contextlib
import os
from datetime import date, datetime
from decimal import Decimal

import psycopg
import pytest

from blackheart_ingest.idx import combo_book as cb
from blackheart_ingest.idx import intents as it

WIB = cb.WIB
BOOK = "test_intents"


def at(hh: int, mm: int) -> datetime:
    return datetime(2026, 9, 28, hh, mm, tzinfo=WIB)          # a Monday


# ---- pure core -----------------------------------------------------------------------------------------------------------
def test_triggers_respect_price_and_window():
    spec = {"type": "price_at_or_below", "level": 950.0, "after": "15:40", "before": "15:50"}
    f = it.TRIGGERS["price_at_or_below"]
    assert f(spec, Decimal(950), at(15, 40).time()) and f(spec, Decimal(900), at(15, 50).time())
    assert not f(spec, Decimal(951), at(15, 45).time())                      # above the level
    assert not f(spec, Decimal(900), at(15, 39).time()) and not f(spec, Decimal(900), at(15, 51).time())   # outside the window
    assert not f(spec, None, at(15, 45).time())                              # no price, no fire
    assert it.TRIGGERS["price_at_or_above"]({"type": "price_at_or_above", "level": 1050}, Decimal(1050), at(10, 0).time())


def test_evaluate_fires_only_armed_intents_with_a_price():
    spec = {"type": "price_at_or_below", "level": 950.0, "after": "15:40", "before": "15:50"}
    ints = [{"id": 1, "code": "AAAA", "status": "armed", "trigger": spec}, {"id": 2, "code": "BBBB", "status": "armed", "trigger": spec},
            {"id": 3, "code": "CCCC", "status": "ticket_issued", "trigger": spec}]
    fired = it.evaluate(ints, {"AAAA": Decimal(940), "BBBB": Decimal(960), "CCCC": Decimal(900)}, at(15, 42))
    assert [f["id"] for f in fired] == [1] and fired[0]["fire_price"] == Decimal(940)
    assert it.evaluate(ints, {"AAAA": Decimal(940)}, at(14, 0)) == []
    with pytest.raises(ValueError):
        it.evaluate([{"id": 9, "code": "X", "status": "armed", "trigger": {"type": "nope"}}], {}, at(15, 45))


def test_plan_ml_stops_arms_rearms_and_cancels():
    pos = {"AAAA": {"lots": 10, "entry_price": Decimal(1000), "entry_date": date(2026, 9, 1)},
           "BBBB": {"lots": 5, "entry_price": Decimal(500), "entry_date": date(2026, 9, 2)}}
    create, cancel = it.plan_ml_stops(pos, 0.05, [])
    assert sorted(c["code"] for c in create) == ["AAAA", "BBBB"] and cancel == []
    a = next(c for c in create if c["code"] == "AAAA")
    assert a["trigger"] == {"type": "price_at_or_below", "level": 950.0, "after": "15:40", "before": "15:50"} and a["ref"]["study"] == 288
    live = [{"id": 1, "code": "AAAA", "kind": "ml_stop", "status": "armed", "trigger": {"level": 950.0}},
            {"id": 2, "code": "CCCC", "kind": "ml_stop", "status": "armed", "trigger": {"level": 190.0}},       # no longer held
            {"id": 3, "code": "BBBB", "kind": "ml_stop", "status": "ticket_issued", "trigger": {"level": 475.0}}]  # running its course
    create, cancel = it.plan_ml_stops(pos, 0.05, live)
    assert create == [] and [(c["id"], why) for c, why in cancel] == [(2, "no longer held in the ML sleeve")]
    pos["AAAA"]["entry_price"] = Decimal(1020)                                                  # a top-up moved the entry
    create, cancel = it.plan_ml_stops(pos, 0.05, live)
    assert [c["id"] for c, _ in cancel] == [1, 2] and [c["code"] for c in create] == ["AAAA"] and create[0]["trigger"]["level"] == 969.0
    create, cancel = it.plan_ml_stops(pos, None, live)                                           # stop switched off
    assert create == [] and {c["id"] for c, _ in cancel} == {1, 2}


# ---- database: life cycle, events, one tick end to end -------------------------------------------------------------------
@pytest.fixture
def conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        c = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    _clean(c)
    yield c
    c.rollback()
    _clean(c)
    c.close()


def _clean(c):
    with c.cursor() as cur:
        cur.execute("DELETE FROM idx.order_intent WHERE book = %s", (BOOK,))
    c.commit()


def _events(c, iid):
    with c.cursor() as cur:
        cur.execute("SELECT from_status, to_status FROM idx.order_intent_event WHERE intent_id = %s ORDER BY id", (iid,))
        return [tuple(r) for r in cur.fetchall()]


def test_life_cycle_is_recorded_and_guarded(conn):
    spec = {"code": "AAAA", "side": "sell", "kind": "ml_stop", "sleeve": "ml", "trigger": {"type": "price_at_or_below", "level": 950.0}, "ref": {}}
    iid = it.create(conn, BOOK, spec)
    conn.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):                      # one live intent per name and kind
        it.create(conn, BOOK, spec)
    conn.rollback()
    row = it.live_intents(conn, BOOK)[0]
    it.transition(conn, row, "triggered", price=Decimal(940), note="t")
    with pytest.raises(ValueError):
        it.transition(conn, row, "armed")                                    # no going back
    it.transition(conn, row, "ticket_issued", ticket_id=123)
    it.transition(conn, row, "filled")
    conn.commit()
    assert _events(conn, iid) == [(None, "armed"), ("armed", "triggered"), ("triggered", "ticket_issued"), ("ticket_issued", "filled")]
    assert it.live_intents(conn, BOOK) == []
    it.create(conn, BOOK, spec)                                               # a filled one does not block a new one
    conn.commit()


def test_one_tick_arms_then_fires_the_same_day_stop_on_paper(conn, monkeypatch):
    book = {"book": BOOK, "cash": Decimal(5_000_000), "fee_buy_pct": Decimal("0.15"), "fee_sell_pct": Decimal("0.25"),
            "params": {"ml": {"stop": 0.05}}}
    positions = {"gap": {}, "trend": {}, "manual": {}, "ml": {"AAAA": {"lots": Decimal(10), "entry_price": Decimal(1000), "entry_date": date(2026, 9, 1)}}}
    prices = {"AAAA": Decimal(945)}
    tickets: dict[int, dict] = {}
    monkeypatch.setattr(it.bk, "get_book", lambda c, b: book)
    monkeypatch.setattr(it.bk, "is_halted", lambda b: False)
    monkeypatch.setattr(it.bk, "snapshot", lambda c, b: {"nav_now": Decimal(20_000_000)})
    monkeypatch.setattr(it.cb, "sleeve_positions", lambda c, b: positions)
    monkeypatch.setattr(it.cb, "_open_lines", lambda c, b: set())
    monkeypatch.setattr(it.gapfade, "last_feed_prices", lambda c, d, codes: {k: v for k, v in prices.items() if k in codes})
    monkeypatch.setattr(it.gapfade, "_ticket_res", lambda *a, **k: {"lines": a[3]})
    monkeypatch.setattr(it.ticket, "_book_lock", lambda c, k: contextlib.nullcontext())
    monkeypatch.setattr(it.ticket, "store", lambda c, res, **k: tickets.setdefault(len(tickets) + 1, {"status": "draft", "lines": [{"id": 1, **res["lines"][0]}]}) and len(tickets))
    monkeypatch.setattr(it.ticket, "validate", lambda c, tid: {"ok": True})
    monkeypatch.setattr(it.ticket, "load", lambda c, tid: tickets.get(tid))
    monkeypatch.setattr(it.ticket, "is_live", lambda b: False)
    monkeypatch.setattr(it.ticket, "set_status", lambda c, tid, st, **k: tickets[tid].__setitem__("status", st))
    fills = []
    monkeypatch.setattr(it.ticket, "fill_line", lambda c, lid, lots, px, **k: fills.append((lots, px)))

    r = it.tick_book(conn, BOOK, at(15, 30))                                  # before the window: armed, not fired
    assert r["created"] == 1 and r["armed"] == 1 and r["fired"] == []
    r = it.tick_book(conn, BOOK, at(15, 35))                                  # idempotent: nothing new
    assert r["created"] == 0 and r["armed"] == 1
    r = it.tick_book(conn, BOOK, at(15, 41))
    assert [(f["code"], f["result"]) for f in r["fired"]] == [("AAAA", "filled")]
    ln = tickets[1]["lines"][0]
    assert "stop:sameday" in ln["flags"] and "exit:must" in ln["flags"] and ln["limit_price"] < Decimal(945) * Decimal("0.85")
    assert fills == [(Decimal(10), Decimal(945))] and tickets[1]["status"] == "closed"   # paper: filled at the firing price
    with conn.cursor() as cur:
        cur.execute("SELECT id, status FROM idx.order_intent WHERE book = %s", (BOOK,))
        (iid, st), = cur.fetchall()
    assert st == "filled" and [e[1] for e in _events(conn, iid)] == ["armed", "triggered", "ticket_issued", "filled"]
    positions["ml"].clear()                                                   # the name left the sleeve
    r = it.tick_book(conn, BOOK, at(15, 43))
    assert r["created"] == 0 and r["armed"] == 0 and r["fired"] == []


def test_session_tick_is_idle_outside_the_session(conn):
    assert it.session_tick(conn, at(16, 30)) == [] and it.session_tick(conn, datetime(2026, 9, 27, 15, 45, tzinfo=WIB)) == []


# ---- phases 2 and 3: ML confirmations and the gap exit ------------------------------------------------------------------
def test_at_time_and_gap_exit_plan():
    spec = {"type": "at_time", "after": it.GAP_AFTER, "before": it.GAP_BEFORE}
    assert it.TRIGGERS["at_time"](spec, None, at(15, 50).time()) and not it.TRIGGERS["at_time"](spec, None, at(15, 49).time())
    assert [f["id"] for f in it.evaluate([{"id": 1, "code": "G", "status": "armed", "trigger": spec}], {}, at(15, 51))] == [1]
    d = date(2026, 9, 28)
    pos = {"GGGG": {"lots": 3, "entry_price": Decimal(100), "entry_date": d}}
    create, cancel = it.plan_gap_exits(pos, [], d)
    assert [(c["code"], c["kind"], c["side"], c["expires_on"]) for c in create] == [("GGGG", "gap_exit", "sell", d)] and cancel == []
    live = [{"id": 5, "code": "GGGG", "kind": "gap_exit", "status": "ticket_issued"}, {"id": 6, "code": "HHHH", "kind": "gap_exit", "status": "armed"}]
    create, cancel = it.plan_gap_exits(pos, live, d)
    assert create == [] and [c["id"] for c, _ in cancel] == [6]
    assert it.in_window(at(15, 55)) and not it.in_window(at(15, 59)) and not it.in_window(datetime(2026, 9, 27, 10, 0, tzinfo=WIB))


def test_ml_confirm_spec_carries_the_watch():
    w = {"code": "AAAA", "signal_date": date(2026, 9, 25), "ref_price": Decimal(1000), "level_price": Decimal(1080), "until_date": date(2026, 10, 9),
         "e_bps": Decimal(150), "cost_bps": Decimal(60), "rule": "+8/10", "size_frac": 0.25}
    s = it.ml_confirm_spec(w)
    assert s["kind"] == "ml_confirm" and s["side"] == "buy" and s["expires_on"] == date(2026, 10, 9)
    assert s["trigger"] == {"type": "price_at_or_above", "level": 1080.0, "after": "08:58", "before": "15:50"}
    assert s["ref"]["rule"] == "+8/10" and s["ref"]["size_frac"] == 0.25 and s["ref"]["signal_date"] == "2026-09-25"


def _fake_desk(monkeypatch, book, positions, prices, tickets, fills):
    monkeypatch.setattr(it.bk, "get_book", lambda c, b: book)
    monkeypatch.setattr(it.bk, "is_halted", lambda b: False)
    monkeypatch.setattr(it.bk, "snapshot", lambda c, b: {"nav_now": Decimal(20_000_000)})
    monkeypatch.setattr(it.cb, "sleeve_positions", lambda c, b: positions)
    monkeypatch.setattr(it.cb, "_open_lines", lambda c, b: set())
    monkeypatch.setattr(it.cb, "adv20", lambda c, codes, d: {})
    monkeypatch.setattr(it.gapfade, "last_feed_prices", lambda c, d, codes: {k: v for k, v in prices.items() if k in codes})
    monkeypatch.setattr(it.gapfade, "_ticket_res", lambda *a, **k: {"lines": a[3]})
    monkeypatch.setattr(it.ticket, "_book_lock", lambda c, k: contextlib.nullcontext())
    monkeypatch.setattr(it.ticket, "store", lambda c, res, **k: tickets.setdefault(len(tickets) + 1, {"status": "draft", "lines": [{"id": 1, **res["lines"][0]}]}) and len(tickets))
    monkeypatch.setattr(it.ticket, "validate", lambda c, tid: {"ok": True})
    monkeypatch.setattr(it.ticket, "load", lambda c, tid: tickets.get(tid))
    monkeypatch.setattr(it.ticket, "is_live", lambda b: False)
    monkeypatch.setattr(it.ticket, "set_status", lambda c, tid, st, **k: tickets[tid].__setitem__("status", st))
    monkeypatch.setattr(it.ticket, "fill_line", lambda c, lid, lots, px, **k: fills.append((lots, px)))


def _statuses(c):
    with c.cursor() as cur:
        cur.execute("SELECT code, ref->>'rule', status FROM idx.order_intent WHERE book = %s ORDER BY id", (BOOK,))
        return [tuple(r) for r in cur.fetchall()]


def test_ml_confirm_fires_its_share_and_expires(conn, monkeypatch):
    book = {"book": BOOK, "cash": Decimal(20_000_000), "fee_buy_pct": Decimal("0.15"), "fee_sell_pct": Decimal("0.25"),
            "params": {"ml": {"stop": None}, "cash_floor": 0}}
    positions = {"gap": {}, "trend": {}, "manual": {}, "ml": {}}
    prices = {"AAAA": Decimal(1000)}
    tickets, fills = {}, []
    _fake_desk(monkeypatch, book, positions, prices, tickets, fills)
    base = {"code": "AAAA", "signal_date": date(2026, 9, 25), "ref_price": Decimal(950), "until_date": date(2026, 10, 9), "e_bps": 150, "cost_bps": 60}
    for rule, lvl in (("+5/10", 998), ("+10/10", 1045)):
        assert it.create(conn, BOOK, it.ml_confirm_spec({**base, "rule": rule, "level_price": Decimal(lvl), "size_frac": 0.25}), if_absent=True)
    assert it.create(conn, BOOK, it.ml_confirm_spec({**base, "rule": "+5/10", "level_price": Decimal(998), "size_frac": 0.25}), if_absent=True) is None
    it.create(conn, BOOK, it.ml_confirm_spec({**base, "code": "ZZZZ", "rule": "+5/10", "level_price": Decimal(10), "size_frac": 1,
                                              "until_date": date(2026, 9, 25)}))
    conn.commit()
    assert {w["code"] for w in cb.pending_watches(conn, BOOK, date(2026, 9, 28))} == {"AAAA"}
    r = it.tick_book(conn, BOOK, at(10, 0))
    assert r["expired"] == ["ZZZZ"]
    assert [(f["code"], f["result"]) for f in r["fired"]] == [("AAAA", "filled")]
    ln = tickets[1]["lines"][0]
    assert ln["side"] == "buy" and "rule:+5/10" in ln["flags"] and ln["notional"] <= Decimal(20_000_000) * Decimal("0.05") * Decimal("0.25")
    assert _statuses(conn) == [("AAAA", "+5/10", "filled"), ("AAAA", "+10/10", "armed"), ("ZZZZ", "+5/10", "expired")]
    assert cb.triggered_share(conn, BOOK, "AAAA", date(2026, 9, 25)) == 0.25
    assert cb.watch_counts(conn, BOOK) == {"triggered": 1, "pending": 1, "expired": 1}


def test_gap_exit_fires_once_at_the_pre_close(conn, monkeypatch):
    book = {"book": BOOK, "cash": Decimal(20_000_000), "fee_buy_pct": Decimal("0.15"), "fee_sell_pct": Decimal("0.25"), "params": {}}
    d = date(2026, 9, 28)
    positions = {"gap": {"GGGG": {"lots": Decimal(3), "entry_price": Decimal(100), "entry_date": d}}, "trend": {}, "manual": {}, "ml": {}}
    _fake_desk(monkeypatch, book, positions, {"GGGG": Decimal(104)}, {}, [])
    calls = []
    monkeypatch.setattr(it.cb, "gap_exit_unlocked", lambda c, b, actor, d: calls.append(d) or {"ticket": 77, "status": "issued", "codes": ["GGGG"], "why": None})
    r = it.tick_book(conn, BOOK, at(15, 30))
    assert r["created"] == 1 and r["fired"] == [] and calls == []
    r = it.tick_book(conn, BOOK, at(15, 50))
    assert [(f["code"], f["kind"], f["ticket"]) for f in r["fired"]] == [("GGGG", "gap_exit", 77)] and calls == [d]
    r = it.tick_book(conn, BOOK, at(15, 51))                                  # ticket_issued: not armed again, not fired again
    assert r["created"] == 0 and r["fired"] == [] and calls == [d]
    assert _statuses(conn) == [("GGGG", None, "ticket_issued")]
