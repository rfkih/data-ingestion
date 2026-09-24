-- Two brokers, one desk (2026-09-23): Stockbit stays the default, Ajaib becomes the standby, and the operator switches
-- from Blackridge without touching a file or restarting anything.
--
-- The shape of the problem, which decides the shape of this migration:
--
--   a provider serves a ROLE, not "everything".  The desk already wants feed = Stockbit (its websocket is wired, 136
--   symbols, months of prints) and orders = Ajaib.  One global "active broker" switch would force those together and be
--   wrong on day one, so the unit of choice is (role, provider), not (provider).
--
--   credentials are per provider, never shared.  ``feed_token`` was a singleton (id = 1): one session, one refresh
--   token, one relay page.  Two providers with one row means one login silently overwriting the other - the exact
--   confusion the operator asked to avoid.  The primary key becomes the provider.
--
--   only one provider collects at a time.  Running both websockets doubles the load and lets two sources disagree about
--   the same print.  The standby is health-checked, not subscribed.  That is why provenance is recorded per SESSION
--   (``feed_status.provider``) and not per row: the hypertables are compressed, a column there is an expensive rewrite,
--   and with one active collector the session already says who produced every row inside it.  If both ever stream at
--   once, that decision has to be revisited.

-- Which provider currently serves each role. One row per role; the row IS the toggle Blackridge writes.
CREATE TABLE IF NOT EXISTS idx.provider_role (
    role        TEXT PRIMARY KEY CHECK (role IN ('feed', 'order')),
    provider    TEXT NOT NULL,
    fallback    TEXT,                              -- the standby, shown in the app; switching is deliberate, never silent
    auto_failover BOOLEAN NOT NULL DEFAULT false,  -- off by default: a silent swap mid-decision is a correctness bug
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by  TEXT,                              -- the account that flipped it, for the journal
    note        TEXT
);

INSERT INTO idx.provider_role (role, provider, fallback, note) VALUES
    ('feed',  'stockbit', 'ajaib',    'Stockbit''s websocket is the wired one: 136 symbols, prints since 2026-09-21'),
    ('order', 'stockbit', 'ajaib',    'no order gateway is implemented yet for either provider - both are drafting only')
ON CONFLICT (role) DO NOTHING;

-- Credentials, one row per provider. The old singleton row becomes Stockbit's.
ALTER TABLE idx.feed_token ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'stockbit';
ALTER TABLE idx.feed_token DROP CONSTRAINT IF EXISTS feed_token_pkey;
ALTER TABLE idx.feed_token DROP CONSTRAINT IF EXISTS feed_token_id_check;
ALTER TABLE idx.feed_token ALTER COLUMN id DROP DEFAULT;
ALTER TABLE idx.feed_token ADD CONSTRAINT feed_token_pkey PRIMARY KEY (provider);
ALTER TABLE idx.feed_token ALTER COLUMN id DROP NOT NULL;
-- ``id`` keeps a unique key on purpose: a collector already running holds the OLD code in memory, which upserts with
-- ON CONFLICT (id). Dropping that key breaks the live feed the moment this migration lands, before any restart.
ALTER TABLE idx.feed_token DROP CONSTRAINT IF EXISTS feed_token_id_key;
ALTER TABLE idx.feed_token ADD CONSTRAINT feed_token_id_key UNIQUE (id);
COMMENT ON COLUMN idx.feed_token.provider IS 'stockbit | ajaib - one session per provider, never shared';

-- Collector heartbeat, one row per provider: the standby has a status too (last health check), it just never streams.
ALTER TABLE idx.feed_status ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'stockbit';
ALTER TABLE idx.feed_status DROP CONSTRAINT IF EXISTS feed_status_pkey;
ALTER TABLE idx.feed_status DROP CONSTRAINT IF EXISTS feed_status_id_check;
ALTER TABLE idx.feed_status ALTER COLUMN id DROP DEFAULT;
ALTER TABLE idx.feed_status ADD CONSTRAINT feed_status_pkey PRIMARY KEY (provider);
ALTER TABLE idx.feed_status ALTER COLUMN id DROP NOT NULL;
ALTER TABLE idx.feed_status DROP CONSTRAINT IF EXISTS feed_status_id_key;
ALTER TABLE idx.feed_status ADD CONSTRAINT feed_status_id_key UNIQUE (id);   -- see the note on feed_token above
COMMENT ON COLUMN idx.feed_status.provider IS 'which provider produced this session''s prints; one active collector at a time';

-- Every switch is journalled, so "why did the book see different prices on the 14th" is answerable a year later.
CREATE TABLE IF NOT EXISTS idx.provider_event (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    role       TEXT NOT NULL,
    from_provider TEXT,
    to_provider   TEXT NOT NULL,
    reason     TEXT NOT NULL,                      -- 'operator' | 'health' | 'seed'
    actor      TEXT,
    detail     JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS provider_event_ts ON idx.provider_event (ts DESC);
