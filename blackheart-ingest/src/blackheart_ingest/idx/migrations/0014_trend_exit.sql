-- Book option (research/IDX_ASYMMETRIC_2026-09-13.md): at the monthly check, sell a held name that crossed from above
-- to below its 200-day average since the previous check. Pairs with entry_gate, which now also buys a held-back name
-- when its 14-day RSI is at or under 30 (oversold), not only when it is above its average.
ALTER TABLE idx.book ADD COLUMN trend_exit BOOLEAN NOT NULL DEFAULT false;
