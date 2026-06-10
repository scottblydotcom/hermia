-- Add hermia_version and backend stack tagging columns.
-- Idempotent — safe to run multiple times.

ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS hermia_version TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS gpu_arch TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS runtime_version TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS backend_stack TEXT;

-- Partial index for version-partition queries (WHERE hermia_version = '...').
-- Excludes NULL rows (historical data before PR #109) to keep the index small.
-- CONCURRENTLY avoids a write lock during build; cannot run in a transaction.
-- If CONCURRENTLY fails mid-build, drop the resulting invalid index manually
-- before re-running (IF NOT EXISTS will otherwise silently skip recreation).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hermia_results_hermia_version
    ON hermia_results (hermia_version)
    WHERE hermia_version IS NOT NULL;
