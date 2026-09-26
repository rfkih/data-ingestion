-- Reproducibility (operator 2026-09-26, item 3 of "1 - 6"): the exact inputs of a study, content-addressed. The data itself
-- lives on disk under data/snapshots/blobs/<sha256> (gitignored, deduplicated); this row is the manifest that names each input
-- by hash, plus table fingerprints so a later run can say which inputs have drifted since. Written by idx/snapshot.py.
CREATE TABLE IF NOT EXISTS idx.study_snapshot (
    study_id    BIGINT NOT NULL REFERENCES idx.study (id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    git_commit  TEXT,
    manifest    JSONB NOT NULL,
    PRIMARY KEY (study_id, created_at)
);
