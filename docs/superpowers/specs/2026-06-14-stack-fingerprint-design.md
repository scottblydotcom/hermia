# Stack Fingerprint — Design

**Date:** 2026-06-14
**Status:** Draft for review
**Target:** v0.2.0 (schema + high-value tier + topology bug-fix) → v0.2.x (richer local probes)
**Related memory:** [[project_hermia_substrate_axes]], [[backlog_hermia_data_versioning]], [[backlog_framework_versions_typed_structure]], [[project_hermia_probe]] (hermia-agent), [[backlog_rocm_execution_path]]

## Problem

Hermia's thesis is "the inference stack is the unit of analysis, not just the model" — but the v0.2 result schema under-captures the stack. Three concrete failures:

1. **Correctness bug (hard, must fix in 0.2.0):** the fleet path runs `MetricsSampler` on the *eval client*, then attaches the client's CPU/GPU/RAM telemetry to rows produced by *remote* inference nodes. Client hardware is being recorded as if it were the node's. This corrupts the dataset.
2. **Thin fingerprint:** we capture Ollama version, a free-form `backend_stack` string, `gpu_arch` (usually null), `execution_path`. We do NOT capture model digest, quant method, backend type, driver/framework versions, offload split, container layer, cold/warm, or any substrate dimension.
3. **No provenance:** a null field is ambiguous — "not applicable," "not detectable here," or "not implemented yet" are indistinguishable.

## Goals

- A **complete, nested, typed, versioned** fingerprint schema covering everything we could plausibly want — populated incrementally.
- **Topology-aware population:** never attribute the eval client's hardware to a remote node.
- **Per-field provenance** so coverage is a queryable fact, not an ambiguous null.
- Ship a **high-value tier** that actually works in 0.2.0; light up the rest across 0.2.x; let `hermia-agent` fill the richest fields later — all into the same slots, no migration.

## Non-goals (this spec)

- Building the hermia-agent sidecar (separate workstream; this schema is agent-compatible so its data slots in).
- Per-OS hardware probes beyond the high-value tier (those are additive 0.2.x point releases).
- Changing the eval/grading logic.

## The three substrate axes (from [[project_hermia_substrate_axes]])

- **Compute topology → correctness** (single-node / multi-GPU / distributed-sharded)
- **Delivery substrate → availability** (LAN / Tailscale / P2P-relay / cloud)
- **Abstraction tier → observability** (bare-metal / IaaS / managed / PaaS)

These become first-class fields under `substrate`.

## Key finding shaping the schema: batch-invariance (Thinking Machines)

Same weights + same hardware + same sampler can still produce **different tokens** purely because of the **server-side batch a request lands in** — non-associative FP reductions pick different strategies at different batch sizes (thinkingmachines.ai; LMSYS SGLang deterministic follow-up). Implications:

- **Server concurrency / effective batch at request time is a CORRECTNESS dimension**, not just throughput. We must capture `num_parallel` and in-flight request count at probe time.
- These are exactly the fields Ollama does **not** expose over HTTP → this elevates `hermia-agent`/log-scraping from telemetry to **necessary for divergence attribution**. Without them, a batch-occupancy difference masquerades as unexplained stack divergence.
- Add a **`batch_invariant_kernels`** flag per backend (SGLang deterministic mode on; vanilla Ollama off) — highest-signal reproducibility predictor; directly bridges the "stack→divergence" empty quadrant.

## Schema

A single nested object `stack_fingerprint` on each result row. Every leaf group carries a `_source` provenance tag: `agent | local-probe | api | declared | inferred | null`. Tier column: **0.2.0** (ship working) / **0.2.x** (additive) / **agent** (needs sidecar or logs).

```
stack_fingerprint:
  fingerprint_schema_version: int                              # 0.2.0

  model:                                                       # all 0.2.0, via /api/tags + /api/show
    name, tag
    digest                  # sha256 manifest — STRONGEST identity ("same tag ≠ same weights")
    family, architecture
    parameter_count, parameter_size
    quant_method, quant_level, file_type
    context_length
    _source

  runtime:
    engine: "ollama"                                           # 0.2.0
    engine_version          # /api/version                     # 0.2.0
    llamacpp_build          # server log / agent                # agent
    num_parallel            # concurrency — CORRECTNESS         # agent (env/log only)
    inflight_at_probe       # in-flight reqs at probe — CORRECTNESS  # agent
    num_ctx, flash_attention, kv_cache_type                    # agent (not HTTP-readable live)
    _source

  offload:                                                     # 0.2.0 via /api/ps proxy
    model_total_bytes, vram_resident_bytes, residency_ratio
    execution_path: gpu | partial | cpu                        # derived from ratio
    gpu_layers, cpu_layers  # exact N/M                         # agent (log/CLI only)
    _source

  compute_backend:
    type: cuda | rocm | metal | vulkan | cpu                   # 0.2.0 (local-probe if local; declared if remote)
    cuda_version | rocm_version | metal_version | vulkan_version  # 0.2.x
    cudnn_version                                              # 0.2.x
    batch_invariant_kernels: bool                              # 0.2.x (predictor field)
    _source

  hardware:
    cpu: {model, microarch, cores_physical, cores_logical, base_ghz, boost_ghz, isa_flags[]}   # 0.2.x
    ram: {total_gb, type, speed_mts, configured_mts, channels, dimm_count}                      # 0.2.x (admin; macOS unified = N/A)
    gpu: [ {model, compute_capability, vram_total_gb, vram_bandwidth_gbps, mem_speed_mts,
            core_count, power_limit_w, temp_c} ]   # ARRAY (multi-GPU)                          # 0.2.x
    pcie: {gpu_link_gen, gpu_link_width, downgraded}  # LnkSta not LnkCap                       # 0.2.x (admin)
    motherboard: {model, chipset, bios_version}                                                 # 0.2.x (admin)
    nic: {model, link_speed_mbps}                                                               # 0.2.x
    _source

  software:
    os: {name, version, patch_level, kernel}                  # 0.2.0 (os/version cheap; patch_level 0.2.x)
    virtualization: bare-metal | docker | wsl2 | vm           # 0.2.0 (systemd-detect-virt etc.)
    drivers: {gpu, nic, chipset}                              # 0.2.x
    router: {litellm_version}                                 # 0.2.x (declared)
    _source

  substrate:
    delivery: lan | tailscale | p2p-relay | cloud-vpc         # 0.2.0 (Tailscale auto via 100.64/10; else declared)
    compute_topology: single-node | multi-gpu-tp | nvlink-pool | distributed-sharded | layer-split  # 0.2.0 declared
    abstraction_tier: bare-metal | iaas | managed-node | paas # 0.2.0 declared
    distributed: {node_count, hop_count, relay_or_direct, block_assignment}  # kwaainet          # agent/parser
    _source

  run_context:
    is_cold: bool                                             # 0.2.0 (real cold/warm pass)
    cold_warm_delta_tps                                       # 0.2.0
    gpu_shared | throttle_state                               # 0.2.x (gaming-gate signal)
    hermia_version, corpus_version                            # 0.2.0
    anonymization_level                                       # 0.2.0
```

## Population strategy (topology-aware, layered)

Per field, take the first available source in priority order:

1. **hermia-agent** (if a node-side agent response is present) — richest, universal. [future; schema-ready now]
2. **local-probe** — ONLY when the Ollama host is confirmed local (see below). Runs `nvidia-smi`/`rocm-smi`/`system_profiler`/`systemd-detect-virt`/`platform`. Describes the real inference machine.
3. **Ollama HTTP API** — always available: `/api/version`, `/api/show` (model identity/quant/arch), `/api/ps` (`size`/`size_vram` → offload proxy).
4. **declared** — fleet YAML `stack:` block; override / remote-node fallback.
5. else `null` with `_source: null`.

### Locality gate (the bug fix)
Add `is_local_ollama(host)`: true iff host resolves to loopback / this machine's own addresses. **Local-probe hardware/OS/virt detection runs ONLY when this is true.** In remote/fleet topology, those fields come from `declared` or stay `null` — never from the client. Replaces today's unconditional `MetricsSampler` attribution. `run_context.gpu_shared`/throttle telemetry likewise only meaningful (and only recorded) when local.

### Offload proxy (HTTP, 0.2.0)
`/api/ps`: `residency_ratio = size_vram / size`. `==1` → `gpu`; `0<r<1` → `partial`; `==0` → `cpu`. Exact `gpu_layers/cpu_layers` is agent/log-only (confirmed: not exposed over HTTP).

### Cold/warm (0.2.0, replaces the hardcoded stub)
Per (host, model): ensure model unloaded (Ollama `keep_alive:0` / unload), run the first test **cold** (`is_cold=true`, capture load+gen timing), then warm for the remainder; compute `cold_warm_delta_tps`. Removes the `is_cold=False / delta=None` hardcode in `fleet.py`.

## Anonymization tiers (for `hermia-submit`)

- **safe (publish):** ollama version, model digest, quant method/level, family, architecture, param count, backend type, compute_capability, vram tier (bucketed), substrate triplet, virtualization, os name+major, is_cold, batch_invariant flag.
- **coarsen (bucket):** exact VRAM GB → tier, exact RAM → tier, NIC/PCIe → gen only, node/hop counts → ranges, patch level → month.
- **redact:** hostname, exact driver build strings, user paths, Tailscale/KwaaiNet peer IPs/IDs, BIOS serials.

`run_context.anonymization_level` records which tier was applied so a submitted row self-describes its redaction.

## Schema versioning & migration

- `fingerprint_schema_version` starts at **1** in 0.2.0.
- After 0.2.0, point releases **only populate existing slots** — never reshape. Reshaping bumps the version.
- Today's pre-fingerprint rows are backfilled to v1 with declared substrate/backend + `_source: declared` and nulls elsewhere (see below), so the whole corpus is forward-compatible.

## Backfill of the 2026-06-13 dataset (895 rows)

One pass over today's result files once this schema's field names are locked:
- Re-stamp `hermia_version` → **0.2.0** (the producing code IS the 0.2.0 release code, pre-tag).
- Set `stack_fingerprint` v1 with: `compute_backend.type` per host (CUDA/Metal/Vulkan/CPU), `substrate.compute_topology` (single-node for the 4 backends, distributed-sharded for KwaaiNet), `substrate.delivery` (tailscale-tunnel for fleet, p2p-relay for KwaaiNet), `substrate.abstraction_tier`, all `_source: declared`.
- Carry existing `execution_path`, `backend_stack`, `vram_server_gb` into the new structure where present.
- Leave hardware/runtime-concurrency fields null (`_source: null`) — they weren't captured.

## Components / isolation

- `fingerprint/locality.py` — `is_local_ollama(host)`.
- `fingerprint/api_probe.py` — Ollama API → model/runtime/offload fields (pure, testable against fixtures).
- `fingerprint/local_probe.py` — per-OS hardware/OS/virt probes, gated by locality; each probe isolated + individually testable, graceful-degrades to null.
- `fingerprint/substrate.py` — Tailscale detection + declared-block merge.
- `fingerprint/assemble.py` — layered priority merge + provenance tagging → `stack_fingerprint` object.
- `backend.py:resolve_stack` — refactored to call `assemble`, replacing the free-form string and the misattributed `MetricsSampler` path.

## Testing

- Locality gate: loopback / LAN-IP / Tailscale-IP / hostname cases.
- API probe: against captured `/api/show` + `/api/ps` fixtures (incl. partial-offload and cpu cases).
- Local probes: per-OS parsers tested against captured command output fixtures; assert graceful null on missing tool.
- Assemble: priority order + provenance correctness; remote topology never yields local-probe hardware.
- Cold/warm: first row `is_cold=true`, delta computed; quiet-mode unaffected.
- Anonymization: each tier redacts/coarsens the right fields; `anonymization_level` stamped.

## Open items to confirm before implementation

- Byte-confirm the few agent-sourced fields' exact log formats when the agent work starts (out of scope here).
- KwaaiNet `hop_count`/`relay_or_direct` need a small parser over `shard` output — agent-tier, not 0.2.0.
