-- Phase 1b: point-in-time daily overlay features per code (wide silver table).
-- Every value is computable from data published at or before the code's close on trade_date:
-- flow from idx.daily_summary (same-day row), events from idx.event with published_at <= that close.
CREATE TABLE idx.feature_daily (
    trade_date                 DATE NOT NULL,
    code                       TEXT NOT NULL,
    foreign_net_share_5d       NUMERIC(8,5),     -- (sum fb - sum fs) / sum volume, trailing 5 bars incl. today
    foreign_net_share_20d      NUMERIC(8,5),
    foreign_net_shares_20d     NUMERIC(24,0),    -- raw net foreign shares, trailing 20 bars
    value_60d_median           NUMERIC(28,0),    -- IDR, trailing 60 bars incl. today
    mcap                       NUMERIC(28,0),    -- listed_shares * close (IDR)
    mcap_quintile              SMALLINT,         -- 1 (smallest) .. 5 among names with a bar that day
    ev_ownership_30d           SMALLINT NOT NULL DEFAULT 0,
    ev_exchange_query_10d      SMALLINT NOT NULL DEFAULT 0,
    ev_dividend_30d            SMALLINT NOT NULL DEFAULT 0,
    ev_buyback_30d             SMALLINT NOT NULL DEFAULT 0,
    ev_material_30d            SMALLINT NOT NULL DEFAULT 0,
    ev_rights_60d              SMALLINT NOT NULL DEFAULT 0,
    computed_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX feature_daily_code_date ON idx.feature_daily (code, trade_date);
