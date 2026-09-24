"""Broker summary feed: config from the environment, URL building, windows, the parser (the real shape + tolerant fallbacks),
the detector block, and a store/backfill/reparse round trip."""
from __future__ import annotations

import json
import os
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import psycopg
import pytest

from blackheart_ingest.idx import broker

ENV = {"STOCKBIT_TOKEN": "k", "STOCKBIT_BS_URL": "https://exodus.stockbit.com/marketdetectors/BBCA?from=2026-09-14&to=2026-09-14&limit=25"
                                                  "&investor_type=INVESTOR_TYPE_FOREIGN&market_board=MARKET_BOARD_ALL&transaction_type=TRANSACTION_TYPE_NET"}


def test_config_and_url() -> None:
    with pytest.raises(broker.BrokerAuthError, match="STOCKBIT_TOKEN"):
        broker.config({})
    cfg = broker.config({"STOCKBIT_TOKEN": "k"})
    assert cfg["base"] == broker.BASE and cfg["params"] == broker.DEFAULT_PARAMS and cfg["params"]["market_board"] == "MARKET_BOARD_REGULER"
    cfg = broker.config(ENV)
    assert cfg["params"]["investor_type"] == "INVESTOR_TYPE_FOREIGN" and cfg["params"]["market_board"] == "MARKET_BOARD_ALL"
    url = broker.build_url("gjtl", date(2026, 8, 1), date(2026, 8, 29), cfg)
    assert url.startswith("https://exodus.stockbit.com/marketdetectors/GJTL?from=2026-08-01&to=2026-08-29&limit=100&") and "INVESTOR_TYPE_FOREIGN" in url


def test_windows() -> None:
    td = [date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8, 9, 10, 11, 14, 15, 16)]
    w = broker.windows(td, date(2026, 9, 1), date(2026, 9, 16), days=5)
    assert w == [(date(2026, 9, 1), date(2026, 9, 2)), (date(2026, 9, 3), date(2026, 9, 9)), (date(2026, 9, 10), date(2026, 9, 16))]
    assert broker.windows(td, date(2026, 9, 8), date(2026, 9, 30), days=20) == [(date(2026, 9, 8), date(2026, 9, 16))]
    assert broker.windows([], date(2026, 9, 1), date(2026, 9, 16)) == []


@pytest.mark.parametrize("raw,val", [("1.234,5", "1234.5"), ("1,234.5", "1234.5"), ("12.345", "12345"), ("2.819329e+06", "2819329"), (98700000, "98700000"),
                                     ("-1.583794e+06", "-1583794"), ("-", None), ("YU", None), (True, None)])
def test_num(raw, val) -> None:
    assert broker._num(raw) == (None if val is None else Decimal(val))


# the real shape (2026-09-17, BBCA 2026-08-18..09-16, trimmed)
REAL = {"message": "Successfully retrieved market detector data",
        "data": {"bandar_detector": {"average": 6502.858, "avg": {"accdist": "Small Acc", "amount": 254631280000, "percent": 8.618914, "vol": 391568.28},
                                     "avg5": {"accdist": "Small Acc", "amount": 345057800000, "percent": 11.679724, "vol": 530624.8},
                                     "broker_accdist": "Acc", "number_broker_buysell": -19,
                                     "top1": {"accdist": "Big Acc", "amount": 803450900000, "percent": 27.19569, "vol": 1235535},
                                     "top3": {"accdist": "Small Acc", "amount": 244725960000, "percent": 8.283632, "vol": 376336},
                                     "top5": {"accdist": "Neutral", "amount": 174110130000, "percent": 5.8933845, "vol": 267744},
                                     "top10": {"accdist": "Neutral", "amount": 131212070000, "percent": 4.441345, "vol": 201776},
                                     "total_buyer": 33, "total_seller": 52, "value": 2954331700000, "volume": 4543128},
                 "broker_summary": {"brokers_buy": [{"blot": "2.819329e+06", "blotv": "4.036399e+08", "bval": "1.8449668375e+12", "bvalv": "2.6352002375e+12",
                                                     "netbs_broker_code": "YU", "netbs_buy_avg_price": "6528.592038349034", "netbs_date": "20260818",
                                                     "netbs_stock_code": "BBCA", "type": "Asing", "freq": "50928"},
                                                    {"blot": "623579", "blotv": "9.60823e+07", "bval": "4.06766735e+11", "bvalv": "6.256702125e+11",
                                                     "netbs_broker_code": "BB", "netbs_buy_avg_price": "6511.815521693382", "netbs_date": "20260818",
                                                     "netbs_stock_code": "BBCA", "type": "Lokal", "freq": "9715"}],
                                    "brokers_sell": [{"netbs_broker_code": "RX", "netbs_date": "20260818", "netbs_sell_avg_price": "6462.611060765535",
                                                      "netbs_stock_code": "BBCA", "slot": "-1.583794e+06", "slotv": "2.255522e+08", "sval": "-1.0224553525e+12",
                                                      "svalv": "1.4576561425e+12", "type": "Asing", "freq": "23318"}],
                                    "symbol": "BBCA"},
                 "from": "2026-08-18", "to": "2026-09-16"}}
FLAT = {"data": {"summary": [{"broker_code": "YU", "broker_name": "CGS International", "bval": 97100000000, "blot": 152400, "bavg": 6368, "sval": 3000000, "slot": 5, "savg": 6370},
                             {"broker_code": "ZP", "bval": 0, "blot": 0, "bavg": 0, "sval": 82700000000, "slot": 129600, "savg": 6367}]}}


def test_parse_real_shape_and_detector() -> None:
    rows, diag = broker.parse(REAL)
    assert diag["keys_seen"] == ["exact"] and [r["broker"] for r in rows] == ["YU", "BB", "RX"]
    yu, rx = rows[0], rows[2]
    assert yu["investor"] == "Asing" and yu["freq"] == 50928
    assert yu["buy_value"] == Decimal("2.6352002375e+12") and yu["buy_lot"] == Decimal("4036399") and yu["buy_avg"] == Decimal("6528.592038349034")
    assert yu["net_value"] == Decimal("1.8449668375e+12") and yu["net_lot"] == Decimal(2819329) and yu["sell_value"] is None
    assert rx["sell_value"] == Decimal("1.4576561425e+12") and rx["sell_lot"] == Decimal("2255522") and rx["net_value"] == Decimal("-1.0224553525e+12")
    assert rx["net_lot"] == Decimal(-1583794) and rx["buy_value"] is None and rx["sell_avg"] == Decimal("6462.611060765535")
    det = broker.parse_detector(REAL)
    assert det["top1_pct"] == Decimal("27.19569") and det["top1_label"] == "Big Acc" and det["broker_accdist"] == "Acc"
    assert det["total_buyer"] == 33 and det["total_seller"] == 52 and det["number_broker_buysell"] == -19 and det["value"] == Decimal(2954331700000)
    assert broker.parse_detector(FLAT) is None


def test_parse_tolerant_fallback() -> None:
    rows, diag = broker.parse(FLAT)
    assert [r["broker"] for r in rows] == ["YU", "ZP"] and diag["n"] == 2 and diag["lists_used"] == [("data.summary", 2)]
    assert rows[0]["broker_name"] == "CGS International" and rows[0]["net_value"] == Decimal(97100000000) - 3000000
    assert broker.parse({"data": {"error": "x"}})[0] == [] and broker.parse(None)[0] == []


def test_fetch_maps_statuses() -> None:
    cfg = broker.config({"STOCKBIT_TOKEN": "k"})
    calls = []

    def fake(url, headers):
        calls.append((url, headers))
        return 200, b'{"data": {"broker_summary": {"brokers_buy": [], "brokers_sell": []}}}'

    status, payload, err = broker.fetch("BBCA", date(2026, 9, 1), date(2026, 9, 16), cfg, fake)
    assert (status, err) == (200, None) and payload["data"]["broker_summary"]["brokers_buy"] == []
    assert calls[0][1]["Authorization"] == "Bearer k" and calls[0][1]["X-Platform"] == "web" and "MARKET_BOARD_REGULER" in calls[0][0]
    with pytest.raises(broker.BrokerAuthError):
        broker.fetch("BBCA", date(2026, 9, 1), date(2026, 9, 16), cfg, lambda u, h: (401, b"{}"))
    with pytest.raises(broker.BrokerRateLimited):
        broker.fetch("BBCA", date(2026, 9, 1), date(2026, 9, 16), cfg, lambda u, h: (429, b""))
    assert broker.fetch("BBCA", date(2026, 9, 1), date(2026, 9, 16), cfg, lambda u, h: (500, b"oops"))[2].startswith("not JSON")


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


def _clean(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.broker_summary_raw WHERE code = 'TEST'")
    conn.commit()


def test_store_backfill_and_reparse_round_trip(conn) -> None:
    _clean(conn)
    cfg = broker.config({"STOCKBIT_TOKEN": "k"})
    try:
        raw_id, n = broker.store(conn, "test", date(2026, 8, 18), date(2026, 9, 16), cfg, 200, REAL, None)
        assert raw_id > 0 and n == 3
        rows = broker.show(conn, "TEST")
        assert [r["broker"] for r in rows] == ["YU", "BB", "RX"] and rows[0]["investor"] == "Asing" and rows[0]["freq"] == 50928
        assert rows[2]["net_value"] == Decimal("-1022455352500.00")
        det = broker.detector(conn, "TEST")
        assert len(det) == 1 and det[0]["top1_pct"] == Decimal("27.1957") and det[0]["broker_accdist"] == "Acc" and det[0]["total_seller"] == 52
        seen = []

        def fake(url, headers):
            seen.append(url)
            return 200, (b'{"data": {"bandar_detector": {"top1": {"percent": 1.5, "accdist": "Neutral"}, "total_buyer": 1, "total_seller": 0, "value": 10},'
                         b' "broker_summary": {"brokers_buy": [{"netbs_broker_code": "CC", "bval": "10", "blot": "1", "bvalv": "10", "blotv": "100",'
                         b' "netbs_buy_avg_price": "10", "type": "Lokal", "freq": "1"}], "brokers_sell": []}}}')

        res = broker.backfill(conn, ["TEST"], date(2026, 7, 1), date(2026, 9, 16), window=20, cfg=cfg, fetcher=fake, sleep=lambda s: None)
        assert res["requested"] == res["windows"] >= 2 and res["ok"] == res["requested"] and res["rows"] == res["requested"] and res["stopped"] is None
        again = broker.backfill(conn, ["TEST"], date(2026, 7, 1), date(2026, 9, 16), window=20, cfg=cfg, fetcher=fake, sleep=lambda s: None)
        assert again["requested"] == 0 and again["skipped"] == res["windows"]
        stop = broker.backfill(conn, ["TEST"], date(2026, 1, 1), date(2026, 3, 31), window=20, cfg=cfg, fetcher=lambda u, h: (401, b"{}"), sleep=lambda s: None)
        assert stop["requested"] == 0 and "401" in stop["stopped"]
        assert broker.reparse(conn, "TEST") == res["windows"] + 3
        assert len(broker.detector(conn, "TEST", n=50)) == res["windows"] + 1
    finally:
        _clean(conn)


# --- daily distribution feed (order-trade/broker/distribution) + token refresh (2026-09-18) --------------------------

# the distribution shape (trimmed): per side, a broker's detail.amount is its gross value on that side.
DIST = {"message": "Successfully loaded Broker Distribution data",
        "data": {"date_info": "2026-09-17",
                 "by_value": {"top_broker_buy": [{"detail": {"code": "YU", "type": "Asing", "amount": 90000000000},
                                                  "distribute_to": [{"code": "ZP", "type": "Asing", "amount": 25000000000}]},
                                                 {"detail": {"code": "AK", "type": "Asing", "amount": 40000000000}, "distribute_to": []},
                                                 {"detail": {"code": "CC", "type": "Pemerintah", "amount": 10000000000}, "distribute_to": []}],
                              "top_broker_sell": [{"detail": {"code": "ZP", "type": "Asing", "amount": 50000000000}, "distribute_to": []},
                                                  {"detail": {"code": "YU", "type": "Asing", "amount": 2000000000}, "distribute_to": []}]},
                 "by_volume": {"top_broker_buy": [], "top_broker_sell": []},
                 "start_date": "2026-09-17", "end_date": "2026-09-17"}}


def test_parse_distribution_and_routing() -> None:
    rows, diag = broker.parse_distribution(DIST)
    assert diag["keys_seen"] == ["distribution"]
    by = {r["broker"]: r for r in rows}
    # YU: buy 90bn, sell 2bn -> net +88bn; ZP: buy 0, sell 50bn -> net -50bn; AK: +40bn; CC: +10bn
    assert by["YU"]["net_value"] == Decimal(88_000_000_000) and by["YU"]["investor"] == "Asing"
    assert by["YU"]["buy_value"] == Decimal(90_000_000_000) and by["YU"]["sell_value"] == Decimal(2_000_000_000)
    assert by["ZP"]["net_value"] == Decimal(-50_000_000_000) and by["ZP"]["buy_value"] is None
    assert [r["broker"] for r in rows] == ["YU", "AK", "CC", "ZP"]                      # sorted by net desc
    assert all(r["buy_lot"] is None and r["sell_avg"] is None and r["freq"] is None for r in rows)
    # parse_any / detector_any route by shape
    assert broker.parse_any(DIST)[0][0]["broker"] == "YU"
    assert broker.parse_any(REAL)[1]["keys_seen"] == ["exact"]
    det = broker.distribution_detector(DIST)
    assert det["total_buyer"] == 3 and det["total_seller"] == 1               # YU,AK,CC net>0 ; ZP net<0
    assert det["value"] == Decimal(140_000_000_000)                          # gross bought 90+40+10
    # top-1 net buyer share of total net buys (88 of 88+40+10 = 138)
    assert det["top1_pct"] == Decimal(88_000_000_000) / Decimal(138_000_000_000) * 100
    assert broker.detector_any(DIST)["total_seller"] == 1 and broker.detector_any(REAL)["broker_accdist"] == "Acc"


def test_fetch_day_maps_statuses_and_date() -> None:
    cfg = broker.config({"STOCKBIT_TOKEN": "k"})
    calls = []

    def ok(url, headers):
        calls.append(url)
        return 200, json.dumps(DIST).encode()

    status, payload, d, err = broker.fetch_day("bbca", cfg, ok)
    assert status == 200 and err is None and d == date(2026, 9, 17) and payload["data"]["date_info"] == "2026-09-17"
    assert "order-trade/broker/distribution" in calls[0] and "symbol=BBCA" in calls[0] and "TB_PERIOD_LAST_1_DAY" in calls[0]
    with pytest.raises(broker.BrokerPaywall):
        broker.fetch_day("BBCA", cfg, lambda u, h: (402, b'{"error_type":"PAYWALL"}'))
    with pytest.raises(broker.BrokerAuthError):
        broker.fetch_day("BBCA", cfg, lambda u, h: (401, b"{}"))


def _jwt(**claims) -> str:
    """An unsigned JWT-shaped token carrying ``claims`` (enough for the iat/exp readers)."""
    import base64
    import json as _json
    enc = lambda o: base64.urlsafe_b64encode(_json.dumps(o).encode()).decode().rstrip("=")  # noqa: E731
    return f"{enc({'alg': 'none'})}.{enc(claims)}.sig"


# the live /login/refresh answer (2026-09-22): tokens nested under access.token / refresh.token
_REFRESH_RESP = b'{"message":"You have been successfully refresh token","data":{"access":{"token":"NEWACCESS","expired_at":"2026-09-23T06:20:05Z"},"refresh":{"token":"NEWREFRESH","expired_at":"2026-09-29T06:20:05Z"}}}'


def test_extract_tokens_and_refresh() -> None:
    assert broker.extract_tokens({"data": {"access": {"token": "AAA", "expired_at": "x"}, "refresh": {"token": "RRR"}}}) == ("AAA", "RRR")
    assert broker.extract_tokens({"data": {"refresh": {"token": "RRR"}, "access": {"token": "AAA"}}}) == ("AAA", "RRR")  # order-proof
    assert broker.extract_tokens({"data": {"access": "AAA", "refresh_token": "RRR"}}) == ("AAA", "RRR")                # flat variant
    assert broker.extract_tokens({"accessToken": "A2"}) == ("A2", None)
    assert broker.extract_tokens({"nothing": 1}) == (None, None)
    posts = []

    def poster(url, body, bearer):
        posts.append((url, body, bearer))
        return 200, _REFRESH_RESP

    access, rotated, _resp = broker.refresh_access_token("oldR", poster)
    assert access == "NEWACCESS" and rotated == "NEWREFRESH"
    assert posts[0] == (broker.REFRESH_URL, {}, "oldR")                    # refresh token travels as the Bearer, body empty
    with pytest.raises(broker.BrokerAuthError):
        broker.refresh_access_token("bad", lambda u, b, t: (401, b'{"message":"UNAUTHORIZED"}'))
    with pytest.raises(broker.BrokerFetchError):
        broker.refresh_access_token("x", lambda u, b, t: (200, b'{"data": {"nope": 1}}'))


def test_newest_refresh_token_prefers_latest_iat() -> None:
    old, new = _jwt(iat=1_000, exp=2_000), _jwt(iat=5_000, exp=6_000)
    assert broker.newest_refresh_token({"STOCKBIT_REFRESH_TOKEN": old}, None) == old
    assert broker.newest_refresh_token({}, None) is None

    class _Cur:
        def __init__(self, tok): self.tok = tok
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): pass
        def fetchone(self): return (self.tok,)

    class _Conn:
        def __init__(self, tok): self.tok = tok
        def cursor(self): return _Cur(self.tok)

    assert broker.newest_refresh_token({"STOCKBIT_REFRESH_TOKEN": old}, _Conn(new)) == new   # relay re-login wins
    assert broker.newest_refresh_token({"STOCKBIT_REFRESH_TOKEN": new}, _Conn(old)) == new   # env rotation wins
    assert broker.newest_refresh_token({}, _Conn(new)) == new                                 # relay only


def test_renew_if_needed(monkeypatch) -> None:
    from blackheart_ingest.idx.feed import store as feed_store
    now = datetime.now(UTC)
    calls: list[str] = []
    monkeypatch.setattr(broker, "refresh_and_persist", lambda env=None, conn=None, **k: (calls.append("refresh"), _jwt(exp=int(now.timestamp()) + 86400))[1])
    fresh = {"access_token": "A", "refresh_token": _jwt(iat=1, exp=2), "expires_at": now + timedelta(hours=10), "source": "relay"}
    monkeypatch.setattr(feed_store, "load_token", lambda conn: fresh)
    rep = broker.renew_if_needed(object(), {})                                  # 10 h left -> nothing to do
    assert rep == {"renewed": False, "minutes_left": 600, "needed": 180, "reason": "fresh"} and calls == []
    monkeypatch.setattr(broker, "_relay_refresh_token", lambda conn: fresh["refresh_token"])
    rep = broker.renew_if_needed(object(), {}, force=True)                      # forced -> refreshed
    assert rep["renewed"] and rep["reason"] == "renewed" and 1430 <= rep["minutes_left"] <= 1440 and calls == ["refresh"]
    stale = {**fresh, "expires_at": now + timedelta(minutes=90)}
    monkeypatch.setattr(feed_store, "load_token", lambda conn: stale)
    assert broker.renew_if_needed(object(), {})["renewed"] and calls == ["refresh", "refresh"]   # 90 min < 3 h -> refreshed
    monkeypatch.setattr(broker, "_relay_refresh_token", lambda conn: None)
    rep = broker.renew_if_needed(object(), {})                                   # nothing to refresh with
    assert not rep["renewed"] and "no refresh token" in rep["reason"] and len(calls) == 2


def test_minutes_needed_and_refresh_status() -> None:
    now = datetime(2026, 9, 23, 2, 0, tzinfo=UTC)                          # 09:00 WIB
    close = datetime(2026, 9, 23, 9, 45, tzinfo=UTC)                       # 16:45 WIB = the close plus the margin
    assert broker.minutes_needed(now, None, 180) == 180
    assert broker.minutes_needed(now, close, 180) == 465                   # must reach the close, not just the floor
    assert broker.minutes_needed(datetime(2026, 9, 23, 9, 0, tzinfo=UTC), close, 180) == 180   # floor wins near the close
    rt = _jwt(iat=int(now.timestamp()), exp=int(now.timestamp()) + 7 * 86400)
    st = broker.refresh_status({"STOCKBIT_REFRESH_TOKEN": rt}, None, now)
    assert st["present"] and 6.9 < st["days_left"] < 7.1
    assert broker.refresh_status({}, None, now) == {"present": False, "expires_at": None, "days_left": None}


def test_renew_if_needed_respects_the_session_end(monkeypatch) -> None:
    from blackheart_ingest.idx.feed import store as feed_store
    now = datetime(2026, 9, 23, 2, 0, tzinfo=UTC)                          # 09:00 WIB, market open
    close = datetime(2026, 9, 23, 9, 45, tzinfo=UTC)
    rt = _jwt(iat=int(now.timestamp()), exp=int(now.timestamp()) + 7 * 86400)
    calls = []
    monkeypatch.setattr(broker, "refresh_and_persist", lambda env=None, conn=None, **k: (calls.append(1), _jwt(exp=int(now.timestamp()) + 86400))[1])
    monkeypatch.setattr(broker, "_relay_refresh_token", lambda conn: rt)
    # 5 hours left: plenty by the 3-hour floor, NOT enough to reach the close -> renewed
    monkeypatch.setattr(feed_store, "load_token", lambda conn: {"access_token": "A", "expires_at": now + timedelta(hours=5), "source": "relay"})
    rep = broker.renew_if_needed(object(), {}, need_until=close, now=now)
    assert rep["renewed"] and rep["needed"] == 465 and len(calls) == 1
    assert not broker.renew_if_needed(object(), {}, now=now)["renewed"]     # same token, no session requirement -> fresh
    # 9 hours left: covers the close -> nothing to do
    monkeypatch.setattr(feed_store, "load_token", lambda conn: {"access_token": "A", "expires_at": now + timedelta(hours=9), "source": "relay"})
    assert broker.renew_if_needed(object(), {}, need_until=close, now=now)["reason"] == "fresh"
    # no refresh token anywhere -> a reason the guard can nag about, never an exception
    monkeypatch.setattr(broker, "_relay_refresh_token", lambda conn: None)
    monkeypatch.setattr(feed_store, "load_token", lambda conn: {"access_token": "A", "expires_at": now - timedelta(minutes=1), "source": "relay"})
    rep = broker.renew_if_needed(object(), {}, need_until=close, now=now)
    assert not rep["renewed"] and "no refresh token" in rep["reason"]


def test_refresh_and_persist_writes_env(tmp_path) -> None:
    env_file = tmp_path / "idx-local.env"
    env_file.write_text("# comment\n#STOCKBIT_TOKEN=old\nSTOCKBIT_REFRESH_TOKEN=oldR\nOTHER=keep\n", encoding="utf-8")
    env = {"STOCKBIT_REFRESH_TOKEN": "oldR"}
    got = broker.refresh_and_persist(env, str(env_file), poster=lambda u, b, t: (200, _REFRESH_RESP))
    assert got == "NEWACCESS"
    txt = env_file.read_text(encoding="utf-8")
    assert "STOCKBIT_TOKEN=NEWACCESS" in txt and "STOCKBIT_REFRESH_TOKEN=NEWREFRESH" in txt and "OTHER=keep" in txt
    assert "#STOCKBIT_TOKEN=old" not in txt and "REFRESH_TOKEN=oldR" not in txt
    with pytest.raises(broker.BrokerAuthError, match="STOCKBIT_REFRESH_TOKEN"):
        broker.refresh_and_persist({}, str(env_file))


def test_snapshot_round_trip(conn) -> None:
    _clean(conn)
    cfg = broker.config({"STOCKBIT_TOKEN": "k"})
    try:
        def one(url, headers):
            return 200, json.dumps(DIST).encode()
        res = broker.snapshot(conn, ["TEST"], cfg, fetcher=one, sleep=lambda s: None, expected_date=date(2026, 9, 17))
        assert res["ok"] == 1 and res["rows"] == 4 and res["date"] == "2026-09-17" and res["stopped"] is None
        again = broker.snapshot(conn, ["TEST"], cfg, fetcher=one, sleep=lambda s: None, expected_date=date(2026, 9, 17))
        assert again["skipped"] == 1 and again["requested"] == 0
        rows = broker.show(conn, "TEST")
        assert rows[0]["date_from"] == rows[0]["date_to"] == date(2026, 9, 17) and rows[0]["broker"] == "YU"
        stop = broker.snapshot(conn, ["TEST"], cfg, fetcher=lambda u, h: (402, b"{}"), sleep=lambda s: None)
        assert stop["ok"] == 0 and "402" in stop["stopped"]
    finally:
        _clean(conn)


# ---------------------------------------------------------------------------------------------------- wide capture
DIST_1Y = {"message": "ok",
           "data": {"date_info": "2026-09-23", "start_date": "2025-09-23", "end_date": "2026-09-23",
                    "by_value": {"top_broker_buy": [{"detail": {"code": "AK", "type": "Asing", "amount": 600_000_000_000},
                                                     "distribute_to": [{"code": "CC", "type": "Pemerintah", "amount": 290_000_000_000},
                                                                       {"code": "XL", "type": "Lokal", "amount": 240_000_000_000}]}],
                                 "top_broker_sell": [{"detail": {"code": "CC", "type": "Pemerintah", "amount": 500_000_000_000},
                                                      "distribute_to": [{"code": "AK", "type": "Asing", "amount": 290_000_000_000}]}]},
                    "by_volume": {"top_broker_buy": [], "top_broker_sell": []}}}
DIST_1Y_VOL = {"message": "ok",
               "data": {"date_info": "2026-09-23", "start_date": "2025-09-23", "end_date": "2026-09-23",
                        "by_value": {"top_broker_buy": [], "top_broker_sell": []},
                        "by_volume": {"top_broker_buy": [{"detail": {"code": "AK", "type": "Asing", "amount": 1_000_000},
                                                          "distribute_to": [{"code": "CC", "type": "Pemerintah", "amount": 600_000}]}],
                                      "top_broker_sell": [{"detail": {"code": "CC", "type": "Pemerintah", "amount": 900_000}, "distribute_to": []}]}}}


def test_parse_dist_totals_and_edges() -> None:
    rows = broker.parse_dist_totals(DIST_1Y)
    by = {r["broker"]: r for r in rows}
    assert by["AK"]["net"] == Decimal(600_000_000_000) and by["CC"]["net"] == Decimal(-500_000_000_000)
    assert [r["broker"] for r in rows] == ["AK", "CC"]
    edges = broker.parse_dist_edges(DIST_1Y)
    assert len(edges) == 3
    assert edges[0] == {"side": "BUY", "broker": "AK", "broker_type": "Asing", "counterparty": "CC", "counterparty_type": "Pemerintah",
                        "amount": Decimal(290_000_000_000)}
    assert edges[2]["side"] == "SELL" and edges[2]["broker"] == "CC" and edges[2]["counterparty"] == "AK"
    # the VOLUME view reads by_volume, and an empty by_value on it yields nothing
    assert broker.parse_dist_totals(DIST_1Y_VOL, broker.DATA_VOLUME)[0]["buy"] == Decimal(1_000_000)
    assert broker.parse_dist_totals(DIST_1Y_VOL) == [] and broker.parse_dist_edges(DIST_1Y) and broker.parse_dist_edges(DIST_1Y, broker.DATA_VOLUME) == []


def test_fetch_dist_window_and_statuses() -> None:
    cfg = {"key": "k", "base": broker.BASE, "params": dict(broker.DEFAULT_PARAMS)}
    seen = {}

    def fake(url, headers):
        seen["url"] = url
        return 200, json.dumps(DIST_1Y).encode()
    status, _payload, d_from, d_to, err = broker.fetch_dist("ptba", broker.PERIOD_YEAR, "INVESTOR_TYPE_FOREIGN", "MARKET_TYPE_ALL", broker.DATA_VOLUME, cfg, fake)
    assert status == 200 and err is None and (d_from, d_to) == (date(2025, 9, 23), date(2026, 9, 23))
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(seen["url"]).query))
    assert q["symbol"] == "PTBA" and q["period"] == broker.PERIOD_YEAR and q["investor_type"] == "INVESTOR_TYPE_FOREIGN"
    assert q["market_board"] == "MARKET_TYPE_ALL" and q["data_type"] == broker.DATA_VOLUME
    with pytest.raises(broker.BrokerPaywall):
        broker.fetch_dist("PTBA", cfg=cfg, fetcher=lambda u, h: (402, b"{}"))
    with pytest.raises(broker.BrokerRateLimited):
        broker.fetch_dist("PTBA", cfg=cfg, fetcher=lambda u, h: (429, b""))
    assert broker.fetch_dist("PTBA", cfg=cfg, fetcher=lambda u, h: (400, b'{"message":"invalid"}'))[0] == 400
    assert len(broker.MATRIX_CORE) == 4 and len(broker.MATRIX_DETAIL) == 48 and set(broker.BOARD_LABEL) == set(broker.DIST_BOARDS)


def test_store_dist_merges_value_and_volume_and_capture_resumes(conn) -> None:
    _clean(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.broker_flow WHERE code = 'TEST'")
    conn.commit()
    try:
        d0, d1 = date(2025, 9, 23), date(2026, 9, 23)
        args = ("TEST", d0, d1, broker.PERIOD_YEAR, "INVESTOR_TYPE_ALL", "MARKET_TYPE_REGULER")
        raw_a, n_a, e_a = broker.store_dist(conn, *args, broker.DATA_VALUE, 200, DIST_1Y, None)
        raw_b, n_b, e_b = broker.store_dist(conn, *args, broker.DATA_VOLUME, 200, DIST_1Y_VOL, None)
        assert raw_a != raw_b and (n_a, e_a, n_b, e_b) == (2, 3, 2, 1)
        with conn.cursor() as cur:
            cur.execute("""SELECT broker, buy_value, buy_lot, sell_lot, market_board, period FROM idx.broker_summary
                            WHERE code = 'TEST' AND date_to = %s ORDER BY broker""", (d1,))
            rows = cur.fetchall()
            cur.execute("SELECT side, broker, counterparty, value, volume FROM idx.broker_flow WHERE code = 'TEST' ORDER BY side, broker, counterparty")
            flow = cur.fetchall()
        rows = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]
        flow = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in flow]
        # one row per broker with value AND lots, the legacy board label, and the period that produced it
        assert rows[0][:4] == ("AK", Decimal(600_000_000_000), Decimal(1_000_000), None) and rows[0][4:] == ("MARKET_BOARD_REGULER", broker.PERIOD_YEAR)
        assert rows[1][0] == "CC" and rows[1][3] == Decimal(900_000)
        # the AK<-CC edge carries both value (from the VALUE view) and volume (from the VOLUME view)
        assert ("BUY", "AK", "CC", Decimal(290_000_000_000), Decimal(600_000)) in flow and len(flow) == 3
        # capture: a fake API that serves the same payload for every view; resume skips what is stored for that day
        calls = []

        def fake(url, headers):
            calls.append(url)
            return 200, json.dumps(DIST_1Y if "VALUE" in url else DIST_1Y_VOL).encode()
        cfg = {"key": "k", "base": broker.BASE, "params": dict(broker.DEFAULT_PARAMS)}
        res = broker.capture(conn, ["TEST"], broker.MATRIX_CORE, cfg, fetcher=fake, sleep=lambda s: None, expected_date=d1)
        assert res["requested"] == 3 and res["skipped"] == 1 and res["ok"] == 3 and res["stopped"] is None   # 1Y/ALL/REGULER/VALUE was stored above
        again = broker.capture(conn, ["TEST"], broker.MATRIX_CORE, cfg, fetcher=fake, sleep=lambda s: None, expected_date=d1)
        assert again["requested"] == 0 and again["skipped"] == 4
        stop = broker.capture(conn, ["TEST"], broker.MATRIX_DETAIL, cfg, fetcher=lambda u, h: (429, b""), sleep=lambda s: None, expected_date=None)
        assert stop["stopped"].startswith("HTTP 429") and stop["requested"] == 0
        capped = broker.capture(conn, ["TEST", "TEST2"], broker.MATRIX_DETAIL, cfg, fetcher=fake, sleep=lambda s: None, expected_date=None, max_requests=5)
        assert capped["requested"] == 5 and capped["stopped"] == "max requests 5"
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM idx.broker_flow WHERE code IN ('TEST', 'TEST2')")
            cur.execute("DELETE FROM idx.broker_summary_raw WHERE code IN ('TEST', 'TEST2')")
        conn.commit()


EMPTY = {"message": "Successfully loaded Broker Distribution data",
         "data": {"date_info": "", "by_value": {"top_broker_buy": [], "top_broker_sell": []},
                  "by_volume": {"top_broker_buy": [], "top_broker_sell": []}, "start_date": "", "end_date": ""}}


def test_capture_rests_on_a_streak_of_empty_payloads_and_gives_up(conn) -> None:
    """Throttling answers 200 with an empty payload - there is no 429 to stop on (measured 2026-09-24)."""
    _clean(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.broker_flow WHERE code LIKE 'TEST%'")
    conn.commit()
    cfg = {"key": "k", "base": broker.BASE, "params": dict(broker.DEFAULT_PARAMS)}
    slept: list[float] = []
    try:
        # one isolated empty name is just an empty name: no rest, nothing stored for it, the run carries on
        seq = [EMPTY, DIST_1Y, DIST_1Y, DIST_1Y]
        calls = {"n": 0}

        def mixed(url, headers):
            p = seq[min(calls["n"], len(seq) - 1)]
            calls["n"] += 1
            return 200, json.dumps(p).encode()
        res = broker.capture(conn, ["TEST"], broker.MATRIX_CORE, cfg, fetcher=mixed, sleep=slept.append, expected_date=None)
        assert res["empty"] == 1 and res["ok"] == 3 and res["backoffs"] == 0 and res["stopped"] is None
        assert 60.0 not in slept                                   # no rest was needed

        # a throttled endpoint: every answer empty -> rest, retry, rest, retry, then stop instead of burning the budget
        slept.clear()
        res2 = broker.capture(conn, ["TEST", "TEST2"], broker.MATRIX_DETAIL, cfg,
                              fetcher=lambda u, h: (200, json.dumps(EMPTY).encode()), sleep=slept.append,
                              expected_date=None, empty_backoff=60.0, max_backoffs=2)
        assert res2["stopped"] and "rate limited" in res2["stopped"]
        assert res2["backoffs"] == 2 and res2["ok"] == 0 and res2["empty"] == broker.EMPTY_STREAK
        assert slept.count(60.0) == 2                              # two rests, then it gave up
        assert res2["requested"] == broker.EMPTY_STREAK + 2        # three views plus the two retries, not thousands

        # the rest works: data on the retry resumes the run and resets the streak
        slept.clear()
        answers = [EMPTY, EMPTY, EMPTY, DIST_1Y]
        i = {"n": 0}

        def recovering(url, headers):
            p = answers[min(i["n"], len(answers) - 1)]
            i["n"] += 1
            return 200, json.dumps(p).encode()
        res3 = broker.capture(conn, ["TEST"], broker.MATRIX_CORE, cfg, fetcher=recovering, sleep=slept.append,
                              expected_date=None, empty_backoff=30.0)
        assert res3["backoffs"] == 1 and res3["stopped"] is None and res3["ok"] >= 1 and 30.0 in slept
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM idx.broker_flow WHERE code LIKE 'TEST%'")
            cur.execute("DELETE FROM idx.broker_summary_raw WHERE code LIKE 'TEST%'")
        conn.commit()
