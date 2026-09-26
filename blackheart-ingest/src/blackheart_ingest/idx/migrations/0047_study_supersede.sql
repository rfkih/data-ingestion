-- A study row is written once and never edited (research_store.record_study). When a study is re-run because its input
-- data was corrected, the new run gets a new row and the old one points at it, so readers follow the chain to the
-- current result and the old numbers stay on file for comparison.
ALTER TABLE idx.study ADD COLUMN IF NOT EXISTS superseded_by BIGINT REFERENCES idx.study (id) ON DELETE SET NULL;
ALTER TABLE idx.study ADD COLUMN IF NOT EXISTS supersede_reason TEXT;
CREATE INDEX IF NOT EXISTS study_superseded_by_idx ON idx.study (superseded_by) WHERE superseded_by IS NOT NULL;
COMMENT ON COLUMN idx.study.superseded_by IS 'the re-run that replaces this row (same study, corrected input); NULL = current';
