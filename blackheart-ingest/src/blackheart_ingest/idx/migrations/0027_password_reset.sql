-- Password resets (2026-09-17): a one-time token made on the desk (`idx account reset-link EMAIL`) and used once on the
-- app's /reset page within its lifetime. Only the token's hash is stored; the link itself is shown once to whoever runs the
-- command. (No mail is sent from this desk; the link reaches the person by hand.)
CREATE TABLE idx.password_reset (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES idx.app_user (id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ
);
CREATE INDEX password_reset_user_idx ON idx.password_reset (user_id);
