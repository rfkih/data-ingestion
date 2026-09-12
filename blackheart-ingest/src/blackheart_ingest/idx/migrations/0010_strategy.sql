-- Strategy catalog support: 12-1 month momentum on candidate rows (the momentum families need it), the strategy and size
-- a book follows, and the historical record each (strategy, size) earned in research (imported from the research JSON).
ALTER TABLE idx.candidate ADD COLUMN mom NUMERIC(10,4);                 -- close 21 bars ago / close 252 bars ago - 1
ALTER TABLE idx.book ADD COLUMN strategy TEXT NOT NULL DEFAULT 'rule';
ALTER TABLE idx.book ADD COLUMN max_names INTEGER;                      -- NULL = the strategy's natural list

CREATE TABLE idx.strategy_history (
    strategy         TEXT NOT NULL,                                       -- catalog key, 'bench', or 'index:<CODE>'
    size             INTEGER NOT NULL DEFAULT 0,                          -- 0 = natural list (top fifth); 10, 15 = cut
    rebalance_month  INTEGER NOT NULL,                                    -- 5 = the reported schedule; 2/8/11 = robustness
    source           TEXT NOT NULL,                                       -- which research output and key it came from
    n_trials         INTEGER,                                             -- DSR multiplicity used for that source
    stats            JSONB NOT NULL,                                      -- total_pct, cagr_pct, sharpe, mdd_pct, dsr, psr, from
    yearly           JSONB,                                               -- calendar-year returns %
    periods          JSONB,                                               -- rebalance-to-rebalance returns %
    holdings         JSONB,                                               -- [{date, n, names, top?, bottom?}]
    generated_at     TIMESTAMPTZ,
    imported_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (strategy, size, rebalance_month)
);
