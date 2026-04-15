-- Community labels: operator-maintained mapping from community patterns
-- to human-readable tags shown next to each community in BGP results.
-- Patterns can be exact (e.g. "65000:100") or prefixes (e.g. "65000:1"
-- matches 65000:1, 65000:10, 65000:1234, …).
--
-- The table ships empty. Operators add their own labels through the
-- /api/community-labels admin endpoints; see scripts/seed-examples.sql
-- for a starter set of generic examples.

CREATE TABLE IF NOT EXISTS community_labels (
    id SERIAL PRIMARY KEY,
    pattern TEXT NOT NULL,
    match_type TEXT NOT NULL CHECK (match_type IN ('exact', 'prefix')),
    label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pattern, match_type)
);
