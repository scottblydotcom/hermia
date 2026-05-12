-- Create the hermia_results base table.
-- Idempotent: safe to run against an existing database.
-- After running this, run add_framework_columns.sql to add framework taxonomy indexes.

CREATE TABLE IF NOT EXISTS hermia_results (
    run_id              TEXT        NOT NULL,
    run_timestamp       TIMESTAMPTZ,
    host                TEXT        NOT NULL,
    model               TEXT        NOT NULL,
    test_id             TEXT        NOT NULL,
    dimension           TEXT,
    json_valid          BOOLEAN,
    schema_compliant    BOOLEAN,
    failure_reason      TEXT,
    tokens              INTEGER,
    elapsed_sec         NUMERIC,
    tokens_per_sec      NUMERIC,
    output_preview      TEXT,
    peak_cpu_pct        NUMERIC,
    peak_ram_used_gb    NUMERIC,
    peak_gpu_pct        NUMERIC,
    peak_vram_used_gb   NUMERIC,
    framework_owasp     TEXT[]      DEFAULT '{}',
    framework_mitre     TEXT[]      DEFAULT '{}',
    framework_maestro   TEXT[]      DEFAULT '{}',
    framework_nist      TEXT[]      DEFAULT '{}',
    score               INTEGER,
    run_index           INTEGER,
    is_cold             BOOLEAN,
    cold_warm_delta_tps NUMERIC,
    consistency_pct     NUMERIC,
    pass_count          INTEGER,
    robustness_n        INTEGER,
    judge_score         INTEGER,
    judge_reasoning     TEXT,
    UNIQUE (run_id, host, model, test_id, run_index)
);
