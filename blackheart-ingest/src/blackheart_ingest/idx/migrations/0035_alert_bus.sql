-- The alert bus (phase 2 of docs/superpowers/plans/2026-09-24-blackridge-strategies-and-alert-stream-plan.md).
--
-- One rule makes "stream everything" one problem instead of seven: a producer INSERTs a row and never picks a channel.
-- The phone push, Telegram and the browser stream are all consumers of idx.alert. So the table learns the fields a
-- consumer needs to route and render a row - what kind of thing happened, which strategy / name / book / person it
-- concerns, the structured detail, how to recognise a repeat, and when it stops being true.
--
-- Every new column is nullable and every existing writer keeps working untouched: a row with kind IS NULL is one of
-- the old free-text alerts and still reads as `severity · job · message`.

ALTER TABLE idx.alert
    ADD COLUMN IF NOT EXISTS kind        TEXT,          -- signal | ticket | exec | regime | ara | risk | feed | ops
    ADD COLUMN IF NOT EXISTS strategy    TEXT,          -- registry key (idx/registry.py)
    ADD COLUMN IF NOT EXISTS code        TEXT,
    ADD COLUMN IF NOT EXISTS book        TEXT,
    ADD COLUMN IF NOT EXISTS user_id     TEXT,          -- whose alert this is; NULL = the desk's
    ADD COLUMN IF NOT EXISTS payload     JSONB,         -- what a screen renders: price, lots, lean, counts
    ADD COLUMN IF NOT EXISTS dedupe_key  TEXT,          -- the producer's name for "this same thing"
    ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ;   -- an execution read is stale in seconds; the page drops it

CREATE INDEX IF NOT EXISTS alert_kind_ts   ON idx.alert (kind, ts DESC);
CREATE INDEX IF NOT EXISTS alert_strategy  ON idx.alert (strategy, ts DESC) WHERE strategy IS NOT NULL;
-- One open row per dedupe_key: a producer that repeats itself updates in place instead of filling the table. Once a
-- row is acknowledged the key is free again, so tomorrow's ticket:12:issued is a new row, not a resurrection.
CREATE UNIQUE INDEX IF NOT EXISTS alert_dedupe ON idx.alert (dedupe_key)
    WHERE dedupe_key IS NOT NULL AND acknowledged_at IS NULL;

-- The stream's wake-up. The payload is the row id only: NOTIFY has an 8 kB limit and a payload column has no such
-- bound, so the listener fetches the row itself rather than risking a truncated message.
CREATE OR REPLACE FUNCTION idx.alert_notify() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('idx_alert', NEW.id::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS alert_notify ON idx.alert;
CREATE TRIGGER alert_notify AFTER INSERT OR UPDATE ON idx.alert
    FOR EACH ROW EXECUTE FUNCTION idx.alert_notify();

-- What each strategy said on a day, whether or not it became a ticket. Tickets are the actionable subset; this is the
-- record a page reads to answer "what did the trend rule see last Tuesday, and what happened to it".
CREATE TABLE IF NOT EXISTS idx.strategy_signal (
    strategy    TEXT NOT NULL,                 -- registry key
    as_of       DATE NOT NULL,
    code        TEXT NOT NULL,
    action      TEXT NOT NULL,                 -- buy | sell | hold | hold_back | watch
    ref_price   NUMERIC(18,2),
    size_pct    NUMERIC(8,4),
    reason      JSONB,                         -- why, in the producer's own terms (volume ratio, gap, gate state)
    book        TEXT NOT NULL DEFAULT '',      -- '' = the strategy said it, not a particular book
    ticket_id   BIGINT,                        -- filled in when the signal became a ticket line
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (strategy, as_of, code, book)
);
CREATE INDEX IF NOT EXISTS strategy_signal_as_of ON idx.strategy_signal (as_of DESC, strategy);

-- Per-person mutes. A row is a mute: no row means everything is delivered, which is the default a new account gets.
CREATE TABLE IF NOT EXISTS idx.alert_pref (
    user_id    TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT '',       -- '' = every kind
    strategy   TEXT NOT NULL DEFAULT '',       -- '' = every strategy
    muted      BOOLEAN NOT NULL DEFAULT true,
    quiet_from TIME,                           -- local (WIB) quiet hours; NULL = none
    quiet_to   TIME,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, kind, strategy)
);
