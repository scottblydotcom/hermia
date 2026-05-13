# hermia-rpr — Audit Capture: raw_prompt + raw_response

**Priority:** P1 (v0.1 launch-blocking)
**Depends on:** hermia-g8r (merged)
**Permitted scope:** `src/hermia/runner.py`, `src/hermia/export.py`, `scripts/add_audit_columns.sql`, `tests/unit/test_runner.py`, `tests/unit/test_export.py`
**Estimate:** 0.5 days

## Why

`output_preview` stores only 120 chars of model output — enough for the TUI but not for
audit or regression workflows. To enable `--audit` (hermia-aud) and future LLM-judge scoring,
every result row needs the verbatim prompt sent and the verbatim response received, stored
at write-time so nothing is lost.

## What changes

### runner.py — run_test() return dict
Add two new keys:

| Key | Value | On error/timeout |
|---|---|---|
| `raw_prompt` | `test["prompt"]` (the user-turn text) | `test["prompt"]` (always preserved) |
| `raw_response` | Full `output` string (untruncated) | `""` |

`raw_prompt` is the user-turn only. The system prompt is fixed per test ID and available
from the test dataset — no need to duplicate it per row.

### export.py — _PG_COLUMNS
Append `raw_prompt` and `raw_response` to the tuple. Both are TEXT, nullable, stored as-is.

### scripts/add_audit_columns.sql
```sql
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS raw_prompt TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS raw_response TEXT;
```

## Acceptance

1. `run_test()` result dict contains `raw_prompt` equal to `test["prompt"]`
2. `run_test()` result dict contains `raw_response` equal to the full model output string
3. On timeout, `raw_prompt` = test prompt, `raw_response` = `""`
4. On generic error, same as timeout
5. `raw_prompt` and `raw_response` appear in `export._PG_COLUMNS`
6. Migration file exists and is idempotent
