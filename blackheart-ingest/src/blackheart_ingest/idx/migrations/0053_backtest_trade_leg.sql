-- Which leg of a strategy a backtest round trip belongs to (operator 2026-09-26: the ML sleeve's four ens4 rules each
-- hold a quarter slot, so one position shows as up to four rows - the leg says which rule, e.g. "+8/10").
ALTER TABLE idx.strategy_backtest_trade ADD COLUMN IF NOT EXISTS leg TEXT;
