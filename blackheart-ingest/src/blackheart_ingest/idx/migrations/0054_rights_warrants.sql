-- Rights (HMETD) and warrants - the data for the Phase 2 arbitrage study (operator 2026-09-26: "Tetap IDX saja"; feasibility
-- research/IDX_RIGHTS_WARRANTS_FEASIBILITY_2026-09-26.md). Written by idx/jobs/deriv.py. Kept OUT of idx.bar: the exchange code
-- (XXXX-R, XXXX-W) is reused by later issues, so a price row belongs to a SERIES, not to a code.

-- The IDX monthly trading summary per right / warrant (DigitalStatistic LINK_TRADING_SUMMARY_RIGHT / _WARRANT): the universe.
-- series = the right's code with its expiry (IDX's own 'COCO-R20260721'); for a warrant the code plus its first listed month
-- ('COCO-W@2025-10'), assigned by the job from consecutive months.
CREATE TABLE IF NOT EXISTS idx.deriv_month (
    kind        TEXT NOT NULL CHECK (kind IN ('right', 'warrant')),
    idx_code    TEXT NOT NULL,                  -- as IDX prints it: 'COCO-R20260721' / 'COCO-W'
    month       DATE NOT NULL,                  -- first day of the month
    board       TEXT NOT NULL DEFAULT '',       -- rights: RG / TN / NG; warrants: ''
    name        TEXT,
    high        NUMERIC(14, 2),
    low         NUMERIC(14, 2),
    close       NUMERIC(14, 2),
    volume      NUMERIC(20, 0),
    value       NUMERIC(22, 2),
    freq        NUMERIC(14, 0),
    days        INTEGER,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (idx_code, month, board)
);

-- The terms of each rights issue (DigitalStatistic LINK_RIGHT_OFFERING, yearly/cumulative): ratio old:new, exercise price, dates.
CREATE TABLE IF NOT EXISTS idx.right_offering (
    code          TEXT NOT NULL,                -- the underlying stock
    ex_date       DATE NOT NULL,
    rec_date      DATE,
    issuer        TEXT,
    ratio_raw     TEXT,
    ratio_old     NUMERIC(20, 6),               -- '100 : 111' -> old 100, new 111 (new shares per `old` held)
    ratio_new     NUMERIC(20, 6),
    ex_price      NUMERIC(14, 2),
    shares_issued NUMERIC(24, 6),               -- as IDX reports it (millions)
    fund_raised   NUMERIC(24, 2),
    trading_note  TEXT,                         -- rightCert: the trading days of the right as free text
    raw           JSONB NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, ex_date)
);

-- Daily bars per series from Stockbit's historical summary (volume > 0 rows only; the API pads expired codes with zero rows).
CREATE TABLE IF NOT EXISTS idx.deriv_bar (
    series      TEXT NOT NULL,
    code        TEXT NOT NULL,                  -- the exchange code the bar was fetched under: 'COCO-R', 'COCO-W'
    trade_date  DATE NOT NULL,
    open        NUMERIC(14, 2),
    high        NUMERIC(14, 2),
    low         NUMERIC(14, 2),
    close       NUMERIC(14, 2),
    volume      NUMERIC(20, 0),                 -- lots, as Stockbit reports it
    value       NUMERIC(22, 2),
    frequency   NUMERIC(14, 0),
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (series, trade_date)
);
CREATE INDEX IF NOT EXISTS deriv_bar_code_idx ON idx.deriv_bar (code, trade_date);
