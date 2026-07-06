# Reproducibility / Self-Divergence Floor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-trial-group `reproducibility` block to every fleet result row, computed over the existing `--repeat N` runs, measuring how consistently a fixed (model, stack, test) reproduces its output and how reliably it passes.

**Architecture:** Extract the grader's fence-stripping into a shared `hermia/normalize.py` so canonical comparison uses the exact same transform the grader uses. Add `compute_reproducibility(run_results) -> ReproducibilityResult` next to `score_rows` in `robustness.py`. Wire it into `fleet.py:_run_host_eval` right after the existing `score_rows` call, stamping `row["reproducibility"] = asdict(repro)` on every row in the trial group. Purely additive to the result schema.

**Tech Stack:** Python 3.14, pytest, `unittest.mock`, stdlib `statistics.pstdev` / `collections.Counter`. No new dependencies.

---

## Terminology

- **trial** — one execution (one prompt → one response → one grade) = one JSONL result row.
- **trial group** — all trials sharing the same `(model, test)` on one host; `--repeat N` produces one group of N trials. Reproducibility is measured over the group.

## File Map

| File | Change |
|---|---|
| `src/hermia/normalize.py` | **Create.** Pure `strip_fences(text)` moved verbatim from `runner._strip_fences` (renamed public). |
| `src/hermia/runner.py` | Remove `def _strip_fences` + `import re`; import `strip_fences` from `normalize`; update the one internal call site (line ~352). |
| `src/hermia/corpus_audit/mining.py` | Re-point import: `from hermia.normalize import strip_fences`; update call site. |
| `src/hermia/corpus_audit/confusion.py` | Re-point import: `from hermia.normalize import strip_fences`; update call site. |
| `src/hermia/robustness.py` | Add `ReproducibilityResult` dataclass + `compute_reproducibility()` + `_modal_match_rate()` helper; import `strip_fences`, `pstdev`. |
| `src/hermia/fleet.py` | In `_run_host_eval`: import `compute_reproducibility` + `asdict`; call after `score_rows`; stamp `row["reproducibility"]`. |
| `tests/unit/test_normalize.py` | **Create.** The 6 fence-stripping tests moved from `test_runner.py` (renamed to `strip_fences`). |
| `tests/unit/test_runner.py` | Remove the 6 `_strip_fences` tests + the `_strip_fences` import (now in `test_normalize.py`). |
| `tests/unit/test_robustness.py` | Add the `compute_reproducibility` test section. |
| `tests/unit/test_fleet.py` | Add a repeat-loop test asserting the stamped `reproducibility` block. |

## Spec correction (note for reviewers)

The spec ([2026-06-15-reproducibility-floor-design.md](../specs/2026-06-15-reproducibility-floor-design.md)) said the `_strip_fences` extraction touches "one import site in runner.py." Reality: **three** production importers (`runner`, `corpus_audit/mining`, `corpus_audit/confusion`) plus 6 tests. Still low-risk (a pure function move), just more sites. This plan updates all of them. The design is unchanged.

## The "valid trial" predicate (locked)

From `run_test`, `raw_response` is `""` exactly when the trial produced no output — `TIMEOUT`, `OLLAMA_ERROR`/`API_ERROR`/`ERROR`, or `EMPTY_RESPONSE`. Rows that produced output but failed grading (`SCHEMA_FAIL`, `JSON_PARSE_ERROR`) keep their (bad) output in `raw_response`. So:

- **valid trial** (counts toward exact-match) ⟺ `bool(row.get("raw_response"))` is truthy.
- **pass** (counts toward pass-rate) ⟺ `row.get("schema_compliant") is True and not row.get("failure_reason")`, over **all** N.

---

## Task 1: Extract `strip_fences` into a shared `normalize.py`

**Files:**
- Create: `src/hermia/normalize.py`
- Create: `tests/unit/test_normalize.py`
- Modify: `src/hermia/runner.py`, `src/hermia/corpus_audit/mining.py`, `src/hermia/corpus_audit/confusion.py`, `tests/unit/test_runner.py`

This is a behavior-preserving refactor. The existing tests are the safety net; no new behavior is added.

- [ ] **Step 1: Create `src/hermia/normalize.py`**

```python
"""Output normalization shared by the grader and reproducibility scoring.

`strip_fences` MUST stay the single source of truth: the eval grader uses it
to extract JSON before checking schema, and reproducibility scoring uses it to
compute canonical-output equality. They must apply the identical transform or
`exact_match_rate_canonical` would diverge from what the grader actually saw.
"""

import re


def strip_fences(text: str) -> str:
    """Extract content from markdown code fences, ignoring surrounding prose."""
    text = text.strip()
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text
```

- [ ] **Step 2: Create `tests/unit/test_normalize.py` with the moved tests**

```python
"""Unit tests for hermia.normalize — shared output normalization."""

from hermia.normalize import strip_fences


def test_strip_fences_json_block() -> None:
    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_plain_block() -> None:
    assert strip_fences('```\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_no_fences() -> None:
    raw = '{"a": 1}'
    assert strip_fences(raw) == raw


def test_strip_fences_whitespace_only() -> None:
    assert strip_fences("   ") == ""


def test_strip_fences_prose_before_block() -> None:
    assert strip_fences('Here is the JSON:\n```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_prose_after_block() -> None:
    assert strip_fences('```json\n{"a": 1}\n```\nHope that helps!') == '{"a": 1}'
```

- [ ] **Step 3: Run the new normalize tests (verify they pass against the new module)**

```bash
cd ~/Git/hermia && source .venv/bin/activate
pytest tests/unit/test_normalize.py -v -p no:cacheprovider --no-cov
```

Expected: 6 PASS.

- [ ] **Step 4: Update `src/hermia/runner.py`**

Remove `import re` (line 5) — it is used *only* by `_strip_fences`. Remove the `def _strip_fences` block (lines 33–39). Add to the import block (after `from hermia.metrics import ...`):

```python
from hermia.normalize import strip_fences
```

Change the one internal call site (≈ line 352) from:

```python
        cleaned = _strip_fences(output)
```

to:

```python
        cleaned = strip_fences(output)
```

- [ ] **Step 5: Update the two corpus_audit importers**

In `src/hermia/corpus_audit/mining.py`, change `from hermia.runner import _strip_fences` to:

```python
from hermia.normalize import strip_fences
```

and the call site `parsed = json.loads(_strip_fences(raw))` to:

```python
        parsed = json.loads(strip_fences(raw))
```

In `src/hermia/corpus_audit/confusion.py`, change `from hermia.runner import _strip_fences` to:

```python
from hermia.normalize import strip_fences
```

and the call site `parsed = json.loads(_strip_fences(response))` to:

```python
            parsed = json.loads(strip_fences(response))
```

- [ ] **Step 6: Remove the moved tests from `tests/unit/test_runner.py`**

Remove `_strip_fences` from the `from hermia.runner import (...)` block (line ~13). Delete the 6 `test_strip_fences_*` functions (lines ~766–788) and their section comment (line ~762 `# hermia-qc: _strip_fences, ...`) — they now live in `test_normalize.py`.

- [ ] **Step 7: Run the full suite to prove the refactor is behavior-preserving**

```bash
pytest -p no:cacheprovider --no-cov -q
```

Expected: all pass (same count as before, the 6 strip-fences tests just relocated). If `ruff` flags an unused `import re` in runner, it means Step 4 missed the removal — fix it.

- [ ] **Step 8: Commit**

```bash
git add src/hermia/normalize.py tests/unit/test_normalize.py src/hermia/runner.py \
        src/hermia/corpus_audit/mining.py src/hermia/corpus_audit/confusion.py \
        tests/unit/test_runner.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "refactor: extract strip_fences into shared hermia/normalize.py

Single source of truth for fence-stripping, shared by the grader and the
upcoming reproducibility canonical-match. Behavior-preserving move; updates
all 3 production importers (runner, corpus_audit/mining, corpus_audit/confusion)
and relocates the 6 tests to test_normalize.py."
```

---

## Task 2: `compute_reproducibility` in `robustness.py`

**Files:**
- Modify: `src/hermia/robustness.py`
- Test: `tests/unit/test_robustness.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_robustness.py` (after the `score_rows` section). Note the import addition at the top of the file: extend the existing `from hermia.robustness import (...)` block to include `ReproducibilityResult` and `compute_reproducibility`.

```python
# ---------------------------------------------------------------------------
# compute_reproducibility
# ---------------------------------------------------------------------------

def _trial(
    raw_response: str = '{"action":"read"}',
    schema_compliant: bool = True,
    failure_reason: str = "",
) -> dict:
    return {
        "raw_response": raw_response,
        "schema_compliant": schema_compliant,
        "failure_reason": failure_reason,
    }


def test_compute_reproducibility_empty() -> None:
    r = compute_reproducibility([])
    assert r.n_repeats == 0
    assert r.n_valid == 0
    assert r.exact_match_rate_raw is None
    assert r.exact_match_rate_canonical is None
    assert r.pass_rate_mean == 0.0
    assert r.pass_rate_stddev == 0.0


def test_compute_reproducibility_all_identical_pass() -> None:
    rows = [_trial() for _ in range(10)]
    r = compute_reproducibility(rows)
    assert r.n_repeats == 10
    assert r.n_valid == 10
    assert r.exact_match_rate_raw == pytest.approx(1.0)
    assert r.exact_match_rate_canonical == pytest.approx(1.0)
    assert r.pass_rate_mean == pytest.approx(1.0)
    assert r.pass_rate_stddev == pytest.approx(0.0)


def test_compute_reproducibility_modal_raw_rate() -> None:
    # 7 identical, 3 different → modal raw rate = 0.7
    rows = [_trial('{"x":1}') for _ in range(7)] + [_trial('{"x":2}') for _ in range(3)]
    r = compute_reproducibility(rows)
    assert r.exact_match_rate_raw == pytest.approx(0.7)


def test_compute_reproducibility_canonical_ignores_fences_and_whitespace() -> None:
    # Same JSON, one fenced one bare, one with surrounding whitespace.
    # raw differs (fences/whitespace) but canonical is identical.
    rows = [
        _trial('{"x":1}'),
        _trial('```json\n{"x":1}\n```'),
        _trial('   {"x":1}   '),
    ]
    r = compute_reproducibility(rows)
    assert r.exact_match_rate_raw == pytest.approx(1 / 3)   # all three raw strings differ
    assert r.exact_match_rate_canonical == pytest.approx(1.0)  # all canonicalize equal


def test_compute_reproducibility_all_errored_is_null_not_one() -> None:
    """The poison case: all trials timed out (raw_response=''). Exact-match must be
    null (not 1.0 from empty strings matching), n_valid=0, pass_rate=0."""
    rows = [_trial(raw_response="", schema_compliant=False, failure_reason="TIMEOUT: 90s")
            for _ in range(5)]
    r = compute_reproducibility(rows)
    assert r.n_repeats == 5
    assert r.n_valid == 0
    assert r.exact_match_rate_raw is None
    assert r.exact_match_rate_canonical is None
    assert r.pass_rate_mean == pytest.approx(0.0)


def test_compute_reproducibility_partial_error_excludes_invalid_from_exact_match() -> None:
    """3 valid identical + 2 timeouts: exact-match over the 3 valid (=1.0); n_valid=3;
    pass_rate over all 5 (=0.6)."""
    rows = (
        [_trial('{"x":1}') for _ in range(3)]
        + [_trial(raw_response="", schema_compliant=False, failure_reason="TIMEOUT: 90s")
           for _ in range(2)]
    )
    r = compute_reproducibility(rows)
    assert r.n_repeats == 5
    assert r.n_valid == 3
    assert r.exact_match_rate_raw == pytest.approx(1.0)
    assert r.pass_rate_mean == pytest.approx(0.6)


def test_compute_reproducibility_schema_fail_row_is_valid_for_exact_match() -> None:
    """A SCHEMA_FAIL trial produced output (bad but present) → counts as valid for
    exact-match, but NOT as a pass."""
    rows = [_trial('{"wrong":1}', schema_compliant=False, failure_reason="SCHEMA_FAIL")
            for _ in range(4)]
    r = compute_reproducibility(rows)
    assert r.n_valid == 4
    assert r.exact_match_rate_raw == pytest.approx(1.0)  # all 4 bad outputs identical
    assert r.pass_rate_mean == pytest.approx(0.0)        # none passed


def test_compute_reproducibility_pass_stddev_matches_formula() -> None:
    # 6 pass, 4 fail (fails still produced output) → mean 0.6, pstdev = sqrt(.6*.4)
    import math
    rows = (
        [_trial('{"x":1}') for _ in range(6)]
        + [_trial('{"x":1}', schema_compliant=False, failure_reason="SCHEMA_FAIL")
           for _ in range(4)]
    )
    r = compute_reproducibility(rows)
    assert r.pass_rate_mean == pytest.approx(0.6)
    assert r.pass_rate_stddev == pytest.approx(math.sqrt(0.6 * 0.4))


def test_compute_reproducibility_single_trial() -> None:
    r = compute_reproducibility([_trial('{"x":1}')])
    assert r.n_repeats == 1
    assert r.n_valid == 1
    assert r.exact_match_rate_raw == pytest.approx(1.0)
    assert r.pass_rate_mean == pytest.approx(1.0)
    assert r.pass_rate_stddev == pytest.approx(0.0)


def test_compute_reproducibility_asdict_matches_schema() -> None:
    """asdict() of the result must equal the documented 6-field schema exactly."""
    from dataclasses import asdict
    r = compute_reproducibility([_trial('{"x":1}') for _ in range(3)])
    d = asdict(r)
    assert set(d.keys()) == {
        "n_repeats", "n_valid",
        "exact_match_rate_raw", "exact_match_rate_canonical",
        "pass_rate_mean", "pass_rate_stddev",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_robustness.py -k compute_reproducibility -v -p no:cacheprovider --no-cov
```

Expected: ImportError / all FAIL (`compute_reproducibility` not defined).

- [ ] **Step 3: Implement in `src/hermia/robustness.py`**

Extend the imports at the top of the file:

```python
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from statistics import pstdev
from typing import Any

from hermia.normalize import strip_fences
from hermia.schemas import _is_refusal
```

Add, after the `RobustnessResult` dataclass:

```python
@dataclass(frozen=True)
class ReproducibilityResult:
    n_repeats: int
    n_valid: int
    exact_match_rate_raw: float | None
    exact_match_rate_canonical: float | None
    pass_rate_mean: float
    pass_rate_stddev: float


def _modal_match_rate(values: list[str]) -> float:
    """Fraction of values equal to the single most common value.

    `values` must be non-empty. This is the self-divergence floor: how reliably
    the group reproduces its dominant output (O(n), vs O(n^2) all-pairs).
    """
    _, modal_count = Counter(values).most_common(1)[0]
    return modal_count / len(values)


def compute_reproducibility(run_results: list[dict[str, Any]]) -> ReproducibilityResult:
    """Self-divergence floor over one trial group (the N repeats of a model+test).

    Exact-match rates are computed over VALID trials only (those that produced
    output, i.e. raw_response is non-empty); a group where everything errored
    yields None, never a spurious 1.0 from empty strings matching. Pass-rate is
    over ALL N trials, because a timeout is an end-to-end failure.
    """
    n_repeats = len(run_results)
    if n_repeats == 0:
        return ReproducibilityResult(
            n_repeats=0, n_valid=0,
            exact_match_rate_raw=None, exact_match_rate_canonical=None,
            pass_rate_mean=0.0, pass_rate_stddev=0.0,
        )

    # A trial is valid for exact-match if it produced output. TIMEOUT /
    # transport-error / EMPTY_RESPONSE rows carry raw_response="".
    valid_raw = [str(r.get("raw_response", "")) for r in run_results if r.get("raw_response")]
    n_valid = len(valid_raw)

    if n_valid > 0:
        exact_raw: float | None = _modal_match_rate(valid_raw)
        exact_canonical: float | None = _modal_match_rate([strip_fences(v) for v in valid_raw])
    else:
        exact_raw = None
        exact_canonical = None

    # Pass = compliant output, over ALL trials (timeout counts as a failure).
    passes = [
        1.0 if (r.get("schema_compliant") is True and not r.get("failure_reason")) else 0.0
        for r in run_results
    ]
    pass_rate_mean = sum(passes) / n_repeats
    pass_rate_stddev = pstdev(passes)  # pstdev([x]) == 0.0; n_repeats >= 1 guaranteed here

    return ReproducibilityResult(
        n_repeats=n_repeats,
        n_valid=n_valid,
        exact_match_rate_raw=exact_raw,
        exact_match_rate_canonical=exact_canonical,
        pass_rate_mean=pass_rate_mean,
        pass_rate_stddev=pass_rate_stddev,
    )
```

- [ ] **Step 4: Run the compute_reproducibility tests**

```bash
pytest tests/unit/test_robustness.py -k compute_reproducibility -v -p no:cacheprovider --no-cov
```

Expected: all PASS (10 tests).

- [ ] **Step 5: Run the full robustness suite (regression)**

```bash
pytest tests/unit/test_robustness.py -v -p no:cacheprovider --no-cov
```

Expected: all pass (existing `run_n_times` / `score_rows` untouched).

- [ ] **Step 6: Commit**

```bash
git add src/hermia/robustness.py tests/unit/test_robustness.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(robustness): add compute_reproducibility self-divergence floor

Per-trial-group block: n_repeats, n_valid, exact_match_rate_raw/canonical
(modal-match over valid trials, null if all errored), pass_rate_mean/stddev
(over all N). Canonical match reuses the grader's strip_fences for parity."
```

---

## Task 3: Wire `compute_reproducibility` into the fleet repeat loop

**Files:**
- Modify: `src/hermia/fleet.py`
- Test: `tests/unit/test_fleet.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_fleet.py`, in the repeat-loop section (after `test_run_host_eval_aggregates_are_per_cell_not_global`):

```python
def test_run_host_eval_stamps_reproducibility_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every row in a trial group carries an identical reproducibility block;
    3 identical passing trials → exact_match_rate_raw=1.0, n_valid=3, pass=1.0."""
    import hermia.fleet as fleet
    from hermia.results import load_jsonl, open_run

    def fake_run(model, test, sampler, **kw):
        return {
            "model": model, "test_id": test["id"],
            "schema_compliant": True, "failure_reason": "",
            "raw_response": '{"action":"read"}',
            "elapsed_sec": 0.1, "tokens_per_sec": 1.0,
        }

    monkeypatch.setattr("hermia.runner.run_test", fake_run, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr(
        "hermia.runner.get_available_models",
        lambda host=None, headers=None: [{"name": "m1"}],
        raising=False,
    )

    jsonl, csv = open_run(tmp_path)
    fleet._run_host_eval(
        {"name": "node1", "host": "http://h1:11434"},
        repeat=3, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )
    rows = load_jsonl(jsonl)

    assert len(rows) == 3
    for row in rows:
        repro = row["reproducibility"]
        assert repro["n_repeats"] == 3
        assert repro["n_valid"] == 3
        assert repro["exact_match_rate_raw"] == 1.0
        assert repro["exact_match_rate_canonical"] == 1.0
        assert repro["pass_rate_mean"] == 1.0
        assert repro["pass_rate_stddev"] == 0.0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/unit/test_fleet.py::test_run_host_eval_stamps_reproducibility_block \
       -v -p no:cacheprovider --no-cov
```

Expected: FAIL with `KeyError: 'reproducibility'`.

- [ ] **Step 3: Update the import line in `_run_host_eval`**

In `src/hermia/fleet.py`, change the local import (line ~126) from:

```python
    from hermia.robustness import score_rows
```

to:

```python
    from dataclasses import asdict

    from hermia.robustness import compute_reproducibility, score_rows
```

- [ ] **Step 4: Add the compute + stamp in the repeat loop**

In `_run_host_eval`, the block that currently reads (lines ~231–237):

```python
            # Compute robustness aggregates across all repeat runs for this pair
            rob = score_rows(run_results)
            for result in run_results:
                result["consistency_pct"] = rob.consistency_pct
                result["pass_count"] = rob.pass_count
                result["robustness_n"] = rob.n
                append_result(result, jsonl_path, csv_path)
```

becomes:

```python
            # Compute robustness + reproducibility aggregates across all repeat
            # runs for this (model, test) trial group, then stamp on every row.
            rob = score_rows(run_results)
            repro = compute_reproducibility(run_results)
            for result in run_results:
                result["consistency_pct"] = rob.consistency_pct
                result["pass_count"] = rob.pass_count
                result["robustness_n"] = rob.n
                result["reproducibility"] = asdict(repro)
                append_result(result, jsonl_path, csv_path)
```

- [ ] **Step 5: Run the new fleet test**

```bash
pytest tests/unit/test_fleet.py::test_run_host_eval_stamps_reproducibility_block \
       -v -p no:cacheprovider --no-cov
```

Expected: PASS.

- [ ] **Step 6: Run the full fleet suite (regression)**

```bash
pytest tests/unit/test_fleet.py -v -p no:cacheprovider --no-cov
```

Expected: all pass. The pre-existing repeat-loop tests still pass — they don't assert absence of `reproducibility`, and rows lacking `raw_response` simply yield `n_valid=0` / null rates without error.

- [ ] **Step 7: Commit**

```bash
git add src/hermia/fleet.py tests/unit/test_fleet.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(fleet): stamp reproducibility block on every trial-group row

After the existing score_rows pass, compute_reproducibility over the same N
repeats and denormalize asdict(repro) onto each row so every row is
self-describing for downstream JSONL consumers."
```

---

## Task 4: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

```bash
cd ~/Git/hermia && source .venv/bin/activate
pytest -p no:cacheprovider --no-cov -q
```

Expected: all pass. Baseline before this slice was 1469 (1464 + 5 coverage tests already committed); this slice adds 6 (normalize, relocated) + 10 (reproducibility) + 1 (fleet) and removes 6 from test_runner → net +11, so ~1480. Confirm zero failures.

- [ ] **Step 2: Lint/type check (matches CI gates)**

```bash
ruff check src/ tests/
mypy src/hermia/normalize.py src/hermia/robustness.py src/hermia/fleet.py src/hermia/runner.py
```

Expected: clean. Watch for: unused `import re` in `runner.py` (Task 1 Step 4), and `float | None` handling in `ReproducibilityResult` (mypy must see the None branches).

- [ ] **Step 3: Confirm no stray `_strip_fences` references remain**

```bash
grep -rn "_strip_fences" src/ tests/ --include="*.py" | grep -v __pycache__
```

Expected: **no output** (every reference re-pointed to `strip_fences`).

---

## Self-Review

### Spec coverage check

| Spec requirement | Task |
|---|---|
| `reproducibility` block with 6 fields | Task 2 (`ReproducibilityResult` + `compute_reproducibility`) |
| Exact-match over valid trials only; null if `n_valid==0` | Task 2 (Step 3 logic + poison-case test) |
| Pass-rate over all N (timeout = fail) | Task 2 (Step 3 `passes` over all rows) |
| Canonical match uses the grader's exact transform | Task 1 (shared `normalize.strip_fences`) + Task 2 import |
| Denormalize block onto every trial-group row | Task 3 (`asdict(repro)` stamped per row) |
| N = existing `--repeat` flag (no new knob) | Inherent — no CLI/YAML change in any task |
| `_strip_fences` extraction (the one production refactor) | Task 1 (all 3 importers + tests) |
| Per-trial `failure_reason`/`raw_response` preserved | Inherent — rows are unmodified except the added key |
| Backward compatibility: purely additive key | Task 3 + Task 4 Step 1 (suite green) |

### Out of scope (recorded in spec, not implemented here)

- Semantic/functional-equivalence rung (`8 = 7+1`) — divergence-ladder future work.
- The A/B cross-stack proof experiment (scope item #5) that consumes this floor.
- Optional precomputed end-to-end "overall identical-output rate" field.
- TUI/screens.py reproducibility display — fleet path only; the TUI repeat loop (`screens.py:363`) is a separate surface not in this slice.

### Placeholder scan

None. Every code step shows complete code; every command shows expected output.

### Type consistency

- `ReproducibilityResult.exact_match_rate_raw: float | None` — set to `_modal_match_rate(...)` (float) or `None`; both branches present in Task 2 Step 3. ✓
- `compute_reproducibility(run_results: list[dict[str, Any]])` — matches how `score_rows` is called in `fleet.py` (same `run_results` list). ✓
- `_modal_match_rate(values: list[str]) -> float` — called only inside the `n_valid > 0` guard, so `values` is non-empty as its docstring requires. ✓
- `asdict(repro)` in `fleet.py` — `repro` is a `@dataclass`, so `asdict` yields the 6-field dict asserted by `test_compute_reproducibility_asdict_matches_schema`. ✓
- `strip_fences` signature identical pre/post move (`(text: str) -> str`) — all 4 call sites unchanged in arity. ✓
- `pstdev(passes)` — `passes` is `list[float]`, non-empty when reached (n_repeats ≥ 1). ✓
```
