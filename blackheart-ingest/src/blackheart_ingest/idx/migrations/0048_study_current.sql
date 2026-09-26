-- Any study id -> the run that currently stands for it (following superseded_by to the end of the chain). Pages and the
-- registry cite study ids that were fixed when they were written; reading through this view keeps them on the latest run.
CREATE OR REPLACE VIEW idx.study_current AS
WITH RECURSIVE chain (id, current_id, depth) AS (
    SELECT id, id, 0 FROM idx.study
    UNION ALL
    SELECT c.id, s.superseded_by, c.depth + 1
      FROM chain c JOIN idx.study s ON s.id = c.current_id
     WHERE s.superseded_by IS NOT NULL AND c.depth < 20
)
SELECT DISTINCT ON (id) id, current_id FROM chain ORDER BY id, depth DESC;
