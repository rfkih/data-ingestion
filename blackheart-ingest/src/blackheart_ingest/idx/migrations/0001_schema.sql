-- IDX data plane — silver layer (schema "idx"), owned by the ingest worker.
-- Spec: docs/superpowers/specs/2026-09-12-idx-data-platform-design.md (§4, §12).
-- Applied by blackheart_ingest.idx.migrate (own history table, sha256-checked).
-- Not part of the trading JVM's Flyway; the JVM and blackheart-equity only read.

CREATE SCHEMA IF NOT EXISTS idx;

-- ---------------------------------------------------------------------------
-- bronze: immutable archive index (files live under INGEST_IDX_BRONZE_DIR)
-- ---------------------------------------------------------------------------
CREATE TABLE idx.bronze_index (
    id           BIGSERIAL PRIMARY KEY,
    endpoint     TEXT        NOT NULL,          -- e.g. stock_summary, securities_stock, trading_info
    key          TEXT        NOT NULL,          -- natural key: date, code, code:year:period ...
    fetched_at   TIMESTAMPTZ NOT NULL,
    path         TEXT        NOT NULL,          -- relative to the bronze dir
    sha256       TEXT        NOT NULL,
    bytes        INTEGER     NOT NULL,
    http_status  INTEGER,
    fingerprint  TEXT,                          -- sorted top-level field names of the payload rows
    UNIQUE (endpoint, key, fetched_at)
);
CREATE INDEX bronze_index_latest ON idx.bronze_index (endpoint, key, fetched_at DESC);

-- ---------------------------------------------------------------------------
-- universe
-- ---------------------------------------------------------------------------
CREATE TABLE idx.listing (
    code           TEXT PRIMARY KEY,
    name           TEXT,
    listing_date   DATE,
    board          TEXT,                        -- Utama | Pengembangan | Akselerasi | Pemantauan Khusus | Ekonomi Baru
    listed_shares  NUMERIC(24,0),
    sector         TEXT,
    subsector      TEXT,
    status         TEXT NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE | DELISTED
    first_seen     DATE,
    last_seen      DATE,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE idx.listing_snapshot (
    snapshot_date  DATE NOT NULL,
    code           TEXT NOT NULL,
    name           TEXT,
    listing_date   DATE,
    board          TEXT,
    listed_shares  NUMERIC(24,0),
    PRIMARY KEY (snapshot_date, code)
);

-- ---------------------------------------------------------------------------
-- prices, flow, corporate actions
-- ---------------------------------------------------------------------------
-- Every field of IDX's Ringkasan Saham row, as published (raw prices, IDR).
CREATE TABLE idx.daily_summary (
    trade_date         DATE NOT NULL,
    code               TEXT NOT NULL,
    name               TEXT,
    remarks            TEXT,
    previous           NUMERIC(18,2),
    open               NUMERIC(18,2),           -- NULL when IDX recorded 0 (no pre-opening session, 2020-03-13..09-04)
    first_trade        NUMERIC(18,2),
    high               NUMERIC(18,2),
    low                NUMERIC(18,2),
    close              NUMERIC(18,2),
    change             NUMERIC(18,2),
    volume             NUMERIC(24,0),
    value              NUMERIC(28,0),
    frequency          INTEGER,
    index_individual   NUMERIC(18,4),
    bid                NUMERIC(18,2),
    bid_volume         NUMERIC(24,0),
    offer              NUMERIC(18,2),
    offer_volume       NUMERIC(24,0),
    listed_shares      NUMERIC(24,0),
    tradeable_shares   NUMERIC(24,0),
    weight_for_index   NUMERIC(28,0),
    foreign_buy        NUMERIC(24,0),
    foreign_sell       NUMERIC(24,0),
    delisting_date     DATE,
    nonreg_volume      NUMERIC(24,0),
    nonreg_value       NUMERIC(28,0),
    nonreg_frequency   INTEGER,
    source_id          BIGINT,                  -- IDStockSummary
    bronze_id          BIGINT REFERENCES idx.bronze_index (id),
    fetched_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX daily_summary_code_date ON idx.daily_summary (code, trade_date);

-- Clean bar. Prices are RAW as traded; adj_factor is the cumulative split/rights
-- factor so that adjusted = raw * adj_factor. A newly detected corporate action
-- only rewrites adj_factor on earlier rows; raw values never change.
CREATE TABLE idx.bar (
    code          TEXT NOT NULL,
    trade_date    DATE NOT NULL,
    source        TEXT NOT NULL,                -- idx | yahoo
    basis         TEXT NOT NULL DEFAULT 'split_only',
    open          NUMERIC(18,4),
    high          NUMERIC(18,4),
    low           NUMERIC(18,4),
    close         NUMERIC(18,4) NOT NULL,
    volume        NUMERIC(24,0),
    value         NUMERIC(28,0),
    adj_factor    NUMERIC(20,10) NOT NULL DEFAULT 1,
    open_missing  BOOLEAN NOT NULL DEFAULT FALSE,
    quality_flags TEXT[] NOT NULL DEFAULT '{}',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX bar_date ON idx.bar (trade_date);

CREATE TABLE idx.index_daily (
    trade_date   DATE NOT NULL,
    index_code   TEXT NOT NULL,                 -- COMPOSITE, LQ45, IDX30, sector codes
    previous     NUMERIC(18,4),
    open         NUMERIC(18,4),
    high         NUMERIC(18,4),
    low          NUMERIC(18,4),
    close        NUMERIC(18,4),
    volume       NUMERIC(24,0),
    value        NUMERIC(28,0),
    bronze_id    BIGINT REFERENCES idx.bronze_index (id),
    fetched_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (trade_date, index_code)
);

CREATE TABLE idx.corporate_action (
    code                  TEXT NOT NULL,
    ex_date               DATE NOT NULL,
    kind                  TEXT NOT NULL,        -- split | reverse_split | rights | bonus | previous_reset
    factor                NUMERIC(20,10) NOT NULL,   -- previous / prior close
    listed_shares_before  NUMERIC(24,0),
    listed_shares_after   NUMERIC(24,0),
    source                TEXT NOT NULL,        -- previous_reset | announcement
    announcement_id       TEXT,
    note                  TEXT,
    detected_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, ex_date, kind)
);

CREATE TABLE idx.dividend (
    code              TEXT NOT NULL,
    ex_date           DATE NOT NULL,
    kind              TEXT NOT NULL DEFAULT 'cash',   -- cash | interim | final | stock
    record_date       DATE,
    payment_date      DATE,
    amount_per_share  NUMERIC(18,4),
    currency          TEXT NOT NULL DEFAULT 'IDR',
    announcement_id   TEXT,
    PRIMARY KEY (code, ex_date, kind)
);

-- ---------------------------------------------------------------------------
-- disclosures, events, news
-- ---------------------------------------------------------------------------
CREATE TABLE idx.announcement (
    id2             TEXT PRIMARY KEY,           -- IDX Id2, e.g. 20260909085608-0011/CSG-IVR/2026_id-id
    code            TEXT,
    published_at    TIMESTAMPTZ NOT NULL,       -- TglPengumuman (WIB → UTC)
    title           TEXT,
    form_id         TEXT,
    perihal         TEXT,
    jenis           TEXT,
    kind            TEXT,                       -- mapped: dividend | rights | buyback | insider_tx | ownership_5pct | uma | suspension | public_expose | material_info | other
    attachments     JSONB,
    extracted_text  TEXT,
    text_hash       TEXT,
    needs_ocr       BOOLEAN NOT NULL DEFAULT FALSE,
    bronze_id       BIGINT REFERENCES idx.bronze_index (id),
    fetched_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX announcement_code_date ON idx.announcement (code, published_at);
CREATE INDEX announcement_kind_date ON idx.announcement (kind, published_at);

CREATE TABLE idx.event (
    id            BIGSERIAL PRIMARY KEY,
    code          TEXT NOT NULL,
    event_date    DATE NOT NULL,
    published_at  TIMESTAMPTZ NOT NULL,
    kind          TEXT NOT NULL,
    source        TEXT NOT NULL,                -- announcement | exchange_notice | previous_reset
    ref_id        TEXT NOT NULL,
    payload       JSONB,
    UNIQUE (source, ref_id, kind, code)
);
CREATE INDEX event_code_date ON idx.event (code, event_date);

CREATE TABLE idx.news_article (
    id            BIGSERIAL PRIMARY KEY,
    source        TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    published_at  TIMESTAMPTZ,
    fetched_at    TIMESTAMPTZ NOT NULL,
    title         TEXT,
    body          TEXT,
    lang          TEXT,
    text_hash     TEXT,
    codes         TEXT[] NOT NULL DEFAULT '{}'
);
CREATE INDEX news_article_published ON idx.news_article (published_at);

CREATE TABLE idx.company_alias (
    code   TEXT NOT NULL,
    alias  TEXT NOT NULL,
    kind   TEXT,                                -- legal | short | abbrev | brand
    PRIMARY KEY (code, alias)
);

-- ---------------------------------------------------------------------------
-- fundamentals (as reported; point-in-time = published_at)
-- ---------------------------------------------------------------------------
CREATE TABLE idx.financial_report (
    id            BIGSERIAL PRIMARY KEY,
    code          TEXT NOT NULL,
    fiscal_year   INTEGER NOT NULL,
    period        TEXT NOT NULL,                -- TW1 | TW2 | TW3 | TAHUNAN
    report_type   TEXT NOT NULL,                -- rdf (financial statement) | ...
    published_at  TIMESTAMPTZ NOT NULL,         -- File_Modified
    attachments   JSONB,
    bronze_id     BIGINT REFERENCES idx.bronze_index (id),
    parse_status  TEXT NOT NULL DEFAULT 'pending',   -- pending | parsed | failed | no_workbook
    parsed_at     TIMESTAMPTZ,
    checksum      TEXT,
    UNIQUE (code, fiscal_year, period, report_type)
);

CREATE TABLE idx.financial_fact (
    report_id     BIGINT NOT NULL REFERENCES idx.financial_report (id) ON DELETE CASCADE,
    concept       TEXT NOT NULL,
    context_ref   TEXT NOT NULL,
    period_start  DATE,
    period_end    DATE,
    value         NUMERIC(28,4),
    unit          TEXT,
    decimals      INTEGER,
    PRIMARY KEY (report_id, concept, context_ref)
);

CREATE TABLE idx.fundamental (
    code              TEXT NOT NULL,
    period_end        DATE NOT NULL,
    published_at      TIMESTAMPTZ NOT NULL,
    report_id         BIGINT REFERENCES idx.financial_report (id),
    revenue           NUMERIC(28,0),
    gross_profit      NUMERIC(28,0),
    operating_profit  NUMERIC(28,0),
    net_profit        NUMERIC(28,0),
    total_assets      NUMERIC(28,0),
    total_liabilities NUMERIC(28,0),
    total_equity      NUMERIC(28,0),
    cash              NUMERIC(28,0),
    total_debt        NUMERIC(28,0),
    shares_out        NUMERIC(24,0),
    eps               NUMERIC(18,4),
    bvps              NUMERIC(18,4),
    roe               NUMERIC(10,6),
    roa               NUMERIC(10,6),
    der               NUMERIC(10,6),
    net_margin        NUMERIC(10,6),
    revenue_yoy       NUMERIC(10,6),
    net_profit_yoy    NUMERIC(10,6),
    PRIMARY KEY (code, period_end, published_at)
);

CREATE TABLE idx.valuation_daily (
    trade_date                DATE NOT NULL,
    code                      TEXT NOT NULL,
    market_cap                NUMERIC(28,0),
    pe_ttm                    NUMERIC(12,4),
    pb                        NUMERIC(12,4),
    dividend_yield_ttm        NUMERIC(10,6),
    fundamental_published_at  TIMESTAMPTZ,
    PRIMARY KEY (trade_date, code)
);

-- ---------------------------------------------------------------------------
-- nightly analysis (manual Claude chat), scores, watchlist
-- ---------------------------------------------------------------------------
CREATE TABLE idx.sentiment_score (
    id              BIGSERIAL PRIMARY KEY,
    doc_type        TEXT NOT NULL,              -- announcement | news | pack
    doc_id          TEXT NOT NULL,
    code            TEXT NOT NULL,
    model           TEXT NOT NULL,              -- claude-chat-manual | ...
    prompt_version  TEXT NOT NULL,
    event_type      TEXT,
    stance          SMALLINT,                   -- -2..+2
    materiality     SMALLINT,                   -- 0..3
    horizon_days    INTEGER,
    confidence      NUMERIC(4,3),
    rationale       TEXT,
    veto            TEXT,                       -- NULL | skip | reduce
    scored_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (doc_type, doc_id, code, model, prompt_version)
);
CREATE INDEX sentiment_score_code_time ON idx.sentiment_score (code, scored_at);

CREATE TABLE idx.sentiment_daily (
    trade_date            DATE NOT NULL,
    code                  TEXT NOT NULL,
    n_docs                INTEGER NOT NULL DEFAULT 0,
    mean_stance           NUMERIC(6,3),
    weighted_stance       NUMERIC(6,3),
    decayed_score         NUMERIC(6,3),
    n_negative_material   INTEGER NOT NULL DEFAULT 0,
    last_insider_buy_days INTEGER,
    PRIMARY KEY (trade_date, code)
);

CREATE TABLE idx.nightly_pack (
    pack_date       DATE PRIMARY KEY,
    prompt_version  TEXT NOT NULL,
    pack_md         TEXT NOT NULL,
    pack_json       JSONB NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    answer_json     JSONB,
    imported_at     TIMESTAMPTZ
);

CREATE TABLE idx.watchlist (
    code      TEXT PRIMARY KEY,
    note      TEXT,
    added_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- operations
-- ---------------------------------------------------------------------------
CREATE TABLE idx.ingest_run (
    id                 BIGSERIAL PRIMARY KEY,
    job                TEXT NOT NULL,
    run_key            TEXT,                    -- e.g. the trade date or code the run covered
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ,
    status             TEXT NOT NULL DEFAULT 'running',   -- running | ok | partial | failed
    rows_in            INTEGER,
    rows_out           INTEGER,
    rows_rejected_pit  INTEGER NOT NULL DEFAULT 0,
    warnings           JSONB NOT NULL DEFAULT '[]',
    error              TEXT
);
CREATE INDEX ingest_run_job_time ON idx.ingest_run (job, started_at DESC);

CREATE TABLE idx.alert (
    id               BIGSERIAL PRIMARY KEY,
    ts               TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity         TEXT NOT NULL,             -- info | warning | critical
    job              TEXT,
    message          TEXT NOT NULL,
    acknowledged_at  TIMESTAMPTZ
);
CREATE INDEX alert_open ON idx.alert (ts DESC) WHERE acknowledged_at IS NULL;

-- ---------------------------------------------------------------------------
-- read access for the JVMs / equity service (they never write here)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'blackheart_research') THEN
        GRANT USAGE ON SCHEMA idx TO blackheart_research;
        GRANT SELECT ON ALL TABLES IN SCHEMA idx TO blackheart_research;
        ALTER DEFAULT PRIVILEGES IN SCHEMA idx GRANT SELECT ON TABLES TO blackheart_research;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'blackheart_equity') THEN
        GRANT USAGE ON SCHEMA idx TO blackheart_equity;
        GRANT SELECT ON ALL TABLES IN SCHEMA idx TO blackheart_equity;
        ALTER DEFAULT PRIVILEGES IN SCHEMA idx GRANT SELECT ON TABLES TO blackheart_equity;
    END IF;
END $$;
