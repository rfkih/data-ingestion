-- ARA watch (2026-09-23; research menus 16, ML-3, 34 = studies #56, #57, #101).
--
-- What the research settled, which decides what these tables hold:
--   * tomorrow's ARA touches are PREDICTABLE from today's bars (ML-3: AUC 0.86-0.92, top-5-per-day precision 7-18 %,
--     17-27x the base rate) but NOT BUYABLE (menu 16: the names that keep going open locked, the fillable ones lose)
--     -> the nightly list is information for a holder or a watcher, never an entry ticket;
--   * for a HOLDER whose name touches ARA the answer depends on whether the touch holds to the close (menu 34):
--     locked close -> holding beats the ARA price by +431 bps the next day (liquid names, n 440, t 8);
--     faded touch  -> selling at the ARA price beats holding by 661 bps (liquid, n 231, t 15)
--     -> the intraday state (locked / sellers at ARA / faded) is the fact the phone gets, with those two numbers.

-- The nightly list: one row per (run, name) - the top-N by model score plus every name a non-archived book holds.
CREATE TABLE IF NOT EXISTS idx.ara_watch (
    run_date    DATE NOT NULL,                  -- the evening the model ran
    bar_date    DATE NOT NULL,                  -- the last bar it scored (the touch is expected on the NEXT session)
    code        TEXT NOT NULL,
    rank        INTEGER,                        -- 1..N in the universe list; NULL for a held name outside the top-N
    p           NUMERIC(8, 5) NOT NULL,         -- model P(touch ARA on the next session)
    prev_close  NUMERIC(18, 4),                 -- the close the limit is computed from
    ara_px      NUMERIC(18, 4),                 -- next session's upper auto-rejection price
    held        BOOLEAN NOT NULL DEFAULT false,
    books       TEXT[],                         -- which books hold it (empty when not held)
    features    JSONB,                          -- the model inputs, for the card and for auditing a call later
    PRIMARY KEY (run_date, code)
);
CREATE INDEX IF NOT EXISTS ara_watch_code_idx ON idx.ara_watch (code, run_date DESC);

-- Today's touches, as the feed sees them: the state machine a holder acts on.
CREATE TABLE IF NOT EXISTS idx.ara_touch (
    trade_date  DATE NOT NULL,
    code        TEXT NOT NULL,
    ara_px      NUMERIC(18, 4) NOT NULL,
    prev_close  NUMERIC(18, 4),
    state       TEXT NOT NULL CHECK (state IN ('locked', 'at_ara', 'faded')),
    first_ts    TIMESTAMPTZ,                    -- first time the day's high reached the limit (as observed)
    last_ts     TIMESTAMPTZ,                    -- last print seen
    high        NUMERIC(18, 4),
    last_price  NUMERIC(18, 4),
    offer_px    NUMERIC(18, 4),                 -- best offer at the last look (NULL = no offer = locked)
    offer_vol   NUMERIC(24, 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, code)
);
