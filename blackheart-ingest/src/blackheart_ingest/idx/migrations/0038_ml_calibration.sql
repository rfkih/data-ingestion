-- idx/ml, second pass (2026-09-24 evening): labels of the 20d+ horizons are EXCESS return over the COMPOSITE (basis
-- 'excess'), probabilities are calibrated from realised outcomes (isotonic, one curve per horizon), and every
-- prediction keeps the raw model probability next to the calibrated one.

ALTER TABLE idx.ml_prediction ADD COLUMN IF NOT EXISTS basis TEXT NOT NULL DEFAULT 'abs';      -- abs | excess (vs COMPOSITE)
ALTER TABLE idx.ml_prediction ADD COLUMN IF NOT EXISTS p_up_raw DOUBLE PRECISION;              -- before calibration

CREATE TABLE IF NOT EXISTS idx.ml_calibration (
    horizon    TEXT        PRIMARY KEY,
    fitted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    n          INTEGER     NOT NULL,
    from_at    TIMESTAMPTZ,                       -- the realised predictions the curve was fitted on
    to_at      TIMESTAMPTZ,
    knots_p    DOUBLE PRECISION[] NOT NULL,       -- isotonic step function: raw probability ->
    knots_y    DOUBLE PRECISION[] NOT NULL,       -- realised up-rate, non-decreasing
    raw_hit    DOUBLE PRECISION,                  -- hit rate at 0.5 before / after, on the fitting rows (in-sample, a diagnostic)
    cal_hit    DOUBLE PRECISION
);
