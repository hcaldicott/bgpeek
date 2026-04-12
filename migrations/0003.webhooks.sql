-- Webhook notifications
-- yoyo migration: applied via `bgpeek-migrate` or `make migrate`

CREATE TABLE webhooks (
    id          SERIAL      PRIMARY KEY,
    name        TEXT        NOT NULL,
    url         TEXT        NOT NULL,
    secret      TEXT,                   -- HMAC secret for signature verification
    events      TEXT[]      NOT NULL,   -- array of event types: {'query', 'device_create', 'device_update', 'device_delete', 'login'}
    enabled     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
