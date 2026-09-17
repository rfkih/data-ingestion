-- Price levels per held name (2026-09-17): a stop, a take-profit or an index level the operator wants to be told about.
-- Checked after every mark (idx/levels.py check, in the daily chain); a hit raises a critical alert (pushed by notify when
-- Telegram is configured) once per level, and the level is stamped so it does not fire again until it is reset.
CREATE TABLE idx.price_level (
    id            BIGSERIAL PRIMARY KEY,
    book          TEXT NOT NULL REFERENCES idx.book (book),
    code          TEXT NOT NULL,                 -- a held code, or an index code (COMPOSITE) for a market-level alert
    kind          TEXT NOT NULL CHECK (kind IN ('stop', 'take_profit', 'warn')),
    level         NUMERIC(18,4) NOT NULL,        -- close at or below (stop, warn) / at or above (take_profit) fires
    note          TEXT,                          -- what to do when it fires, in the operator's words
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    triggered_at  TIMESTAMPTZ,
    triggered_px  NUMERIC(18,4),
    UNIQUE (book, code, kind)
);
