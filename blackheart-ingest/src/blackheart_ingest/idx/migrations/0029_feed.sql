-- Stockbit datafeed collector (2026-09-21): real-time prints and order books streamed from the operator's OWN Stockbit
-- session (wss://wss-jkt.trading.stockbit.com/ws). Personal research data: never published through /pub, never shown in
-- Blackridge. History starts the day the collector first ran - nothing here can be backfilled.
--
-- Design: the two raw streams are TimescaleDB hypertables (1-day chunks, columnar compression after 3 days, segmented by
-- code) - prints as they arrive, order books as 1-second samples of the top 10 levels. Everything derived (1-minute bars,
-- 1-minute books) is a continuous aggregate refreshed every minute, so the collector only ever appends and the derived
-- tables can be rebuilt from the raw ones. Reconnects re-deliver frames: the primary keys make the re-insert a no-op.

-- The session token the operator's browser relays after each login (24 h JWT). One row, replaced on every relay.
CREATE TABLE idx.feed_token (
    id            SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    access_token  TEXT NOT NULL,
    refresh_token TEXT,
    user_id       TEXT,                          -- Stockbit user id the datafeed auth message needs
    expires_at    TIMESTAMPTZ,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    source        TEXT NOT NULL DEFAULT 'relay', -- relay (browser extension) | paste (CLI) | env
    raw_keys      JSONB NOT NULL DEFAULT '{}'::jsonb   -- shape of what the relay sent (keys only, never values)
);

-- What to subscribe to. Re-read on every (re)connect, so the list changes without a restart.
CREATE TABLE idx.feed_symbol (
    code       TEXT PRIMARY KEY,
    channels   TEXT[] NOT NULL DEFAULT '{order_book,liveprice}',
    reason     TEXT,                              -- liquid | book | watch | manual
    enabled    BOOLEAN NOT NULL DEFAULT true,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every print the liveprice channel delivers. The cumulative columns are the day's running totals the exchange sends with
-- each match, so a jump in cum_freq of more than 1 between consecutive rows shows the feed skipped matches (throttling) -
-- and Σqty per day against idx.daily_summary.volume is the collector's coverage check.
CREATE TABLE idx.feed_trade (
    ts          TIMESTAMPTZ NOT NULL,             -- exchange time of the match; receipt time when the feed carries none
    code        TEXT NOT NULL,
    seq         BIGINT NOT NULL DEFAULT 0,        -- sequence_number from the feed (0 when absent)
    price       INTEGER NOT NULL,                 -- rupiah (IDX prices are whole rupiah)
    qty         BIGINT NOT NULL,                  -- shares in this match
    verb        CHAR(1),                          -- aggressor side as the feed labels it (B/S), NULL when absent
    board       TEXT,
    cum_volume  BIGINT,
    cum_value   NUMERIC(20,0),
    cum_freq    INTEGER,
    recv_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, ts, seq)
);
SELECT create_hypertable('idx.feed_trade', 'ts', chunk_time_interval => INTERVAL '1 day');
ALTER TABLE idx.feed_trade SET (timescaledb.compress, timescaledb.compress_segmentby = 'code', timescaledb.compress_orderby = 'ts, seq');
SELECT add_compression_policy('idx.feed_trade', INTERVAL '3 days');

-- The order book, sampled at most once per second per name and only when it changed: top 10 levels each side as parallel
-- arrays (best first), plus totals over the whole depth received. price in rupiah, vol in shares, n = number of orders.
CREATE TABLE idx.feed_book (
    ts          TIMESTAMPTZ NOT NULL,             -- feed datetime of the last update in this sample
    code        TEXT NOT NULL,
    seq         BIGINT NOT NULL DEFAULT 0,
    bid_px      INTEGER[] NOT NULL,
    bid_vol     BIGINT[]  NOT NULL,
    bid_n       INTEGER[] NOT NULL,
    off_px      INTEGER[] NOT NULL,
    off_vol     BIGINT[]  NOT NULL,
    off_n       INTEGER[] NOT NULL,
    bid_total   BIGINT NOT NULL,                  -- shares over the full depth
    off_total   BIGINT NOT NULL,
    bid_levels  SMALLINT NOT NULL,
    off_levels  SMALLINT NOT NULL,
    n_updates   INTEGER NOT NULL DEFAULT 1,       -- feed messages folded into this sample
    PRIMARY KEY (code, ts)
);
SELECT create_hypertable('idx.feed_book', 'ts', chunk_time_interval => INTERVAL '1 day');
ALTER TABLE idx.feed_book SET (timescaledb.compress, timescaledb.compress_segmentby = 'code', timescaledb.compress_orderby = 'ts');
SELECT add_compression_policy('idx.feed_book', INTERVAL '3 days');

-- One-minute bars from the prints. Real-time: the current minute is computed on read, older minutes are materialised.
CREATE MATERIALIZED VIEW idx.feed_bar_1m WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', ts) AS minute,
       code,
       first(price, ts)                      AS open,
       max(price)                            AS high,
       min(price)                            AS low,
       last(price, ts)                       AS close,
       sum(qty)                              AS volume,
       sum(price::numeric * qty)             AS value,
       count(*)                              AS n_trades,
       sum(qty) FILTER (WHERE verb = 'B')    AS buy_volume,
       sum(qty) FILTER (WHERE verb = 'S')    AS sell_volume
  FROM idx.feed_trade
 GROUP BY 1, 2
WITH NO DATA;
SELECT add_continuous_aggregate_policy('idx.feed_bar_1m', start_offset => INTERVAL '2 days', end_offset => INTERVAL '1 minute',
                                       schedule_interval => INTERVAL '1 minute');

-- The book at the end of each minute (last sample) with the minute's activity.
CREATE MATERIALIZED VIEW idx.feed_book_1m WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', ts) AS minute,
       code,
       last(bid_px, ts)   AS bid_px,
       last(bid_vol, ts)  AS bid_vol,
       last(off_px, ts)   AS off_px,
       last(off_vol, ts)  AS off_vol,
       last(bid_total, ts) AS bid_total,
       last(off_total, ts) AS off_total,
       avg(bid_total)::bigint AS bid_total_avg,
       avg(off_total)::bigint AS off_total_avg,
       sum(n_updates)     AS n_updates
  FROM idx.feed_book
 GROUP BY 1, 2
WITH NO DATA;
SELECT add_continuous_aggregate_policy('idx.feed_book_1m', start_offset => INTERVAL '2 days', end_offset => INTERVAL '1 minute',
                                       schedule_interval => INTERVAL '1 minute');

-- Collector heartbeat (one row): what state it is in and when the last frame arrived. GET /idx/feed/status reads it; the
-- scheduler alerts when it goes stale during a session.
CREATE TABLE idx.feed_status (
    id            SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    state         TEXT NOT NULL,                 -- off | waiting | connecting | live | reconnecting | token_expired | error
    detail        TEXT,
    connected_at  TIMESTAMPTZ,
    last_frame_at TIMESTAMPTZ,
    n_frames      BIGINT NOT NULL DEFAULT 0,
    n_trades      BIGINT NOT NULL DEFAULT 0,
    n_books       BIGINT NOT NULL DEFAULT 0,
    n_symbols     INTEGER NOT NULL DEFAULT 0,
    reconnects    INTEGER NOT NULL DEFAULT 0,
    pid           INTEGER,
    started_at    TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Connection log: every connect, auth, subscribe, disconnect and error with its reason - the audit trail for "why is
-- 10:32-10:41 missing".
CREATE TABLE idx.feed_event (
    id        BIGSERIAL PRIMARY KEY,
    at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind      TEXT NOT NULL,                     -- connect | auth | subscribe | frame_gap | close | error | token
    detail    TEXT,
    data      JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX feed_event_at_idx ON idx.feed_event (at DESC);

-- Daily coverage audit per name, filled by the nightly chain the next day: what the collector saw against what IDX
-- reports for the day. coverage = Σqty / official volume; a name below 0.95 on a session it was subscribed to is a gap.
CREATE TABLE idx.feed_day (
    trade_date   DATE NOT NULL,
    code         TEXT NOT NULL,
    n_trades     INTEGER NOT NULL,
    volume       BIGINT NOT NULL,                -- Σqty seen
    official_vol BIGINT,                         -- idx.daily_summary.volume
    official_frq INTEGER,                        -- idx.daily_summary.frequency
    coverage     NUMERIC(6,4),
    first_at     TIMESTAMPTZ,
    last_at      TIMESTAMPTZ,
    n_books      INTEGER NOT NULL DEFAULT 0,
    max_gap_s    INTEGER,                        -- longest silence between prints during the session
    PRIMARY KEY (trade_date, code)
);
