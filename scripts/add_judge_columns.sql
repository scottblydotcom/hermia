-- hermia-97t: Add LLM-as-judge columns to hermia_results.
-- Idempotent: safe to run multiple times.
-- v0.1 rows write NULL for both columns.
-- v0.3 LLM-as-judge work populates them via the --judge flag.

ALTER TABLE hermia_results
    ADD COLUMN IF NOT EXISTS judge_score     NUMERIC,
    ADD COLUMN IF NOT EXISTS judge_reasoning TEXT;
