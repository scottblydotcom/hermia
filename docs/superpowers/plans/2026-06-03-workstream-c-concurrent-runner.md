# Workstream C — Concurrent Fleet Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the headless fleet eval against multiple hosts concurrently (instead of sequentially), with thread-safe shared state and VRAM-aware sequencing so no single inference node is overloaded.

**Architecture:** The concurrency unit is the **host**. Each fleet entry's full eval loop (model → test → repeat) runs in its own worker thread; a `ThreadPoolExecutor` runs up to `max_concurrency` hosts at once. This is VRAM-aware *by construction*: within a host, models still run strictly sequentially (one model loaded at a time, evicted between), so a single GPU node is never asked to hold two models; across distinct hosts (separate physical machines), we parallelize. Entries that share the same normalized host URL are serialized into one worker so two lanes pointing at the same box never thrash its VRAM. Three pieces of shared state become concurrent and get locks: the global `_ps_cache` (runner), the result-file writer (`append_result`), and progress output.

**Tech Stack:** Python 3.11+, `concurrent.futures.ThreadPoolExecutor`, `threading.Lock`, `pytest`, `unittest.mock`.

---

## Background — current state (post-Workstream-A `dev`)

- `src/hermia/fleet.py::run_fleet` iterates `entries` **sequentially** (one host fully done before the next), writing each result via `append_result`.
- `src/hermia/runner.py` holds a module-global `_ps_cache: dict` accessed by `fetch_server_ps_data` (read at L65–66, write at L73 & L92) and evicted by `unload_model` (L148–150). **No lock.** This is the deferred Gemini HIGH from PR #87 — it is Task 1 here.
- `src/hermia/results.py::append_result` opens the JSONL and CSV files in append mode and writes one row. **No lock.**
- `MetricsSampler` is created once per host loop today; in fleet mode it is not started (remote hosts are non-local after the A fix), but we keep one instance per host worker for correctness.

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| MODIFY | `src/hermia/runner.py` | Add `_ps_cache_lock`; guard all `_ps_cache` access |
| MODIFY | `src/hermia/results.py` | Add `_write_lock`; guard `append_result` file writes |
| MODIFY | `src/hermia/fleet.py` | Extract `_run_host_eval`; concurrent dispatch; host grouping; print lock; `max_concurrency` param |
| MODIFY | `src/hermia/app.py` | `--max-concurrency` CLI flag → `run_fleet` |
| MODIFY | `tests/unit/test_runner.py` | Concurrency test for `_ps_cache` |
| MODIFY | `tests/unit/test_results.py` | Concurrency test for `append_result` |
| MODIFY | `tests/unit/test_fleet.py` | Host-grouping + concurrent dispatch tests |
| CREATE | `tests/unit/test_fleet_concurrency.py` | End-to-end concurrent run against fake transports |

---

## Task 1: Thread-safe `_ps_cache` (Gemini HIGH prerequisite)

**Files:**
- Modify: `src/hermia/runner.py`
- Test: `tests/unit/test_runner.py`

- [ ] **Step 1: Write the failing concurrency test**

Add to `tests/unit/test_runner.py`:

```python
def test_ps_cache_is_thread_safe_under_concurrent_access() -> None:
    """Many threads hammering fetch_server_ps_data + unload_model must not raise
    RuntimeError('dictionary changed size during iteration') or corrupt the cache."""
    import threading
    import hermia.runner as rmod
    from hermia.runner import fetch_server_ps_data, unload_model

    rmod._ps_cache.clear()
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(200):
                host = f"http://h{n % 4}:11434"
                model = f"m{i % 8}"
                with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
                    fetch_server_ps_data(host, model)
                if i % 3 == 0:
                    unload_model(model)  # mutates/evicts cache concurrently
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [], f"concurrent cache access raised: {errors[:3]}"
```

- [ ] **Step 2: Run it to confirm it fails (or is flaky) without a lock**

Run: `python -m pytest tests/unit/test_runner.py::test_ps_cache_is_thread_safe_under_concurrent_access -v --no-cov`
Expected: FAIL or flaky — `RuntimeError: dictionary changed size during iteration` from `unload_model`'s `list(_ps_cache)` racing a write, or a `KeyError`. (If it passes by luck, raise the loop counts; the unguarded version is not safe.)

- [ ] **Step 3: Add the lock and guard every access site**

In `src/hermia/runner.py`, add `import threading` to the stdlib imports (after `import re`), then change the cache block:

```python
_ps_cache: dict[tuple[Any, ...], dict[str, float | None]] = {}
_ps_cache_lock = threading.Lock()
_vram_cache = _ps_cache  # backward-compat alias
```

In `fetch_server_ps_data`, guard the read and both writes — but keep the HTTP call **outside** the lock:

```python
    with _ps_cache_lock:
        if key in _ps_cache:
            return _ps_cache[key]

    empty: dict[str, float | None] = {"vram_server_gb": None, "model_size_server_gb": None}
    try:
        resp = requests.get(f"{host}/api/ps", timeout=2, headers=headers or {})
        if not resp.ok:
            if resp.status_code == 404:
                with _ps_cache_lock:
                    _ps_cache[key] = dict(empty)
            return dict(empty)

        result = dict(empty)
        data = resp.json()
        if isinstance(data, dict):
            models_list = data.get("models")
            for m in (models_list if isinstance(models_list, list) else []):
                if not isinstance(m, dict):
                    continue
                if m.get("name") == model:
                    sv = m.get("size_vram")
                    st = m.get("size")
                    if sv is not None:
                        result["vram_server_gb"] = float(sv) / (1024 ** 3)
                    if st is not None:
                        result["model_size_server_gb"] = float(st) / (1024 ** 3)
                    break

        with _ps_cache_lock:
            _ps_cache[key] = result
        return result
    except Exception:  # noqa: BLE001
        return dict(empty)
```

In `unload_model`, guard the snapshot-and-evict so it is atomic:

```python
    with _ps_cache_lock:
        keys_to_remove = [k for k in list(_ps_cache) if k[1] == model_name]
        for k in keys_to_remove:
            _ps_cache.pop(k, None)
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `python -m pytest tests/unit/test_runner.py::test_ps_cache_is_thread_safe_under_concurrent_access -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Run the full runner suite (no regressions)**

Run: `python -m pytest tests/unit/test_runner.py -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/hermia/runner.py tests/unit/test_runner.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "fix(runner): make _ps_cache thread-safe with a lock (Gemini HIGH, WS-C prereq)"
```

---

## Task 2: Thread-safe result writing

**Files:**
- Modify: `src/hermia/results.py`
- Test: `tests/unit/test_results.py`

- [ ] **Step 1: Write the failing concurrency test**

Add to `tests/unit/test_results.py`:

```python
def test_append_result_is_thread_safe(tmp_path) -> None:
    """Concurrent appends must not drop, interleave, or corrupt JSONL lines."""
    import json
    import threading
    from hermia.results import append_result, load_jsonl

    jsonl = tmp_path / "eval_x.jsonl"
    csv = tmp_path / "eval_x.csv"
    n_threads, per_thread = 8, 100

    def worker(tid: int) -> None:
        for i in range(per_thread):
            append_result(
                {"run_id": "r", "host": "h", "model": f"m{tid}", "test_id": f"t{i}"},
                jsonl, csv,
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = load_jsonl(jsonl)
    assert len(rows) == n_threads * per_thread          # nothing dropped
    # every line is valid JSON (no interleaving/corruption)
    for line in jsonl.read_text().splitlines():
        json.loads(line)
```

- [ ] **Step 2: Run it to confirm it fails/flakes without a lock**

Run: `python -m pytest tests/unit/test_results.py::test_append_result_is_thread_safe -v --no-cov`
Expected: FAIL/flaky — line count < expected or `json.loads` raises on an interleaved line.

- [ ] **Step 3: Add a module lock and guard the writes**

In `src/hermia/results.py`, add after the imports:

```python
import threading

_write_lock = threading.Lock()
```

Wrap the body of `append_result` in the lock:

```python
def append_result(
    result: dict[str, Any],
    jsonl_path: Path | None,
    csv_path: Path | None,
) -> None:
    """Append a single test result to JSONL and/or CSV. Pass None to skip either.

    Thread-safe: a process-wide lock serializes writes so concurrent fleet
    workers cannot interleave or drop lines.
    """
    with _write_lock:
        if jsonl_path is not None:
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")

        if csv_path is not None:
            write_header = not csv_path.exists()
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=result.keys(), extrasaction="ignore", restval=""
                )
                if write_header:
                    writer.writeheader()
                writer.writerow(result)
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `python -m pytest tests/unit/test_results.py::test_append_result_is_thread_safe -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/results.py tests/unit/test_results.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "fix(results): serialize append_result writes with a lock for concurrent fleet"
```

---

## Task 3: Extract `_run_host_eval` (behavior-preserving refactor)

Pull the per-host body of `run_fleet` into a standalone function so it can be submitted to an executor. **No behavior change yet** — `run_fleet` still calls it in a sequential loop.

**Files:**
- Modify: `src/hermia/fleet.py`
- Test: `tests/unit/test_fleet.py`

- [ ] **Step 1: Write a test pinning current per-host output**

Add to `tests/unit/test_fleet.py` (uses the existing fake-transport patterns in that file; if none exist, mock `hermia.fleet.run_test` to return a canned result dict):

```python
def test_run_host_eval_writes_expected_rows(tmp_path, monkeypatch) -> None:
    import hermia.fleet as fleet
    from hermia.results import load_jsonl, open_run

    captured = []
    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None):
        return {"model": model, "test_id": test["id"], "failure_reason": "",
                "elapsed_sec": 0.1, "tokens_per_sec": 1.0}
    monkeypatch.setattr(fleet, "run_test", fake_run_test, raising=False)
    monkeypatch.setattr(fleet, "load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr(fleet, "get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)

    jsonl, csv = open_run(tmp_path)
    entry = {"name": "node1", "host": "http://h1:11434"}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )
    rows = load_jsonl(jsonl)
    assert [r["model"] for r in rows] == ["m1"]
    assert [r["test_id"] for r in rows] == ["t1"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_fleet.py::test_run_host_eval_writes_expected_rows -v --no-cov`
Expected: FAIL — `AttributeError: module 'hermia.fleet' has no attribute '_run_host_eval'`.

- [ ] **Step 3: Extract the function**

In `src/hermia/fleet.py`, move the imports to module-load-safe positions inside `run_fleet` as today, but add a new function above `run_fleet`. It contains the existing per-host body verbatim, parameterized:

```python
def _run_host_eval(
    entry: dict[str, Any],
    repeat: int,
    run_id: str,
    jsonl_path: Path,
    csv_path: Path,
    print_lock: "threading.Lock",
    print_fn: Callable[[str], None],
    stderr_fn: Callable[[str], None],
    verbosity: int,
) -> None:
    """Evaluate every (model, test, repeat) for one fleet host. Writes rows as it goes.

    Models run strictly sequentially within the host (VRAM-aware: one model loaded
    at a time). Safe to call concurrently for *different* hosts.
    """
    from datetime import UTC, datetime
    from hermia.metrics import MetricsSampler
    from hermia.results import append_result
    from hermia.robustness import score_rows
    from hermia.runner import _normalize_host, get_available_models, load_tests_all, run_test
    from hermia.transport.ollama import OllamaTransport
    from hermia.transport.openai_compat import OpenAICompatTransport

    tests = load_tests_all()
    name = entry["name"]
    host_url = _normalize_host(entry["host"])
    headers = _build_auth_headers(entry)
    transport_type = entry.get("transport", "ollama")
    host_transport = (
        OpenAICompatTransport(host_url, headers)
        if transport_type == "openai-compat"
        else OllamaTransport(host_url, headers)
    )
    host_start = datetime.now(UTC).isoformat()

    requested = entry.get("models")
    if transport_type == "openai-compat" and not requested:
        with print_lock:
            stderr_fn(
                f"  ERROR: openai-compat host '{name}' requires an explicit"
                f" 'models:' list in fleet YAML — skipping host"
            )
        return
    all_models = (
        get_available_models(host=host_url, headers=headers)
        if transport_type != "openai-compat"
        else []
    )
    models, missing = _resolve_models(transport_type, requested, all_models)
    if missing:
        with print_lock:
            stderr_fn(f"  WARNING: models not found on {name}: {', '.join(sorted(missing))}")

    if verbosity >= 0:
        with print_lock:
            print_fn(f"{name} ({host_url}) — {len(models)} models, {len(tests)} tests")

    sampler = MetricsSampler()
    for model_entry in models:
        model = model_entry["name"]
        for test in tests:
            run_results: list[dict[str, Any]] = []
            for run_index in range(1, repeat + 1):
                result = run_test(
                    model, test, sampler,
                    host=host_url, headers=headers, transport=host_transport,
                )
                result["run_id"] = run_id
                result["run_timestamp"] = datetime.now(UTC).isoformat()
                result["run_index"] = run_index
                result["is_cold"] = False
                result["cold_warm_delta_tps"] = None
                result["fleet_host_name"] = name
                result["fleet_host_start"] = host_start
                run_results.append(result)

            rob = score_rows(run_results)
            for result in run_results:
                result["consistency_pct"] = rob.consistency_pct
                result["pass_count"] = rob.pass_count
                result["robustness_n"] = rob.n
                append_result(result, jsonl_path, csv_path)
                if verbosity >= 0:
                    status = "✓" if not result.get("failure_reason") else "✗"
                    elapsed = result.get("elapsed_sec") or 0.0
                    line = f"  {status} {name}/{model}:{test['id']} ({elapsed}s)"
                    if verbosity >= 1:
                        tps = result.get("tokens_per_sec") or 0.0
                        reason = result.get("failure_reason") or ""
                        line += f"  {tps:.1f} t/s"
                        if reason:
                            line += f"  [{reason}]"
                    with print_lock:
                        print_fn(line)
```

Add `import threading` and `from pathlib import Path` are already imported in fleet.py (Path is). Add `import threading` near the top imports.

Then make `run_fleet` call it sequentially for now:

```python
    jsonl_path, csv_path = open_run(results_dir)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    print_lock = threading.Lock()

    for entry in entries:
        _run_host_eval(entry, repeat, run_id, jsonl_path, csv_path,
                       print_lock, print_fn, stderr_fn, verbosity)

    print_fn(f"Saved: {jsonl_path}")
    return jsonl_path
```

(Remove the now-duplicated per-host body and the `enumerate`/`[idx/len]` header — the header moved into `_run_host_eval`. The `from ... import` block that remains at the top of `run_fleet` can be deleted since the imports now live in `_run_host_eval`; keep `open_run` import at the top of `run_fleet`.)

- [ ] **Step 4: Run the new test + full fleet suite**

Run: `python -m pytest tests/unit/test_fleet.py -q --no-cov`
Expected: all pass (behavior preserved).

- [ ] **Step 5: Commit**

```bash
git add src/hermia/fleet.py tests/unit/test_fleet.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "refactor(fleet): extract _run_host_eval (behavior-preserving) for concurrency"
```

---

## Task 4: VRAM-aware host grouping + concurrent dispatch

Group entries by normalized host so two entries on the same physical box are serialized; run distinct hosts concurrently with a `ThreadPoolExecutor` capped at `max_concurrency`.

**Files:**
- Modify: `src/hermia/fleet.py`
- Test: `tests/unit/test_fleet.py`, `tests/unit/test_fleet_concurrency.py` (CREATE)

- [ ] **Step 1: Write the grouping unit test**

Add to `tests/unit/test_fleet.py`:

```python
def test_group_entries_by_host_serializes_same_host() -> None:
    from hermia.fleet import _group_entries_by_host
    entries = [
        {"name": "a", "host": "http://h1:11434"},
        {"name": "b", "host": "http://h2:11434"},
        {"name": "c", "host": "http://h1:11434/"},  # same as a after normalize
    ]
    groups = _group_entries_by_host(entries)
    # two groups (h1, h2); h1 group holds a and c in order
    assert len(groups) == 2
    h1 = [g for g in groups if len(g) == 2][0]
    assert [e["name"] for e in h1] == ["a", "c"]
```

- [ ] **Step 2: Write the concurrency end-to-end test**

Create `tests/unit/test_fleet_concurrency.py`:

```python
"""Concurrent fleet dispatch: all rows land, same-host entries serialize."""
import threading
from pathlib import Path

from hermia import fleet
from hermia.results import load_jsonl


def _setup(monkeypatch, active: dict, max_seen: dict):
    monkeypatch.setattr(fleet, "load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr(fleet, "get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)
    lock = threading.Lock()

    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None):
        with lock:
            active["n"] += 1
            max_seen["n"] = max(max_seen["n"], active["n"])
        # sleep releases the GIL so concurrent workers reliably overlap —
        # more robust and cheaper than a CPU-bound spin loop
        import time
        time.sleep(0.01)
        with lock:
            active["n"] -= 1
        return {"model": model, "test_id": test["id"], "failure_reason": "",
                "elapsed_sec": 0.1, "tokens_per_sec": 1.0}
    monkeypatch.setattr(fleet, "run_test", fake_run_test, raising=False)


def test_distinct_hosts_run_concurrently(tmp_path: Path, monkeypatch) -> None:
    active, max_seen = {"n": 0}, {"n": 0}
    _setup(monkeypatch, active, max_seen)
    entries = [{"name": f"n{i}", "host": f"http://h{i}:11434"} for i in range(4)]
    out = fleet.run_fleet(entries, repeat=1, results_dir=tmp_path,
                          print_fn=lambda s: None, verbosity=-1, max_concurrency=4)
    rows = load_jsonl(out)
    assert len(rows) == 4                       # every host wrote its row
    assert max_seen["n"] >= 2                    # genuine overlap occurred


def test_same_host_entries_do_not_overlap(tmp_path: Path, monkeypatch) -> None:
    active, max_seen = {"n": 0}, {"n": 0}
    _setup(monkeypatch, active, max_seen)
    entries = [{"name": "a", "host": "http://h1:11434"},
               {"name": "b", "host": "http://h1:11434"}]  # same box
    fleet.run_fleet(entries, repeat=1, results_dir=tmp_path,
                    print_fn=lambda s: None, verbosity=-1, max_concurrency=4)
    assert max_seen["n"] == 1                     # never ran concurrently on one host
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `python -m pytest tests/unit/test_fleet.py::test_group_entries_by_host_serializes_same_host tests/unit/test_fleet_concurrency.py -v --no-cov`
Expected: FAIL — `_group_entries_by_host` missing and `run_fleet` has no `max_concurrency` kwarg.

- [ ] **Step 4: Implement grouping + executor**

In `src/hermia/fleet.py`, add the grouping helper above `run_fleet`:

```python
def _group_entries_by_host(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group entries by normalized host URL, preserving first-seen order.

    Entries sharing a physical host are returned in one group so they run
    sequentially (VRAM-aware); distinct hosts become separate groups that may
    run concurrently.
    """
    from hermia.runner import _normalize_host
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for entry in entries:
        key = _normalize_host(entry["host"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(entry)
    return [groups[k] for k in order]
```

Update `run_fleet`'s signature and body:

```python
def run_fleet(
    entries: list[dict[str, Any]],
    repeat: int,
    results_dir: Path,
    print_fn: Callable[[str], None] = print,
    stderr_fn: Callable[[str], None] = lambda msg: print(msg, file=sys.stderr),
    verbosity: int = 0,
    max_concurrency: int = 4,
) -> Path:
    """Run headless eval against all fleet entries, concurrently across hosts.

    max_concurrency caps how many distinct hosts run at once (default 4).
    Entries sharing a normalized host run sequentially within one worker.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from hermia.results import open_run

    jsonl_path, csv_path = open_run(results_dir)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    print_lock = threading.Lock()

    groups = _group_entries_by_host(entries)
    workers = max(1, min(max_concurrency, len(groups)))

    def run_group(group: list[dict[str, Any]]) -> None:
        for entry in group:  # same physical host → strictly sequential
            _run_host_eval(entry, repeat, run_id, jsonl_path, csv_path,
                           print_lock, print_fn, stderr_fn, verbosity)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run_group, groups))

    print_fn(f"Saved: {jsonl_path}")
    return jsonl_path
```

> **Note on exceptions:** `pool.map` re-raises the first worker exception after all complete. `_run_host_eval` already swallows per-test transport errors into result rows, so a raised exception here means a programming error — surfacing it is correct.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_fleet.py tests/unit/test_fleet_concurrency.py -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/hermia/fleet.py tests/unit/test_fleet.py tests/unit/test_fleet_concurrency.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(fleet): concurrent host dispatch with VRAM-aware same-host grouping"
```

---

## Task 5: `--max-concurrency` CLI flag

Wire the new knob through the headless entrypoint.

**Files:**
- Modify: `src/hermia/app.py`
- Test: `tests/unit/test_app.py`

- [ ] **Step 1: Locate the fleet CLI path**

Run: `grep -n "run_fleet\|--fleet\|add_argument" src/hermia/app.py`
Read the surrounding `argparse` setup so the new flag matches the existing style.

- [ ] **Step 2: Write the failing arg-parse test**

Add to `tests/unit/test_app.py` (match the file's existing invocation pattern — adapt the call to however `app` exposes parsing; if it parses inside `main`, drive it via `monkeypatch.setattr("sys.argv", [...])`). **`app.main()` does `from hermia.fleet import load_fleet_config, run_fleet` *inside* the function, so patch at the definition site (`hermia.fleet.run_fleet`), not `app.run_fleet`** — patching the `app` module attribute would not intercept the call:

```python
def test_max_concurrency_flag_passed_to_run_fleet(monkeypatch, tmp_path) -> None:
    import hermia.app as app
    captured = {}
    def spy(entries, repeat, results_dir, **kw):
        captured.update(kw)
        return tmp_path / "eval_x.jsonl"
    monkeypatch.setattr("hermia.fleet.run_fleet", spy, raising=False)
    monkeypatch.setattr("hermia.fleet.load_fleet_config", lambda p: [{"name": "a", "host": "http://h1:11434"}], raising=False)
    monkeypatch.setattr("sys.argv",
        ["hermia", "--fleet", "fleet.yaml", "--max-concurrency", "7"])
    app.main()
    assert captured.get("max_concurrency") == 7
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_app.py::test_max_concurrency_flag_passed_to_run_fleet -v --no-cov`
Expected: FAIL — flag unknown / `max_concurrency` not forwarded.

- [ ] **Step 4: Add the flag and forward it**

In `src/hermia/app.py`, next to the other fleet args:

```python
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="Max number of distinct hosts evaluated concurrently (default: 4)",
    )
```

And at the `run_fleet(...)` call site, pass it through:

```python
        run_fleet(
            entries, repeat, results_dir,
            verbosity=verbosity,
            max_concurrency=args.max_concurrency,
        )
```

(Match the exact existing call — only add the `max_concurrency=` kwarg.)

- [ ] **Step 5: Run the test + full app suite**

Run: `python -m pytest tests/unit/test_app.py -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/hermia/app.py tests/unit/test_app.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(cli): --max-concurrency flag for the headless fleet runner"
```

---

## Task 6: Full gates + docs

**Files:**
- Modify: `README.md` (fleet section), `docs/usage.md` (fleet mode), `docs/WORKSTREAMS.md` (mark C status)

- [ ] **Step 1: Run the entire suite + linters**

```bash
python -m pytest -q --no-cov
python -m ruff check src tests
python -m mypy src/hermia
```
Expected: all green.

- [ ] **Step 2: Document the flag**

Add to `README.md` and `docs/usage.md` fleet sections: that fleet runs are concurrent across hosts by default (cap with `--max-concurrency N`), and that entries sharing a host are serialized for VRAM safety.

- [ ] **Step 3: Update the workstream manifest**

In `docs/WORKSTREAMS.md`, set Workstream C row to in-review with this branch + PR.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/usage.md docs/WORKSTREAMS.md
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "docs: document concurrent fleet runner + --max-concurrency"
```

---

## Self-review checklist (done while writing)

- **Spec coverage:** ThreadPoolExecutor ✓ (Task 4), VRAM-aware sequencing ✓ (within-host sequential + same-host grouping, Tasks 3–4), `_ps_cache` thread-safety prerequisite ✓ (Task 1). Result-write and print races (introduced by concurrency) ✓ (Tasks 2–4).
- **Type consistency:** `_run_host_eval(entry, repeat, run_id, jsonl_path, csv_path, print_lock, print_fn, stderr_fn, verbosity)` is called identically in Task 3 (sequential) and Task 4 (`run_group`). `_group_entries_by_host` returns `list[list[dict]]`, consumed as groups in Task 4. `run_fleet` gains `max_concurrency: int = 4`, used in Tasks 4–5.
- **No placeholders:** every code step shows full code; CLI task includes a `grep` step because `app.py`'s exact arg wiring must be read in-repo before editing (the only read-first step, called out explicitly).

## Merge-overlap note (coordination with Workstream E)

C and E both touch `runner.py`/`fleet.py`. C lands first. When E (deterministic multi-turn) starts, it must rebase on top of merged C so the message-list/run_test changes compose with C's `_run_host_eval` extraction and the `_ps_cache` lock. Do not run C and E agents against the same files concurrently.
