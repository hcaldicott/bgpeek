-- Example community labels — generic, RFC-safe patterns to illustrate
-- the format. Apply manually if you want a starting point:
--   psql "$BGPEEK_DATABASE_URL" -f scripts/seed-examples.sql
--
-- Operators will normally maintain their own labels via the
-- /api/community-labels admin API instead of editing this file.

INSERT INTO community_labels (pattern, match_type, label) VALUES
    ('0:0',          'exact',  'no-export equivalent'),
    ('65535:65281',  'exact',  'NO_EXPORT (well-known)'),
    ('65535:65282',  'exact',  'NO_ADVERTISE (well-known)'),
    ('65535:65283',  'exact',  'NO_EXPORT_SUBCONFED (well-known)'),
    ('65535:0',      'prefix', 'reserved well-known')
ON CONFLICT (pattern, match_type) DO NOTHING;
