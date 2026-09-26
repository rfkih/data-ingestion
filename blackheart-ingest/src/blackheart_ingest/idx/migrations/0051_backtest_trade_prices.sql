-- Entry and exit prices on imported backtest trades (operator 2026-09-26: the Results tab's recent trades showed none).
-- The price the backtest traded at: the fill price before fees, unadjusted as of that day. NULL for trade lists without them.
ALTER TABLE idx.strategy_backtest_trade ADD COLUMN IF NOT EXISTS entry_price NUMERIC(14, 2);
ALTER TABLE idx.strategy_backtest_trade ADD COLUMN IF NOT EXISTS exit_price NUMERIC(14, 2);
