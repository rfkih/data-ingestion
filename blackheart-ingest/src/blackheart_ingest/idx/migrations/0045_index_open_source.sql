-- IDX publishes previous / high / low / close for an index and no open, so idx.index_daily.open was NULL on every row.
-- jobs/index_open.py fills it from Yahoo's ^JKSE series (bounded by IDX's own high and low for the day) and says so here.
-- The IDX upsert (jobs/index.py) never writes `open`, so a filled value survives the nightly refresh.
ALTER TABLE idx.index_daily ADD COLUMN IF NOT EXISTS open_src TEXT;
COMMENT ON COLUMN idx.index_daily.open_src IS 'where `open` came from: yahoo (^JKSE, bounded by IDX high/low); NULL = no open';
