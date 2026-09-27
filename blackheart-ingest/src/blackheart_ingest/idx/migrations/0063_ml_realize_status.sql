-- Prediction desk: every forecast ends with an actual or a reason it has none (operator 2026-09-27: "pencatatan lengkap dari
-- prediksi dan aktualnya"). 'ok' = realised; 'void' = the horizon passed long ago and no price exists (feed gap, suspension,
-- delisting). A void row leaves the realisation queue, so rows that can never be realised no longer take its batch.
ALTER TABLE idx.ml_prediction ADD COLUMN IF NOT EXISTS realize_status TEXT;
UPDATE idx.ml_prediction SET realize_status = 'ok' WHERE realized_ret IS NOT NULL AND realize_status IS NULL;
