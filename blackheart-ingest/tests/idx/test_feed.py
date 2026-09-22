"""Stockbit datafeed collector: wire codec, parsers, token relay parsing, session window; a DB round trip for the
store (inserts, book sampling keys, audit) on a throwaway code when INGEST_DB_DSN is set."""
from __future__ import annotations

import json
import os
import struct
import time
import urllib.parse
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from blackheart_ingest.idx.feed import proto, store
from blackheart_ingest.idx.feed.collector import in_session, next_session_start
from blackheart_ingest.idx.feed.parse import (
    WIB,
    Side,
    book_key,
    book_row,
    parse_book_body,
    parse_ts,
    trade_row,
)


def _jwt(claims: dict) -> str:
    import base64
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{b({'alg': 'RS256'})}.{b(claims)}.{'x' * 40}"


# ---- codec ---------------------------------------------------------------------------------------------------------


def test_request_encoding_round_trips_through_the_decoder():
    b = proto.encode_request(user_id="1915399", key="k" * 44, access_token="eyJ.a.b",
                             channels={"order_book": ["BBCA", "BMRI"], "liveprice": ["BBCA"]})
    f = proto.fields(b)
    assert f[1] == [b"1915399"] and f[3] == [b"k" * 44] and f[5] == [b"eyJ.a.b"]
    ch = proto.fields(f[2][0])
    assert [x.decode() for x in ch[2]] == ["BBCA", "BMRI"] and [x.decode() for x in ch[6]] == ["BBCA"]
    ping = proto.fields(proto.encode_request(ping="ping"))
    assert proto.fields(ping[4][0])[1] == [b"ping"]


def _lp_frame(code="BMRI", price=4210.0, qty=500, verb="B", seq=99, when="2026-09-21T14:59:11.076279+07:00", freq=1522.0):
    body = (proto._str(1, code) + proto._varint((2 << 3) | 1) + struct.pack("<d", price) + proto._varint((3 << 3) | 1) + struct.pack("<d", 4476200.0)
            + proto._varint((7 << 3) | 1) + struct.pack("<d", freq) + proto._str(11, when) + proto._str(16, verb)
            + proto._varint(17 << 3) + proto._varint(qty) + proto._varint(19 << 3) + proto._varint(seq))
    return proto._ld(9, body)


def test_decode_liveprice_and_trade_row():
    m = proto.decode_frame(_lp_frame())
    assert m["kind"] == "liveprice" and m["stock_code"] == "BMRI" and m["lastprice"] == 4210.0 and m["quantity"] == 500 and m["sequence_number"] == 99
    row = trade_row(m, datetime.now(UTC))
    assert row["code"] == "BMRI" and row["price"] == 4210 and row["qty"] == 500 and row["verb"] == "B" and row["seq"] == 99
    assert row["ts"] == datetime(2026, 9, 21, 14, 59, 11, 76279, tzinfo=WIB) and row["cum_volume"] == 4476200 and row["cum_freq"] == 1522
    assert trade_row({**m, "quantity": 0, "trade_trigger": {"quantity": 0}}, datetime.now(UTC)) is None    # no match -> no print
    assert trade_row({**m, "quantity": 0, "trade_trigger": {"quantity": 300}}, datetime.now(UTC))["qty"] == 300


def test_decode_orderbook_error_ping_and_unknown():
    body = "#O|BMRI|BID|4210;1522;4476200|4200;4550;16042600|4190;792;2692900"
    inner = proto._str(1, "BMRI") + proto._str(2, body) + proto._varint(3 << 3) + proto._varint(778) + proto._str(5, "2026-09-21T14:59:11+07:00")
    m = proto.decode_frame(proto._ld(10, inner))
    assert m["kind"] == "orderbook" and m["sequence_number"] == 778 and m["body"] == body
    code, side, lv = parse_book_body(m["body"])
    assert (code, side) == ("BMRI", "BID") and lv.px == [4210, 4200, 4190] and lv.n == [1522, 4550, 792] and lv.total == 4476200 + 16042600 + 2692900
    assert parse_book_body("#X|BMRI|BID|1;2;3") is None and parse_book_body("#O|BMRI|MID|1;2;3") is None
    err = proto.decode_frame(proto._ld(7, proto._varint(1 << 3) + proto._varint(401) + proto._str(2, "unauthorized")))
    assert err == {"kind": "error", "code": 401, "message": "unauthorized"}
    assert proto.decode_frame(proto._ld(2, proto._str(1, "pong")))["kind"] == "ping"
    assert proto.decode_frame(proto._ld(17, b"\x0a\x01x"))["kind"] == "other"
    with pytest.raises(ValueError):
        proto.decode(b"\x0a\xff")                                   # truncated length-delimited field


def test_book_sampling_key_and_row():
    bid = Side(px=[100, 99], vol=[1000, 2000], n=[1, 2], total=3000, levels=2)
    off = Side(px=[101], vol=[500], n=[1], total=500, levels=1)
    k1 = book_key(bid, off)
    bid2 = Side(px=[100, 99], vol=[1000, 2500], n=[1, 3], total=3500, levels=2)
    assert book_key(bid2, off) != k1 and book_key(bid, off) == k1
    r = book_row("AAAA", datetime.now(UTC), 5, bid, off, 7)
    assert r["bid_px"] == [100, 99] and r["off_vol"] == [500] and r["bid_total"] == 3000 and r["n_updates"] == 7 and r["off_levels"] == 1


def test_parse_ts_forms():
    now = datetime(2026, 9, 21, 3, 0, tzinfo=UTC)
    assert parse_ts("2026-09-21T14:59:11.076279+07:00", now).astimezone(UTC) == datetime(2026, 9, 21, 7, 59, 11, 76279, tzinfo=UTC)
    assert parse_ts("14:59:11", now) == datetime(2026, 9, 21, 14, 59, 11, tzinfo=WIB)
    assert parse_ts("2026-09-21 14:59:11", now).tzinfo == WIB
    assert parse_ts("garbage", now) == now and parse_ts(None, now) == now


# ---- token relay ---------------------------------------------------------------------------------------------------


def test_parse_relay_accepts_cookie_json_object_and_bare_jwt():
    exp = int((datetime.now(UTC) + timedelta(hours=20)).timestamp())
    jwt = _jwt({"data": {"id": 1915399, "username": "x"}, "exp": exp})
    cookie = {"state": {"access": {"token": jwt, "expired_at": "2026-09-22T08:00:00+07:00"}, "refresh": {"token": "r" * 40, "expired_at": "2026-09-28T08:00:00+07:00"},
                        "user": {"id": 1915399}}, "version": 0}
    f = store.parse_relay(urllib.parse.quote(json.dumps(cookie)))
    assert f["access_token"] == jwt and f["refresh_token"] == "r" * 40 and f["user_id"] == "1915399"
    assert f["expires_at"] == datetime(2026, 9, 22, 8, 0, tzinfo=WIB) and "state" in f["raw_keys"] and jwt not in json.dumps(f["raw_keys"])
    f2 = store.parse_relay(json.dumps({"access_token": jwt}))
    assert f2["user_id"] == "1915399" and f2["expires_at"] == datetime.fromtimestamp(exp, tz=UTC)
    f3 = store.parse_relay(jwt.encode())
    assert f3["access_token"] == jwt
    with pytest.raises(ValueError):
        store.parse_relay("not a token at all")
    with pytest.raises(ValueError):
        store.parse_relay(json.dumps({"state": {"nothing": 1}}))


def test_looks_like_refresh_jwt():
    now = int(datetime.now(UTC).timestamp())
    assert store.looks_like_refresh_jwt(_jwt({"iat": now, "exp": now + 7 * 86400}))         # Stockbit refresh: 7 days
    assert not store.looks_like_refresh_jwt(_jwt({"iat": now, "exp": now + 86400}))         # access: 24 h
    assert store.looks_like_refresh_jwt(_jwt({"exp": now + 7 * 86400}))                     # no iat: measured from now
    assert not store.looks_like_refresh_jwt(_jwt({"exp": now + 20 * 3600}))                 # a 24 h token is never 2 days out
    assert not store.looks_like_refresh_jwt("not a jwt")


def test_token_status():
    now = datetime(2026, 9, 21, 8, 0, tzinfo=UTC)
    assert store.token_status(None)["valid"] is False
    ok = store.token_status({"expires_at": now + timedelta(hours=3), "source": "paste", "user_id": "1", "received_at": now}, now)
    assert ok["valid"] and ok["minutes_left"] == 180 and ok["source"] == "paste"
    assert store.token_status({"expires_at": now - timedelta(minutes=1), "source": "env"}, now)["valid"] is False


# ---- session window ------------------------------------------------------------------------------------------------


def test_session_window():
    assert in_session(datetime(2026, 9, 21, 9, 0, tzinfo=WIB))            # Monday 09:00
    assert not in_session(datetime(2026, 9, 21, 8, 30, tzinfo=WIB))
    assert not in_session(datetime(2026, 9, 21, 16, 30, tzinfo=WIB))
    assert not in_session(datetime(2026, 9, 19, 10, 0, tzinfo=WIB))       # Saturday
    assert next_session_start(datetime(2026, 9, 18, 17, 0, tzinfo=WIB)) == datetime(2026, 9, 21, 8, 40, tzinfo=WIB)   # Fri evening -> Mon
    assert next_session_start(datetime(2026, 9, 21, 7, 0, tzinfo=WIB)) == datetime(2026, 9, 21, 8, 40, tzinfo=WIB)


# ---- store round trip ----------------------------------------------------------------------------------------------


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
    with c.cursor() as cur:
        for t in ("feed_trade", "feed_book", "feed_day", "feed_symbol"):
            cur.execute(f"DELETE FROM idx.{t} WHERE code = 'ZZFD'")
        cur.execute("DELETE FROM idx.feed_event WHERE detail LIKE 'test_feed%%'")
    c.commit()
    c.close()


def test_store_round_trip(conn):
    now = datetime.now(UTC).replace(microsecond=0)
    rows = [{"ts": now, "code": "ZZFD", "seq": 1, "price": 100, "qty": 500, "verb": "B", "board": "RG", "cum_volume": 500, "cum_value": 50000, "cum_freq": 1, "recv_at": now},
            {"ts": now + timedelta(seconds=1), "code": "ZZFD", "seq": 2, "price": 101, "qty": 300, "verb": "S", "board": "RG", "cum_volume": 800, "cum_value": 80300, "cum_freq": 2, "recv_at": now}]
    assert store.insert_trades(conn, rows) == 2
    assert store.insert_trades(conn, rows) == 2                       # duplicates (reconnect replay) are no-ops
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM idx.feed_trade WHERE code = 'ZZFD'")
        assert cur.fetchone()[0] == 2
    bid, off = Side(px=[100], vol=[1000], n=[1], total=1000, levels=1), Side(px=[101], vol=[500], n=[1], total=500, levels=1)
    br = book_row("ZZFD", now, 1, bid, off, 3)
    assert store.insert_books(conn, [br]) == 1
    store.insert_books(conn, [br])                                    # same (code, ts): n_updates accumulates
    with conn.cursor() as cur:
        cur.execute("SELECT n_updates, bid_px, off_vol FROM idx.feed_book WHERE code = 'ZZFD'")
        assert cur.fetchone() == (6, [100], [500])
    assert store.set_symbols(conn, ["zzfd"], reason="manual") == 1
    assert store.symbols(conn)["order_book"].count("ZZFD") == 1
    assert store.disable_symbols(conn, ["ZZFD"]) == 1 and "ZZFD" not in store.symbols(conn).get("order_book", [])
    store.event(conn, "test", "test_feed event")
    day = now.astimezone(WIB).date()
    audit = [r for r in store.audit_day(conn, day) if r["code"] == "ZZFD"]
    assert audit and audit[0]["n_trades"] == 2 and audit[0]["volume"] == 800 and audit[0]["n_books"] == 1 and audit[0]["max_gap_s"] == 1
    st = store.status(conn)
    assert "collector" in st and "token" in st and st["today"]["trades"] >= 2


# ---- hardening: processor, writer, archive + replay, session phases -----------------------------------------------


def test_data_expected_phases():
    from blackheart_ingest.idx.feed.collector import data_expected
    assert data_expected(datetime(2026, 9, 21, 10, 0, tzinfo=WIB))          # Monday session 1
    assert not data_expected(datetime(2026, 9, 21, 12, 30, tzinfo=WIB))     # lunch
    assert data_expected(datetime(2026, 9, 21, 14, 0, tzinfo=WIB))
    assert not data_expected(datetime(2026, 9, 21, 15, 55, tzinfo=WIB))     # pre-closing
    assert not data_expected(datetime(2026, 9, 25, 11, 45, tzinfo=WIB))     # Friday long break
    assert data_expected(datetime(2026, 9, 25, 14, 10, tzinfo=WIB))
    assert not data_expected(datetime(2026, 9, 26, 10, 0, tzinfo=WIB))      # Saturday


def test_processor_counts_skipped_matches_and_samples_books():
    from blackheart_ingest.idx.feed.collector import Processor
    p = Processor()
    t0 = 1_000_000.0
    p.on_frame(_lp_frame(freq=10.0, seq=1), t0)
    p.on_frame(_lp_frame(freq=11.0, seq=2), t0 + 0.1)
    p.on_frame(_lp_frame(freq=15.0, seq=3), t0 + 0.2)                        # 12,13,14 never delivered
    assert p.n_skipped_matches == 3 and len(p.trades) == 3 and p.n_data == 3 and p.last_data == t0 + 0.2
    body = proto._str(1, "BMRI") + proto._str(2, "#O|BMRI|BID|4210;1;100|4200;2;200") + proto._str(5, "2026-09-21T10:00:00+07:00")
    p.on_frame(proto._ld(10, body), t0 + 0.3)
    trades, books = p.drain(t0 + 0.3)
    assert len(trades) == 3 and len(books) == 1 and books[0]["bid_px"] == [4210, 4200] and books[0]["n_updates"] == 1
    p.on_frame(proto._ld(10, body), t0 + 0.5)                                # same book -> not dirty
    assert p.drain(t0 + 2.0) == ([], [])
    body2 = proto._str(1, "BMRI") + proto._str(2, "#O|BMRI|BID|4210;1;150") + proto._str(5, "2026-09-21T10:00:01+07:00")
    p.on_frame(proto._ld(10, body2), t0 + 0.6)
    assert p.drain(t0 + 0.9) == ([], [])                                     # changed, but < 1 s since the last sample
    _, books = p.drain(t0 + 1.4)
    assert len(books) == 1 and books[0]["bid_vol"] == [150]
    assert p.on_frame(b"\x0a\xff", t0) is None and p.n_undecodable == 1


def test_writer_keeps_rows_through_failures(monkeypatch):
    from blackheart_ingest.idx.feed import collector as C
    calls = {"n": 0}

    def flaky_insert(conn, rows):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        return len(rows)

    monkeypatch.setattr(C.store, "insert_trades", flaky_insert)
    monkeypatch.setattr(C.Writer, "_db", lambda self: None)
    w = C.Writer("dsn", maxlen=10)
    w.put("trade", [{"x": 1}, {"x": 2}])
    w.put("trade", [{"x": i} for i in range(20)])                             # over capacity -> dropped, counted
    assert w.dropped == 20 and w.pending == 2
    w.start()
    deadline = time.time() + 5
    while w.written["trade"] < 2 and time.time() < deadline:
        time.sleep(0.05)
    w.stop()
    assert w.written["trade"] == 2 and w.failures == 1 and w.pending == 0


def test_raw_archive_round_trip_and_replay_parsing(tmp_path):
    from blackheart_ingest.idx.feed.collector import Processor, RawArchive
    a = RawArchive(tmp_path, keep_days=7)
    f1, f2 = _lp_frame(seq=1), _lp_frame(seq=2, price=4220.0)
    a.write(f1, 1_800_000_000_000)
    a.write(f2, 1_800_000_000_500)
    a.close()
    files = list(tmp_path.glob("*.frames.gz"))
    assert len(files) == 1
    got = list(RawArchive.iter_frames(files[0]))
    assert [g[0] for g in got] == [f1, f2] and got[1][1] == 1_800_000_000.5
    with open(files[0], "ab") as fh:                                          # a truncated tail must not break the reader
        fh.write(b"\x00\x01")
    p = Processor()
    for frame, at in RawArchive.iter_frames(files[0]):
        p.on_frame(frame, at)
    assert p.n_frames == 2 and [t["price"] for t in p.trades] == [4210, 4220]
