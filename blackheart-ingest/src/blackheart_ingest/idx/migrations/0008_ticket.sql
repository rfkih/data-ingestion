-- Rebalance ticket: the trade list the operator works by hand at the broker; fills are captured back into idx.fill.
CREATE TABLE idx.ticket (
    id           BIGSERIAL PRIMARY KEY,
    book         TEXT NOT NULL REFERENCES idx.book (book),
    ticket_date  DATE NOT NULL,                              -- prices as of this close; to be worked the next session
    run_date     DATE,                                       -- candidate run the targets came from
    mode         TEXT NOT NULL,                              -- rebalance | exits
    status       TEXT NOT NULL DEFAULT 'draft',              -- draft | issued | closed | cancelled
    nav          NUMERIC(20,2),
    cash         NUMERIC(20,2),
    n_targets    INTEGER,
    params       JSONB NOT NULL DEFAULT '{}',
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ticket_book_date ON idx.ticket (book, ticket_date DESC);

CREATE TABLE idx.ticket_line (
    id            BIGSERIAL PRIMARY KEY,
    ticket_id     BIGINT NOT NULL REFERENCES idx.ticket (id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    code          TEXT NOT NULL,
    side          TEXT NOT NULL,                             -- buy | sell
    lots          NUMERIC(14,2) NOT NULL,
    limit_price   NUMERIC(18,4) NOT NULL,                    -- tick-snapped, inside the auto-rejection band
    ref_close     NUMERIC(18,4),
    notional      NUMERIC(20,2),
    weight_now    NUMERIC(8,5),
    weight_target NUMERIC(8,5),
    reason        TEXT,
    flags         TEXT[] NOT NULL DEFAULT '{}',              -- strict-gate fails, warnings, pack stance/veto, cash-limited
    status        TEXT NOT NULL DEFAULT 'open',              -- open | filled | partial | skipped
    filled_lots   NUMERIC(14,2) NOT NULL DEFAULT 0,
    fill_id       BIGINT REFERENCES idx.fill (id),
    skip_reason   TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticket_id, code, side)
);
