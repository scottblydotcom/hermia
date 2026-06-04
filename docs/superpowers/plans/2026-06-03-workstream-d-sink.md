# Workstream D — Submission API + partial Sink (lean plan)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Generation is delegated to the fleet (`coder-biggest-5090`); the Sonnet implementer integrates, runs gates, commits. Steps use `- [ ]`.

**Goal:** Introduce a pluggable `Sink` output seam (mirroring the v0.2 `Transport` pattern), port the existing JSONL/CSV and Postgres outputs behind thin adapters, and add an **opt-in, anonymized** community-submission Sink — with a default-deny anonymizer that can never leak identifying data.

**Architecture:** New `src/hermia/sink/` package. `Sink` is a `Protocol` with `write(rows: list[dict]) -> None`. Concrete sinks: `JsonlCsvSink` and `PostgresSink` are **thin adapters over the existing `results.append_result` / `export.push`** (establish the seam without ripping out current call sites — full migration is deferred). `SubmissionSink` is the new capability: it runs each row through a **whitelist-based anonymizer** and POSTs the safe subset to a configured endpoint (opt-in; dry-run prints the payload and sends nothing). The anonymizer is the privacy-critical core and gets property tests proving no stripped field or sensitive value ever appears in output.

**Tech Stack:** Python 3.11+, `typing.Protocol`, `requests`, `hypothesis`, `pytest`.

**Privacy model (default-deny):** a row is anonymized by copying ONLY an explicit whitelist of safe fields. Everything else is dropped. `failure_reason` is reduced to a category (it can contain `ERROR: ...<host/IP>...`). Auth tokens, hostnames, IPs, raw prompt/response text, local-client hardware metrics, run ids/timestamps are never included.

## Fleet delegation protocol (every task)
The Sonnet implementer delegates GENERATION to the fleet's `coder-biggest-5090` lane via the LiteLLM gateway (dispatch helper/endpoint/credentials live in the **ailab ops repo**, never here), then critically reviews, adapts, verifies, and commits. Never commit fleet output unread. **For Task D2 (privacy core), favor your own careful authorship over fleet output** — fleet code is a starting point only.

## File Map
| Action | Path | Responsibility |
|--------|------|----------------|
| CREATE | `src/hermia/sink/__init__.py` | exports |
| CREATE | `src/hermia/sink/base.py` | `Sink` protocol |
| CREATE | `src/hermia/sink/local.py` | `JsonlCsvSink`, `PostgresSink` adapters |
| CREATE | `src/hermia/sink/anonymize.py` | whitelist anonymizer + failure categorizer |
| CREATE | `src/hermia/sink/submission.py` | `SubmissionSink` (opt-in POST, dry-run) |
| CREATE | `tests/unit/test_sink_base.py`, `test_sink_local.py`, `test_anonymize.py`, `test_submission.py` | tests |
| MODIFY | `src/hermia/app.py` | `--submit` / `--submit-dry-run` flag wiring |
| MODIFY | `tests/unit/test_app.py` | flag test |

---

## Task D1: Sink protocol + local adapters
**Files:** `src/hermia/sink/{__init__,base,local}.py`, `tests/unit/test_sink_base.py`, `tests/unit/test_sink_local.py`

- [ ] **D1.1** Write `tests/unit/test_sink_base.py`: a trivial object with `write(self, rows)` satisfies `isinstance(obj, Sink)` (runtime-checkable Protocol); the protocol exposes `write`.
- [ ] **D1.2** Implement `base.py`:
```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class Sink(Protocol):
    def write(self, rows: list[dict[str, Any]]) -> None: ...
```
- [ ] **D1.3** Write `tests/unit/test_sink_local.py` (fleet-generate, then verify): `JsonlCsvSink(jsonl_path, csv_path).write(rows)` appends each row via the existing writer (assert rows land via `load_jsonl`); `PostgresSink(dsn, dry_run=True).write(rows)` calls `export.push(rows, dsn, dry_run=True)` (patch `export.push` and assert called with those args).
- [ ] **D1.4** Implement `local.py`: `JsonlCsvSink` wraps `results.append_result` (loop rows); `PostgresSink` wraps `export.push`. Thin adapters — no new behavior. `__init__.py` exports `Sink, JsonlCsvSink, PostgresSink`.
- [ ] **D1.5** `pytest tests/unit/test_sink_base.py tests/unit/test_sink_local.py -q`, ruff, mypy → green. Commit: `feat(sink): Sink protocol + JsonlCsvSink/PostgresSink adapters`

## Task D2: Anonymizer (privacy-critical — author carefully, property-test hard)
**Files:** `src/hermia/sink/anonymize.py`, `tests/unit/test_anonymize.py`

- [ ] **D2.1** Write `tests/unit/test_anonymize.py` FIRST. Define the whitelist and forbidden sets in the test and assert the implementation honors them:
```python
from hermia.sink.anonymize import anonymize_row, SUBMIT_WHITELIST

FORBIDDEN_KEYS = {
    "host", "fleet_host_name", "fleet_host_start", "raw_prompt", "raw_response",
    "raw_system", "output_preview", "run_id", "run_timestamp",
    "peak_cpu_pct", "peak_ram_used_gb", "peak_gpu_pct", "peak_vram_used_gb",
}

def test_anonymize_drops_all_forbidden_keys():
    row = {k: "SENSITIVE" for k in FORBIDDEN_KEYS}
    row.update({"model": "qwen2.5:32b", "tokens": 10})
    out = anonymize_row(row)
    assert FORBIDDEN_KEYS.isdisjoint(out.keys())

def test_anonymize_only_whitelisted_keys_plus_derived():
    row = {k: 1 for k in list(SUBMIT_WHITELIST) + ["host", "raw_response", "surprise_new_field"]}
    out = anonymize_row(row)
    allowed = SUBMIT_WHITELIST | {"failure_category", "hermia_version"}
    assert set(out).issubset(allowed)   # default-deny: unknown future fields never leak

def test_failure_reason_reduced_to_category():
    out = anonymize_row({"failure_reason": "ERROR: HTTPConnectionPool(host='192.168.1.5', port=11434)"})
    assert out["failure_category"] == "ERROR"
    assert "192.168" not in str(out)     # no host/IP detail survives
    assert "failure_reason" not in out

def test_no_sensitive_value_survives():
    sentinel = "host-marker-9f3a2c"
    row = {"host": sentinel, "raw_response": sentinel, "output_preview": sentinel,
           "model": "m", "tokens": 1}
    out = anonymize_row(row)
    assert sentinel not in repr(out)
```
Also add a hypothesis property test: for an arbitrary dict that includes random FORBIDDEN_KEYS with random string values, `set(out).issubset(allowed)` AND none of the forbidden values appear in `repr(out)`.
- [ ] **D2.2** Run the tests → fail (module missing).
- [ ] **D2.3** Implement `anonymize.py` (YOU author this; fleet output is reference only):
```python
from __future__ import annotations
from typing import Any
from hermia import __version__

SUBMIT_WHITELIST = frozenset({
    "model", "dimension", "test_id", "frameworks",
    "json_valid", "schema_compliant", "had_markdown_fence",
    "tokens", "elapsed_sec", "tokens_per_sec",
    "mode", "orchestration", "orchestration_version", "execution_path",
    "vram_server_gb", "model_size_server_gb",
    "score", "consistency_pct", "pass_count", "robustness_n",
    "run_index", "is_cold", "cold_warm_delta_tps", "signals",
})
_KNOWN_FAILURE_PREFIXES = ("SCHEMA_FAIL", "JSON_PARSE_ERROR", "EMPTY_RESPONSE",
                           "TIMEOUT", "OLLAMA_ERROR", "API_ERROR", "ERROR")

def _categorize_failure(reason: object) -> str:
    if not reason or not isinstance(reason, str):
        return "none"
    for p in _KNOWN_FAILURE_PREFIXES:
        if reason.startswith(p):
            return p
    return "other"

def anonymize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Default-deny: copy only whitelisted fields; reduce failure_reason to a
    category; stamp the Hermia version. Never emits host identity, raw text,
    client hardware metrics, run ids/timestamps, or any non-whitelisted field."""
    out: dict[str, Any] = {k: row[k] for k in SUBMIT_WHITELIST if k in row}
    out["failure_category"] = _categorize_failure(row.get("failure_reason"))
    out["hermia_version"] = __version__
    return out
```
- [ ] **D2.4** Tests green; ruff + mypy clean. Commit: `feat(sink): default-deny anonymizer for community submission (privacy core)`

## Task D3: SubmissionSink (opt-in POST, dry-run)
**Files:** `src/hermia/sink/submission.py`, `tests/unit/test_submission.py`

- [ ] **D3.1** Write `tests/unit/test_submission.py` (fleet-generate, then verify):
  - dry-run: `SubmissionSink(endpoint=None, dry_run=True).write(rows)` does NOT call `requests.post` and prints/returns the anonymized payload; every emitted row is `anonymize_row` of an input.
  - live: `SubmissionSink(endpoint="https://example.test/submit", token_env="X", dry_run=False)` with `requests.post` patched POSTs the anonymized payload; the Authorization header is built from the env var only (never logged); on non-2xx it does not raise (best-effort, logs a warning).
  - **Privacy guard test:** a row with `host`/`raw_response` set to a sentinel → the JSON body passed to `requests.post` does NOT contain the sentinel.
- [ ] **D3.2** Implement `submission.py`: `SubmissionSink.write` maps rows through `anonymize_row`, builds the payload, and either prints (dry-run) or POSTs with a short timeout; auth token sourced from `os.environ[token_env]` only; never logs the token or body at error level. No endpoint or `dry_run=True` ⇒ dry-run.
- [ ] **D3.3** Tests green; ruff + mypy clean. Commit: `feat(sink): SubmissionSink — opt-in anonymized POST with dry-run`

## Task D4: CLI wiring (`--submit` / `--submit-dry-run`)
**Files:** `src/hermia/app.py`, `tests/unit/test_app.py`. READ app.py's fleet branch first.

- [ ] **D4.1** Test: `--submit-dry-run` causes a `SubmissionSink` dry-run over the run's results after a fleet eval (patch `SubmissionSink` and assert `.write` called; assert no network). `--submit` (with endpoint env configured) constructs a live `SubmissionSink`. Default: neither flag ⇒ no submission.
- [ ] **D4.2** Add `--submit` and `--submit-dry-run` args; after `run_fleet` returns, if set, load the run's rows (`results.load_jsonl`) and call the sink. Endpoint + token come from env vars (e.g. `HERMIA_SUBMIT_URL`, `HERMIA_SUBMIT_TOKEN`); document that nothing is sent without `--submit`.
- [ ] **D4.3** Tests green; full suite green; ruff + mypy. Commit: `feat(cli): --submit / --submit-dry-run opt-in community submission`

## Task D5: Docs + manifest + gates
- [ ] Full suite, ruff, mypy green. Document the Sink seam + the opt-in/anonymized submission (README + docs/usage.md), emphasizing default-deny + what is/isn't sent. Update `docs/WORKSTREAMS.md` D row → in review + PR #. Commit: `docs: document Sink + opt-in anonymized submission`

## Self-review
- Spec coverage: Sink protocol ✓ (D1), port existing outputs behind adapters ✓ (D1), anonymizer ✓ (D2), SubmissionSink opt-in/dry-run ✓ (D3), CLI ✓ (D4). Server/auth/other sinks explicitly DEFERRED.
- Privacy: whitelist default-deny + property test that unknown future fields and forbidden values never leak (D2) — the load-bearing guarantee.
- Type consistency: `anonymize_row(row) -> dict`, `SUBMIT_WHITELIST` frozenset, `Sink.write(rows)` used identically across D1/D3/D4.

## Coordination
D is independent of C/E/F (new package + thin adapters; does not modify runner/fleet logic). Safe to run in parallel.
