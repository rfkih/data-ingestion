"""Dead-man switch for the desk's scheduler (Track A1, operator 2026-09-26: "okay do track A").

The scheduler already restarts itself when its process dies (the 10-minute Windows task trigger). What nothing caught: a
scheduler that is alive but not firing, and a job that fails or never runs while the process looks fine - a missed 21:10 plan
or 09:00 gap scan costs a day of trades and nobody hears about it. Two halves:

  heartbeat  ``record(event)`` - an APScheduler listener in idx/scheduler.py writes idx.job_heartbeat (migration 0056) as each
             job starts, finishes, fails or is missed. Never raises: a heartbeat must not break the job it watches.
  watchdog   ``check(conn, now)`` - pure rules over those rows, run by its OWN Windows task every 10 minutes
             (scripts/idx-watchdog-task.ps1 -> ``idx watchdog``), so a hung scheduler cannot silence it. A breach is a critical
             alert on job ``watchdog`` (pushed at once - alert_policy), one per rule per day.

Rules (WIB, Monday-Friday; a job fires on exchange holidays too - it checks the calendar itself - so a holiday is not a miss):
  alive           some job started in the last 15 minutes (feed_watch every 5, token_guard every 10 run every day)
  <job> by HH:MM  the job must have finished OK today by the deadline (the time it is scheduled plus room to run)
  session_tick    09:05-15:55: finished OK within the last 5 minutes (the session rule engine: ML confirmations, stops, gap exits)
  failed          a money-critical job (CRITICAL) whose last error today is newer than its last success
  db_backup       the nightly backup succeeded within the last 26 hours (every day)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
ALIVE_MIN = 15
TICK_MAX_AGE = timedelta(minutes=5)
TICK_WINDOW = (time(9, 5), time(15, 55))


@dataclass(frozen=True)
class Deadline:
    job: str
    by: time
    what: str


# the jobs money depends on; deadline = scheduled time + the time it normally needs + slack
DEADLINES = (
    Deadline("combo_preopen", time(8, 45), "the 08:30 pre-open plan push"),
    Deadline("combo_gap_entry", time(9, 15), "the 09:00 gap-fade entry scan"),
    Deadline("daily_last", time(20, 20), "the daily data chain (last run 20:00)"),
    Deadline("risk_check", time(20, 40), "the nightly risk check"),
    Deadline("combo_expire", time(20, 45), "the 20:30 missed-line expiry, scorecard and kill rules"),
    Deadline("combo_plan", time(21, 30), "the 21:10 plan for tomorrow"),
)


# jobs that must have succeeded within a maximum age, every day (a job that has never run is not judged yet)
STALE = (("db_backup", timedelta(hours=26), "the nightly database backup"),)
CRITICAL = {d.job for d in DEADLINES} | {"session_tick", "gapfade_entry", "gapfade_exit", "combo_nudge"}


def record(conn: psycopg.Connection, job: str, kind: str, when: datetime | None = None, error: str | None = None) -> None:
    """kind: start | ok | error | missed. Upsert one heartbeat row."""
    when = when or datetime.now(WIB)
    col = {"start": "last_start", "ok": "last_ok", "error": "last_error_at", "missed": "last_missed"}[kind]
    extra = {"ok": ", runs = idx.job_heartbeat.runs + 1", "error": ", errors = idx.job_heartbeat.errors + 1, last_error = EXCLUDED.last_error"}.get(kind, "")
    with conn.cursor() as cur:
        cur.execute(f"""INSERT INTO idx.job_heartbeat (job, {col}, last_error, runs, errors) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (job) DO UPDATE SET {col} = EXCLUDED.{col}{extra}""",
                    (job, when, (error or "")[:500] if kind == "error" else None, 1 if kind == "ok" else 0, 1 if kind == "error" else 0))
    conn.commit()


def listener(event: Any) -> None:
    """APScheduler listener (EVENT_JOB_SUBMITTED | EXECUTED | ERROR | MISSED). Never raises."""
    try:
        from apscheduler.events import (
            EVENT_JOB_ERROR,
            EVENT_JOB_EXECUTED,
            EVENT_JOB_MISSED,
            EVENT_JOB_SUBMITTED,
        )

        from ..shared.db import get_connection
        kind = {EVENT_JOB_SUBMITTED: "start", EVENT_JOB_EXECUTED: "ok", EVENT_JOB_ERROR: "error", EVENT_JOB_MISSED: "missed"}.get(event.code)
        if kind is None or event.job_id == "singleton_lock":
            return
        err = f"{type(event.exception).__name__}: {event.exception}" if kind == "error" and getattr(event, "exception", None) else None
        with get_connection() as conn:
            record(conn, event.job_id, kind, error=err)
    except Exception:                                               # a heartbeat must never break the job it watches
        logger.exception("job heartbeat failed")


def check(rows: dict[str, dict[str, Any]], now: datetime, trading: bool | None = None) -> list[dict[str, str]]:
    """Pure. heartbeat rows by job -> breaches [{rule, message}]. ``trading`` = is today an exchange trading day (the caller
    reads idx/exchange_calendar.py); None = Monday-Friday. On a closed day only the alive and backup rules apply."""
    now = now.astimezone(WIB)
    out: list[dict[str, str]] = []
    starts = [r["last_start"] for r in rows.values() if r.get("last_start")]
    if not starts or max(starts) < now - timedelta(minutes=ALIVE_MIN):
        last = max(starts).astimezone(WIB).strftime("%a %H:%M") if starts else "never"
        out.append({"rule": "alive", "message": f"scheduler silent: no job started for {ALIVE_MIN}+ minutes (last {last}) - hung or down"})
        return out                                                   # everything below would only repeat it
    for job, age, what in STALE:
        r = rows.get(job)
        if r is not None and (r.get("last_ok") is None or r["last_ok"] < now - age):
            out.append({"rule": job, "message": f"{what} has not succeeded for more than {int(age.total_seconds() // 3600)} h"})
    if not (trading if trading is not None else now.weekday() < 5):
        return out
    day0 = datetime.combine(now.date(), time(0), WIB)
    for d in DEADLINES:
        if now.time() < d.by:
            continue
        ok = rows.get(d.job, {}).get("last_ok")
        if ok is None or ok < day0:
            out.append({"rule": d.job, "message": f"{d.what} has not completed today (job {d.job}, due by {d.by:%H:%M})"})
    if TICK_WINDOW[0] <= now.time() <= TICK_WINDOW[1]:
        ok = rows.get("session_tick", {}).get("last_ok")
        if ok is None or ok < now - TICK_MAX_AGE:
            age = "never" if ok is None else f"{int((now - ok).total_seconds() // 60)} min ago"
            out.append({"rule": "session_tick", "message": f"session rule engine stalled: last good tick {age} (ML confirmations, stops, gap exits)"})
    for job, r in rows.items():
        if job not in CRITICAL:                                      # other jobs retry on their own (the daily chain every 15 min)
            continue
        e, ok = r.get("last_error_at"), r.get("last_ok")
        if e and e >= day0 and (ok is None or e > ok):
            out.append({"rule": f"failed:{job}", "message": f"job {job} failed at {e.astimezone(WIB):%H:%M}: {(r.get('last_error') or '')[:160]}"})
    return out


def run(conn: psycopg.Connection, now: datetime | None = None, alert: bool = True) -> list[dict[str, str]]:
    from . import runlog
    now = now or datetime.now(WIB)
    with conn.cursor() as cur:
        cur.execute("SELECT job, last_start, last_ok, last_error_at, last_error, last_missed FROM idx.job_heartbeat")
        cols = [c.name for c in cur.description]
        rows = {}
        for r in cur.fetchall():
            d = r if isinstance(r, dict) else dict(zip(cols, r, strict=True))
            rows[d["job"]] = d
    from .exchange_calendar import is_trading_day
    breaches = check(rows, now, trading=is_trading_day(now))
    if alert:
        for b in breaches:
            runlog.alert(conn, "critical", "watchdog", f"[watchdog] {b['message']}", kind="ops",
                         dedupe_key=f"watchdog:{b['rule']}:{now.astimezone(WIB).date()}")
    return breaches
