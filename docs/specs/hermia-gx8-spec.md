# Spec: hermia-gx8 — Determinism / Stability Harness

**Bead:** hermia-gx8  
**Status:** P0 launch-blocking  
**Depends on:** hermia-w59 ✅ (fake-Ollama fixture, merged)

---

## Problem

"Trust our scores" requires "the scores are stable." Without a determinism test, a silent regression in the scoring path — a schema checker change, a JSON parsing tweak, a field rename — could flip results without any CI signal. This test is the credibility guarantee: same inputs always produce the same scoring outputs.

---

## Design

Call `run_test` twice with identical inputs against the `fake_ollama` fixture. Compare result dicts field-by-field. Scoring fields must be bytewise identical. Timing fields are excluded or computed-check only.

### Stable fields (bytewise identical both runs)

These must match exactly:

- `model`
- `test_id`
- `dimension`
- `frameworks`
- `failure_reason`
- `json_valid`
- `schema_compliant`
- `tokens`
- `output_preview`
- `peak_cpu_pct`, `peak_ram_used_gb`, `peak_gpu_pct`, `peak_vram_used_gb`

Note: peak_* fields are stable because the mock sampler always returns fixed values.

### Timing fields (excluded / computed-check only)

- `elapsed_sec` — excluded from equality check (wall-clock jitter)
- `tokens_per_sec` — assert > 0 when tokens returned; stability not assertable against mock server

### Fields not present in runner output

- `run_id`, `run_timestamp` — stamped by `screens.py`, not `runner.run_test`; not in scope here

---

## Test File

New file: `tests/integration/test_determinism.py`

Uses existing fixtures: `fake_ollama` (from `tests/integration/conftest.py`), `monkeypatch`.

---

## Test Matrix

### T1 — Scoring fields are bytewise stable across two runs

**Given:** fake server returns canned success response (DEFAULT_GENERATE from conftest)  
**When:** `run_test("fake-model", test, sampler)` called twice with identical inputs  
**Then:** all stable fields are equal between run1 and run2

```python
STABLE_FIELDS = [
    "model", "test_id", "dimension", "frameworks",
    "failure_reason", "json_valid", "schema_compliant",
    "tokens", "output_preview",
    "peak_cpu_pct", "peak_ram_used_gb", "peak_gpu_pct", "peak_vram_used_gb",
]
for field in STABLE_FIELDS:
    assert run1[field] == run2[field], f"field '{field}' not deterministic"
```

### T2 — tokens_per_sec is computed (non-zero when tokens returned)

**Given:** same setup as T1  
**When:** `tokens_per_sec` extracted from the result  
**Then:** `result["tokens"] > 0` and `result["tokens_per_sec"] > 0`

Note: ±5% stability is only meaningful against a real model under load. Against a
fake HTTP server in a Python thread, OS scheduling noise produces ~20%+ variance.
The meaningful invariant is that the field is computed, not that it's stable.

### T3 — Failure-path fields are stable (error result)

**Given:** fake server returns HTTP 500  
**When:** `run_test` called twice  
**Then:** `failure_reason`, `json_valid`, `schema_compliant`, `tokens` are identical between runs

This ensures error paths are also deterministic — not just happy path.

### T4 — Test completes in under 2 seconds total

**Given:** T1 + T2 setup (two `run_test` calls)  
**When:** wall time measured  
**Then:** total elapsed < 2.0s

Use `time.monotonic()` around both calls.

---

## Implementation Notes for Fleet

### Sampler

Use `_mock_sampler()` pattern from `tests/unit/test_runner.py` (same pattern already in `tests/integration/test_fake_ollama.py` — copy it here, don't import across test files).

### Test case

Use `TOOL_CALLING_TEST` — same dict as in `test_fake_ollama.py`. Define it locally in this file (don't import from the other test file).

### tokens_per_sec check

```python
result = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
assert result["tokens"] > 0
assert result["tokens_per_sec"] > 0
```

### T4 timing

```python
import time
t0 = time.monotonic()
result1 = run_test(...)
result2 = run_test(...)
assert time.monotonic() - t0 < 2.0
```

Keep T1/T2/T3/T4 as separate test functions. Do not collapse into one mega-test.

---

## What NOT to do

- Do not import `TOOL_CALLING_TEST` or `_mock_sampler` from `test_fake_ollama.py` — test files should not depend on each other
- Do not use `scope="function"` on `fake_ollama` — it's session-scoped, keep it that way
- Do not assert `elapsed_sec` equality — it will flap
- Do not add new dependencies

---

## Acceptance Checklist

- [ ] `tests/integration/test_determinism.py` created
- [ ] T1–T4 all passing
- [ ] Test suite completes in < 2s (T4 asserts this)
- [ ] `ruff` and `mypy` clean
- [ ] `runner.py` `run_test` path covered (lines 52–69 are `prewarm_timed`, not exercised by these tests)
