-- dt_watch review fix (2026-09-27, before the first row): the universe row stores the eligible list frozen at pick time, so the
-- settle never re-derives it from a feed-symbol set that may have changed after the session (look-ahead).
ALTER TABLE idx.dt_watch ADD COLUMN IF NOT EXISTS universe TEXT[];
