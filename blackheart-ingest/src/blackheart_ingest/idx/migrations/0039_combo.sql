-- The combined book (idx/combo_book.py, 2026-09-25; operator: live Rp 20 M, "3 aktif strategi top 1,2,3", 5 % / 5 % / 10 % of NAV,
-- push + a trading plan every night and before the open, execution measured against the plan).
--
-- idx.book.params   free-form per-book settings the newer rules read (the combo sleeves and their sizes, the ML parameters);
--                   the older columns stay as they are.
-- idx.combo_watch   the ML sleeve's two-step entry: a name the score qualified at the close (signal) is bought only when its
--                   price confirms (>= level) within the window; one row per (book, code, signal day).
-- idx.combo_scorecard  the nightly per-sleeve reading of the live book against its backtest: fills, misses, slippage, delay, P&L.

ALTER TABLE idx.book ADD COLUMN IF NOT EXISTS params JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS idx.combo_watch (
    id            BIGSERIAL PRIMARY KEY,
    book          TEXT NOT NULL REFERENCES idx.book(book),
    code          TEXT NOT NULL,
    sleeve        TEXT NOT NULL DEFAULT 'ml',
    signal_date   DATE NOT NULL,                       -- the close whose score qualified the name
    ref_price     NUMERIC(14, 2) NOT NULL,             -- that close (raw)
    level_price   NUMERIC(14, 2) NOT NULL,             -- buy when the price is at or above this (ref x (1 + confirm), on the tick)
    until_date    DATE NOT NULL,                       -- the last day the confirmation counts
    e_bps         NUMERIC(10, 2),                      -- the expected 5-day excess the score gave, in bps
    cost_bps      NUMERIC(10, 2),                      -- the round trip the score had to pay for
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'triggered', 'expired', 'cancelled')),
    ticket_id     BIGINT,
    triggered_at  TIMESTAMPTZ,
    trigger_price NUMERIC(14, 2),
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (book, code, signal_date)
);
CREATE INDEX IF NOT EXISTS combo_watch_pending_idx ON idx.combo_watch (book, until_date) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS idx.combo_scorecard (
    book         TEXT NOT NULL REFERENCES idx.book(book),
    d            DATE NOT NULL,
    payload      JSONB NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (book, d)
);
