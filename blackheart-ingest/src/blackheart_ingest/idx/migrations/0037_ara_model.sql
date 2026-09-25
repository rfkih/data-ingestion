-- ARA watch, model v2 (2026-09-24, study #146 = research/IDX_ARA_MICRO_2026-09-24.md; operator: "terapkan di page ARA
-- untuk prediksi dan keyakinannya").
--
-- The evening list now carries two calibrated probabilities and a confidence word instead of one raw score:
--   p_lock   P(next session CLOSES at the ARA price)  - the primary prediction, Platt-calibrated on a 12-month holdout
--   p_touch  P(next session's high reaches it)        - the old list's label, calibrated the same way
--   p_dl     the GRU's calibrated P(lock) (NULL when the run had no torch / the GRU failed)
--   score    the rank key: mean of the within-day percentile ranks of p_lock and p_dl (ENS, the study's rank model),
--            or p_lock alone when p_dl is NULL
--   locked_today / buyable  what a reader needs before acting: a name locked today has no offer to buy
--   confidence  'high' (p_lock >= 10 %), 'medium' (>= 3 %), 'low' - bands from the study's calibration table
--   model    'ens' | 'tree'
-- ``p`` stays and now holds the calibrated p_lock (it was the raw touch-model score), so old readers keep working.
ALTER TABLE idx.ara_watch
    ADD COLUMN IF NOT EXISTS p_lock       NUMERIC(8, 5),
    ADD COLUMN IF NOT EXISTS p_touch      NUMERIC(8, 5),
    ADD COLUMN IF NOT EXISTS p_dl         NUMERIC(8, 5),
    ADD COLUMN IF NOT EXISTS score        NUMERIC(10, 6),
    ADD COLUMN IF NOT EXISTS locked_today BOOLEAN,
    ADD COLUMN IF NOT EXISTS buyable      BOOLEAN,
    ADD COLUMN IF NOT EXISTS confidence   TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    ADD COLUMN IF NOT EXISTS model        TEXT;
COMMENT ON COLUMN idx.ara_watch.p IS 'calibrated P(lock at ARA next session) since 0036; before: raw touch-model score';
