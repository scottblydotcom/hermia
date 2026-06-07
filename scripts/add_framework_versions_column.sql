-- Code-review 2026-06-07: stamp framework_versions on every result row.
-- Stores the agentic-tasks.json::framework_versions sidecar as a JSON object
-- so a result can be tied to the exact framework revision used to score it
-- without git archaeology after a framework bump (ATLAS 6.1, OWASP refresh, etc.).
-- Idempotent: safe to run multiple times.

ALTER TABLE hermia_results
    ADD COLUMN IF NOT EXISTS framework_versions TEXT;
