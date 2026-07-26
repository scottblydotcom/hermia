# Topology bug fix — declared locality (Hermia v0.2.0, item #3)

**Date:** 2026-06-15
**Status:** Approved (brainstorming complete)
**Scope:** v0.2.0
**Predecessor slices:** determinism (PR #113), reproducibility floor (PR #114)
**Successor:** correctness fingerprint + sidecar provenance (item #4)

## Problem

`runner.run_test()` derives `is_local` by passing the host string through `detect_mode()`, which returns `"local"` when the URL's hostname is `localhost`, `127.0.0.1`, or `::1`. This is correct for standalone single-host runs, but it is **wrong** for fleet runs.

Fleet entries reach remote nodes via SSH tunnels on loopback ports — e.g. `http://localhost:11440` is forwarded through the gateway to the remote node's `127.0.0.1:11434`. The hostname is loopback at the TCP layer, but the work happens on a remote machine. `detect_mode()` returns `"local"`, so `is_local=True`, so:

1. `MetricsSampler` runs against the orchestrator's own CPU/GPU/RAM and the resulting `peak_*` values are misattributed to a row whose work was computed elsewhere.
2. The `mode` field is stamped `"local"` when it should be `"fleet"`.

Every row produced by a tunnelled fleet run since v0.1.x carries this misattribution. The 895-row pre-determinism baseline is affected.

The root cause is **inference**: deriving locality from the shape of a string that's been deliberately rewritten by an intermediate network layer. The fix is to make locality **declared by the caller**, not inferred by `run_test()`.

## Principle

> Locality must be declared, not inferred.

`detect_mode()`'s loopback heuristic is correct in any path that has no intervening tunnel layer. It is wrong only when a caller knows more than the URL reveals. That caller — `fleet.py` — must declare the truth explicitly. Every other caller continues to rely on the heuristic.

## Architecture

### Two call paths, one declaration

| Path | Caller | Locality |
|---|---|---|
| TUI single-host (loopback default) | `app.py` | omits param → `detect_mode("localhost:11434")` → `"local"` |
| TUI single-host (remote URL via `--host`) | `app.py` | omits param → `detect_mode("node-a:11434")` → `"fleet"` |
| Fleet via YAML | `fleet.py::_run_host_eval` | **explicit `locality="remote"`** |
| openai-compat / API host | either | `is_api_mode=True` short-circuits locality entirely |

### `run_test()` signature change

```python
def run_test(
    model: str,
    test: dict[str, Any],
    sampler: MetricsSampler,
    host: str | None = None,
    headers: dict[str, str] | None = None,
    transport: Any | None = None,
    *,
    locality: str | None = None,  # NEW: "local" | "remote" | None
) -> dict[str, Any]:
```

New keyword-only parameter, default `None` (preserves the existing call surface; nothing breaks).

### Derivation rule

```python
if locality is not None and locality not in ("local", "remote"):
    raise ValueError(f"locality must be 'local', 'remote', or None; got {locality!r}")

resolved = locality if locality is not None else detect_mode(_host)
is_local = (not is_api_mode) and (resolved == "local")
```

Explicit declaration wins; `None` falls back to the existing heuristic.

### `fleet.py` change

One line. In `_run_host_eval`, the `run_test(...)` call adds `locality="remote"`:

```python
result = run_test(
    model, test, sampler,
    host=host_url, headers=headers, transport=host_transport,
    locality="remote",
)
```

No YAML schema change. No `_parse_fleet_yaml` update. Fleet entries are always remote in v0.2.0 (the local-machine-in-a-fleet case is intentionally not supported — use standalone TUI for that, or wait for the hermia-agent sidecar in v0.2.x).

### `app.py` change

None. The existing `detect_mode(args.host) == "fleet"` call for the TUI's `fleet_mode` flag is correct for the standalone single-host path and stays as-is.

## What does NOT change

- `detect_mode()` — unchanged signature, unchanged behavior, still public.
- Result row shape — same fields, same types.
- `export.py::_PG_COLUMNS` — same column set.
- YAML schema — no new fields.
- Transport layer — untouched.
- TUI rendering — untouched.

## User-facing UX

| Scenario | Before fix | After fix |
|---|---|---|
| `hermia` (default loopback TUI) | `mode="local"`, peaks populated | identical |
| `hermia --host http://remote:11434` | `mode="fleet"`, peaks null | identical |
| `hermia --fleet config.yaml` (tunnel hosts) | `mode="local"`, peaks misattributed ❌ | `mode="fleet"`, peaks null ✓ |
| openai-compat host in fleet | `mode="api"`, peaks null | identical |

The fix is invisible to users in three of four scenarios. The fourth (fleet via tunnels) finally stamps the truth.

## Data implications (the broader context)

Fleet rows previously carried the orchestrator's `peak_*` telemetry misattributed as the remote node's. After the fix, fleet rows have null `peak_*`. That is a *correctness improvement* and an *observability regression* — the data is now truthful but contains less information. The observability gap is exactly what the hermia-agent sidecar (Workstream B, v0.2.x) closes: each node self-reports its own hardware telemetry over an authenticated endpoint, and the orchestrator stamps the remote-reported values on each row. v0.2.0 ships the truth ("we don't have remote hardware data"); v0.2.x ships the data.

## Backfill (private — hermia-research, not the public repo)

The bug fix above only affects rows produced *after* the fix lands. The existing 895-row pre-determinism baseline still carries the misattribution and must be corrected separately.

This work is **private** — the affected dataset is local development data, the script targets `~/Git/hermia/results/` on Scott's machine, and the realistic user base for a generic migration tool is currently zero (Hermia has only been run by Scott and a couple of internal testers; Kwaai testers are coming in on v0.2.0 fresh). The backfill script lives in `~/Git/hermia-research/` and is not shipped in the public repo.

### Affected-row predicate

```
fleet_host_name != None  AND  mode == "local"
```

The conjunction is unambiguous:
- A true standalone local row has `fleet_host_name=None` → not matched.
- A correctly stamped fleet row already has `mode="fleet"` → not matched.
- A tunnelled fleet row has both fields set → matched.

### Mutations on each matched row

| Field | Before | After |
|---|---|---|
| `peak_cpu_pct` | float | `None` |
| `peak_ram_used_gb` | float | `None` |
| `peak_gpu_pct` | float | `None` |
| `peak_vram_used_gb` | float | `None` |
| `mode` | `"local"` | `"fleet"` |

### Mechanism

- Script: `~/Git/hermia-research/scripts/backfill_topology_locality.py`
- Walks `~/Git/hermia/results/eval_*.jsonl`
- Applies the predicate, applies the mutations
- Uses `hermia.results.patch_results()` for in-place JSONL rewrite
- Regenerates `.csv` sibling from the patched JSONL
- Prints per-file `(affected_rows / total_rows)` summary
- `--dry-run` default; `--apply` to write
- Idempotent: a row already corrected (`mode="fleet"`) is not matched on re-run

### Tests (deferred to implementation phase)

Backfill script tests are useful but not yet written — written during implementation, not planning. Public-repo tests for the bug fix itself remain in scope per the test plan below.

### Postgres status

Confirmed 2026-06-15: no `HERMIA_PG_DSN` set, no Postgres push activity in shell history, the most recent eval (`eval_20260614_132321.jsonl`) is unpushed. JSONL is the source of truth. Patching JSONL is sufficient; no DB migration needed.

## Test plan (public repo)

### Unit tests in `tests/unit/test_runner.py`

| Test | Verifies |
|---|---|
| `test_run_test_locality_explicit_remote_overrides_loopback_host` | `locality="remote"` + loopback host → `is_local=False`, `peak_*` null, `mode="fleet"` |
| `test_run_test_locality_explicit_local` | `locality="local"` + remote host → `is_local=True`, sampler runs, `mode="local"` |
| `test_run_test_locality_none_falls_back_to_detect_mode` | `locality=None` + loopback host → existing behavior preserved (`mode="local"`) |
| `test_run_test_locality_invalid_value_raises` | `locality="weird"` → `ValueError` |
| `test_run_test_api_mode_short_circuits_locality` | `is_api_mode=True` + `locality="local"` → still `mode="api"`, sampler not run |

`detect_mode` tests in `test_runner.py:393–422` stay as-is.

### Integration test in `tests/integration/test_fleet.py`

| Test | Verifies |
|---|---|
| `test_fleet_run_stamps_mode_fleet_on_loopback_tunnel_rows` | Fleet entry with `host="http://localhost:11440"` + mocked transport → resulting rows have `mode="fleet"` and `peak_* is None` |

### Determinism / reproducibility regression check

The existing `STABLE_FIELDS` integration test from the determinism slice should continue to pass — `mode` and `peak_*` are not in the stability set but a re-run with the fix in place should produce row shapes identical to before for non-fleet scenarios.

### Test count: ~6 new tests.

## Rollout

1. **Branch:** `feat/v0.2-topology-locality` off `dev` (currently `dda9293`).
2. **Implementation order:**
   - Runner change + 5 unit tests
   - `fleet.py` one-liner + integration test
   - Private backfill script in `hermia-research/` (separate session or commit)
   - Run backfill with `--dry-run` against `~/Git/hermia/results/`, verify ~895 affected rows expected, then `--apply`
3. **Commit shape (public repo, 2 commits):**
   - `feat(runner): declared locality parameter; preserve detect_mode fallback`
   - `feat(fleet): declare locality=remote for all fleet hosts`
4. **Gates (per [[feedback_code_review_workflow]]):**
   - `/code-review` from `~/Git/hermia` cwd
   - Push, post `/gemini review` comment, iterate until clean
   - Opus `/review` in-window
   - All gates green before merge
5. **Merge:** PR to `dev`.
6. **Next:** item #4 — correctness fingerprint (digest/quant/arch/chat-template/KV-precision) + sidecar `_provenance` map.

## Cross-references

- Source of truth: `~/Git/hermia/docs/superpowers/specs/2026-06-14-stack-fingerprint-design.md` (Problem §1 + "Locality gate — corrected")
- Predecessor: `2026-06-15-reproducibility-floor-design.md`
- Related: `[[project_hermia_stack_fingerprint]]`, `[[project_hermia_data_accounting]]`, `[[backlog_hermia_agent_liveness]]`
