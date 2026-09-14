-- Annual reports (blackheart_ingest.idx.annual): listings live in idx.financial_report with report_type 'ar'; the pages
-- that carry the company's plan (prospects, next-year projection, strategy, work plan / capex, risks, dividend policy)
-- are extracted here and rendered into the thesis card.
CREATE TABLE idx.annual_excerpt (
    id           BIGSERIAL PRIMARY KEY,
    report_id    BIGINT NOT NULL REFERENCES idx.financial_report (id) ON DELETE CASCADE,
    code         TEXT NOT NULL,
    fiscal_year  INTEGER NOT NULL,
    section      TEXT NOT NULL,                 -- proyeksi | prospek | strategi | rencana | risiko | dividen
    page         INTEGER NOT NULL,
    text         TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_id, section)
);
CREATE INDEX annual_excerpt_code_year_idx ON idx.annual_excerpt (code, fiscal_year DESC);
