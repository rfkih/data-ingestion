-- Candidate list per run date (the systematic half of the value/quality book; app + pack read it).
CREATE TABLE idx.candidate (
    run_date       DATE NOT NULL,
    code           TEXT NOT NULL,
    rank           INTEGER NOT NULL,
    selected       BOOLEAN NOT NULL,
    score          INTEGER,
    price          NUMERIC(18,4),
    mcap           NUMERIC(28,0),
    ep             NUMERIC(12,6),
    bp             NUMERIC(12,6),
    dy             NUMERIC(12,6),
    ep_ttm         NUMERIC(12,6),
    roe            NUMERIC(10,6),
    der            NUMERIC(10,6),
    np_yoy         NUMERIC(12,6),
    gate_loose     BOOLEAN NOT NULL,
    gate_strict    BOOLEAN NOT NULL,
    strict_fails   TEXT[] NOT NULL DEFAULT '{}',
    warnings       TEXT[] NOT NULL DEFAULT '{}',
    f20            NUMERIC(8,5),
    v60            NUMERIC(28,0),
    annual_period  DATE,
    ttm_basis      TEXT,
    sector         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_date, code)
);
CREATE INDEX candidate_selected ON idx.candidate (run_date) WHERE selected;
