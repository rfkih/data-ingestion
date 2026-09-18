-- Phones that receive the desk's notifications through the Papan Android app (Firebase Cloud Messaging device tokens).
-- One row per device token; a token FCM reports as gone is disabled, not deleted, so the app can re-register cleanly.

CREATE TABLE idx.push_device (
    token       TEXT PRIMARY KEY,
    platform    TEXT NOT NULL DEFAULT 'android',
    username    TEXT,                               -- the desk account that registered it (from the app session)
    label       TEXT,                               -- device model / app version, free text from the app
    disabled    BOOLEAN NOT NULL DEFAULT false,
    error       TEXT,                               -- last FCM error, if any
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- last register call from the app
    last_sent   TIMESTAMPTZ
);
