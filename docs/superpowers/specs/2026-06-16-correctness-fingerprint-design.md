# Correctness Fingerprint + Sidecar Provenance — Design

**Date:** 2026-06-16
**Status:** Approved
**Scope:** v0.2.0 item #4 — correctness fingerprint (Ollama probe) + `_provenance` sidecar map
**Parent spec:** `2026-06-14-stack-fingerprint-design.md` (schema, multi-engine plan, empirical promotion criterion)
**Branch:** `feat/v0.2-correctness-fingerprint` off `dev` (post-merge of items #1–3)

## Decisions resolved in brainstorming

1. **Chat template hash = template body only.** The raw Jinja2 template string from `/api/show` is a stack property (same for every row on a given host+model). The system message is eval content that changes per test. Store the raw template string + its sha256 hash on the row. Rendered output can be reconstructed on demand from the stored template + test definition.

2. **Probe lives in a new `fingerprint/` package** (not in transport or runner). Per-engine probe modules behind a shared interface. Independently testable against fixtures. 0.2.x engine probes drop in as new files, zero changes to existing modules.

3. **In-memory cache per (host, model)** during a fleet run. Dict keyed by `(host_url, model_name)`, created at run start, discarded when the run ends. Probe fires once per model on each host; all repeats and tests for that model reuse the cached result. No disk persistence, no cross-run state.

## File layout

```
src/hermia/fingerprint/
  __init__.py          — public API: probe_model(), assemble_fingerprint()
  types.py             — dataclasses: CorrectnessFingerprint, ProbeResult, etc.
  cache.py             — FingerprintCache: dict wrapper keyed by (host, model)
  assemble.py          — layered merge (probe + declared) → fingerprint + _provenance
  probes/
    __init__.py        — engine detection (try endpoints; fleet YAML override)
    base.py            — ProbeResult protocol/base
    ollama.py          — /api/show + /api/ps → ProbeResult (0.2.0)
```

Future 0.2.x additions: `probes/vllm.py`, `probes/llamacpp.py`, `probes/sglang.py`, `probes/tgi.py` — each a new file, no changes to existing modules.

### Touched existing files

- **`fleet.py`** — creates `FingerprintCache`, calls `cache.get_or_probe()` once per (host, model) before the test/repeat inner loops, stamps `stack_fingerprint` + `_provenance` on each row.
- **`runner.py`** — standalone TUI path: calls `probe_model()` inline when `locality == "local"`.
- **`backend.py`** — `resolve_stack` preserved. Probe-derived `gpu_arch`/`runtime_version` merge into the result alongside the legacy fields (probe wins where present).

### Not touched

`app.py`, `screens.py`, transports, graders, sink, corpus_audit, `is_cold`/`cold_warm_delta_tps` (item #6).

## Ollama probe: what it collects

Two HTTP calls per (host, model):

### `/api/show` (POST, body: `{"name": "<model>"}`)

| Source field | Maps to | Notes |
|---|---|---|
| `digest` | `model.digest` | sha256 manifest hash — strongest identity |
| `model_info.general.architecture` | `model.architecture` | e.g. `"qwen2"`, `"llama"` |
| `model_info.general.family` | `model.family` | |
| `model_info.general.parameter_count` | `model.parameter_count` | raw count |
| `model_info.general.file_type` | `model.quant_method` | integer maps to Q4_K_M etc. |
| `quantization_level` | `model.quant_level` | human-readable string |
| `template` | `model.chat_template` | raw Jinja2 string |
| (computed) | `model.chat_template_hash` | `sha256(template.encode()).hexdigest()` |
| `details.parameter_size` | `model.parameter_size` | e.g. `"8.0B"` |

### `/api/ps` (GET) — model currently loaded

| Source field | Maps to | Notes |
|---|---|---|
| `size_vram / size` | `offload.residency_ratio` | guard `size == 0` |
| (computed) | `offload.execution_path` | ratio == 1 → `"gpu"`, 0 < r < 1 → `"partial"`, r == 0 → `"cpu"` |

**Defensive: Ollama #4840** — older versions omit `size_vram` when it's 0 (pure CPU). Treat missing `size_vram` as 0 → `"cpu"`. Test fixtures must reflect field-omission, not `size_vram: 0`.

### Engine version

Comes from `/api/version` (GET), but `runner.py` already fetches and stores `orchestration_version`. The probe accepts the already-fetched version as input rather than re-calling.

### Failure mode

If either call fails (timeout, connection error, 404, model not loaded for `/api/ps`), the probe returns nulls for affected fields. Provenance records `"api:error"`. The eval run continues — a fingerprint gap never blocks eval.

## `_provenance` sidecar map

Every result row gets a `_provenance` dict alongside `stack_fingerprint`.

### Source vocabulary (closed set)

| Value | Meaning |
|---|---|
| `"api"` | Retrieved from engine HTTP endpoint |
| `"declared"` | From fleet YAML `stack:` block |
| `"computed"` | Derived from other fields |
| `"local-probe"` | From local system commands (standalone TUI, locality="local") |
| `"agent"` | From hermia-agent sidecar (future — schema-ready, not populated 0.2.0) |
| `"api:error"` | Probe attempted and failed |
| `null` | No source available |

### Rules

- Every field in `stack_fingerprint` gets a provenance entry. No exceptions.
- If a field is `null`, provenance explains why (`null` = no source; `"api:error"` = tried and failed).
- Provenance is write-once per row — assembled at fingerprint time, never mutated.
- `assemble.py` builds both `stack_fingerprint` and `_provenance` in one pass using layered priority: agent > local-probe > api > declared > null.
- For 0.2.0, only `"api"`, `"declared"`, `"computed"`, `"api:error"`, and `null` appear.

### Example (fleet run, Ollama)

```json
"_provenance": {
  "model.digest": "api",
  "model.architecture": "api",
  "model.family": "api",
  "model.parameter_count": "api",
  "model.quant_method": "api",
  "model.context_length": "api",
  "model.chat_template": "api",
  "model.chat_template_hash": "computed",
  "runtime.engine": "api",
  "runtime.engine_version": "api",
  "offload.residency_ratio": "api",
  "offload.execution_path": "computed",
  "compute_backend.type": "declared",
  "substrate.delivery": "declared",
  "substrate.compute_topology": "declared"
}
```

## Integration

### Fleet path (`fleet.py`)

```
cache = FingerprintCache()

for model_entry in models:
    model = model_entry["name"]
    fingerprint, provenance = cache.get_or_probe(host_url, model, entry)

    for test in tests:
        for run_index in range(1, repeat + 1):
            result = run_test(...)
            result["stack_fingerprint"] = fingerprint
            result["_provenance"] = provenance
```

`cache.get_or_probe` returns cached result on hit, or calls `probe_model()` → `assemble_fingerprint()` on miss.

### Standalone TUI path (`runner.py`)

When `locality == "local"`, call `probe_model()` inline. No cache needed (one model at a time in standalone). In 0.2.0 the standalone TUI only supports Ollama, so the Ollama probe is always correct here. When 0.2.x adds other engines, the probe dispatches by detected engine type.

### Backward compatibility

`resolve_stack` continues to produce `gpu_arch`, `runtime_version`, `backend_stack` as top-level row keys. These fields remain for existing consumers (TUI, CSV, Postgres `_PG_COLUMNS`). Probe values merge alongside: where the probe provides `gpu_arch` or `runtime_version`, those win. Deprecation of the legacy fields is a separate decision, not 0.2.0 scope.

### Row schema additions

Two new top-level keys on every result row:
- `stack_fingerprint` — nested dict with `fingerprint_schema_version: 1` + the correctness fields
- `_provenance` — flat dict mapping dotted paths to source strings

## Testing

### New test files

```
tests/unit/fingerprint/
  test_probes_ollama.py    — probe against fixture data (no HTTP)
  test_assemble.py         — layered merge + provenance correctness
  test_cache.py            — hit/miss/key behavior
```

### Ollama probe tests

Against captured JSON fixtures mimicking `/api/show` and `/api/ps`:
- Happy path — all fields present, GPU-resident model
- Partial offload — residency_ratio between 0 and 1
- CPU-only — `size_vram` field **omitted** (Ollama #4840)
- Minimal response — some `model_info` fields missing → graceful nulls
- API error — returns nulls, provenance `"api:error"`
- Chat template hash — sha256 of known template matches expected

### Assemble tests

- Probe-only (no declared block) → provenance all `"api"` / `"computed"`
- Declared-only (probe failed) → provenance all `"declared"` / `null`
- Probe + declared overlap → probe wins, provenance says `"api"`
- Computed fields → provenance says `"computed"`
- Structural invariant: every `stack_fingerprint` field has a `_provenance` entry

### Cache tests

- First call invokes probe (mock), second call same key returns cached — probe not called again
- Different key triggers new probe call

### Integration (existing files)

- `test_fleet.py` — `stack_fingerprint` and `_provenance` appear on result row with correct shape
- `test_runner.py` — standalone path produces fingerprint when locality="local"

### Not tested this slice

vLLM/llama.cpp/SGLang/TGI probes, local system probes, cold/warm.
