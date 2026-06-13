# v0.2.1 "Kwaai-Ready" — Design

**Date:** 2026-06-13
**Status:** Approved (design); pending spec review
**Branch:** `feat/v0.2.1-kwaai-ready`
**Target release:** v0.2.1 (patch on top of v0.2.0)

## Problem

Hermia already runs end-to-end on KwaaiNet with zero shim — `OpenAICompatTransport`
ships today and ran the full 28-test corpus against distributed Llama-3.1-8B on
2026-06-12. So "KwaaiNet compatibility" is no longer a build problem; it is a
**packaging + ease-of-use** problem.

Two concrete friction points remain for a Kwaai user:

1. **openai-compat hosts require a hand-written `models:` list.** `fleet.py`
   hard-errors when `models:` is omitted on an openai-compat host (the comment
   says "openai-compat hosts have no /api/tags endpoint"). That is half-right:
   they have no Ollama `/api/tags`, but they **do** serve `GET /v1/models`, which
   KwaaiNet's `shard api` returns (`id: unsloth/Llama-3.1-8B-Instruct`). The user
   is forced to type a long, typo-prone model id.
2. **No bundled example or quickstart** for either Kwaai path, so a new user must
   reconstruct the setup from scratch.

## Goal

Make Hermia "Kwaai-ready" with the smallest honest change: one client
convenience, one bundled example, one quickstart doc. No new subcommands, no
node-pinning, no governance work.

## Non-Goals (explicitly out of scope)

- **KwaaiNet node-pinning / reproducibility** — lives in Kwaai's Rust repo and is
  a research-grade problem (`shard api` has no `--name-filter`). Raise with Kwaai;
  do not solve here.
- **The M1 local perf bug** — Scott-specific, not a release gate.
- **Submission provenance distinction** (distributed KwaaiNet stack vs single
  local Ollama stack producing different leaderboard rows) — real and worth doing,
  but it is v0.3 stack-dimension work, not v0.2.1.
- **Leaderboard governance / "Responsible AI Certification" charter** — org work,
  not code.

## Design

### 1. Client convenience — model auto-discovery for openai-compat hosts

**`OpenAICompatTransport.list_models()`** (new method in
`src/hermia/transport/openai_compat.py`):
- Issues `GET {base_url}/v1/models`.
- Parses the OpenAI-standard response shape: `data["data"]` is a list of objects,
  each with an `id` field. Returns `list[str]` of ids.
- Defensive parsing consistent with the existing `generate()` style: tolerate a
  non-dict body, missing/`null` `data`, and non-dict elements (skip them) rather
  than raising on malformed responses.
- Honors the same `self._headers` (auth). Uses a short timeout (default 15s) —
  this is a lightweight metadata call, not generation, so it should not inherit
  `generate()`'s 90s.
- Raises `TransportError(kind="openai-compat")` on HTTP error or an `error` body,
  matching `generate()`.

**`fleet.py` trigger — the `models: auto` sentinel:**
- Today: `models` must be a list of strings, or absent.
- New: `models: auto` (the literal string `"auto"`) is accepted **only** for
  openai-compat hosts and means "discover via `GET /v1/models`."
- Behavior matrix for an openai-compat host:
  - `models: [a, b]` → unchanged (explicit list, used as today).
  - `models: auto` → call `list_models()`, evaluate every discovered id.
  - `models:` omitted → unchanged: the existing clear error
    ("requires an explicit 'models:' list") still fires. Omission is **not** a
    discovery trigger.
- Rationale for the sentinel over omission-as-trigger: a user pointing at a cloud
  endpoint (e.g. `api.openai.com`) with no list would otherwise auto-enumerate
  every model the provider exposes (gpt-4, dall-e, whisper, …) — a footgun and a
  cost/time explosion. An explicit opt-in keeps the default safe while making the
  local/KwaaiNet/LiteLLM/vLLM case trivial. `models: auto` is also arguably easier
  than typing a long model id.
- For ollama hosts, `models: auto` is rejected by validation (ollama already
  auto-discovers via `/api/tags` when `models:` is omitted; `auto` is redundant
  and would be ambiguous).

**Validation change in `load_fleet_config`:** the `models` field may now be either
a list of strings (as today) or the exact string `"auto"`. If it is `"auto"` and
the transport is not `openai-compat`, raise a clear `ValueError`.

**Discovery failure handling:** if `list_models()` fails (host down, malformed
response) for an `auto` host, emit a warning via `stderr_fn` and skip the host —
consistent with how other per-host failures degrade — rather than aborting the
whole fleet run.

### 2. Bundled example — `examples/kwaainet-fleet.yaml`

```yaml
fleet:
  - name: kwaainet-metro
    host: http://localhost:11435        # kwaainet shard api --port 11435
    transport: openai-compat
    models: auto                        # discovers via GET /v1/models
    stack:                              # documents the distributed/relay stack
      orchestration: kwaainet
      topology: distributed-sharded
      transport: relay
```

(If `examples/` does not yet exist, create it. The existing fleet YAMLs at the
repo root stay where they are; new Kwaai-specific example goes under `examples/`.)

### 3. Kwaai quickstart — `docs/kwaai-quickstart.md`

Covers both paths, scaled so a Kwaai community member can self-serve:

- **Path A — pAI-OS (the easy default).** pAI-OS runs Ollama on `:11434`, which is
  Hermia's native default. Just `hermia --host http://localhost:11434`. Then the
  `hermia-submit` flow to the public leaderboard.
- **Path B — KwaaiNet distributed.** The `shard api --port 11435` bringup (from
  the verified 2026-06-12 runbook), point Hermia at `examples/kwaainet-fleet.yaml`,
  run `hermia --fleet examples/kwaainet-fleet.yaml`. Note the relay-speed caveat
  (full corpus is slow; run subsets) and that node-pinning is a known gap.
- **Submit.** `hermia-submit --dry-run` then `hermia-submit` against the live
  endpoint; confirm the returned public URL renders.

### 4. Tests

- `OpenAICompatTransport.list_models()`: happy path (well-formed `data[].id`),
  malformed body (non-dict, missing `data`, non-dict elements → skipped), HTTP
  error → `TransportError`, auth headers forwarded.
- `load_fleet_config`: `models: auto` accepted for openai-compat; `models: auto`
  rejected for ollama; list form still valid.
- `fleet.py` resolution: `auto` host calls discovery and evaluates discovered ids;
  discovery failure warns + skips host without aborting the run.

## Components & boundaries

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `OpenAICompatTransport.list_models()` | One HTTP call + defensive parse → `list[str]` | `requests`, `TransportError` |
| `load_fleet_config` (validation) | Accept/validate the `auto` sentinel | yaml only |
| `_run_host_eval` (fleet) | Wire `auto` → discovery, degrade on failure | transport, runner |
| `examples/kwaainet-fleet.yaml` | Copy-paste-ready KwaaiNet config | — |
| `docs/kwaai-quickstart.md` | Both-path onboarding | — |

## Data flow

```
fleet YAML (models: auto, openai-compat)
        │  load_fleet_config validates sentinel
        ▼
_run_host_eval: transport.list_models() ──GET /v1/models──▶ KwaaiNet shard api
        │  list[str] of model ids
        ▼
_resolve_models → per-model eval loop (unchanged downstream)
```

## Risks & mitigations

- **Cloud-API model explosion** → mitigated by the explicit `auto` opt-in; omission
  keeps the error.
- **Malformed `/v1/models` response** → defensive parse + per-host warn-and-skip.
- **Docs drift from KwaaiNet CLI changes** → quickstart cites the binary path and
  port explicitly and dates the runbook so staleness is visible.

## Release mechanics

- Branch `feat/v0.2.1-kwaai-ready` off `dev`.
- Lands after v0.2.0 ships (this is a patch on top). If v0.2.0 has not yet been
  tagged when this is ready, it can fold into v0.2.0 — but it is designed as an
  independent, additive 0.2.1.
- Version bump `pyproject.toml` to `0.2.1` as the final step of the
  implementation plan (not before v0.2.0 exists).
