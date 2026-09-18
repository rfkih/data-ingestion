-- Guardrails for the agent-run desk (docs/superpowers/plans/2026-09-17-idx-agent-desk-plan.md, phase 1): a kill switch
-- and risk limits per book that the server enforces at issue time (idx/ticket.py validate / set_status), and a decision
-- journal so every action - agent, operator or scheduler - has a row saying who, what and why.

ALTER TABLE idx.book ADD COLUMN status           TEXT NOT NULL DEFAULT 'active';      -- active | halted (halted: no build, no issue, no paper fill)
ALTER TABLE idx.book ADD CONSTRAINT book_status_chk CHECK (status IN ('active', 'halted'));
ALTER TABLE idx.book ADD COLUMN halted_at        TIMESTAMPTZ;
ALTER TABLE idx.book ADD COLUMN halt_reason      TEXT;
ALTER TABLE idx.book ADD COLUMN max_weight_pct   NUMERIC(5,2)  NOT NULL DEFAULT 12;   -- one name after the ticket, % of NAV (buys only)
ALTER TABLE idx.book ADD COLUMN max_sector_pct   NUMERIC(5,2)  NOT NULL DEFAULT 35;   -- one sector after the ticket, % of NAV (buys only)
ALTER TABLE idx.book ADD COLUMN max_turnover_pct NUMERIC(5,2)  NOT NULL DEFAULT 40;   -- agent-built rebalance outside May 1-10: traded / NAV
ALTER TABLE idx.book ADD COLUMN min_v60          NUMERIC(20,2) NOT NULL DEFAULT 5000000000;  -- Rp/day, 60-day median value, for a buy

CREATE TABLE idx.decision (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    book        TEXT REFERENCES idx.book (book),
    actor       TEXT NOT NULL,                 -- agent | operator | scheduler
    action      TEXT NOT NULL,                 -- pack_answer | ticket_build | ticket_status | ticket_fill | ticket_skip | fill | halt | resume | settings | note
    code        TEXT,
    ticket_id   BIGINT,
    line_id     BIGINT,
    rationale   TEXT,
    refs        JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX decision_book_ts_idx ON idx.decision (book, ts DESC);
CREATE INDEX decision_code_ts_idx ON idx.decision (code, ts DESC);
