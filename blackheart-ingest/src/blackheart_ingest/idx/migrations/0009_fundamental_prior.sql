-- Prior-period comparatives as reported (the YoY ratio cannot be inverted for turnarounds), data-quality flags from the
-- EPS x shares scale check (eps_rescaled | report_rescaled | eps_mismatch | scale_mismatch), and average-rank candidate
-- scores (ties share the mean position, so scores are halves).
ALTER TABLE idx.fundamental
    ADD COLUMN net_profit_prior NUMERIC(28,0),
    ADD COLUMN revenue_prior    NUMERIC(28,0),
    ADD COLUMN cfo_prior        NUMERIC(28,0),
    ADD COLUMN flags            TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE idx.candidate ALTER COLUMN score TYPE NUMERIC(10,1);
