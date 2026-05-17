-- hermia_findings: stores analyst observations derived from hermia_results.
-- Each row is one finding. content_hash enforces idempotency — running the
-- statistical pass twice on the same data produces no duplicate rows.

CREATE TABLE IF NOT EXISTS hermia_findings (
    id              SERIAL PRIMARY KEY,
    observed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Classification
    finding_type    TEXT NOT NULL,   -- universal_weakness | model_failure | security_critical | worst_performer | regression
    scope           TEXT NOT NULL,   -- cross_model | model_specific | test_specific

    -- What it applies to
    models          TEXT[] NOT NULL DEFAULT '{}',
    test_ids        TEXT[] NOT NULL DEFAULT '{}',
    host_tags       TEXT[] NOT NULL DEFAULT '{}',

    -- Severity and summary
    severity        TEXT NOT NULL,   -- info | medium | high | critical
    headline        TEXT NOT NULL,

    -- Metric that backs the claim
    metric_name     TEXT,
    metric_value    NUMERIC,
    baseline_value  NUMERIC,

    -- Provenance
    source          TEXT NOT NULL DEFAULT 'statistical',  -- statistical | llm-manual | llm-auto
    run_id_refs     TEXT[] NOT NULL DEFAULT '{}',
    supporting_sql  TEXT,

    -- Flexible tagging (talk dates, model families, themes)
    tags            TEXT[] NOT NULL DEFAULT '{}',
    notes           TEXT,

    -- Lifecycle
    invalidated_at  TIMESTAMPTZ,

    -- Deduplication key: SHA-256 of (type+scope+models+test_ids+run_ids+metric_name+metric_value)
    content_hash    TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_findings_type      ON hermia_findings(finding_type);
CREATE INDEX IF NOT EXISTS idx_findings_severity  ON hermia_findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_source    ON hermia_findings(source);
CREATE INDEX IF NOT EXISTS idx_findings_models    ON hermia_findings USING gin(models);
CREATE INDEX IF NOT EXISTS idx_findings_test_ids  ON hermia_findings USING gin(test_ids);
CREATE INDEX IF NOT EXISTS idx_findings_tags      ON hermia_findings USING gin(tags);
