"""Dead-man switch (idx/watchdog.py): the pure deadline rules, and that its alert is pushed at once."""
from __future__ import annotations

from datetime import datetime, timedelta

from blackheart_ingest.idx import alert_policy as ap
from blackheart_ingest.idx import watchdog as wd

W = wd.WIB
MON = datetime(2026, 9, 28, tzinfo=W)                      # a Monday


def at(h: int, m: int, day: datetime = MON) -> datetime:
    return day.replace(hour=h, minute=m)


def healthy(now: datetime) -> dict:
    rows = {"feed_watch": {"last_start": now - timedelta(minutes=2), "last_ok": now - timedelta(minutes=2)}}
    for d in wd.DEADLINES:
        rows[d.job] = {"last_start": at(d.by.hour, d.by.minute) - timedelta(minutes=20), "last_ok": at(d.by.hour, d.by.minute) - timedelta(minutes=10)}
    rows["session_tick"] = {"last_start": now - timedelta(minutes=1), "last_ok": now - timedelta(minutes=1)}
    return rows


def test_quiet_when_everything_ran() -> None:
    now = at(21, 45)
    assert wd.check(healthy(now), now) == []


def test_silent_scheduler_is_one_alert_only() -> None:
    now = at(10, 0)
    rows = {"feed_watch": {"last_start": now - timedelta(minutes=40)}}
    got = wd.check(rows, now)
    assert [b["rule"] for b in got] == ["alive"]


def test_missed_plan_and_stalled_session() -> None:
    now = at(21, 45)
    rows = healthy(now)
    rows["combo_plan"]["last_ok"] = at(21, 10) - timedelta(days=1)           # yesterday's run only
    assert [b["rule"] for b in wd.check(rows, now)] == ["combo_plan"]
    now = at(11, 0)
    rows = healthy(now)
    rows["session_tick"]["last_ok"] = now - timedelta(minutes=12)
    rules = [b["rule"] for b in wd.check(rows, now)]
    assert "session_tick" in rules and "combo_plan" not in rules               # not due yet at 11:00


def test_failed_critical_job_but_not_a_retrying_one() -> None:
    now = at(21, 45)
    rows = healthy(now)
    rows["combo_plan"]["last_error_at"] = now - timedelta(minutes=1)
    rows["combo_plan"]["last_error"] = "KeyError: x"
    rows["daily_chain"] = {"last_start": now, "last_error_at": now - timedelta(minutes=1)}
    rules = [b["rule"] for b in wd.check(rows, now)]
    assert "failed:combo_plan" in rules and not any("daily_chain" in r for r in rules)


def test_weekend_only_checks_alive() -> None:
    sat = at(21, 45, MON + timedelta(days=5))
    rows = {"feed_watch": {"last_start": sat - timedelta(minutes=3)}}
    assert wd.check(rows, sat) == []


def test_watchdog_alert_is_pushed_at_once() -> None:
    row = {"severity": "critical", "job": "watchdog", "kind": "ops", "message": "[watchdog] the 21:10 plan has not completed"}
    assert ap.actionable(row) and not ap.deferred(row) and ap.push_now(row)


def test_stale_backup_is_flagged_every_day_but_never_before_its_first_run() -> None:
    sat = at(10, 0, MON + timedelta(days=5))
    alive = {"feed_watch": {"last_start": sat - timedelta(minutes=3)}}
    assert wd.check(alive, sat) == []                                           # never ran yet: not judged
    rows = {**alive, "db_backup": {"last_start": sat - timedelta(hours=30), "last_ok": sat - timedelta(hours=30)}}
    assert [b["rule"] for b in wd.check(rows, sat)] == ["db_backup"]
    rows["db_backup"]["last_ok"] = sat - timedelta(hours=12)
    assert wd.check(rows, sat) == []
