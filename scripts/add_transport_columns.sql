-- Workstream A (transport abstraction) + execution-path columns.
-- Idempotent: safe to run against an existing hermia_results table.
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS model_size_server_gb DOUBLE PRECISION;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS execution_path TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS orchestration TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS orchestration_version TEXT;
-- signals is a JSON object stored as text (flat map of probe signal -> bool).
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS signals TEXT;
