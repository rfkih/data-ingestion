-- Forward paper watch of research rule C1 (menu DT-3, study #398; operator 2026-09-27 "okay mulai langkahnya"): at the end
-- of each session, the five names with the strongest day (prev close -> 15:49, first hour also up) that WOULD be bought in the
-- closing auction and sold in the next opening auction, plus five random eligible names as the placebo. No orders, no pushes.
-- idx/dt_watch.py writes and settles the rows; the judgement rule is in its docstring.
CREATE TABLE IF NOT EXISTS idx.dt_watch (
    run_date    DATE NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('pick', 'placebo')),
    code        TEXT NOT NULL,
    rank        INT,
    r_day       DOUBLE PRECISION,        -- prev close -> last print before 15:50
    r_first     DOUBLE PRECISION,        -- prev close -> last print before 10:00
    px_1549     NUMERIC,                 -- last print before 15:50
    prev_close  NUMERIC,
    buy_close   NUMERIC,                 -- run_date's closing-auction price (daily_summary.close)
    next_date   DATE,
    sell_open   NUMERIC,                 -- next session's opening-auction price (daily_summary.open)
    gross       DOUBLE PRECISION,
    net_retail  DOUBLE PRECISION,        -- fees 0.15 % + 0.25 %, 5 bps impact each side
    net_low     DOUBLE PRECISION,        -- fees 0.10 % + 0.20 %, 5 bps impact each side
    made_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled_at  TIMESTAMPTZ,
    PRIMARY KEY (run_date, kind, code)
);
