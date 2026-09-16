-- Research results as rows, not files (2026-09-17): a study run (what was tested, the summary numbers), the names it
-- surfaced on its as-of date with their figures, and the evidence gathered per name (news, disclosures, annual-report
-- plans, web references) so a name's whole picture is one query: `idx study name CODE` / GET /idx/name/{code}.

CREATE TABLE idx.study (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,                     -- e.g. 'doublers'
    as_of         DATE NOT NULL,                     -- the snapshot the name list was built on
    run_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,   -- design: snapshots, targets, screens, trial count
    summary       JSONB NOT NULL DEFAULT '{}'::jsonb,   -- base rates, feature and screen tables
    report_path   TEXT,                              -- the markdown paper
    note          TEXT
);
CREATE INDEX study_name_run_idx ON idx.study (name, run_at DESC);

CREATE TABLE idx.study_name (
    study_id      BIGINT NOT NULL REFERENCES idx.study (id) ON DELETE CASCADE,
    code          TEXT NOT NULL,
    screens       TEXT[] NOT NULL DEFAULT '{}',      -- pre-registered screens the name satisfies on as_of
    score         NUMERIC(8,4),                      -- the study's ranking score, if any
    rank          INTEGER,
    features      JSONB NOT NULL DEFAULT '{}'::jsonb,   -- the numbers on as_of (E/P ttm, growth, size, ...)
    context       JSONB NOT NULL DEFAULT '{}'::jsonb,   -- historical hit rate / lift of the screens the name is in
    PRIMARY KEY (study_id, code)
);
CREATE INDEX study_name_code_idx ON idx.study_name (code);

CREATE TABLE idx.evidence (
    id            BIGSERIAL PRIMARY KEY,
    code          TEXT NOT NULL,
    kind          TEXT NOT NULL,                     -- news | announcement | annual | web | analyst | note
    ts            TIMESTAMPTZ,                       -- when it was published
    source        TEXT,
    title         TEXT NOT NULL,
    url           TEXT,
    summary       TEXT,
    tags          TEXT[] NOT NULL DEFAULT '{}',      -- operational | guidance | corporate_action | risk | ...
    study_id      BIGINT REFERENCES idx.study (id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    dedup         TEXT GENERATED ALWAYS AS (md5(code || '|' || kind || '|' || coalesce(url, '') || '|' || title)) STORED
);
CREATE UNIQUE INDEX evidence_dedup_idx ON idx.evidence (dedup);
CREATE INDEX evidence_code_ts_idx ON idx.evidence (code, ts DESC);
