-- Broker summary, second cut after the first real payload (2026-09-17): the rows carry the broker's investor class and trade
-- count, and the API's own "bandar detector" block (top-1/3/5/10 buyer concentration over the window, accumulation labels)
-- gets its own table - it is the accumulation feature menu 4 will test.

ALTER TABLE idx.broker_summary ADD COLUMN investor TEXT;          -- Asing | Lokal | Pemerintah (as the API labels the broker)
ALTER TABLE idx.broker_summary ADD COLUMN freq INTEGER;           -- number of trades by that broker in the window

CREATE TABLE idx.broker_detector (
    code              TEXT NOT NULL,
    date_from         DATE NOT NULL,
    date_to           DATE NOT NULL,
    investor_type     TEXT NOT NULL,
    market_board      TEXT NOT NULL,
    transaction_type  TEXT NOT NULL,
    value             NUMERIC(24,2),                 -- traded value in the window
    volume            NUMERIC(20,2),                 -- lots
    average           NUMERIC(18,4),                 -- average price
    total_buyer       INTEGER,                       -- net-buying brokers
    total_seller      INTEGER,
    number_broker_buysell INTEGER,                   -- buyers - sellers
    broker_accdist    TEXT,                          -- Acc | Dist | Neutral (API label)
    top1_pct          NUMERIC(8,4),                  -- top-1 net buyer's share of traded value, %
    top3_pct          NUMERIC(8,4),
    top5_pct          NUMERIC(8,4),
    top10_pct         NUMERIC(8,4),
    avg_pct           NUMERIC(8,4),
    avg5_pct          NUMERIC(8,4),
    top1_label        TEXT,
    top3_label        TEXT,
    top5_label        TEXT,
    top10_label       TEXT,
    raw_id            BIGINT REFERENCES idx.broker_summary_raw (id) ON DELETE CASCADE,
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, date_from, date_to, investor_type, market_board, transaction_type)
);
CREATE INDEX broker_detector_code_to_idx ON idx.broker_detector (code, date_to DESC);
