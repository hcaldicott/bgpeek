-- SSH credential management: credentials as a first-class entity.
-- Devices reference credentials via FK; keys stored on disk.

CREATE TABLE credentials (
    id          SERIAL          PRIMARY KEY,
    name        TEXT            NOT NULL UNIQUE,
    description TEXT            NOT NULL DEFAULT '',
    auth_type   TEXT            NOT NULL DEFAULT 'key'
                CHECK (auth_type IN ('key', 'password', 'key+password')),
    username    TEXT            NOT NULL,
    key_name    TEXT,           -- filename in keys directory (e.g. "noc-juniper.key")
    password    TEXT,           -- Fernet-encrypted, for password auth
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX credentials_name_idx ON credentials (name);

-- Add FK from devices to credentials (nullable for backward compatibility)
ALTER TABLE devices ADD COLUMN credential_id INTEGER REFERENCES credentials(id) ON DELETE SET NULL;
