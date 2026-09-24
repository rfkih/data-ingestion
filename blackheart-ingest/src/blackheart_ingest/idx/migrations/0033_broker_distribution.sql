-- Broker distribution, widened (2026-09-24). The free ``order-trade/broker/distribution`` endpoint was re-probed
-- (research/IDX_BREAKOUT_ACCUM_2026-09-24.md section D) and serves far more than the desk was storing:
--   period      = TB_PERIOD_LAST_1_DAY | LAST_1_MONTH | LAST_3_MONTHS | LAST_1_YEAR   (rolling, always ending on the
--                 last trading day - the window cannot be moved into the past, so history only accumulates forward)
--   investor_type = INVESTOR_TYPE_ALL | FOREIGN | DOMESTIC
--   market_board  = MARKET_TYPE_REGULER | MARKET_TYPE_ALL (incl. negotiated) | MARKET_TYPE_TUNAI
--   data_type     = ..._VALUE | ..._VOLUME
-- and every response carries the full buyer -> seller matrix (``distribute_to``, up to ~77 edges per broker) that the
-- parser was dropping on the floor. This migration makes room for all of it: data_type joins the raw key, the window
-- rows learn which period produced them, and the matrix gets its own table.

-- period joins the key too: two views must never overwrite each other even if the API ever answers the same window
-- for two periods. Rows fetched before this migration (the legacy per-window feed and the 1-day snapshots) get 'LEGACY'.
ALTER TABLE idx.broker_summary_raw ADD COLUMN IF NOT EXISTS data_type TEXT NOT NULL DEFAULT 'BROKER_DISTRIBUTION_DATA_TYPE_VALUE';
ALTER TABLE idx.broker_summary_raw ADD COLUMN IF NOT EXISTS period    TEXT NOT NULL DEFAULT 'LEGACY';
ALTER TABLE idx.broker_summary_raw DROP CONSTRAINT IF EXISTS broker_summary_raw_code_date_from_date_to_investor_type_mar_key;
CREATE UNIQUE INDEX IF NOT EXISTS broker_summary_raw_key
    ON idx.broker_summary_raw (code, date_from, date_to, investor_type, market_board, transaction_type, data_type, period);

ALTER TABLE idx.broker_summary  ADD COLUMN IF NOT EXISTS period TEXT;   -- which rolling window produced these totals
ALTER TABLE idx.broker_detector ADD COLUMN IF NOT EXISTS period TEXT;

-- One row per directed edge: on BUY rows `broker` bought `value` worth of the name from `counterparty` inside the
-- window; on SELL rows `broker` sold to `counterparty`. Value and volume land in the same row (two requests, one row).
CREATE TABLE IF NOT EXISTS idx.broker_flow (
    code              TEXT NOT NULL,
    date_from         DATE NOT NULL,
    date_to           DATE NOT NULL,
    investor_type     TEXT NOT NULL,
    market_board      TEXT NOT NULL,
    side              TEXT NOT NULL,                  -- BUY | SELL (whose book `broker` is on)
    broker            TEXT NOT NULL,
    counterparty      TEXT NOT NULL,
    broker_type       TEXT,                           -- Asing | Lokal | Pemerintah, as the API labels it
    counterparty_type TEXT,
    value             NUMERIC(28,2),                  -- IDR traded between the two inside the window
    volume            NUMERIC(28,2),                  -- lots, when the VOLUME view has been captured
    period            TEXT NOT NULL,
    raw_id            BIGINT REFERENCES idx.broker_summary_raw (id) ON DELETE SET NULL,
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, date_from, date_to, investor_type, market_board, period, side, broker, counterparty)
);
CREATE INDEX IF NOT EXISTS broker_flow_code_to_idx ON idx.broker_flow (code, date_to DESC);
CREATE INDEX IF NOT EXISTS broker_flow_broker_idx  ON idx.broker_flow (broker, date_to DESC);
CREATE INDEX IF NOT EXISTS broker_flow_cp_idx      ON idx.broker_flow (counterparty, date_to DESC);
