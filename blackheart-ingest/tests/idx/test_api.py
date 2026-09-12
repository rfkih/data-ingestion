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
