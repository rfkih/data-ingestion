-- Macro series the desk watches (blackheart_ingest.idx.macro): BI-Rate, USD/IDR, GDP, CPI, US rates, VIX, Brent, gold, CPO.
-- One row per (series, observation date); sources are free (FRED, Bank Indonesia's page, Yahoo, World Bank) and the
-- scheduler refreshes them daily. The series catalog (labels, sources, units) lives in code.
CREATE TABLE idx.macro (
    series     TEXT NOT NULL,
    obs_date   DATE NOT NULL,
    value      NUMERIC(20,6) NOT NULL,
    source     TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (series, obs_date)
);
CREATE INDEX macro_series_date_idx ON idx.macro (series, obs_date DESC);
