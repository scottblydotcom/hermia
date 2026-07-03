-- Release-prep for v0.2.0 (hermia-khq): stamp corpus_sha256 on every result row.
-- Stores the SHA-256 hex digest of the shipped agentic-tasks.json so a result
-- can be tied to the exact corpus that produced it — the row-level half of the
-- roadmap's provenance promise (hermia_version + corpus hash). Makes corpus
-- drift self-evident and underwrites the "reproducible by anyone" claim at the
-- row level, without git archaeology.
-- Idempotent: safe to run multiple times.

ALTER TABLE hermia_results
    ADD COLUMN IF NOT EXISTS corpus_sha256 TEXT;
