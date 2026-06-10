-- Add hermia_version and backend stack tagging columns.
-- Idempotent — safe to run multiple times.

ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS hermia_version TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS gpu_arch TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS runtime_version TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS backend_stack TEXT;

-- Index for version-partition queries (WHERE hermia_version = '...').
CREATE INDEX IF NOT EXISTS idx_hermia_results_hermia_version
    ON hermia_results (hermia_version);
