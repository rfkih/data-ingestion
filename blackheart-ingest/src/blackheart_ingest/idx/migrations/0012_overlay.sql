-- Book-level overlays (research/IDX_TREND_OVERLAY_2026-09-13.md), both off by default:
--   regime_filter  cash while the COMPOSITE is under its 200-day average (monthly check; cash / re-entry tickets)
--   entry_gate     buy a listed name only when it is above its own 200-day average (held back until it crosses)
ALTER TABLE idx.book ADD COLUMN regime_filter BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE idx.book ADD COLUMN entry_gate    BOOLEAN NOT NULL DEFAULT false;

-- one row per monthly check (first trading day of the month, after the close)
CREATE TABLE idx.regime_check (
    check_date   DATE PRIMARY KEY,
    index_code   TEXT NOT NULL,
    close        NUMERIC(18,4) NOT NULL,
    sma          NUMERIC(18,4),
    regime_on    BOOLEAN NOT NULL,
    detail       JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- ticket.mode gains 'cash' (sell everything: regime off) and 'entry' (buy held-back names that crossed above their average)
