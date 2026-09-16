-- Analyst consensus snapshots (blackheart_ingest.idx.consensus), recorded weekly from Yahoo Finance so the desk builds
-- the point-in-time history no free source provides: target level, spread, coverage, recommendation, and therefore
-- their revisions. Snapshots only; nothing here is a signal until it has been tested.
CREATE TABLE idx.consensus (
    code           TEXT NOT NULL,
    snapshot_date  DATE NOT NULL,
    price          NUMERIC(18,4),
    target_mean    NUMERIC(18,4),
    target_median  NUMERIC(18,4),
    target_low     NUMERIC(18,4),
    target_high    NUMERIC(18,4),
    n_analysts     INTEGER NOT NULL DEFAULT 0,
    reco_mean      NUMERIC(6,3),                 -- 1 strong buy .. 5 strong sell
    reco_key       TEXT,
    fwd_pe         NUMERIC(10,3),
    ttm_pe         NUMERIC(10,3),
    upside_pct     NUMERIC(10,3),
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, snapshot_date)
);
