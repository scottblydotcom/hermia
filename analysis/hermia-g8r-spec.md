# hermia-g8r — Fleet config file (`hermia-fleet.yaml` + `--fleet` flag)

## What this bead does

Adds a `--fleet FILE` CLI flag that reads a YAML config listing multiple Ollama
hosts and runs eval headlessly against all of them in a single command.

**Current state:** fleet eval = 4 separate `hermia --host <url>` invocations,
each launching the TUI, requiring manual model/test selection.

**After this bead:** `hermia --fleet hermia-fleet.yaml` runs all hosts silently,
writes a combined JSONL/CSV, and exits.

## YAML schema

```yaml
# hermia-fleet.yaml
fleet:
  - name: node3
    host: http://100.x.x.x:11434
  - name: marcus-3090
    host: http://100.x.x.x:11434
  - name: eric-5090
    host: https://hermia.example.com:4000
    auth:
      bearer:
        key_env: ERIC_API_KEY   # name of env var; value never stored in YAML
  - name: gateway
    host: http://100.x.x.x:11434
```

Required per entry: `name` (str), `host` (str).  
Optional: `auth.bearer.key_env` (str — name of env var containing the token).

## New module: `src/hermia/fleet.py`

### `load_fleet_config(path: Path) -> list[dict[str, Any]]`

Parses YAML, validates each entry has `name` and `host`. Returns list of dicts.
Raises `ValueError` with a clear message if a required field is missing.

```python
def load_fleet_config(path: Path) -> list[dict[str, Any]]:
    import yaml
    with path.open() as f:
        data = yaml.safe_load(f)
    entries = data.get("fleet", [])
    for i, entry in enumerate(entries):
        if not entry.get("name"):
            raise ValueError(f"Fleet entry [{i}] missing 'name'")
        if not entry.get("host"):
            raise ValueError(f"Fleet entry [{i}] missing 'host'")
    return entries
```

### `_build_auth_headers(entry: dict[str, Any]) -> dict[str, str]`

Reads bearer token from env at runtime. Raises `RuntimeError` if `key_env` is
set but the env var is absent.

```python
def _build_auth_headers(entry: dict[str, Any]) -> dict[str, str]:
    auth = entry.get("auth") or {}
    bearer = auth.get("bearer") or {}
    key_env = bearer.get("key_env")
    if not key_env:
        return {}
    token = os.environ.get(key_env)
    if not token:
        raise RuntimeError(
            f"Fleet entry '{entry['name']}': auth.bearer.key_env={key_env!r} "
            f"is set but the env var is not present or empty"
        )
    return {"Authorization": f"Bearer {token}"}
```

### `run_fleet(entries, repeat, results_dir, print_fn=print) -> Path`

Iterates entries. For each host:

1. Set `os.environ["HERMIA_HOST"]` to the host URL
2. Call `get_available_models()` — queries `/api/tags`
3. Load all tests from `agentic-tasks.json`
4. For each (model, test, run_index in range(repeat)):
   - Build a no-op `MetricsSampler` (fleet mode suppresses local metrics)
   - Call `run_test(model, test, sampler, host=host_url)` — existing function
   - Add fields: `run_id`, `run_timestamp`, `host` (the host URL from entry),
     `run_index`, `is_cold=False`, `cold_warm_delta_tps=None`,
     `consistency_pct=None`, `pass_count=None`, `robustness_n=None`
   - Append to JSONL via `append_result()`
5. After all entries complete, reset `HERMIA_HOST` env var

Open a single `open_run(results_dir)` before the outer loop so all hosts land
in one JSONL + CSV file.

Print progress to stdout: `[1/4] node3 (http://...) — 3 models, 12 tests`
and `  ✓ model:test_id (elapsed)` per result.

```python
def run_fleet(
    entries: list[dict[str, Any]],
    repeat: int,
    results_dir: Path,
    print_fn: Callable[[str], None] = print,
) -> Path:
    """Run headless eval against all fleet entries. Returns path to JSONL."""
    from hermia.metrics import MetricsSampler
    from hermia.results import append_result, open_run
    from hermia.runner import get_available_models, load_tests, run_test

    jsonl_path, csv_path = open_run(results_dir)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    all_test_ids = [t["id"] for t in load_tests_all()]  # see below

    for idx, entry in enumerate(entries, 1):
        name = entry["name"]
        host_url = entry["host"].rstrip("/")
        headers = _build_auth_headers(entry)

        os.environ["HERMIA_HOST"] = host_url
        models = get_available_models()
        tests = load_tests(all_test_ids)
        print_fn(f"[{idx}/{len(entries)}] {name} ({host_url}) — {len(models)} models, {len(tests)} tests")

        sampler = MetricsSampler()
        for model_entry in models:
            model = model_entry["name"]
            for test in tests:
                for run_index in range(repeat):
                    result = run_test(model, test, sampler, host=host_url, headers=headers)
                    result["run_id"] = run_id
                    result["run_timestamp"] = datetime.now(UTC).isoformat()
                    result["host"] = host_url
                    result["run_index"] = run_index
                    result["is_cold"] = False
                    result["cold_warm_delta_tps"] = None
                    result["consistency_pct"] = None
                    result["pass_count"] = None
                    result["robustness_n"] = None
                    append_result(result, jsonl_path, csv_path)
                    status = "✓" if not result.get("failure_reason") else "✗"
                    print_fn(f"  {status} {model}:{test['id']} ({result['elapsed_sec']}s)")

    return jsonl_path
```

### `load_tests_all() -> list[dict[str, Any]]`

Helper: loads all test cases from `agentic-tasks.json` (no filter).

```python
def load_tests_all() -> list[dict[str, Any]]:
    from hermia.runner import PROJECT_ROOT
    import json
    path = PROJECT_ROOT / "test-datasets" / "agentic-tasks.json"
    with open(path) as f:
        return json.load(f)["agentic_test_cases"]
```

## Changes to `src/hermia/runner.py`

Add `headers: dict[str, str] | None = None` parameter to `run_test()`.

```python
def run_test(
    model: str,
    test: dict[str, Any],
    sampler: MetricsSampler,
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    _host = _normalize_host(host) if host is not None else get_ollama_host()
    mode = detect_mode(_host)
    payload = { ... }  # unchanged
    req_headers = headers or {}
    ...
    resp = requests.post(f"{_host}/api/generate", json=payload, headers=req_headers, timeout=TEST_TIMEOUT)
    ...
```

Also pass `req_headers` to the unload call in `unload_model()` — but since
`unload_model()` is TUI-path only (called from screens.py, not fleet), do NOT
change its signature in this bead. Fleet runner never calls `unload_model()`.

## Changes to `src/hermia/app.py`

Add `--fleet FILE` argument. When present, call `run_fleet()` and `sys.exit(0)`.
No `EvalApp` is created.

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Hermia LLM Eval")
    parser.add_argument("--host", ...)
    parser.add_argument("--repeat", ...)
    parser.add_argument(
        "--fleet",
        metavar="FILE",
        help="YAML fleet config; runs headless eval against all hosts and exits",
    )
    args = parser.parse_args()

    if args.fleet:
        import sys
        from pathlib import Path
        from hermia.fleet import load_fleet_config, run_fleet
        from hermia.screens import RESULTS_DIR
        entries = load_fleet_config(Path(args.fleet))
        run_fleet(entries, repeat=args.repeat, results_dir=RESULTS_DIR)
        sys.exit(0)

    os.environ["HERMIA_HOST"] = args.host.rstrip("/")
    fleet_mode = detect_mode(args.host) == "fleet"
    EvalApp(fleet_mode=fleet_mode, repeat=args.repeat).run()
```

## New test file: `tests/unit/test_fleet.py`

### Tests required

1. `test_load_fleet_config_valid` — parse a minimal YAML with 2 entries; assert
   correct `name` and `host` fields.

2. `test_load_fleet_config_missing_name` — entry without `name` raises
   `ValueError`.

3. `test_load_fleet_config_missing_host` — entry without `host` raises
   `ValueError`.

4. `test_build_auth_headers_no_auth` — entry with no `auth` block → `{}`.

5. `test_build_auth_headers_bearer_present` — entry with `auth.bearer.key_env`
   and env var set → `{"Authorization": "Bearer <token>"}`.

6. `test_build_auth_headers_bearer_missing_env` — key_env set but env var
   absent → raises `RuntimeError` with the env var name in the message.

7. `test_run_fleet_iterates_all_hosts` — mock `get_available_models` returning
   1 model, `load_tests_all` returning 1 test, `run_test` returning a minimal
   result dict; assert `run_test` called once per host × model × test × repeat,
   and JSONL written with correct `host` values.

8. `test_run_fleet_result_host_field` — same mock setup with 2 hosts; assert
   the two result rows written have different `host` values matching the YAML
   entries.

9. `test_fleet_flag_skips_tui` — monkeypatch `sys.argv` with `--fleet
   <tmp_yaml>`; call `main()`; assert `EvalApp.run` NOT called (mock it).

### Fixture pattern

Use `tmp_path` for YAML files and JSONL output dir. Use `unittest.mock.patch`
for `run_test`, `get_available_models`, `load_tests_all`.

## Permitted scope

- `src/hermia/fleet.py` (NEW)
- `src/hermia/runner.py` (add `headers` param to `run_test`)
- `src/hermia/app.py` (add `--fleet` flag)
- `tests/unit/test_fleet.py` (NEW)

## Acceptance criteria

1. `hermia --fleet hermia-fleet.yaml` runs headlessly, writes JSONL, exits 0
2. Each result row has `host` = the fleet entry's host URL
3. Auth bearer token read from env var at runtime; absent var raises `RuntimeError`
4. `run_test()` signature extended with `headers`; all existing callers unaffected
5. `--host` and TUI path completely unchanged
6. All 9 fleet unit tests pass; existing test suite still green (≥525 tests)

## Estimate

0.5 days

## Why

Four manual TUI invocations per lab run is the real workflow friction. Single
command + config makes fleet eval repeatable and scriptable.
