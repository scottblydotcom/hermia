# hermia-aud — Audit Retrieval: `--audit` flag

**Priority:** P1 (v0.1 launch-blocking)
**Depends on:** hermia-rpr (merged)
**Permitted scope:** `src/hermia/runner.py`, `src/hermia/export.py`, `src/hermia/audit.py` (new),
`src/hermia/app.py`, `scripts/add_audit_columns.sql`,
`tests/unit/test_runner.py`, `tests/unit/test_audit.py` (new)
**Estimate:** 0.5 days

## Why

hermia-rpr stores `raw_prompt` + `raw_response` at write-time. hermia-aud surfaces that data at
retrieval time so practitioners can reconstruct and inspect every prompt/response pair without
re-running an eval. The output must be self-contained: a viewer reading a JSONL or HTML audit
report should see the full prompt (system + user) alongside the full response.

## System prompt strategy

The `raw_prompt` field stores the user-turn only. The system prompt is fixed per test ID and
was not stored per row in hermia-rpr (by design). For audit output to be self-contained, we
add `raw_system` alongside `raw_prompt` in `run_test()`. This avoids re-querying the dataset
at retrieval time and makes JSONL audit records portable.

For backward compatibility, the audit reader (`audit.py`) falls back to dataset lookup when
`raw_system` is absent from a row (handles JSONL files written before this change).

## None-guard fix (P3 backlog, pulled in here)

Ollama can return `{"response": null}`. The current code does:

```python
output: str = data.get("response", "")
```

If the key exists with value `null`, `output` is `None`. The `raw_response` field guards with
`(output or "")`, but `output_preview` does `output[:120]` which crashes on `None`.

Fix: normalize early — `output = data.get("response") or ""` — covers both missing key and null.

## What changes

### runner.py — run_test() return dict

Add `raw_system` key. Fix `output` None guard.

| Change | Detail |
|---|---|
| `output = data.get("response") or ""` | Normalize at source; eliminates latent None risk |
| `"raw_system": test["system"] or ""` | Store system prompt per row for self-contained audit |

### export.py — _PG_COLUMNS

Append `raw_system` after `raw_response`.

### scripts/add_audit_columns.sql

Append:
```sql
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS raw_system TEXT;
```

### src/hermia/audit.py (new)

Core audit retrieval logic. Public API:

```python
def run_audit(source: Path, fmt: str = "jsonl", output: Path | None = None) -> None
```

- `source`: JSONL file or directory. Directory mode reads all `eval_*.jsonl` in order.
- `fmt`: `"jsonl"` (default) or `"html"`.
- `output`: write to file if given, else stdout.

Internal helpers:
- `_load_system_prompts() -> dict[str, str]` — loads dataset, returns `{test_id: system}`
- `_iter_audit_rows(source: Path) -> Iterator[dict]` — yields rows from file or directory
- `_enrich(rows: list[dict]) -> list[dict]` — adds `raw_system` to rows that lack it
- `render_jsonl(rows: list[dict]) -> str` — one JSON object per line
- `render_html(rows: list[dict]) -> str` — full HTML report with prompt/response cards

### app.py — `--audit` flag

```
hermia --audit [FILE]                    # audit specific file, or all in results/ if omitted
hermia --audit --audit-format html       # HTML output
hermia --audit results/eval_x.jsonl --audit-format html > report.html
```

Implemented with `nargs="?"`:
```python
parser.add_argument("--audit", nargs="?", const=True, metavar="FILE")
parser.add_argument("--audit-format", choices=["jsonl", "html"], default="jsonl")
```

`--audit` is mutually exclusive at runtime with `--fleet` (both exit without starting the TUI).
`--audit` takes priority: if both are given, audit runs and `--fleet` is ignored.

## Acceptance

1. `run_test()` result dict contains `raw_system` equal to `test["system"]`
2. `output = data.get("response") or ""` normalizes None at source
3. `raw_system` appears in `export._PG_COLUMNS`
4. `scripts/add_audit_columns.sql` adds `raw_system` column idempotently
5. `hermia --audit` reads all `eval_*.jsonl` in `results/`, emits JSONL to stdout
6. `hermia --audit FILE` reads a specific JSONL file
7. `hermia --audit --audit-format html` emits a valid HTML document
8. HTML output contains system prompt, user prompt, and full response for each row
9. Rows missing `raw_system` are enriched via dataset lookup (backward compat)
10. `test_run_test_response_null_coerced_to_empty_string` — Ollama `{"response": null}` does not crash; `raw_response == ""`
11. `test_run_test_has_raw_system` — `raw_system` key present and equal to `test["system"]`
