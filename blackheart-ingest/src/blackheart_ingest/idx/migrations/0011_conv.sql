-- Cash conversion (operating cash flow / net profit, same audited year, capped at 3) on the candidate row: the fourth rank
-- input of the strict_cash strategy (research/IDX_CASH_CONVERSION_2026-09-12.md).
ALTER TABLE idx.candidate ADD COLUMN conv NUMERIC(10,4);
