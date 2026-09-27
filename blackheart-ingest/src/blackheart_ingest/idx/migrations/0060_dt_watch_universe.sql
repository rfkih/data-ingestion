-- dt_watch judgement redesign (2026-09-27, before the first row): one 'universe' row per session (code '*') holds the
-- equal-weight closing-auction -> next-opening-auction return of every eligible name, so the report can test the pick's
-- SELECTION edge (pick - universe) with a sequential test instead of an underpowered t on the raw return.
ALTER TABLE idx.dt_watch DROP CONSTRAINT IF EXISTS dt_watch_kind_check;
ALTER TABLE idx.dt_watch ADD CONSTRAINT dt_watch_kind_check CHECK (kind IN ('pick', 'placebo', 'universe'));
