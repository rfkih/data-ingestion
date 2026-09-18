-- Open-research plan phase 2 (2026-09-18): the nightly factor scores, the historical statistics behind each criteria, and the
-- example screener templates. Everything here is public read: no book, no ticket, no user data.

-- Four factor scores per liquid name per trade date (0-100 = percentile within that day's liquid universe), the flags the
-- templates filter on, and the raw numbers behind each score so a stock page can show the formula's ingredients.
CREATE TABLE idx.score_daily (
    trade_date   DATE NOT NULL,
    code         TEXT NOT NULL,
    value        NUMERIC(5,1),                -- cheapness: avg rank of E/P, B/P, DY among profitable tradable names
    quality      NUMERIC(5,1),                -- gates passed (0-8) -> percentile
    trend        NUMERIC(5,1),                -- close/60d high, close/MA200, volume/median20 -> avg percentile
    turnaround   BOOLEAN NOT NULL DEFAULT false,
    trend_flag   BOOLEAN NOT NULL DEFAULT false,   -- meets the breakout rule (60d high, > MA200, vol >= 1.5x) today
    gates        SMALLINT,                     -- quality gates passed, 0-8 (NULL: < 5 audited years)
    bucket       TEXT,                         -- turnaround bucket: mcap band x momentum band
    inputs       JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX score_daily_code_idx ON idx.score_daily (code, trade_date DESC);

-- What happened, historically, to the group of names that met a criteria: one row per (criteria, bucket, horizon).
-- Filled from recorded research (idx.study / research files) by idx/signal_stats.py; every row names its source.
CREATE TABLE idx.signal_stats (
    id            BIGSERIAL PRIMARY KEY,
    criteria      TEXT NOT NULL,               -- trend_breakout | turnaround | value_strict | quality8
    bucket        TEXT NOT NULL DEFAULT 'all', -- all | small | LIQ | mcap:3-20T,mom:<=150 | ...
    horizon_days  INTEGER NOT NULL DEFAULT 0,  -- 0 = held until the rule's own exit; else a fixed horizon
    sample_from   DATE,
    sample_to     DATE,
    n             INTEGER NOT NULL,
    hit           NUMERIC(6,4),                -- share with a positive outcome (or the target touched)
    median        NUMERIC(8,4),
    mean          NUMERIC(8,4),
    p_loss50      NUMERIC(6,4),                -- share losing more than half
    mdd_book      NUMERIC(6,4),                -- worst drawdown of a K-slot book running the rule (negative)
    extra         JSONB NOT NULL DEFAULT '{}'::jsonb,   -- avg hold, payoff, cagr, sharpe, avg_net ... whatever the study had
    by_year       JSONB NOT NULL DEFAULT '{}'::jsonb,
    study_id      BIGINT REFERENCES idx.study (id),
    source        TEXT,                        -- report path when the study predates the research store
    refreshed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (criteria, bucket, horizon_days)
);

-- Example screener templates: criteria the public app shows in words and lets the user edit. Editable here without a deploy.
CREATE TABLE idx.template (
    key             TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    description     TEXT NOT NULL,
    criteria        JSONB NOT NULL,            -- [{"field": "trend_flag", "op": "eq", "value": true}, ...]
    stats_criteria  TEXT,                      -- signal_stats.criteria shown in the results header
    stats_bucket    TEXT NOT NULL DEFAULT 'all',
    sort            TEXT NOT NULL DEFAULT 'value',
    position        SMALLINT NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO idx.template (key, label, description, criteria, stats_criteria, stats_bucket, sort, position) VALUES
('value_strict', 'Value strict (contoh)',
 'Nama likuid dengan laba audit positif, ROE >= 10 %, laba tahun sebelumnya positif, arus kas operasi positif dan utang/ekuitas <= 1,5 — diurutkan dari yang termurah (E/P, B/P, dividend yield).',
 '[{"field": "gate_strict", "op": "eq", "value": true}, {"field": "value", "op": "gte", "value": 80}]', 'value_strict', 'all', 'value', 1),
('trend_breakout', 'Trend breakout (contoh)',
 'Close hari ini = tertinggi 60 hari, di atas rata-rata 200 hari, volume >= 1,5x median 20 hari.',
 '[{"field": "trend_flag", "op": "eq", "value": true}]', 'trend_breakout', 'small', 'trend', 2),
('quality8', '8 kriteria kualitas (contoh)',
 'Lima tahun laba, ROE >= 12 % tiap tahun dan >= 15 % rata-rata, EPS naik, utang kecil, kas nyata, tanpa dilusi + dividen tunai, laba TTM utuh, P/E <= 15 dan owner-earnings yield >= 6 %.',
 '[{"field": "gates", "op": "gte", "value": 7}]', 'quality8', 'all', 'quality', 3),
('turnaround', 'Turnaround (contoh)',
 'Laba tahun lalu negatif, laba TTM positif, pendapatan YTD tumbuh, likuid, dan belum lari lebih dari +150 % dalam 12 bulan.',
 '[{"field": "turnaround", "op": "eq", "value": true}, {"field": "mom_12_1", "op": "lte", "value": 1.5}]', 'turnaround', 'all', 'trend', 4);

-- A read-only role for the public API (created only if absent; grants are idempotent). The served app keeps using its
-- own role; INGEST_PUB_DSN may point at this one once the public app is deployed.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'idx_public') THEN
        CREATE ROLE idx_public NOLOGIN;
    END IF;
END $$;
GRANT USAGE ON SCHEMA idx TO idx_public;
GRANT SELECT ON idx.score_daily, idx.signal_stats, idx.template, idx.listing, idx.bar, idx.feature_daily, idx.study, idx.evidence,
                idx.announcement, idx.news_article TO idx_public;
