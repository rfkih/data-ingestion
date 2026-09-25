-- Self-learning prediction desk (idx/ml): model registry, every prediction with its realised outcome, and the daily
-- scorecard. The models are LightGBM boosters kept as text (model_to_string) so a fresh process can load the champion
-- without a file system; candidates that lost keep their metrics but not their artifact.

CREATE TABLE IF NOT EXISTS idx.ml_model (
    model_id     BIGSERIAL PRIMARY KEY,
    horizon      TEXT        NOT NULL,                 -- 1m 10m 30m 60m 1d 5d 20d 60d 120d 250d
    task         TEXT        NOT NULL,                 -- dir (P(up)) | ret (log return -> price)
    trained_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_to      DATE        NOT NULL,                 -- last day whose rows the fit saw
    val_from     DATE,                                 -- the out-of-sample window every challenger is judged on
    val_to       DATE,
    rows_fit     INTEGER     NOT NULL DEFAULT 0,
    rows_val     INTEGER     NOT NULL DEFAULT 0,
    params       JSONB       NOT NULL,
    features     TEXT[]      NOT NULL,
    val_metrics  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    importance   JSONB,                                -- feature -> share of gain
    status       TEXT        NOT NULL DEFAULT 'candidate',   -- candidate | champion | retired
    origin       TEXT        NOT NULL DEFAULT 'refresh',     -- refresh (champion params, more data) | tune (perturbed params)
    reason       TEXT,                                 -- why it was promoted / kept / retired
    promoted_at  TIMESTAMPTZ,
    retired_at   TIMESTAMPTZ,
    artifact     TEXT                                  -- LightGBM model string; NULL once retired for > 30 days
);
CREATE INDEX IF NOT EXISTS ml_model_champion_idx ON idx.ml_model (horizon, task) WHERE status = 'champion';
CREATE INDEX IF NOT EXISTS ml_model_trained_idx ON idx.ml_model (trained_at DESC);

-- One row per (name, horizon, cut time). made_at = when the features were cut: the bar close (16:00 WIB) for the daily
-- horizons, the minute for the intraday ones. realised_* are filled by the evaluation job once the horizon has passed.
CREATE TABLE IF NOT EXISTS idx.ml_prediction (
    made_at        TIMESTAMPTZ      NOT NULL,
    code           TEXT             NOT NULL,
    horizon        TEXT             NOT NULL,
    model_dir      BIGINT,
    model_ret      BIGINT,
    ref_price      DOUBLE PRECISION NOT NULL,          -- raw price the prediction is relative to
    p_up           DOUBLE PRECISION,                   -- P(price higher at the horizon)
    pred_ret       DOUBLE PRECISION,                   -- predicted log return
    pred_price     DOUBLE PRECISION,                   -- ref_price * exp(pred_ret), on the tick
    target_at      TIMESTAMPTZ,                        -- when the label matures (intraday: known at cut; daily: resolved on evaluation)
    realized_price DOUBLE PRECISION,
    realized_ret   DOUBLE PRECISION,
    realized_at    TIMESTAMPTZ,
    hit            BOOLEAN,                            -- direction right (zero moves are neither)
    PRIMARY KEY (code, horizon, made_at)
);
SELECT create_hypertable('idx.ml_prediction', 'made_at', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS ml_prediction_open_idx ON idx.ml_prediction (horizon, made_at) WHERE realized_ret IS NULL;
CREATE INDEX IF NOT EXISTS ml_prediction_code_idx ON idx.ml_prediction (code, made_at DESC);

-- The honest number: how the live predictions did against what happened, per horizon, over a trailing window.
CREATE TABLE IF NOT EXISTS idx.ml_scorecard (
    score_date     DATE             NOT NULL,
    horizon        TEXT             NOT NULL,
    window_days    INTEGER          NOT NULL,
    n              INTEGER          NOT NULL,
    hit_rate       DOUBLE PRECISION,
    base_hit       DOUBLE PRECISION,                   -- always-guess-the-majority-direction hit rate on the same rows
    auc            DOUBLE PRECISION,
    ic             DOUBLE PRECISION,                   -- Spearman(pred_ret, realized_ret)
    mae_bps        DOUBLE PRECISION,
    naive_mae_bps  DOUBLE PRECISION,                   -- predict "no change"
    computed_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (score_date, horizon, window_days)
);
