-- 0043  the learning agent may hold past the close (operator, 2026-09-25: "akhir hari ga harus menjual bisa hold sampe besok
--       lusa atau minggu depan"): actions H1 / H2 / H5 keep a position up to 1 / 2 / 5 sessions after the entry day, so a
--       decision is settled on the evening its bracket fills or its time runs out, and records WHEN it left.
ALTER TABLE idx.agent_decision ADD COLUMN IF NOT EXISTS exit_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS agent_decision_open_idx ON idx.agent_decision (agent) WHERE settled_at IS NULL;
