-- Many users, each with their own books (2026-09-17). Everything that is somebody's gets an owner: books (and through them
-- tickets, fills, marks, levels, book alerts), journal rows, watchlists, phones. Research (bars, candidates, cards, packs,
-- studies) stays shared. The books that exist today belong to the first account created on this desk (the operator).

ALTER TABLE idx.book
    ADD COLUMN owner_id      UUID REFERENCES idx.app_user (id),
    ADD COLUMN label         TEXT,                                   -- what the owner calls it ("Live", "Trend paper")
    ADD COLUMN rule          TEXT NOT NULL DEFAULT 'annual',          -- annual (value list, May rebalance) | trend (breakout + trailing stop)
    ADD COLUMN trend_variant TEXT,                                    -- trend books: small | all
    ADD COLUMN archived_at   TIMESTAMPTZ;                             -- a closed book stays for its history, out of every list and job

UPDATE idx.book SET owner_id = (SELECT id FROM idx.app_user ORDER BY created_at LIMIT 1) WHERE book NOT LIKE 'test%';
UPDATE idx.book SET label = CASE book WHEN 'live' THEN 'Live' WHEN 'paper' THEN 'Paper' WHEN 'trend_live' THEN 'Trend'
                                      WHEN 'paper_trend' THEN 'Trend paper' ELSE book END WHERE label IS NULL;
UPDATE idx.book SET rule = 'trend', trend_variant = CASE WHEN lower(split_part(substr(note, 7), ' ', 1)) = 'all' THEN 'all' ELSE 'small' END
 WHERE note LIKE 'trend:%';
CREATE INDEX book_owner_idx ON idx.book (owner_id);

ALTER TABLE idx.decision ADD COLUMN user_id UUID;
UPDATE idx.decision d SET user_id = b.owner_id FROM idx.book b WHERE d.book = b.book;
UPDATE idx.decision SET user_id = (SELECT id FROM idx.app_user ORDER BY created_at LIMIT 1) WHERE user_id IS NULL AND book IS NULL;
CREATE INDEX decision_user_ts_idx ON idx.decision (user_id, ts DESC);

ALTER TABLE idx.watchlist DROP CONSTRAINT watchlist_pkey;
ALTER TABLE idx.watchlist ADD COLUMN user_id UUID;
UPDATE idx.watchlist SET user_id = (SELECT id FROM idx.app_user ORDER BY created_at LIMIT 1);
DELETE FROM idx.watchlist WHERE user_id IS NULL;                      -- no account yet on a fresh desk: nothing to keep
ALTER TABLE idx.watchlist ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE idx.watchlist ADD PRIMARY KEY (user_id, code);

ALTER TABLE idx.push_device ADD COLUMN user_id UUID;
UPDATE idx.push_device p SET user_id = u.id FROM idx.app_user u WHERE lower(p.username) = u.email;
CREATE INDEX push_device_user_idx ON idx.push_device (user_id);

-- room for what comes with more users: a plan per account, and the terms they accepted
ALTER TABLE idx.app_user
    ADD COLUMN plan              TEXT NOT NULL DEFAULT 'free',
    ADD COLUMN accepted_terms_at TIMESTAMPTZ;
