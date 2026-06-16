# Topology Locality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the topology bug where `run_test()` infers `is_local` from the host URL — which is wrong for fleet entries that reach remote nodes via loopback-port SSH tunnels — by adding a declared `locality` parameter, and wire `fleet.py` to pass `locality="remote"` for every fleet host.

**Architecture:** `run_test()` gains a keyword-only `locality: str | None = None` parameter. When `None`, it falls back to the existing `detect_mode(_host)` heuristic (preserving today's behavior for the TUI standalone path). When set, `locality="local"` or `"remote"` overrides the heuristic. `fleet.py::_run_host_eval` explicitly passes `locality="remote"` on every `run_test` call. `detect_mode()` itself is unchanged. No YAML schema change.

**Tech Stack:** Python 3.14, pytest, ruff, mypy. Venv at `~/Git/hermia/.venv`. Commits use `PRE_COMMIT_ALLOW_NO_CONFIG=1`.

**Spec:** `docs/superpowers/specs/2026-06-15-topology-locality-design.md` (commit `0625e63` on `dev`).

**Branch:** `feat/v0.2-topology-locality` off `dev` (at `dda9293` or later).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/hermia/runner.py` | Modify | Add `locality` kwarg to `run_test()`, validate, derive `is_local` from declaration-or-fallback |
| `src/hermia/fleet.py` | Modify | One-line addition: pass `locality="remote"` in `_run_host_eval`'s `run_test` call |
| `tests/unit/test_runner.py` | Modify | Add 5 unit tests covering the locality contract |
| `tests/unit/test_fleet.py` | Modify | Add 1 test asserting `_run_host_eval` passes `locality="remote"` |

No new files. No new modules. `detect_mode()`, transport layer, result row shape, export columns, YAML parser — all untouched.

---

## Task 1: Add `locality` parameter to `run_test()` (TDD)

**Files:**
- Modify: `src/hermia/runner.py:272-407` (the `run_test` function)
- Test: `tests/unit/test_runner.py` (append 5 new tests)

### Setup

- [ ] **Step 1.1: Create the branch off dev**

```bash
cd ~/Git/hermia
git fetch origin
git checkout dev
git pull origin dev
git checkout -b feat/v0.2-topology-locality
```

### First test — invalid value raises

- [ ] **Step 1.2: Append failing test for invalid locality value**

Append to `tests/unit/test_runner.py` (after the `detect_mode` test block ending around line 422):

```python
# ── run_test locality parameter ───────────────────────────────────────────────

def _stub_test_dict() -> dict:
    """Minimal valid test dict for run_test() unit tests."""
    return {
        "id": "locality-stub",
        "dimension": "stub",
        "system": "you are a stub",
        "prompt": "stub prompt",
        "frameworks": {},
    }


def _stub_transport(text: str = '{"ok": true}', tokens: int = 4, elapsed: float = 0.01):
    """A transport double that returns a canned response without network I/O."""
    from unittest.mock import MagicMock
    t = MagicMock()
    t.is_api_mode = False
    resp = MagicMock()
    resp.text = text
    resp.tokens = tokens
    resp.elapsed_sec = elapsed
    resp.orchestration = "stub"
    resp.orchestration_version = None
    return t, resp


def test_run_test_locality_invalid_value_raises() -> None:
    from unittest.mock import MagicMock
    from hermia.runner import run_test
    sampler = MagicMock()
    transport, _ = _stub_transport()
    with pytest.raises(ValueError, match="locality"):
        run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://localhost:11434", transport=transport,
            locality="weird",
        )
```

- [ ] **Step 1.3: Run the test — confirm it fails**

```bash
cd ~/Git/hermia
.venv/bin/pytest tests/unit/test_runner.py::test_run_test_locality_invalid_value_raises -v -p no:cacheprovider --no-cov
```

Expected: FAIL with `TypeError: run_test() got an unexpected keyword argument 'locality'`.

### Minimal implementation — add param + validation

- [ ] **Step 1.4: Add `locality` keyword-only param + validation to `run_test()`**

In `src/hermia/runner.py`, modify the `run_test` signature (currently at line 272-279) to add a keyword-only `locality` parameter:

Old:
```python
def run_test(
    model: str,
    test: dict[str, Any],
    sampler: MetricsSampler,
    host: str | None = None,
    headers: dict[str, str] | None = None,
    transport: Any | None = None,
) -> dict[str, Any]:
```

New:
```python
def run_test(
    model: str,
    test: dict[str, Any],
    sampler: MetricsSampler,
    host: str | None = None,
    headers: dict[str, str] | None = None,
    transport: Any | None = None,
    *,
    locality: str | None = None,
) -> dict[str, Any]:
```

Then immediately after `_host = _normalize_host(...)` (around line 280), add validation:

```python
    if locality is not None and locality not in ("local", "remote"):
        raise ValueError(
            f"locality must be 'local', 'remote', or None; got {locality!r}"
        )
```

- [ ] **Step 1.5: Run the test — confirm it passes**

```bash
.venv/bin/pytest tests/unit/test_runner.py::test_run_test_locality_invalid_value_raises -v -p no:cacheprovider --no-cov
```

Expected: PASS.

### Add the four behavior tests

- [ ] **Step 1.6: Append the four locality-behavior tests**

Append to `tests/unit/test_runner.py` after `test_run_test_locality_invalid_value_raises`:

```python
def test_run_test_locality_none_falls_back_to_detect_mode() -> None:
    """locality=None + loopback host preserves today's behavior: is_local=True."""
    from unittest.mock import MagicMock, patch
    from hermia.runner import run_test
    sampler = MagicMock()
    sampler.peak.return_value = {"cpu_pct": 12.0, "ram_used_gb": 1.0, "gpu_pct": 0, "vram_used_gb": 0}
    transport, resp = _stub_transport()
    with patch("hermia.runner._play_turns", return_value=resp), \
         patch("hermia.runner.fetch_server_ps_data",
               return_value={"vram_server_gb": None, "model_size_server_gb": None}):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://localhost:11434", transport=transport,
        )
    assert row["mode"] == "local"
    sampler.start.assert_called_once()
    sampler.stop.assert_called_once()
    assert row["peak_cpu_pct"] is not None


def test_run_test_locality_explicit_remote_overrides_loopback_host() -> None:
    """locality='remote' + loopback host: sampler NOT run, peak_* null, mode='fleet'."""
    from unittest.mock import MagicMock, patch
    from hermia.runner import run_test
    sampler = MagicMock()
    transport, resp = _stub_transport()
    with patch("hermia.runner._play_turns", return_value=resp), \
         patch("hermia.runner.fetch_server_ps_data",
               return_value={"vram_server_gb": None, "model_size_server_gb": None}):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://localhost:11440", transport=transport,
            locality="remote",
        )
    assert row["mode"] == "fleet"
    sampler.start.assert_not_called()
    sampler.stop.assert_not_called()
    assert row["peak_cpu_pct"] is None
    assert row["peak_ram_used_gb"] is None
    assert row["peak_gpu_pct"] is None
    assert row["peak_vram_used_gb"] is None


def test_run_test_locality_explicit_local_overrides_remote_host() -> None:
    """locality='local' + remote-looking host: sampler runs, mode='local'."""
    from unittest.mock import MagicMock, patch
    from hermia.runner import run_test
    sampler = MagicMock()
    sampler.peak.return_value = {"cpu_pct": 5.0, "ram_used_gb": 1.0, "gpu_pct": 0, "vram_used_gb": 0}
    transport, resp = _stub_transport()
    with patch("hermia.runner._play_turns", return_value=resp), \
         patch("hermia.runner.fetch_server_ps_data",
               return_value={"vram_server_gb": None, "model_size_server_gb": None}):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://192.0.2.1:11434", transport=transport,
            locality="local",
        )
    assert row["mode"] == "local"
    sampler.start.assert_called_once()
    sampler.stop.assert_called_once()


def test_run_test_api_mode_short_circuits_locality() -> None:
    """is_api_mode=True wins over any locality value: mode='api', sampler not run."""
    from unittest.mock import MagicMock, patch
    from hermia.runner import run_test
    sampler = MagicMock()
    transport, resp = _stub_transport()
    transport.is_api_mode = True
    with patch("hermia.runner._play_turns", return_value=resp):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://localhost:11434", transport=transport,
            locality="local",
        )
    assert row["mode"] == "api"
    sampler.start.assert_not_called()
    sampler.stop.assert_not_called()
    assert row["peak_cpu_pct"] is None
```

- [ ] **Step 1.7: Run the four new tests — confirm `test_run_test_locality_none_falls_back_to_detect_mode` passes (no logic change yet exposes it), and the three explicit-locality tests FAIL**

```bash
.venv/bin/pytest tests/unit/test_runner.py -k locality -v -p no:cacheprovider --no-cov
```

Expected (5 tests collected):
- `test_run_test_locality_invalid_value_raises` → PASS
- `test_run_test_locality_none_falls_back_to_detect_mode` → PASS (current behavior)
- `test_run_test_locality_explicit_remote_overrides_loopback_host` → **FAIL** (current code ignores `locality`, falls back to `detect_mode` which returns "local" for loopback)
- `test_run_test_locality_explicit_local_overrides_remote_host` → **FAIL** (current code calls `detect_mode` which returns "fleet" for `192.0.2.1`)
- `test_run_test_api_mode_short_circuits_locality` → PASS (`is_api_mode` already short-circuits via `(not is_api_mode) and ...`)

The two failing ones are the ones we're about to fix.

### Implementation — wire `locality` into `is_local`

- [ ] **Step 1.8: Change `is_local` derivation in `run_test()` to consult `locality` first**

In `src/hermia/runner.py`, find line 293:

Old:
```python
    is_api_mode = getattr(transport, "is_api_mode", False) is True
    is_local = (not is_api_mode) and (detect_mode(_host) == "local")
```

New:
```python
    is_api_mode = getattr(transport, "is_api_mode", False) is True
    resolved_locality = locality if locality is not None else detect_mode(_host)
    is_local = (not is_api_mode) and (resolved_locality == "local")
```

That's the only line of production logic in this task.

- [ ] **Step 1.9: Run all five locality tests — confirm pass**

```bash
.venv/bin/pytest tests/unit/test_runner.py -k locality -v -p no:cacheprovider --no-cov
```

Expected: 5 PASSED.

- [ ] **Step 1.10: Run the full unit test suite — confirm no regression**

```bash
.venv/bin/pytest tests/unit/ -p no:cacheprovider --no-cov
```

Expected: all tests pass (1485+ from the prior reproducibility floor merge, plus the 5 new ones).

- [ ] **Step 1.11: Run ruff and mypy**

```bash
.venv/bin/ruff check src/hermia/runner.py tests/unit/test_runner.py
.venv/bin/mypy src/hermia/runner.py
```

Expected: both clean (no errors, no warnings).

- [ ] **Step 1.12: Commit Task 1**

```bash
PRE_COMMIT_ALLOW_NO_CONFIG=1 git add src/hermia/runner.py tests/unit/test_runner.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "$(cat <<'EOF'
feat(runner): declared locality parameter; preserve detect_mode fallback

run_test() gains a keyword-only locality: str | None = None parameter.
When None, falls back to detect_mode(host) (preserving today's behavior
for the standalone TUI path). When "local" or "remote", overrides the
heuristic. Invalid values raise ValueError.

This is the v0.2.0 fix for the tunnel-locality bug: detect_mode infers
is_local from the URL hostname (loopback ↔ local), which is wrong for
fleet runs that reach remote nodes via SSH tunnels on loopback ports.
Callers that know the truth (fleet.py) declare it; the heuristic
remains correct for callers with no tunnel layer (app.py).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Wire `fleet.py` to declare `locality="remote"` (TDD)

**Files:**
- Modify: `src/hermia/fleet.py:216-219` (the `run_test` call inside `_run_host_eval`)
- Test: `tests/unit/test_fleet.py` (append 1 test)

### First test — failing

- [ ] **Step 2.1: Append failing test for `_run_host_eval` passing `locality="remote"`**

Append to `tests/unit/test_fleet.py` (after the last test in the file):

```python
def test_run_host_eval_passes_locality_remote_to_run_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fleet entries always declare locality='remote' — covers tunnel-port topology."""
    import hermia.fleet as fleet
    from hermia.results import open_run

    captured_kwargs: list[dict] = []

    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None, **kw):  # type: ignore[no-untyped-def]
        captured_kwargs.append(dict(kw))
        return {
            "model": model, "test_id": test["id"], "failure_reason": "",
            "elapsed_sec": 0.1, "tokens_per_sec": 1.0,
            "mode": "fleet",
            "peak_cpu_pct": None, "peak_ram_used_gb": None,
            "peak_gpu_pct": None, "peak_vram_used_gb": None,
        }

    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)

    jsonl, csv = open_run(tmp_path)
    # Loopback-port host simulating an SSH tunnel to a remote node.
    entry = {"name": "tunneled-node", "host": "http://localhost:11440"}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )

    assert len(captured_kwargs) == 1, f"expected exactly one run_test call, got {len(captured_kwargs)}"
    assert captured_kwargs[0].get("locality") == "remote", (
        f"_run_host_eval must declare locality='remote'; got {captured_kwargs[0].get('locality')!r}"
    )
```

- [ ] **Step 2.2: Run the test — confirm it fails**

```bash
cd ~/Git/hermia
.venv/bin/pytest tests/unit/test_fleet.py::test_run_host_eval_passes_locality_remote_to_run_test -v -p no:cacheprovider --no-cov
```

Expected: FAIL with assertion `_run_host_eval must declare locality='remote'; got None`.

### Implementation — add `locality="remote"` to the fleet call

- [ ] **Step 2.3: Add `locality="remote"` to the `run_test` call in `_run_host_eval`**

In `src/hermia/fleet.py`, find the `run_test` call (around lines 216-219):

Old:
```python
                result = run_test(
                    model, test, sampler,
                    host=host_url, headers=headers, transport=host_transport,
                )
```

New:
```python
                result = run_test(
                    model, test, sampler,
                    host=host_url, headers=headers, transport=host_transport,
                    locality="remote",
                )
```

That's the only production change in this task.

- [ ] **Step 2.4: Run the new test — confirm it passes**

```bash
.venv/bin/pytest tests/unit/test_fleet.py::test_run_host_eval_passes_locality_remote_to_run_test -v -p no:cacheprovider --no-cov
```

Expected: PASS.

- [ ] **Step 2.5: Run the full test suite — confirm no regression**

```bash
.venv/bin/pytest tests/ -p no:cacheprovider --no-cov
```

Expected: every test passes. Pay particular attention to the existing `tests/unit/test_fleet.py::test_run_host_eval_writes_expected_rows` and `test_run_fleet_result_host_field` — these use `fake_run_test` doubles whose signatures must absorb the new `locality` kwarg via `**kw`. If they fail with `unexpected keyword argument 'locality'`, the existing fakes need a `**kw` catch-all (verify by inspection at `test_fleet.py:201` and `test_fleet.py:221`).

If any existing fake fails because it doesn't accept `**kw`:

- The fake at `test_fleet.py:201` is `side_effect=lambda *a, host=None, **kw: ...` — already accepts `**kw`, no change needed.
- The fake at `test_fleet.py:221` is `def fake_run_test(model, test, sampler, host=None, headers=None, transport=None):` — does NOT accept `**kw`. Add `**kw` to its signature:

  Old:
  ```python
      def fake_run_test(model, test, sampler, host=None, headers=None, transport=None):
  ```
  New:
  ```python
      def fake_run_test(model, test, sampler, host=None, headers=None, transport=None, **kw):  # type: ignore[no-untyped-def]
  ```

  (One-line signature edit. Don't change the body.)

- [ ] **Step 2.6: Run ruff and mypy**

```bash
.venv/bin/ruff check src/hermia/fleet.py tests/unit/test_fleet.py
.venv/bin/mypy src/hermia/fleet.py
```

Expected: both clean.

- [ ] **Step 2.7: Commit Task 2**

```bash
PRE_COMMIT_ALLOW_NO_CONFIG=1 git add src/hermia/fleet.py tests/unit/test_fleet.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "$(cat <<'EOF'
feat(fleet): declare locality=remote for all fleet hosts

_run_host_eval now passes locality="remote" to run_test(), forcing
correct attribution regardless of whether the YAML host uses a tunnel
port (http://localhost:11440) or a direct URL. Closes the topology
bug: previously every tunnelled fleet row got the orchestrator's own
peak_* telemetry stamped on it with mode="local".

YAML schema unchanged. The local-machine-in-a-fleet case is intentionally
not supported in v0.2.0 — use standalone TUI for that, or wait for the
hermia-agent sidecar in v0.2.x.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Push, run code-review gates, open PR

- [ ] **Step 3.1: Push the branch**

```bash
cd ~/Git/hermia
git push -u origin feat/v0.2-topology-locality
```

- [ ] **Step 3.2: Run `/code-review` from `~/Git/hermia` cwd**

In a Claude Code session with cwd = `~/Git/hermia`, run `/code-review`. Address any high-confidence findings inline. Re-run after fixes until clean.

- [ ] **Step 3.3: Open the PR**

```bash
gh api repos/scottbly/hermia/pulls -f title="feat(v0.2): topology locality — declared not inferred" \
  -f head="feat/v0.2-topology-locality" -f base="dev" \
  -f body="$(cat <<'EOF'
## Summary

Item #3 of the v0.2.0 stack-fingerprint scope. Fixes the long-standing topology bug where fleet rows carry misattributed `peak_*` telemetry and the wrong `mode` label because `detect_mode()` infers locality from the URL hostname — which is wrong when fleet entries reach remote nodes via loopback-port SSH tunnels.

**Principle:** locality declared, not inferred.

**Change surface:**
- `runner.py`: `run_test()` gains keyword-only `locality: str | None = None`. When `None`, falls back to `detect_mode(host)` (preserves today's TUI behavior). When `"local"` or `"remote"`, overrides the heuristic. Invalid values raise `ValueError`.
- `fleet.py`: `_run_host_eval` declares `locality="remote"` on every call.
- `app.py`: unchanged. `detect_mode` is correct there (no tunnels).
- YAML schema: unchanged. Fleet entries are remote-by-definition in v0.2.0.

**Tests:** 5 unit tests in `test_runner.py` + 1 in `test_fleet.py`.

**Data implications:** the 895-row pre-determinism baseline still carries misattribution and is corrected separately via a private backfill script in `~/Git/hermia-research/` (no public-repo migration tooling — realistic affected user base is approximately empty).

**Spec:** `docs/superpowers/specs/2026-06-15-topology-locality-design.md`

## Test plan
- [x] 5 new unit tests in `tests/unit/test_runner.py` cover invalid values, fallback, explicit remote/local, and api-mode short-circuit
- [x] 1 new test in `tests/unit/test_fleet.py` verifies `_run_host_eval` declares `locality="remote"`
- [x] Full suite passes (`pytest tests/ -p no:cacheprovider --no-cov`)
- [x] Ruff + mypy clean
EOF
)"
```

- [ ] **Step 3.4: Post `/gemini review` as a PR comment**

```bash
# Find the PR number from the response above (or via `gh pr list -H feat/v0.2-topology-locality`).
PR=$(gh pr list -H feat/v0.2-topology-locality --json number -q '.[0].number')
gh pr comment "$PR" --body "/gemini review"
```

- [ ] **Step 3.5: Wait for Gemini review; address findings**

Monitor the PR for Gemini's review. Address any findings, push fixes, re-post `/gemini review` per `[[feedback_gemini_rereview]]`. Iterate until Gemini comes back clean.

- [ ] **Step 3.6: Run Opus `/review` in-window**

In a Claude Code session with cwd = `~/Git/hermia`, run `/review` (the Opus skill). This is in-window — never post Opus output as a PR comment. Address any findings; push fixes; re-run Gemini if you push.

- [ ] **Step 3.7: Merge the PR to `dev`**

Once all gates are green, squash-merge (or merge-commit per convention) the PR. Delete the branch.

```bash
gh pr merge "$PR" --merge --delete-branch
```

---

## Task 4: Private backfill (run from `~/Git/hermia-research/`, NOT this repo)

This task is **out of scope for the public PR** above. Run separately from `~/Git/hermia-research/` after Task 3 merges. Detailed instructions:

- [ ] **Step 4.1: Write the one-shot backfill script**

Create `~/Git/hermia-research/scripts/backfill_topology_locality.py` with this content (adapt path constants if `~/Git/hermia-research/` has its own layout convention):

```python
#!/usr/bin/env python3
"""One-shot backfill for the topology-locality bug (v0.2.0 item #3).

Identifies fleet rows that were incorrectly stamped with mode="local" and
the orchestrator's own peak_* telemetry, then nulls peak_* and corrects
mode to "fleet". Idempotent.

Predicate: fleet_host_name != None AND mode == "local"
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PEAK_FIELDS = ("peak_cpu_pct", "peak_ram_used_gb", "peak_gpu_pct", "peak_vram_used_gb")


def is_affected(row: dict) -> bool:
    return row.get("fleet_host_name") is not None and row.get("mode") == "local"


def fix_row(row: dict) -> dict:
    out = dict(row)
    for f in PEAK_FIELDS:
        out[f] = None
    out["mode"] = "fleet"
    return out


def process_file(jsonl_path: Path, apply: bool) -> tuple[int, int]:
    rows = []
    affected = 0
    with jsonl_path.open() as f:
        for line in f:
            row = json.loads(line)
            if is_affected(row):
                affected += 1
                row = fix_row(row)
            rows.append(row)
    total = len(rows)
    if apply and affected > 0:
        tmp = jsonl_path.with_suffix(".jsonl.tmp")
        with tmp.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        tmp.replace(jsonl_path)
        # Regenerate CSV sibling
        csv_path = jsonl_path.with_suffix(".csv")
        if csv_path.exists() and rows:
            fieldnames = list(rows[0].keys())
            with csv_path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                for r in rows:
                    w.writerow(r)
    return affected, total


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", default="~/Git/hermia/results")
    p.add_argument("--apply", action="store_true", help="Without this flag, dry-run only")
    args = p.parse_args()

    results_dir = Path(args.results_dir).expanduser()
    total_affected = 0
    total_rows = 0
    for jsonl in sorted(results_dir.glob("eval_*.jsonl")):
        affected, total = process_file(jsonl, apply=args.apply)
        total_affected += affected
        total_rows += total
        if affected:
            print(f"{jsonl.name}: {affected}/{total} rows affected")
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n[{mode}] Total: {total_affected}/{total_rows} rows affected across all files")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4.2: Dry-run against the results directory**

```bash
python3 ~/Git/hermia-research/scripts/backfill_topology_locality.py
```

Expected: total affected count near 895. Verify per-file counts look reasonable (large counts on fleet-run files, zero on standalone-local files).

- [ ] **Step 4.3: Apply**

```bash
python3 ~/Git/hermia-research/scripts/backfill_topology_locality.py --apply
```

- [ ] **Step 4.4: Re-run dry-run — confirm idempotent**

```bash
python3 ~/Git/hermia-research/scripts/backfill_topology_locality.py
```

Expected: `Total: 0/<total> rows affected` — every previously-matched row now has `mode="fleet"` and no longer matches the predicate.

- [ ] **Step 4.5: Spot-check a patched file**

```bash
jq -c 'select(.fleet_host_name != null) | {mode, peak_cpu_pct, fleet_host_name}' \
  ~/Git/hermia/results/eval_20260613_223658.jsonl | head -5
```

Expected: every line shows `"mode":"fleet"` and `"peak_cpu_pct":null`.

- [ ] **Step 4.6: Commit the backfill script in hermia-research**

```bash
cd ~/Git/hermia-research
git add scripts/backfill_topology_locality.py
git commit -m "scripts: one-shot topology-locality backfill for pre-v0.2.0 dataset"
```

(Patched JSONL/CSV files in `~/Git/hermia/results/` are NOT tracked by either repo — `.gitignore` excludes them — so no data commit needed.)

---

## Self-review

### Spec coverage

- ✅ Architecture (Section 2 of spec) → Task 1.4 (signature) + Task 1.8 (derivation) + Task 2.3 (fleet wiring)
- ✅ User UX scenarios (Section 1 of spec) → Task 1 covers loopback default, remote URL, api short-circuit; Task 2 covers tunnel fleet
- ✅ Test plan: 5 unit + 1 integration (Section 4 of spec) → Tasks 1.2, 1.6, 2.1 add exactly those tests
- ✅ Rollout (Section 5 of spec) → Task 3 covers branch → PR → gates → merge
- ✅ Backfill (Section 3 of spec, marked private) → Task 4 in hermia-research, NOT in public PR

### Placeholder scan

No TBDs, no "add appropriate error handling," no "similar to Task N." Every code block is concrete; every command has expected output.

### Type/signature consistency

- `run_test` signature: keyword-only `locality: str | None = None` — used consistently in Task 1.4 (definition), Task 1.6 (tests), Task 2.1 (assertion), Task 2.3 (wiring).
- Validation message: `"locality must be 'local', 'remote', or None"` — matches in Task 1.4 and the test's `pytest.raises(ValueError, match="locality")` in Task 1.2.
- `detect_mode` signature unchanged throughout.
- Fake `run_test` doubles in `test_fleet.py` — Task 2.5 explicitly addresses the `**kw` compatibility concern.

Plan is internally consistent.
