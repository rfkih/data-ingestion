-- Phase 2: fields the workbook parser produces beyond the 0001 fundamental columns.
ALTER TABLE idx.fundamental
    ADD COLUMN period_start   DATE,
    ADD COLUMN months         SMALLINT,              -- length of the P&L period (3, 6, 9, 12)
    ADD COLUMN period_label   TEXT,                  -- TW1 | TW2 | TW3 | TAHUNAN
    ADD COLUMN pretax_profit  NUMERIC(28,0),
    ADD COLUMN cfo            NUMERIC(28,0),
    ADD COLUMN capex          NUMERIC(28,0),
    ADD COLUMN dividends_paid NUMERIC(28,0),
    ADD COLUMN current_assets NUMERIC(28,0),
    ADD COLUMN current_liabilities NUMERIC(28,0),
    ADD COLUMN sector         TEXT,
    ADD COLUMN subsector      TEXT,
    ADD COLUMN rounding       INTEGER,
    ADD COLUMN facts_n        INTEGER;

CREATE INDEX fundamental_code_pub ON idx.fundamental (code, published_at);

-- financial_fact carries the statement code in context_ref ("<ctx>|<sheet>|r<row>"); no schema change.
