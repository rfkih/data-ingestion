-- The desk registry (phase 0 of docs/superpowers/plans/2026-09-24-blackridge-strategies-and-alert-stream-plan.md).
--
-- ``idx/registry.py`` holds what a strategy IS - the rule, the falsifier, which books can follow it, which studies are
-- its evidence. What it EARNED is not typed there: it is imported from the research store (the ROI scorecard study,
-- ``idx.study`` name = 'roi_scorecard') into this table, so a page can never show a number no study computed. One row
-- per registry key; ``refreshed_at`` is what the page shows when it says how current the record is.

CREATE TABLE IF NOT EXISTS idx.strategy_state (
    key           TEXT PRIMARY KEY,              -- registry key (registry.REGISTRY[].key)
    status        TEXT NOT NULL,                 -- live | paper | overlay | research | reference | closed
    scorecard     JSONB,                         -- {cagr_pct, sharpe, mdd_pct, window, verdict, roi_rank, live, effect}
    evidence      INTEGER[] NOT NULL DEFAULT '{}', -- idx.study ids behind the numbers
    source_study  INTEGER REFERENCES idx.study (id) ON DELETE SET NULL,   -- the scorecard study the numbers came from
    note          TEXT,
    refreshed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS strategy_state_status ON idx.strategy_state (status);
