# hermia-pg4: Local vs Fleet Mode Detection + /api/ps Server Metrics

**Bead:** hermia-pg4  
**Priority:** P1  
**Permitted scope:** `src/hermia/runner.py`, `src/hermia/export.py`, `scripts/` (new migration), `tests/unit/test_runner.py`, `tests/unit/test_export.py`  
**Do NOT touch:** `src/hermia/screens.py`, `src/hermia/metrics.py`, any other file

---

## What this bead does

Currently `runner.py` hardcodes `OLLAMA_BASE = "http://localhost:11434"` and always collects local hardware metrics (CPU%, RAM, GPU%, VRAM via the sampler). When Hermia runs against a remote fleet node, it reports the eval client's idle Mac metrics — actively misleading.

This bead:
1. Adds host configuration via `HERMIA_HOST` env var
2. Adds mode detection (`"local"` vs `"fleet"`) based on the host URL
3. In fleet mode, suppresses local hardware collection — writes `None` for cpu/ram/gpu/vram fields
4. Queries `/api/ps` against the Ollama host in both modes to get `size_vram` (what the inference server reports the model is consuming)
5. Adds `mode` and `vram_server_gb` to result rows and Postgres schema

---

## Changes to `src/hermia/runner.py`

### 1. Remove the module-level constant

Delete:
```python
OLLAMA_BASE = "http://localhost:11434"
```

### 2. Add three new public functions (insert after imports, before `get_available_models`)

```python
import os
from urllib.parse import urlparse

def get_ollama_host() -> str:
    """Return the configured Ollama host URL from env var or default."""
    return os.environ.get("HERMIA_HOST", "http://localhost:11434")


def detect_mode(host: str) -> str:
    """Return 'local' if host resolves to localhost/loopback, else 'fleet'."""
    hostname = urlparse(host).hostname or ""
    return "local" if hostname in ("localhost", "127.0.0.1") else "fleet"


def fetch_server_vram(host: str, model: str) -> float | None:
    """Query /api/ps on host; return size_vram for model in GiB, or None.

    Returns None if the endpoint is unavailable, the model is not listed,
    or size_vram is absent. Never raises.
    """
    try:
        resp = requests.get(f"{host}/api/ps", timeout=5)
        for m in resp.json().get("models", []):
            if m.get("name") == model:
                size = m.get("size_vram")
                if size is not None:
                    return size / (1024 ** 3)
        return None
    except Exception:  # noqa: BLE001
        return None
```

### 3. Update `get_available_models`, `unload_model`, `prewarm_timed` to use `get_ollama_host()`

Replace every occurrence of `OLLAMA_BASE` in these three functions with `get_ollama_host()`. Each function should call `get_ollama_host()` once at the top (local variable `host`) and use that variable for the URL. Do not add a `host` parameter to these functions — that is out of scope.

Example for `get_available_models`:
```python
def get_available_models() -> list[dict[str, Any]]:
    host = get_ollama_host()
    try:
        resp = requests.get(f"{host}/api/tags", timeout=5)
        return resp.json().get("models", [])
    except Exception:
        return []
```

Apply the same pattern to `unload_model` and `prewarm_timed`.

### 4. Update `run_test` signature and body

New signature:
```python
def run_test(
    model: str, test: dict[str, Any], sampler: MetricsSampler, host: str | None = None
) -> dict[str, Any]:
```

At the top of the function body, add:
```python
_host = host if host is not None else get_ollama_host()
mode = detect_mode(_host)
```

Replace `OLLAMA_BASE` in the two `requests.post` calls inside `run_test` with `_host`.

**Sampler behavior — conditional on mode:**

In local mode: start and stop sampler as today.
In fleet mode: do NOT call `sampler.start()` or `sampler.stop()`.

Replace the current unconditional `sampler.start()` at the top with:
```python
if mode == "local":
    sampler.start()
```

And after the `except` blocks, replace the unconditional `sampler.stop()` / `peak = sampler.peak()` with:
```python
if mode == "local":
    sampler.stop()
peak = sampler.peak() if mode == "local" else {}
```

**Local metrics — conditional on mode:**

Replace the four metric lines at the bottom of the return dict:
```python
"peak_cpu_pct": round(peak.get("cpu_pct", 0), 1) if mode == "local" else None,
"peak_ram_used_gb": round(peak.get("ram_used_gb", 0), 2) if mode == "local" else None,
"peak_gpu_pct": round(peak.get("gpu_pct", 0), 1) if mode == "local" else None,
"peak_vram_used_gb": round(peak.get("vram_used_gb", 0), 2) if mode == "local" else None,
```

**Add two new fields to the return dict:**

Add after `peak_vram_used_gb`:
```python
"mode": mode,
"vram_server_gb": fetch_server_vram(_host, model),
```

**Full return dict after changes** (for reference — preserve all existing fields, just update the four metric lines and add two new ones):
```python
return {
    "model": model,
    "test_id": test["id"],
    "dimension": test.get("dimension", ""),
    "frameworks": test.get("frameworks", {}),
    "failure_reason": error_type,
    "json_valid": json_valid,
    "schema_compliant": schema_ok,
    "tokens": tokens,
    "elapsed_sec": round(elapsed, 2),
    "tokens_per_sec": round(tps, 1),
    "output_preview": preview,
    "peak_cpu_pct": round(peak.get("cpu_pct", 0), 1) if mode == "local" else None,
    "peak_ram_used_gb": round(peak.get("ram_used_gb", 0), 2) if mode == "local" else None,
    "peak_gpu_pct": round(peak.get("gpu_pct", 0), 1) if mode == "local" else None,
    "peak_vram_used_gb": round(peak.get("vram_used_gb", 0), 2) if mode == "local" else None,
    "mode": mode,
    "vram_server_gb": fetch_server_vram(_host, model),
}
```

---

## Changes to `src/hermia/export.py`

Add `"mode"` and `"vram_server_gb"` to `_PG_COLUMNS` at the end of the tuple (after `"judge_reasoning"`):

```python
_PG_COLUMNS = (
    "run_id",
    "run_timestamp",
    "host",
    "model",
    "test_id",
    "dimension",
    "json_valid",
    "schema_compliant",
    "failure_reason",
    "tokens",
    "elapsed_sec",
    "tokens_per_sec",
    "output_preview",
    "peak_cpu_pct",
    "peak_ram_used_gb",
    "peak_gpu_pct",
    "peak_vram_used_gb",
    "framework_owasp",
    "framework_mitre",
    "framework_maestro",
    "framework_nist",
    "score",
    "run_index",
    "is_cold",
    "cold_warm_delta_tps",
    "consistency_pct",
    "pass_count",
    "robustness_n",
    "judge_score",
    "judge_reasoning",
    "mode",
    "vram_server_gb",
)
```

`_INSERT_SQL` auto-generates from `_PG_COLUMNS` — no other change needed.

---

## New file: `scripts/add_mode_columns.sql`

```sql
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS mode TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS vram_server_gb DOUBLE PRECISION;
```

---

## Changes to `tests/unit/test_runner.py`

Add the following imports at the top if not already present:
```python
import os
from unittest.mock import patch
```

Add the following test functions. Insert them in logical groups — mode/host tests first, then fetch_server_vram tests, then additions to the run_test section.

### IMPORTANT: patch requests.get in ALL existing run_test tests

`run_test` now calls `fetch_server_vram` which uses `requests.get`. Every existing `run_test` test must add a `patch("hermia.runner.requests.get")` context so `vram_server_gb` is deterministic (returns None). Use the helper below.

**Add this helper near the top of the file (after `_mock_sampler`):**
```python
def _mock_ps_empty() -> MagicMock:
    """Mock /api/ps returning no loaded models."""
    m = MagicMock()
    m.json.return_value = {"models": []}
    return m
```

**Update every existing `run_test` test** to wrap in an additional `patch("hermia.runner.requests.get", return_value=_mock_ps_empty())`. Example:

```python
def test_run_test_success_json_valid() -> None:
    payload = '{"action": "get_weather", "city": "London"}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 50, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["json_valid"] is True
    # ... rest of assertions unchanged
```

Apply this pattern to ALL existing run_test tests (there are ~10 of them). Tests for `get_available_models` and `unload_model` already patch `requests.get` or `requests.post` at their own level — leave those alone.

### New test functions to add

```python
# ── get_ollama_host ───────────────────────────────────────────────────────────

def test_get_ollama_host_default() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HERMIA_HOST", None)
        from hermia.runner import get_ollama_host
        assert get_ollama_host() == "http://localhost:11434"


def test_get_ollama_host_from_env() -> None:
    with patch.dict(os.environ, {"HERMIA_HOST": "http://192.0.2.1:11434"}):
        from hermia.runner import get_ollama_host
        assert get_ollama_host() == "http://192.0.2.1:11434"


# ── detect_mode ───────────────────────────────────────────────────────────────

def test_detect_mode_localhost() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://localhost:11434") == "local"


def test_detect_mode_loopback() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://127.0.0.1:11434") == "local"


def test_detect_mode_remote_ip() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://192.0.2.1:11434") == "fleet"


def test_detect_mode_remote_hostname() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://erics-origin-neuron:11434") == "fleet"


# ── fetch_server_vram ─────────────────────────────────────────────────────────

def test_fetch_server_vram_found() -> None:
    from hermia.runner import fetch_server_vram
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5:32b", "size_vram": 19_271_950_336},
        ]
    }
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        result = fetch_server_vram("http://localhost:11434", "qwen2.5:32b")
    assert result is not None
    assert abs(result - 19_271_950_336 / (1024 ** 3)) < 0.01


def test_fetch_server_vram_model_not_found() -> None:
    from hermia.runner import fetch_server_vram
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": "other:7b", "size_vram": 5_000_000_000}]}
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        assert fetch_server_vram("http://localhost:11434", "qwen2.5:32b") is None


def test_fetch_server_vram_empty_models() -> None:
    from hermia.runner import fetch_server_vram
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": []}
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        assert fetch_server_vram("http://localhost:11434", "qwen2.5:32b") is None


def test_fetch_server_vram_connection_error() -> None:
    from hermia.runner import fetch_server_vram
    with patch("hermia.runner.requests.get", side_effect=requests.exceptions.ConnectionError):
        assert fetch_server_vram("http://192.0.2.1:11434", "qwen2.5:32b") is None


def test_fetch_server_vram_missing_size_vram_key() -> None:
    from hermia.runner import fetch_server_vram
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": "qwen2.5:32b"}]}  # no size_vram key
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        assert fetch_server_vram("http://localhost:11434", "qwen2.5:32b") is None


# ── run_test — mode and vram_server_gb fields ─────────────────────────────────

def test_run_test_has_mode_field_local() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["mode"] == "local"


def test_run_test_has_vram_server_gb_field() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert "vram_server_gb" in result
    assert result["vram_server_gb"] is None  # empty models list → None


def test_run_test_fleet_mode_suppresses_local_metrics() -> None:
    """In fleet mode, all local hardware fields must be None."""
    mock_post = MagicMock()
    mock_post.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    mock_get = MagicMock()
    mock_get.json.return_value = {"models": []}
    with patch("hermia.runner.requests.post", return_value=mock_post):
        with patch("hermia.runner.requests.get", return_value=mock_get):
            result = run_test(
                "qwen2.5:32b", _BASE_TEST, _mock_sampler(),
                host="http://192.0.2.1:11434"
            )
    assert result["mode"] == "fleet"
    assert result["peak_cpu_pct"] is None
    assert result["peak_ram_used_gb"] is None
    assert result["peak_gpu_pct"] is None
    assert result["peak_vram_used_gb"] is None


def test_run_test_fleet_mode_sampler_not_started() -> None:
    """In fleet mode, sampler.start() must never be called."""
    mock_post = MagicMock()
    mock_post.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    sampler = _mock_sampler()
    with patch("hermia.runner.requests.post", return_value=mock_post):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            run_test("qwen2.5:32b", _BASE_TEST, sampler, host="http://192.0.2.1:11434")
    sampler.start.assert_not_called()
    sampler.stop.assert_not_called()


def test_run_test_fleet_mode_vram_server_gb_populated() -> None:
    """vram_server_gb comes from /api/ps even in fleet mode."""
    mock_post = MagicMock()
    mock_post.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    mock_get = MagicMock()
    mock_get.json.return_value = {
        "models": [{"name": "qwen2.5:32b", "size_vram": 10_737_418_240}]  # 10 GiB
    }
    with patch("hermia.runner.requests.post", return_value=mock_post):
        with patch("hermia.runner.requests.get", return_value=mock_get):
            result = run_test(
                "qwen2.5:32b", _BASE_TEST, _mock_sampler(),
                host="http://192.0.2.1:11434"
            )
    assert result["vram_server_gb"] is not None
    assert abs(result["vram_server_gb"] - 10.0) < 0.01


def test_run_test_local_mode_still_collects_metrics() -> None:
    """In local mode, local hardware fields are not None."""
    mock_post = MagicMock()
    mock_post.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    sampler = _mock_sampler(cpu=42.0, ram=16.5, gpu=90.0, vram=22.3)
    with patch("hermia.runner.requests.post", return_value=mock_post):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test(
                "qwen2.5:32b", _BASE_TEST, sampler,
                host="http://localhost:11434"
            )
    assert result["mode"] == "local"
    assert result["peak_cpu_pct"] == 42.0
    assert result["peak_ram_used_gb"] == 16.5
    assert result["peak_gpu_pct"] == 90.0
    assert result["peak_vram_used_gb"] == 22.3
```

---

## Changes to `tests/unit/test_export.py`

Add the following tests. The `_PG_COLUMNS` import:
```python
from hermia.export import _PG_COLUMNS, collect_results, compute_score, main, push
```

Add tests:
```python
def test_pg_columns_includes_mode() -> None:
    assert "mode" in _PG_COLUMNS


def test_pg_columns_includes_vram_server_gb() -> None:
    assert "vram_server_gb" in _PG_COLUMNS


def test_push_dry_run_includes_mode_and_vram_server_gb(tmp_path: Path, capsys) -> None:
    """mode and vram_server_gb survive the push pipeline in dry-run."""
    row = {
        **_ROW,
        "mode": "fleet",
        "vram_server_gb": 18.5,
        "frameworks": {},
    }
    p = tmp_path / "eval_20260509_120000.jsonl"
    _write_jsonl(p, [row])
    rows = collect_results(tmp_path)
    push(rows, dsn="", dry_run=True)
    captured = capsys.readouterr()
    assert "Would process 1 row" in captured.out
```

---

## Acceptance checklist

Before calling this done, verify all of these:

- [ ] `detect_mode("http://localhost:11434")` → `"local"`
- [ ] `detect_mode("http://127.0.0.1:11434")` → `"local"`
- [ ] `detect_mode("http://192.0.2.1:11434")` → `"fleet"`
- [ ] `run_test(... host="http://192.0.2.1:11434")` → `peak_cpu_pct is None`
- [ ] `run_test(... host="http://localhost:11434")` → `peak_cpu_pct` is a float
- [ ] `result["mode"]` present in every `run_test` result
- [ ] `result["vram_server_gb"]` present in every `run_test` result (may be None)
- [ ] `"mode"` and `"vram_server_gb"` in `_PG_COLUMNS`
- [ ] `scripts/add_mode_columns.sql` exists with both `ADD COLUMN IF NOT EXISTS` statements
- [ ] All existing tests still pass (no regressions)
- [ ] `pytest tests/unit/test_runner.py tests/unit/test_export.py -v` is green
- [ ] `ruff check src/hermia/runner.py src/hermia/export.py` is clean
- [ ] No `OLLAMA_BASE` remaining in `runner.py`
