-- Dead-man switch (Track A1, operator 2026-09-26): the scheduler writes one row per job id as its jobs start, finish, fail or
-- are missed (an APScheduler event listener in idx/scheduler.py). idx/watchdog.py - run by its OWN Windows task, outside the
-- scheduler, so a hung or dead scheduler cannot silence it - checks the rows against the deadlines the desk depends on.
CREATE TABLE IF NOT EXISTS idx.job_heartbeat (
    job            TEXT PRIMARY KEY,
    last_start     TIMESTAMPTZ,
    last_ok        TIMESTAMPTZ,
    last_error_at  TIMESTAMPTZ,
    last_error     TEXT,
    last_missed    TIMESTAMPTZ,
    runs           BIGINT NOT NULL DEFAULT 0,
    errors         BIGINT NOT NULL DEFAULT 0
);
