-- Book option (research/IDX_SELL_RULES_2026-09-13.md): sell a held name at the monthly check once it is take_profit_pct
-- above its purchase price (NULL = off). Passed its pre-registered bar on ten doubling events; offered, not the default.
ALTER TABLE idx.book ADD COLUMN take_profit_pct NUMERIC(6,2);
