-- TimescaleDB >= 2.13 creates continuous aggregates as materialized-only; the feed's 1-minute views must also show the
-- minutes not yet materialised (the current session), so switch both to real-time aggregation.
ALTER MATERIALIZED VIEW idx.feed_bar_1m SET (timescaledb.materialized_only = false);
ALTER MATERIALIZED VIEW idx.feed_book_1m SET (timescaledb.materialized_only = false);
