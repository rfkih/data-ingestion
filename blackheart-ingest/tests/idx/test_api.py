"""/idx/* routes on the served app (needs the local DB; skipped otherwise)."""
from __future__ import annotations

import os

import psycopg
import pytest
from fastapi.testclient import TestClient


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


def test_ops_shape(client) -> None:
    r = client.get("/idx/ops")
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("now", "last_bar_date", "daily_summary", "active_listings", "bronze_objects", "open_alerts", "runs"):
        assert k in body
    assert isinstance(body["runs"], list) and isinstance(body["open_alerts"], list)


def test_runs_filter(client) -> None:
    r = client.get("/idx/runs", params={"job": "daily", "limit": 5})
    assert r.status_code == 200
    assert all(x["job"] == "daily" for x in r.json())


def test_ack_unknown_alert_is_404(client) -> None:
    r = client.post("/idx/alerts/999999999/ack")
    assert r.status_code == 404


def test_candidates_shape(client) -> None:
    r = client.get("/idx/candidates")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"run_date", "pool", "selected", "rows", "strategy", "size"}
    if body["rows"]:
        row = body["rows"][0]
        assert row["rank"] == 1 and row["selected"] is True
        assert {"code", "ep", "bp", "dy", "gate_strict", "strict_fails", "warnings"} <= set(row)
        assert len(body["rows"]) == body["selected"]
        assert len(client.get("/idx/candidates", params={"all": 1}).json()["rows"]) == body["pool"]


def test_push_register_needs_an_account(client, monkeypatch) -> None:
    """The per-account paths are in test_multiuser.py; here: a phone belongs to an account, the desk's own routes still answer."""
    from blackheart_ingest.idx import push
    monkeypatch.delenv(push.SA_ENV, raising=False)
    assert client.post("/idx/push/register", json={"token": "test-device-api-" + "x" * 24}).status_code == 401
    d = client.get("/idx/push/devices").json()
    assert d["configured"] is False and isinstance(d["devices"], list)
    t = client.post("/idx/push/test", json={}).json()
    assert t["sent"] == 0 and t["configured"] is False                                     # no Firebase file: a no-op that says so


def test_books_list(client) -> None:
    r = client.get("/idx/books")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows and {"book", "kind", "rule", "nav_now", "cash", "positions", "open_ticket", "halted"} <= set(rows[0])
    assert all(x["kind"] in ("live", "paper") and x["rule"] in ("annual", "trend", "gapfade", "combo") and not x["book"].startswith("test") for x in rows)
    assert [x["kind"] for x in rows] == sorted((x["kind"] for x in rows), key=lambda k: k != "live")    # live first
