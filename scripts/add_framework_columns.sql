-- hermia-36u: Add framework taxonomy columns to hermia_results.
-- Idempotent: safe to run multiple times.

ALTER TABLE hermia_results
    ADD COLUMN IF NOT EXISTS framework_owasp    TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS framework_mitre    TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS framework_maestro  TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS framework_nist     TEXT[] DEFAULT '{}';

-- Index each column for efficient array-contains queries:
--   WHERE framework_owasp @> ARRAY['LLM01:2025']
CREATE INDEX IF NOT EXISTS idx_hermia_framework_owasp
    ON hermia_results USING GIN (framework_owasp);
CREATE INDEX IF NOT EXISTS idx_hermia_framework_mitre
    ON hermia_results USING GIN (framework_mitre);
CREATE INDEX IF NOT EXISTS idx_hermia_framework_maestro
    ON hermia_results USING GIN (framework_maestro);
CREATE INDEX IF NOT EXISTS idx_hermia_framework_nist
    ON hermia_results USING GIN (framework_nist);
