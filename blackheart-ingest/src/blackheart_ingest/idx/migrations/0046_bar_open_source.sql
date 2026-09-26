-- Where idx.bar.open came from. IDX leaves the open out for names outside the pre-opening session (open_missing = true);
-- jobs/bar_open.py fills those from Yahoo only where the day aligns with IDX's close, lands on IDX's tick grid and lies
-- inside IDX's own low-high, after the rule has reproduced IDX's published opens on the same window. open_missing keeps
-- saying that IDX itself published none.
ALTER TABLE idx.bar ADD COLUMN IF NOT EXISTS open_src TEXT;
UPDATE idx.bar SET open_src = 'idx' WHERE open IS NOT NULL AND open_src IS NULL AND source = 'idx';
UPDATE idx.bar SET open_src = source WHERE open IS NOT NULL AND open_src IS NULL;
COMMENT ON COLUMN idx.bar.open_src IS 'where `open` came from: idx (published) | yahoo (filled by jobs/bar_open.py, validated) | NULL = no open';
