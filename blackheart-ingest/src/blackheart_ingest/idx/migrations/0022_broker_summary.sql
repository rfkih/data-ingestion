-- Broker summary ("bandarmologi") per name per window, fetched from the operator's Stockbit data account (research feed,
-- 2026-09-17; docs: idx/broker.py). Raw payloads are kept whole so the parser can be re-run when the shape is learned or
-- changes; the parsed rows are one line per broker per (name, window, view).

CREATE TABLE idx.broker_summary_raw (
    id               BIGSERIAL PRIMARY KEY,
    code             TEXT NOT NULL,
    date_from        DATE NOT NULL,
    date_to          DATE NOT NULL,
    investor_type    TEXT NOT NULL,               -- as sent to the API (e.g. INVESTOR_TYPE_ALL)
    market_board     TEXT NOT NULL,               -- e.g. MARKET_BOARD_REGULAR
    transaction_type TEXT NOT NULL,               -- e.g. TRANSACTION_TYPE_NET
    http_status      INTEGER,
    payload          JSONB,
    error            TEXT,
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (code, date_from, date_to, investor_type, market_board, transaction_type)
);

CREATE TABLE idx.broker_summary (
    code             TEXT NOT NULL,
    date_from        DATE NOT NULL,
    date_to          DATE NOT NULL,
    investor_type    TEXT NOT NULL,
    market_board     TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    broker           TEXT NOT NULL,               -- broker code (YU, ZP, CC, ...)
    broker_name      TEXT,
    buy_value        NUMERIC(24,2),               -- IDR
    buy_lot          NUMERIC(18,2),
    buy_avg          NUMERIC(18,4),
    sell_value       NUMERIC(24,2),
    sell_lot         NUMERIC(18,2),
    sell_avg         NUMERIC(18,4),
    net_value        NUMERIC(24,2),               -- buy - sell
    net_lot          NUMERIC(18,2),
    raw_id           BIGINT REFERENCES idx.broker_summary_raw (id) ON DELETE CASCADE,
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, date_from, date_to, investor_type, market_board, transaction_type, broker)
);
CREATE INDEX broker_summary_code_to_idx ON idx.broker_summary (code, date_to DESC);
CREATE INDEX broker_summary_broker_idx ON idx.broker_summary (broker, date_to DESC);
