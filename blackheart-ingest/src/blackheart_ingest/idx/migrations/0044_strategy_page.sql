-- 0044  the Strategies page (operator, 2026-09-25: "add strategies page, so each strategy has it own details, from training
--       history and options of strategy like regime filter"; design "Blackridge Strategies.dc.html").
--
--   strategy_config_version  every change to a strategy's settings in one portfolio, as an immutable version: what changed
--                            (option, from, to, reason), who, when, and the full settings after it. The settings themselves
--                            still live where the runners read them (idx.book columns and idx.book.params) - this is the
--                            audit trail and the version counter the page shows and the write path checks (expected_version).
--                            A (book, strategy) with no row is at v1: the settings it was created with.
--   strategy_backtest_trade  the round trips a backtest study produced for a strategy, imported from the study's trade list
--                            so the page reads the database, never a research scratch file.
CREATE TABLE IF NOT EXISTS idx.strategy_config_version (
    id          BIGSERIAL PRIMARY KEY,
    book        TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 2),
    changes     JSONB NOT NULL,
    snapshot    JSONB NOT NULL,
    actor       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (book, strategy, version)
);

CREATE TABLE IF NOT EXISTS idx.strategy_backtest_trade (
    strategy    TEXT NOT NULL,
    study_id    BIGINT NOT NULL REFERENCES idx.study (id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    code        TEXT NOT NULL,
    d_in        DATE NOT NULL,
    d_out       DATE NOT NULL,
    cost        NUMERIC(20, 2) NOT NULL,
    pnl         NUMERIC(20, 2) NOT NULL,
    exit_reason TEXT,
    PRIMARY KEY (strategy, study_id, seq)
);
CREATE INDEX IF NOT EXISTS strategy_backtest_trade_d_out_idx ON idx.strategy_backtest_trade (strategy, d_out);
