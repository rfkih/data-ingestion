"""Broker summary feed: config from the environment, URL building, windows, the parser (the real shape + tolerant fallbacks),
the detector block, and a store/backfill/reparse round trip."""
from __future__ import annotations

import json
import os
from datetime import date
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


def test_extract_tokens_and_refresh() -> None:
    assert broker.extract_tokens({"data": {"access": "AAA", "refresh_token": "RRR"}}) == ("AAA", "RRR")
    assert broker.extract_tokens({"accessToken": "A2"}) == ("A2", None)
    assert broker.extract_tokens({"nothing": 1}) == (None, None)
    posts = []

    def poster(url, body):
        posts.append((url, body))
        return 200, b'{"data": {"access": "NEWACCESS", "refresh": "NEWREFRESH"}}'

    access, rotated, resp = broker.refresh_access_token("oldR", poster)
    assert access == "NEWACCESS" and rotated == "NEWREFRESH"
    assert posts[0][0] == broker.REFRESH_URL and posts[0][1] == {"refresh_token": "oldR"}
    with pytest.raises(broker.BrokerAuthError):
        broker.refresh_access_token("bad", lambda u, b: (401, b'{"message":"invalid"}'))
    with pytest.raises(broker.BrokerFetchError):
        broker.refresh_access_token("x", lambda u, b: (200, b'{"data": {"nope": 1}}'))


def test_refresh_and_persist_writes_env(tmp_path) -> None:
    env_file = tmp_path / "idx-local.env"
    env_file.write_text("# comment\n#STOCKBIT_TOKEN=old\nSTOCKBIT_REFRESH_TOKEN=oldR\nOTHER=keep\n", encoding="utf-8")
    env = {"STOCKBIT_REFRESH_TOKEN": "oldR"}
    got = broker.refresh_and_persist(env, str(env_file), poster=lambda u, b: (200, b'{"access":"NEWA","refresh":"NEWR"}'))
    assert got == "NEWA"
    txt = env_file.read_text(encoding="utf-8")
    assert "STOCKBIT_TOKEN=NEWA" in txt and "STOCKBIT_REFRESH_TOKEN=NEWR" in txt and "OTHER=keep" in txt
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
