# Spec: hermia-0ws — Robustness module wiring + `--repeat N` flag

**Bead:** hermia-0ws  
**Priority:** P0 (launch-blocking)  
**Status:** Awaiting tests

---

## 1. What this bead does

Wires the existing `robustness.py` module into the TUI run loop. Adds a `--repeat N` CLI flag so each (model, test_id) pair is evaluated N times in sequence. Stamps `run_index` and `is_cold` on every result row. Computes `cold_warm_delta_tps` and robustness aggregates per (model, test_id) after all N runs complete.

**This bead does NOT change the `run_test` function signature or its single-call semantics.** The repeat loop lives entirely in `screens.py`.

---

## 2. Permitted scope

| File | Change type |
|---|---|
| `src/hermia/app.py` | Add `--repeat N` argparse flag; pass to `EvalApp` and `RunnerScreen` |
| `src/hermia/screens.py` | Inner loop N times per (model, test_id); stamp new fields; post-loop aggregation |
| `src/hermia/robustness.py` | Add `score_rows()` function |
| `src/hermia/export.py` | Add new columns to `_PG_COLUMNS` and `ON CONFLICT` clause |
| `src/hermia/runner.py` | No changes expected; listed as permitted in case of minor adjustments |
| `tests/security/test_robustness.py` | Add tests for `score_rows()` |
| `tests/unit/test_runner.py` | Add tests for new result row fields |

Do **not** touch: `schemas.py`, `metrics.py`, `preflight.py`, `regression.py`, `results.py`, any file in `tests/integration/`.

---

## 3. Interface changes

### 3.1 `app.py` — new `--repeat` flag

```python
parser.add_argument(
    "--repeat",
    type=int,
    default=1,
    metavar="N",
    help="Run each (model, test) pair N times (default: 1)",
)
```

- Valid range: N ≥ 1. Raise `argparse.ArgumentTypeError` if N < 1.
- Pass `repeat=args.repeat` to `EvalApp.__init__`.
- `EvalApp` stores it as `self.repeat` and passes it to `SelectionScreen`, which passes it to `RunnerScreen` when pushing.

### 3.2 `screens.RunnerScreen` — repeat loop

Current (simplified):
```python
for test in tests:
    result = run_test(model, test, sampler)
    # stamp + export
```

New:
```python
for test in tests:
    run_results: list[dict] = []
    for run_index in range(1, repeat + 1):
        result = run_test(model, test, sampler)
        result["run_index"] = run_index
        result["is_cold"] = (run_index == 1)
        result["run_id"] = run_id
        result["run_timestamp"] = datetime.now(UTC).isoformat()
        result["host"] = run_host
        run_results.append(result)
        self.all_results.append(result)
        append_result(result, jsonl_path, csv_path)
        # update TUI progress bar once per run

    # Post-loop: compute aggregates and back-fill onto run_results
    _backfill_aggregates(run_results)
    # Re-write or update records in all_results with aggregated fields
```

**`is_cold` rule:** A `model_first_call` flag (reset to `True` before each model's test loop) tracks whether any `run_test` call has been made for this model in this session. The very first call sets `is_cold=True` and flips the flag to `False`; all subsequent calls — including later tests and all repeats — are `is_cold=False`. Only one row per model per session is ever cold, reflecting the single `prewarm_timed()` load.

### 3.3 Aggregate computation (internal helper in `screens.py`)

```python
def _backfill_aggregates(run_results: list[dict]) -> None:
    """Compute cold_warm_delta_tps and robustness fields; stamp onto each row in-place."""
```

Algorithm:
1. Separate cold row (run_index=1) from warm rows (run_index≥2).
2. `cold_warm_delta_tps`:
   - If len(run_results) == 1: `None`
   - Else: `cold_tps - mean(warm_tps)` where `cold_tps = run_results[0]["tokens_per_sec"]` and `warm_tps = [r["tokens_per_sec"] for r in run_results[1:]]`
   - If cold_tps is 0 (timeout/error) and all warm_tps are 0: `None`
3. Call `robustness.score_rows(run_results)` → `RobustnessResult`.
4. Stamp onto **every row** in `run_results`:
   - `cold_warm_delta_tps`: float or `None`
   - `consistency_pct`: `result.consistency_pct`
   - `pass_count`: `result.pass_count`
   - `robustness_n`: `result.n`

### 3.4 `robustness.py` — new `score_rows()` function

```python
def score_rows(result_rows: list[dict[str, Any]]) -> RobustnessResult:
    """Score a list of already-evaluated result dicts for consistency.

    Uses schema_compliant + failure_reason to classify each row as pass or fail.
    No refusal detection at the result-row level (raw output not available here).
    """
```

Classification rules per row:
- `failure_reason` is non-empty → **fail**
- `schema_compliant == True` and no `failure_reason` → **pass**
- Otherwise → **fail**

Returns a `RobustnessResult` with `refusal_count=0` always (refusal detection requires raw output, unavailable here). Delegates to the existing `run_n_times` internal logic or reimplements the same counting directly — either is acceptable, but **do not modify `run_n_times`**.

Empty list → same zero-result as `run_n_times([])`.

### 3.5 `export.py` — new columns

Add to `_PG_COLUMNS` (after `score`):
```python
"run_index",
"is_cold",
"cold_warm_delta_tps",
"consistency_pct",
"pass_count",
"robustness_n",
```

Update `ON CONFLICT` clause to include `run_index` so multiple runs of the same (run_id, host, model, test_id) don't collide:
```python
"ON CONFLICT (run_id, host, model, test_id, run_index) DO NOTHING"
```

In `push()`, map new fields from each row dict directly (no special transform needed). Missing fields → `None`.

---

## 4. New result row fields — complete data contract

| Field | Type | Present when | Description |
|---|---|---|---|
| `run_index` | `int` | always | Which repetition: 1..N |
| `is_cold` | `bool` | always | True only for run_index==1 |
| `cold_warm_delta_tps` | `float \| None` | always | cold_tps − mean(warm_tps); None if N==1 or all tps==0 |
| `consistency_pct` | `float` | always | Fraction of N runs with majority outcome |
| `pass_count` | `int` | always | Runs where schema_compliant==True |
| `robustness_n` | `int` | always | N (total runs for this pair) |

All six fields must be present on every result row written to JSONL/CSV. Rows from older runs (missing these fields) are handled by existing `export.push()` `row.get(c)` default-None logic — no change needed there.

---

## 5. Edge cases

| Case | Expected behaviour |
|---|---|
| `--repeat 1` (default), first test for model | `run_index=1`, `is_cold=True`, `cold_warm_delta_tps=None` (only one run, no warm baseline), `consistency_pct=1.0`, `robustness_n=1` |
| `--repeat 3`, second+ test for model | `is_cold=False` on all rows; `cold_warm_delta_tps=None` (no cold run in this test) |
| `--repeat 0` or negative | argparse rejects; prints error, exits non-zero |
| First run times out (`tokens_per_sec=0`), subsequent succeed | `cold_warm_delta_tps = 0 - mean(warm_tps)` → negative float |
| All N runs timeout | `cold_warm_delta_tps = None` (all tps==0 sentinel) |
| `score_rows([])` | Returns `RobustnessResult(n=0, pass_count=0, refusal_count=0, consistency_pct=0.0, is_robust=False)` |
| N=2, both pass | `consistency_pct=1.0`, `pass_count=2`, `is_robust=True` |
| N=3, 2 pass 1 fail | `consistency_pct=2/3≈0.667`, `is_robust=False` |

---

## 6. Test matrix

### `tests/security/test_robustness.py` — new tests for `score_rows`

| Test name | Scenario |
|---|---|
| `test_score_rows_empty` | Empty list → zero RobustnessResult |
| `test_score_rows_all_pass` | All rows: `schema_compliant=True`, no `failure_reason` → pass_count==n, consistency_pct==1.0 |
| `test_score_rows_all_fail_schema` | All rows: `schema_compliant=False` → pass_count==0, consistency_pct==1.0 |
| `test_score_rows_all_fail_error` | All rows: `failure_reason="TIMEOUT"` → pass_count==0 |
| `test_score_rows_mixed` | 2 pass, 1 fail → consistency_pct==2/3, is_robust==False |
| `test_score_rows_failure_reason_overrides` | `schema_compliant=True` but `failure_reason` non-empty → counted as fail |
| `test_score_rows_no_refusal_count` | refusal_count always 0 regardless of content |

### `tests/unit/test_runner.py` — new tests for result row shape

| Test name | Scenario |
|---|---|
| `test_run_test_result_has_no_repeat_fields` | `run_test()` return dict does **not** include `run_index`, `is_cold`, `cold_warm_delta_tps` — those are added by screens |

### `tests/unit/test_screens.py` (if present) or inline in `test_runner.py`

| Test name | Scenario |
|---|---|
| `test_backfill_aggregates_single_run` | N=1 → `cold_warm_delta_tps=None`, `consistency_pct` present |
| `test_backfill_aggregates_two_runs_pass_pass` | N=2, both pass → delta = cold_tps − warm_tps, consistency_pct=1.0 |
| `test_backfill_aggregates_all_zero_tps` | All tps=0 → `cold_warm_delta_tps=None` |
| `test_backfill_aggregates_stamps_all_rows` | All rows in the list get identical aggregate fields |
| `test_backfill_aggregates_negative_delta` | cold_tps < warm_tps → delta is negative float (valid) |

### `tests/unit/test_export.py` — column coverage

| Test name | Scenario |
|---|---|
| `test_pg_columns_includes_repeat_fields` | `_PG_COLUMNS` contains all six new fields |
| `test_on_conflict_includes_run_index` | `_INSERT_SQL` string contains `run_index` in ON CONFLICT clause |
| `test_push_dry_run_new_fields` | dry-run with rows containing new fields does not raise |

---

## 7. README note (scope: `README.md`)

Add under the CLI usage section:

```
--repeat N    Run each (model, test) pair N times (default: 1).
              Run 1 is cold (fresh model load); runs 2..N are warm.
              Exports consistency_pct, pass_count, and cold_warm_delta_tps
              alongside every result row.
```

---

## 8. What NOT to do

- Do not change `run_n_times()` — it is stable and tested; `score_rows()` is additive.
- Do not add a progress bar tick for aggregate computation — only tick once per `run_test` call.
- Do not store raw model output on result rows to enable refusal detection — out of scope.
- Do not add a Postgres migration script — column additions go in `_PG_COLUMNS`; the DBA migration is a separate bead.
