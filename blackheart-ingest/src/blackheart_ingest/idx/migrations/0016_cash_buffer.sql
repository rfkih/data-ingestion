-- Book option (research/IDX_CASH_BUFFER_2026-09-14.md): a standing cash buffer (cash_floor_pct of NAV kept in cash) and a
-- higher buffer (stress_cash_pct) while the market-stress detector is on. stress_rule: 'ma' = the COMPOSITE under its 200-day
-- average; 'any2' = at least two of {under MA200, volatility spike, >10 % under the 52-week high, breadth under 40 %}.
-- Both percentages 0 = off. The monthly check records the signals and, when the cash target moves by more than 5 points,
-- issues a rebalance ticket at the new target.
ALTER TABLE idx.book ADD COLUMN cash_floor_pct  NUMERIC(5,2) NOT NULL DEFAULT 0;
ALTER TABLE idx.book ADD COLUMN stress_cash_pct NUMERIC(5,2) NOT NULL DEFAULT 0;
ALTER TABLE idx.book ADD COLUMN stress_rule     TEXT NOT NULL DEFAULT 'ma';

CREATE TABLE idx.stress_check (
    check_date   DATE PRIMARY KEY,
    index_code   TEXT NOT NULL,
    close        NUMERIC(18,4) NOT NULL,
    sma          NUMERIC(18,4),
    vol20        NUMERIC(10,4),                    -- annualised 20-day realised volatility of the index
    vol_p80      NUMERIC(10,4),                    -- its trailing three-year 80th percentile
    dd_pct       NUMERIC(8,4),                     -- index against its 252-day high (negative = below)
    breadth_pct  NUMERIC(8,4),                     -- share of names with 200 bars closing above their own average
    s_ma         BOOLEAN NOT NULL,
    s_vol        BOOLEAN NOT NULL,
    s_dd         BOOLEAN NOT NULL,
    s_breadth    BOOLEAN NOT NULL,
    n_on         INTEGER NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
