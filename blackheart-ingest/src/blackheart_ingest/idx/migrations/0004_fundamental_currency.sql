-- Filers presenting in USD (e.g. BRPT, TPIA, INCO): values are converted to IDR at the reporting-date rate from the info sheet.
ALTER TABLE idx.fundamental ADD COLUMN currency TEXT NOT NULL DEFAULT 'IDR', ADD COLUMN fx_rate NUMERIC(18,4);
