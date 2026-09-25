-- 0041  combo_watch: one row per confirmation RULE (menu ML-8, study #175: the ML sleeve as an ensemble of price-confirmation
--       rules, each with an equal share of the sleeve's slot). `rule` names the rule ("+5/10" = +5 % within 10 trading days),
--       `size_frac` is that rule's share of the ML slot (1 = the single-rule sleeve as before). The uniqueness moves from
--       (book, code, signal_date) to (book, code, signal_date, rule) so the ensemble can watch one name at several levels.
ALTER TABLE idx.combo_watch ADD COLUMN IF NOT EXISTS rule TEXT NOT NULL DEFAULT '+5/10';
ALTER TABLE idx.combo_watch ADD COLUMN IF NOT EXISTS size_frac NUMERIC(6, 4) NOT NULL DEFAULT 1;
ALTER TABLE idx.combo_watch DROP CONSTRAINT IF EXISTS combo_watch_book_code_signal_date_key;
CREATE UNIQUE INDEX IF NOT EXISTS combo_watch_rule_uq ON idx.combo_watch (book, code, signal_date, rule);
