"""/idx/search and /idx/stock/{code} - the app's search box and Stock screen (needs the local DB; skipped otherwise)."""
from __future__ import annotations

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

STOCK_KEYS = {"code", "name", "sector", "subsector", "board", "listed", "as_of", "close", "prev", "open", "high", "low", "volume", "value", "trades",
              "chg_pct", "mcap", "shares", "pe", "pbv", "dy", "eps", "bvps", "hi52", "lo52", "v60", "liquid", "quarterly", "annual", "dividends",
              "profile", "holders", "news", "foreign"}


@pytest.fixture(scope="module")
def client():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        psycopg.connect(dsn, connect_timeout=5).close()
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    from blackheart_ingest.workers.server import app
    with TestClient(app) as c:
        yield c


def test_search_prefix_first_then_name(client) -> None:
    rows = client.get("/idx/search", params={"q": "bb", "limit": 8}).json()
    assert rows and all({"code", "name", "sector", "close", "chg_pct"} <= set(r) for r in rows)
    assert rows[0]["code"].startswith("BB")
    by_name = client.get("/idx/search", params={"q": "rakyat"}).json()
    assert any(r["code"] == "BBRI" for r in by_name)
    assert client.get("/idx/search", params={"q": ""}).json() == []
    recent = client.get("/idx/search", params={"q": "", "codes": "TLKM,BBRI"}).json()
    assert [r["code"] for r in recent] == ["TLKM", "BBRI"]


def test_stock_shape(client) -> None:
    r = client.get("/idx/stock/bbri")
    assert r.status_code == 200, r.text
    body = r.json()
    assert STOCK_KEYS <= set(body)
    assert body["code"] == "BBRI" and body["close"] and body["as_of"]
    assert body["profile"] is None and body["holders"] == []                     # not held by the data plane - never invented
    assert body["liquid"] in (True, False, None)
    for f in body["quarterly"] + body["annual"]:
        assert {"period", "revenue", "net_profit", "eps", "margin"} <= set(f)
    assert all({"ex_date", "pay_date", "amount", "yield_pct"} <= set(d) for d in body["dividends"])
    assert all({"date", "net_value"} <= set(x) for x in body["foreign"]) and len(body["foreign"]) <= 5
    if body["hi52"] is not None:
        assert body["lo52"] <= body["hi52"] and body["lo52"] <= body["close"] * 1.05 and body["hi52"] >= body["close"] * 0.95


def test_stock_unknown_is_404(client) -> None:
    assert client.get("/idx/stock/ZZZZ9").status_code == 404
