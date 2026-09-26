-- Session rule engine (idx/intents.py, operator 2026-09-26): an action that waits for a condition is a ROW, not a scheduled job.
-- One session tick evaluates every armed intent of every book against the live prices and turns the ones whose trigger holds
-- into tickets. Every status change is recorded in order_intent_event (who, when, at what price) so any exit can be audited.
-- Phase 1 kind: 'ml_stop' (the ML sleeve's stop checked from 15:40 WIB and sold in the same closing session, study #288).
CREATE TABLE IF NOT EXISTS idx.order_intent (
    id          BIGSERIAL PRIMARY KEY,
    book        TEXT        NOT NULL,
    sleeve      TEXT        NOT NULL,
    code        TEXT        NOT NULL,
    side        TEXT        NOT NULL CHECK (side IN ('buy', 'sell')),
    kind        TEXT        NOT NULL,
    trigger     JSONB       NOT NULL,              -- {"type": "price_at_or_below", "level": 997.5, "after": "15:40", "before": "15:50"}
    lots        NUMERIC(20, 0),                    -- NULL = the sleeve's whole position when it fires
    ref         JSONB       NOT NULL DEFAULT '{}', -- what the intent was derived from (entry price, stop %, ...)
    status      TEXT        NOT NULL DEFAULT 'armed'
                CHECK (status IN ('armed', 'triggered', 'ticket_issued', 'filled', 'expired', 'cancelled')),
    expires_on  DATE,
    ticket_id   BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- one live intent of a kind per name and book
CREATE UNIQUE INDEX IF NOT EXISTS order_intent_one_live ON idx.order_intent (book, code, kind)
    WHERE status IN ('armed', 'triggered', 'ticket_issued');
CREATE INDEX IF NOT EXISTS order_intent_armed ON idx.order_intent (status) WHERE status IN ('armed', 'ticket_issued');

CREATE TABLE IF NOT EXISTS idx.order_intent_event (
    id          BIGSERIAL PRIMARY KEY,
    intent_id   BIGINT      NOT NULL REFERENCES idx.order_intent (id) ON DELETE CASCADE,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    from_status TEXT,
    to_status   TEXT        NOT NULL,
    price       NUMERIC(20, 4),
    note        TEXT,
    actor       TEXT        NOT NULL DEFAULT 'scheduler'
);
CREATE INDEX IF NOT EXISTS order_intent_event_intent ON idx.order_intent_event (intent_id, at);
