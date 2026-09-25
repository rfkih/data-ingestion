-- The ARA model scores every main-board name that traded (762 last session) but only the top of that ranking was ever
-- stored, so a person who asked about any other name got nothing back. The evening now keeps every scored row and marks
-- the ones the list and the push are built from, which is what `listed` is for: the screens and the notification read
-- `listed OR held` and are unchanged, while a lookup by code can answer for the whole board.
--
-- Existing rows were all part of a list, so the default is right for them.
ALTER TABLE idx.ara_watch ADD COLUMN IF NOT EXISTS listed BOOLEAN NOT NULL DEFAULT true;
COMMENT ON COLUMN idx.ara_watch.listed IS 'in the evening list (the top N, plus any held name); false = scored but not shown';
COMMENT ON COLUMN idx.ara_watch.rank IS 'position in the full ranking of every scored name; NULL when the model could not rank it';
