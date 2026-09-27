-- ARA prediction vs actual (operator 2026-09-27: "aku mau pencatatan lengkap dari prediksi dan aktualnya"). Measurement only:
-- no book, no entry rule, no new screen (the ARA freeze). Every idx.ara_watch row gets what the NEXT session did, filled by
-- ara.settle once that session's official day summary is in; one idx.ara_scorecard row per run grades the run as a whole.
ALTER TABLE idx.ara_watch
    ADD COLUMN IF NOT EXISTS next_date         DATE,
    ADD COLUMN IF NOT EXISTS next_prev         NUMERIC,     -- IDX's own previous for that session (adjusts for corporate actions)
    ADD COLUMN IF NOT EXISTS next_ara_px       NUMERIC,     -- the limit that session actually had (from next_prev, not from the stored ara_px)
    ADD COLUMN IF NOT EXISTS next_open         NUMERIC,
    ADD COLUMN IF NOT EXISTS next_high         NUMERIC,
    ADD COLUMN IF NOT EXISTS next_low          NUMERIC,
    ADD COLUMN IF NOT EXISTS next_close        NUMERIC,
    ADD COLUMN IF NOT EXISTS next_volume       NUMERIC,
    ADD COLUMN IF NOT EXISTS next_offer_volume NUMERIC,     -- offer queue left at the close: 0 at the limit = locked with no sellers
    ADD COLUMN IF NOT EXISTS touched           BOOLEAN,     -- next high >= next_ara_px (the model's TOUCH1 label)
    ADD COLUMN IF NOT EXISTS locked            BOOLEAN,     -- next close >= next_ara_px (the model's LOCK1 label)
    ADD COLUMN IF NOT EXISTS ret_close         NUMERIC,     -- next close / next_prev - 1
    ADD COLUMN IF NOT EXISTS ret_high          NUMERIC,     -- next high / next_prev - 1
    ADD COLUMN IF NOT EXISTS outcome           TEXT,        -- lock | touch | none | no_trade (no volume that session) | no_bar (no row that session)
    ADD COLUMN IF NOT EXISTS settled_at        TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ara_watch_unsettled ON idx.ara_watch (run_date) WHERE settled_at IS NULL;

CREATE TABLE IF NOT EXISTS idx.ara_scorecard (
    run_date        DATE PRIMARY KEY,
    bar_date        DATE,
    next_date       DATE,
    model           TEXT,
    whole_ranking   BOOLEAN NOT NULL,      -- the run kept every scored name (2026-09-25 on); list-only runs cannot give AUC / base rate
    n_stored        INT NOT NULL,
    n_listed        INT NOT NULL,
    universe        INT,                   -- names the model could score that evening (main board, traded, previous >= MIN_PREV)
    universe_locks  INT,                   -- of those, how many locked the next session: the recall denominator
    universe_touches INT,
    base_rate       NUMERIC,               -- universe_locks / universe
    top5_locks      INT, top10_locks INT, top20_locks INT,
    top5_touches    INT, top10_touches INT, top20_touches INT,
    top5_n          INT, top10_n INT, top20_n INT,   -- settled names in the top-k (a name with no bar next session drops out)
    prec5           NUMERIC, prec10 NUMERIC, prec20 NUMERIC,   -- locks among the top-k by rank / k
    recall20        NUMERIC,               -- top20_locks / universe_locks (study #146: 48-76 % a year)
    listed_locks    INT,                   -- locks among the listed names (top-N + held)
    listed_buyable  INT,                   -- listed names with an offer at the close of the run day
    listed_buyable_locks INT,
    mean_p_top10    NUMERIC,               -- the calibrated P(lock) the top 10 carried, next to prec10 = the calibration check
    auc_lock        NUMERIC,               -- whole-ranking runs only
    auc_touch       NUMERIC,
    brier_lock      NUMERIC,
    settled_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
