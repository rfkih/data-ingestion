-- Exchange holidays (operator 2026-09-27: "implement tanggal merah hari libur, dan tanggal bursa, sesuaikan job-nya"). The
-- official "Kalender Libur Bursa" of the Indonesia Stock Exchange, parsed from the exchange's own announcement PDF by
-- idx/exchange_calendar.py. A trading day = Monday-Friday and not a row here.
CREATE TABLE IF NOT EXISTS idx.exchange_holiday (
    day          DATE PRIMARY KEY,
    name         TEXT,
    source       TEXT NOT NULL,          -- the announcement's title and number
    published_at TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
