-- Tamper-evident signal ledger (evidence plan item 3, operator 2026-09-26 "okay do all"): every nightly plan and every morning
-- gap scan of a combo book is sealed BEFORE the market acts on it. Each entry's hash covers the previous entry's hash, so editing
-- or deleting any past signal breaks every later hash (idx/signal_ledger.py verify). The same lines go to a git repository
-- (data/signal-ledger) whose pushes - once the operator gives it a remote - are the external timestamp.
CREATE TABLE IF NOT EXISTS idx.signal_ledger (
    seq          BIGSERIAL PRIMARY KEY,
    sealed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    book         TEXT NOT NULL,
    event        TEXT NOT NULL,                   -- plan | gap_entry
    payload      JSONB NOT NULL,
    payload_sha  TEXT NOT NULL,
    prev_sha     TEXT NOT NULL,
    entry_sha    TEXT NOT NULL UNIQUE
);
