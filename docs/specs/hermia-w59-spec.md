# Spec: hermia-w59 — Fake-Ollama Integration Test Fixture

**Bead:** hermia-w59  
**Status:** P0 launch-blocking  
**Blocks:** hermia-gx8 (determinism harness)

---

## Problem

Every `runner.py` test today mocks `requests.post` at the function level. That means:

- If Ollama renames `response` → `content`, all unit tests still pass
- If `eval_count` disappears, no test catches it
- The full pipeline (HTTP call → JSON parse → schema check → result row) is never exercised end-to-end

A fake HTTP server fixture exercises the real `requests` call stack. Any Ollama API shape drift will immediately break the integration tests.

---

## Design

### Fixture: `fake_ollama` (session-scoped, conftest.py)

Use `stdlib` only — `http.server.HTTPServer` + `threading.Thread`. **No new dependencies.**  
No `pytest-httpserver` or similar (AGENTS.md hard rule #1 / #3).

The fixture:
1. Binds to `127.0.0.1:0` (OS picks a free port — no hardcoded port collisions)
2. Starts the server in a daemon thread
3. Yields `base_url` (e.g. `http://127.0.0.1:54321`)
4. On teardown: calls `server.shutdown()`

The handler routes on `self.path`:
- `POST /api/generate` → return canned success JSON (see below)
- `GET /api/tags` → return canned tags JSON (see below)
- Anything else → 404

Canned responses are **class-level defaults** on the handler, overridable per-test via a shared mutable dict passed into the fixture. This avoids global state while keeping the fixture simple.

### Canned Success Response (`/api/generate`)

```json
{
  "model": "fake-model",
  "created_at": "2026-01-01T00:00:00Z",
  "response": "{\"action\": \"get_weather\", \"location\": \"London\"}",
  "done": true,
  "eval_count": 42,
  "eval_duration": 1000000000
}
```

`response` is a JSON string that passes `tool-calling-basic` schema check.

### Canned Tags Response (`/api/tags`)

```json
{
  "models": [
    {"name": "fake-model", "size": 5368709120}
  ]
}
```

---

## Test File

New file: `tests/integration/test_fake_ollama.py`  
New conftest: `tests/integration/conftest.py` (fixture lives here)  
New init: `tests/integration/__init__.py`

---

## Test Matrix

### T1 — Happy path: full pipeline

**Given:** fake server returns canned success response  
**When:** `run_test("fake-model", test, sampler)` called with `tool-calling-basic` test case  
**Then:**
- `result["failure_reason"] == ""`
- `result["json_valid"] is True`
- `result["schema_compliant"] is True`
- `result["tokens"] == 42`
- `result["elapsed_sec"] >= 0`
- `result["model"] == "fake-model"`
- `result["test_id"] == "tool-calling-basic"`

### T2 — Drift tolerance: unknown fields ignored

**Given:** fake server injects extra fields into the generate response:
```json
{"response": "...", "eval_count": 42, "done": true, "thinking": "...", "unknown_future_field": 99}
```
**When:** `run_test` called  
**Then:**
- `result["failure_reason"] == ""`
- `result["json_valid"] is True` (extra fields don't cause a crash)

### T3 — Timeout produces failure_reason

**Given:** fake server sleeps longer than `runner.TEST_TIMEOUT` before responding  
**When:** `run_test` called (with TEST_TIMEOUT monkeypatched to 0.1s to keep test fast)  
**Then:**
- `result["failure_reason"]` starts with `"TIMEOUT:"`
- `result["json_valid"] is False`
- `result["schema_compliant"] is False`
- `result["tokens"] == 0`

### T4 — HTTP 500 produces failure_reason

**Given:** fake server returns HTTP 500 with body `{"error": "model not found"}`  
**When:** `run_test` called  
**Then:**
- `result["failure_reason"]` contains `"OLLAMA_ERROR:"` or is non-empty
- `result["json_valid"] is False`

### T5 — Malformed JSON produces failure_reason

**Given:** fake server returns HTTP 200 with body `not valid json at all`  
**When:** `run_test` called  
**Then:**
- `result["failure_reason"]` is non-empty (ERROR path)
- `result["json_valid"] is False`

### T6 — `get_available_models` against fake /api/tags

**Given:** fake server responds to `GET /api/tags` with canned tags response  
**When:** `get_available_models()` called with base URL pointing at fake server  
**Then:**
- Returns a list with one entry: `{"name": "fake-model", "size": 5368709120}`

---

## Implementation Notes for Fleet

### Fixture structure (conftest.py sketch)

```python
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import pytest

class _FakeOllamaHandler(BaseHTTPRequestHandler):
    # Set on the class by the fixture to allow per-test override
    response_override: dict = {}

    def do_POST(self):
        if self.path == "/api/generate":
            body = self.response_override.get("generate") or DEFAULT_GENERATE_RESPONSE
            self._send_json(200, body)
        else:
            self._send_json(404, {"error": "not found"})

    def do_GET(self):
        if self.path == "/api/tags":
            body = self.response_override.get("tags") or DEFAULT_TAGS_RESPONSE
            self._send_json(200, body)
        else:
            self._send_json(404, {"error": "not found"})

    def _send_json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass  # suppress test output noise

@pytest.fixture(scope="session")
def fake_ollama():
    server = HTTPServer(("127.0.0.1", 0), _FakeOllamaHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
```

### Patching OLLAMA_BASE in runner

`runner.OLLAMA_BASE` is a module-level constant. Tests patch it via `monkeypatch`:

```python
def test_happy_path(fake_ollama, monkeypatch):
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    ...
```

### Timeout test

Monkeypatch `hermia.runner.TEST_TIMEOUT` to `0.1` and make the handler sleep 0.5s for that specific test. Use a flag on the handler class.

### Sampler mock

Reuse the `_mock_sampler()` pattern already established in `tests/unit/test_runner.py`.

---

## What NOT to do

- Do not import `pytest-httpserver`, `responses`, `httpretty`, or any other HTTP mocking library (AGENTS.md #1/#3)
- Do not hardcode a port number
- Call `server.server_close()` after `server.shutdown()` to release the socket immediately
- Do not add a `scope="function"` fixture if session scope works — server startup cost is non-trivial

---

## Acceptance Checklist

- [ ] `tests/integration/` directory created with `__init__.py`
- [ ] `tests/integration/conftest.py` with `fake_ollama` fixture (stdlib only)
- [ ] T1 through T6 all passing
- [ ] No new entries in `pyproject.toml [project.optional-dependencies]`
- [ ] `pytest --cov` shows `runner.py` lines 52-69 now covered
- [ ] `ruff` and `mypy` clean
