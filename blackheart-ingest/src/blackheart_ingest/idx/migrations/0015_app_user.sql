-- Desk accounts (blackheart_ingest.idx.accounts): anyone can register; the Papan app signs people in against this
-- table through the platform-shaped user API on this worker. Passwords are scrypt hashes, never the platform's.
CREATE TABLE idx.app_user (
    id            UUID PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,                 -- stored lower-case
    full_name     TEXT NOT NULL,
    phone         TEXT,
    password_hash TEXT NOT NULL,                        -- scrypt$N$r$p$salt$hash
    role          TEXT NOT NULL DEFAULT 'USER',
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
