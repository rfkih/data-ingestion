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


def test_a_repeating_failure_stays_one_alert_and_resolves_when_it_clears(db, monkeypatch) -> None:
    """The 2026-09-23 Cloudflare day raised 17 identical critical rows - one per 15-minute retry - and nothing ever
    closed them. A repeated failure is one incident, and the run that finally succeeds is what clears it."""
    import datetime as dt
    marker = "forced repeat failure for test_scheduler_alerts"
    d = dt.date(2026, 9, 11)                                                  # a Friday
    monkeypatch.setattr(scheduler, "today_wib", lambda: d)
    monkeypatch.setattr(job_daily, "run", lambda conn, client, day: runlog.RunResult("daily", day.isoformat(), status="failed", error=marker))
    monkeypatch.setattr(job_daily, "latest_bar_date", lambda conn: None)
    runlog.resolve(db, "daily", like=f"%{marker}%")                           # a clean slate if an earlier run left rows

    for _ in range(3):                                                        # the chain retries every 15 minutes
        scheduler.run_daily_chain()
    mine = [a for a in runlog.open_alerts(db, limit=200) if marker in a["message"]]
    assert len(mine) == 1, f"one incident must stay one alert, got {len(mine)}"

    monkeypatch.setattr(job_daily, "latest_bar_date", lambda conn: d)         # the bar finally lands
    scheduler.run_daily_chain()
    assert not [a for a in runlog.open_alerts(db, limit=200) if marker in a["message"]], "the alert should have resolved itself"


def test_bar_gaps_finds_a_failed_day_and_ignores_a_holiday(db) -> None:
    """Only a day that FAILED (or was never attempted) is a gap: a public holiday answers with an empty payload, so its
    run is 'ok' with no rows and must not be re-asked for every twelve hours forever."""
    import datetime as dt
    failed_day, holiday = dt.date(2026, 3, 19), dt.date(2026, 3, 20)          # two weekdays with no bars in the test db
    with db.cursor() as cur:
        cur.execute("DELETE FROM idx.ingest_run WHERE job = 'daily' AND run_key = ANY(%s)",
                    ([failed_day.isoformat(), holiday.isoformat()],))
        cur.execute("INSERT INTO idx.ingest_run (job, run_key, started_at, finished_at, status, rows_out) "
                    "VALUES ('daily', %s, now(), now(), 'failed', 0), ('daily', %s, now(), now(), 'ok', 0)",
                    (failed_day.isoformat(), holiday.isoformat()))
    db.commit()
    try:
        days = (dt.date.today() - failed_day).days + 1
        gaps = scheduler.bar_gaps(db, days=days)
        assert failed_day in gaps, "a day the fetch failed on is a gap"
        assert holiday not in gaps, "a holiday that answered empty is not a gap"
    finally:
        with db.cursor() as cur:
            cur.execute("DELETE FROM idx.ingest_run WHERE job = 'daily' AND run_key = ANY(%s)",
                        ([failed_day.isoformat(), holiday.isoformat()],))
        db.commit()
