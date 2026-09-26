-- Mutual-fund NAV per unit, a benchmark for the Strategies page's equity chart (operator 2026-09-26: compare with IHSG and
-- equity mutual funds). The desk has no fund feed: histories are imported (idx cli fund-import / benchmarks.import_fund_csv).
CREATE TABLE IF NOT EXISTS idx.fund_nav (
    fund_code   TEXT NOT NULL,
    name        TEXT NOT NULL,
    nav_date    DATE NOT NULL,
    nav         NUMERIC(18, 4) NOT NULL CHECK (nav > 0),
    source      TEXT NOT NULL DEFAULT 'csv',
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (fund_code, nav_date)
);
