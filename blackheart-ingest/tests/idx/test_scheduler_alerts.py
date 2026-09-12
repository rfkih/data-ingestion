"""Scheduler wrappers turn job failures into idx.alert rows the app can show and acknowledge (needs DB)."""
from __future__ import annotations

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from blackheart_ingest.idx import runlog, scheduler
from blackheart_ingest.idx.jobs import daily as job_daily


@pytest.fixture
def db():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield conn
    conn.close()


def test_failed_daily_becomes_alert_and_can_be_acknowledged(db, monkeypatch) -> None:
    marker = "forced failure for test_scheduler_alerts"

    def fake_run(conn, client, d):
        r = runlog.RunResult("daily", d.isoformat(), status="failed", error=marker)
        return r

    monkeypatch.setattr(job_daily, "run", fake_run)
    monkeypatch.setattr(job_daily, "latest_bar_date", lambda conn: None)
    monkeypatch.setattr(scheduler, "today_wib", lambda: __import__("datetime").date(2026, 9, 11))  # a Friday
    scheduler.run_daily_chain()

    open_alerts = runlog.open_alerts(db)
    mine = [a for a in open_alerts if marker in a["message"]]
    assert mine, "expected the forced failure to raise an alert"
    assert mine[0]["severity"] == "critical" and mine[0]["job"] == "daily"

    from blackheart_ingest.workers.server import app
    with TestClient(app) as c:
        ops = c.get("/idx/ops").json()
        assert any(marker in a["message"] for a in ops["open_alerts"])
        for a in mine:
            assert c.post(f"/idx/alerts/{a['id']}/ack").status_code == 200
        ops2 = c.get("/idx/ops").json()
        assert not any(marker in a["message"] for a in ops2["open_alerts"])
