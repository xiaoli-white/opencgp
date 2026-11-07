-- 2026-11-07 add the long-form authoring brief to series and standalone pieces.
-- Existing instances only: fresh databases already create the column from the
-- repository schema. The migration is idempotent: PostgreSQL supports
-- ADD COLUMN IF NOT EXISTS directly, and SQLite is handled by the repository
-- schema reconciler (COLUMN_MIGRATIONS) which checks PRAGMA table_info before
-- issuing ALTER TABLE, so applying this file to a database that already has
-- the column is a no-op.
-- Back up the database before running this.

BEGIN;

ALTER TABLE series ADD COLUMN IF NOT EXISTS brief TEXT NOT NULL DEFAULT '';
ALTER TABLE pieces ADD COLUMN IF NOT EXISTS brief TEXT NOT NULL DEFAULT '';

COMMIT;
