# Stack Fingerprint — Design

**Date:** 2026-06-14
**Status:** Draft — round-2 review folded in + verified (see "Round-2 review synthesis", below). All open decisions resolved (logprob-KL = optional tier, 2026-06-14). Ready for writing-plans.
**Target:** v0.2.0 (determinism + reproducibility floor + topology bug-fix + correctness fingerprint + sidecar provenance, Ollama probe) → v0.2.x (richer local probes + vLLM/llama.cpp-server/SGLang/TGI engine probes, promotion-gated)
**Related memory:** [[project_hermia_substrate_axes]], [[backlog_hermia_data_versioning]], [[backlog_framework_versions_typed_structure]], [[project_hermia_probe]] (hermia-agent), [[backlog_rocm_execution_path]]

## Round-2 review synthesis & revised scope (2026-06-14)

This section is authoritative where it conflicts with anything below; the original schema/sections are retained as the field inventory and detailed design. Two adversarial reviews (and a self code-audit) converged. Key conclusions:

**A. A code audit invalidated an unstated assumption: the eval is not sampling-deterministic.**
28 of 30 corpus tests are single-turn → they run at **temperature 0.1, no seed** (`runner.py:312` passes `None`; transports default to `0.1` at `openai_compat.py:59` / `ollama.py:43`); no `top_p`/`top_k`/`repeat_penalty` pinning; **and the sampling config is not recorded on the row.** The harness has been injecting the very variance the fingerprint is meant to attribute. → **Determinism is the new #1 priority, above all hardware probing.** Pin `temperature=0`, fixed `seed`, single-stream (concurrency=1) for *all* runs; **record the full sampling config per row** (temperature, seed, top_p, top_k, repeat_penalty, num_predict, num_ctx) with provenance. The 895-row dataset is a **pre-determinism baseline** — valid for aggregate pass-rate, invalid for token-level divergence attribution.

**B. Determinism is necessary but NOT sufficient — measure the self-divergence floor first.**
*Necessary-but-not-sufficient + measure-the-floor-first is unanimous.* At `temp=0`, residual nondeterminism can still flip outputs run-to-run — and per Thinking Machines the dominant cause is **batch-variant FP-reduction order (reduction strategy varies with batch shape), NOT GPU atomics/concurrency** (a misconception that source explicitly debunks). Before claiming any *cross-stack* effect, characterize *intra-cell self-divergence*: N=10–20 identical re-runs on one fixed stack.
*The acceptance bar was a real Gemini-vs-ChatGPT split (NOT unanimous), resolved here:* Gemini wanted ~100%/near-0 intra-cell exact-match as the floor; ChatGPT wanted `within-stack variance << between-stack variance` (not necessarily zero). **Adopt ChatGPT's relative bar** — residual batch/FP nondeterminism makes a hard-0 floor unattainable on real GPUs, so it would disqualify legitimately-attributable stacks. Add a first-class `reproducibility` block per cell.

**C. Pass/fail is too lossy to prove the thesis — adopt a divergence metric ladder.**
Layers, application-level → token-level: (1) schema-pass (keep), (2) field-level correctness, (3) **canonical-JSON equality**, (4) **exact-output equality / normalized edit distance**. **RESOLVED (2026-06-14, Scott): logprob-KL is an OPTIONAL high-fidelity tier, never required.** The portable exact-match / canonical-JSON ladder is the *required* floor (works everywhere); logprob-KL switches on only where the engine exposes top-token logprobs. (Was a Gemini-require vs ChatGPT-don't-gate split; the don't-gate side won on verified portability evidence.) **Engine reality (verified 2026-06-14):** only **vLLM** is a solid source (full `logprobs`+`top_logprobs` over `/v1`); **TGI** exposes only a *scalar* logprob (no top-token logprobs); **llama.cpp**'s OpenAI path exposes none (only the non-OpenAI `/completion` `n_probs`); **Ollama** added logprobs in **v0.12.11** (native; OpenAI-compat path is inconsistent/version-gated, null on Ollama Cloud). So logprob-KL is "vLLM-tier (+ any future engine exposing top_logprobs), conditionally enabled by `engine_version`" — confirming it must stay optional, never a gate.

**D. Provenance = sidecar `_provenance` map, NOT per-leaf `_source` (unanimous).**
One map per row keyed by dotted path, e.g. `{"_provenance": {"model.digest": "api", "model.quant_method": "declared", "performance.gpu": "local-probe"}}`. Keeps the data tree flat/queryable for SQL/DynamoDB and preserves field-level merge fidelity (which record-level provenance would destroy). Supersedes the per-leaf `_source` tags in the schema below — those leaf `_source` lines now denote *which fields need a provenance entry*, not literal inline tags.

**E. Empirical promotion criterion (adopted) — the antidote to becoming a telemetry collector.**
A field is admitted to the **stable** fingerprint only after it has explained observed correctness variance in ≥1 controlled experiment. Until then it lives in an **experimental** namespace. The entire `hardware`/`software.drivers` tree ships experimental and gated by this rule.

**F. Framing: near-term divergence detector → durable reproducibility verifier / compliance oracle (unanimous).**
As the industry engineers determinism in (SGLang batch-invariant, vLLM offline modes), the durable category is *verifying* reproducibility claims and baseline-vs-edge conformance for regulated deployments — which survives, and is enlarged by, the determinism trend. Determinism kills *within-stack* noise (helps us); it does not erase *cross-stack* divergence (the thesis).

**G. MVP-proof-before-probes (unanimous scope cut).**
Before any OS/hardware probe: prove the thesis on ~6–8 correctness fields + a minimal A/B matrix — one sensitivity-prone prompt, same weights/quant/seed, vary ONE axis (engine OR quant), N=10–20 repeats. Success = self-divergence ≈ floor, cross-cell exact-mismatch > 0, pass-rate gap > noise band. Only then expand attribution resolution.

**Revised 0.2.0 order:** (1) determinism + sampling-config recording, (2) reproducibility/self-divergence floor, (3) topology bug-fix, (4) correctness fingerprint (digest/quant/arch/chat-template/KV-precision/deterministic-kernel-flag) + sidecar provenance, (5) divergence metric ladder, (6) MVP proof experiment, (7) cold/warm + backfill. Hardware/OS tree → 0.2.x, experimental, promotion-gated.

---

## Problem

Hermia's thesis is "the inference stack is the unit of analysis, not just the model" — but the v0.2 result schema under-captures the stack. Three concrete failures:

1. **Correctness bug (hard, must fix in 0.2.0) — CONFIRMED ACTIVE, and subtler than first stated:** `run_test` *does* gate `MetricsSampler` behind `is_local` (runner.py:295/302/336) — but `is_local` is computed by `detect_mode()` (runner.py:45) as **"hostname ∈ {localhost, 127.0.0.1, ::1}"**. The fleet reaches remote nodes through **SSH tunnels on loopback ports** (`hermia-fleet.yaml`: `host: http://localhost:11440`, `:11450`, …). So every tunnelled remote node evaluates `is_local=True` → the sampler runs → **the eval client's CPU/GPU/RAM peak telemetry is attached to rows actually computed on the remote node.** The loopback heuristic *is* the bug. This affected the tunnelled nodes in the 895-row run (their `peak_*` fields are the orchestrator's, not the node's). The current `is_local` gate does NOT fix it, and neither would a naive `is_local_ollama = loopback?` check — see the corrected Locality gate below.
2. **Thin fingerprint:** we capture Ollama version, a free-form `backend_stack` string, `gpu_arch` (usually null), `execution_path`. We do NOT capture model digest, quant method, backend type, driver/framework versions, offload split, container layer, cold/warm, or any substrate dimension.
3. **No provenance:** a null field is ambiguous — "not applicable," "not detectable here," or "not implemented yet" are indistinguishable.

## Goals

- A **complete, nested, typed, versioned** fingerprint schema covering everything we could plausibly want — populated incrementally.
- **Topology-aware population:** never attribute the eval client's hardware to a remote node.
- **Sidecar per-field provenance map** (keyed by dotted path; see Round-2 §D) so coverage is a queryable fact, not an ambiguous null.
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

## Multi-runtime support (vLLM / llama.cpp-server / SGLang / TGI)

The runtime layer is **engine-agnostic**: `runtime.engine` is an enum and fingerprinting is done by a **pluggable per-engine probe** (see Components). Transport already exists — `OpenAICompatTransport` covers the OpenAI `/v1` endpoints these engines serve; this work is purely the *fingerprint* probe layer.

The payoff beyond coverage: **these engines expose over HTTP the concurrency/batch fields Ollama hides** — the exact fields the batch-invariance finding makes correctness-critical. So `num_parallel` / `inflight_at_probe` move from agent-tier to **api-tier** on these engines:

| Engine | Detect via | Concurrency/batch source | Notable extra |
|--------|-----------|--------------------------|---------------|
| Ollama | `/api/version` | agent/log only | `/api/show` model_info |
| vLLM | `/version` + `/metrics` | `/metrics` `num_requests_running/waiting` (API) | dtype, served model |
| llama.cpp-server | `/props` | `/props` `total_slots`, `/slots` live (API) | `build_info` (build hash), `n_ctx`, `chat_template`. **NOT backend/GPU** — `/props` has no `system_info`; backend+GPU are log-scrape/agent only (verified 2026-06-14) |
| SGLang | `/get_server_info` | `/get_server_info` (API) | deterministic/batch-invariant flag — *expected* in `/get_server_info` `server_args` (reflects launch flags); **byte-confirm at implementation** (not a verified API contract) |
| TGI | `/info` | `/info` `max_concurrent_requests`, `max_batch_total_tokens` (API) | `model_dtype`, `quantize` |

Enum members all ship in 0.2.0 (free); probe **implementations** land across 0.2.x. Per-engine exact field shapes get a live byte-confirm at implementation time (same discipline as the Ollama confirm).

## Schema

A single nested object `stack_fingerprint` on each result row, split into a `correctness` sub-tree (fields that can change *tokens*) and a `performance` sub-tree (fields that change only *latency/throughput*) — keep the two from masquerading as each other. Provenance is a **sidecar `_provenance` map** keyed by dotted path (see Round-2 §D); the `_source` markers below are a field inventory of what needs a provenance entry, **not** literal inline tags. Provenance values: `agent | local-probe | api | declared | inferred | null`. Tier column: **0.2.0** (ship working) / **0.2.x** (additive) / **agent** (needs sidecar or logs).

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
    chat_template           # /api/show `template` — TOP real-world divergence source (Llama3 vs ChatML); 0.2.0
    _source

  runtime:
    engine: ollama | vllm | llama.cpp-server | sglang | tgi    # 0.2.0 enum (all members); per-engine probes land across 0.2.x
    engine_version          # ollama /api/version · vllm /version · llama.cpp /props · tgi /info   # 0.2.0
    engine_build            # llama.cpp build hash (also the engine inside ollama); vllm git sha    # 0.2.x (HTTP on llama.cpp /props)
    num_parallel            # configured concurrency. SOURCE VARIES: vLLM /metrics, llama.cpp /props total_slots, TGI /info = API; Ollama = agent. With single-stream eval (Round-2 §A) this is pinned to 1 for the run.
    inflight_at_probe       # COARSE "run-under-load" annotation only (Round-2 §1b/round-1): a point-in-time REST snapshot does NOT reflect per-decode-step batch composition — do NOT use for token-level attribution. Real batch-invariance signal = compute_backend.batch_invariant_kernels + controlled concurrency cells.
    num_ctx, flash_attention, kv_cache_type                    # llama.cpp /props = API; Ollama = agent
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
    batch_invariant_kernels: bool                              # 0.2.x — SGLang deterministic mode; EXPECTED via /get_server_info server_args (byte-confirm at impl, not a verified contract); others default false
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
    sampling:               # 0.2.0 — Round-2 §A. RECORDED per row (currently unrecorded); pinned for determinism.
      temperature           # pinned 0.0 (greedy)
      seed                  # recorded for provenance + any temp>0 cell. NOTE: at temp=0 (greedy/argmax) seed is a NO-OP — residual nondeterminism is batch/FP-driven, not RNG (addressed by single-stream + batch-invariant kernels), so determinism rests on temp=0, not the seed.
      top_p, top_k, repeat_penalty   # PER-ENGINE FIELD DIVERGENCE: Ollama options carries all of these; OpenAI /v1 (vLLM/llamacpp/tgi) takes top_p + seed but NOT top_k/repeat_penalty (extra_body on vLLM only) — assemble per transport.
      num_predict, num_ctx
      _source
    is_cold: bool                                             # 0.2.0 (real cold/warm pass)
    cold_warm_delta_tps                                       # 0.2.0
    gpu_shared | throttle_state                               # 0.2.x (gaming-gate signal)
    hermia_version, corpus_version                            # 0.2.0
    anonymization_level                                       # 0.2.0

  reproducibility:          # 0.2.0 — Round-2 §B. Per (model, stack, sampling) cell over N=10-20 identical re-runs.
    n_repeats
    exact_match_rate        # P(output == modal output) within the cell — the self-divergence floor
    pass_rate_mean, pass_rate_stddev
    _source                 # noise floor MUST be established before any cross-stack divergence claim
```

## Divergence metric ladder (Round-2 §C)

Pass/fail alone cannot show the math changed. Compute per output, application-level → token-level:
1. **schema_pass** (current metric — keep; product-relevant)
2. **field_correctness** — per-field equality against expected
3. **canonical_json_equal** — equality after canonicalization (catches `"OpenAI"` vs `"Open AI"` that both schema-pass)
4. **exact_output_equal** / **normalized_edit_distance** — token-level
5. **logprob_kl** — OPTIONAL high-fidelity tier (RESOLVED 2026-06-14: optional, never required), ONLY on engines exposing **top-token** logprobs. Solid: **vLLM**. Partial/none: TGI (scalar only), llama.cpp-OpenAI (none), Ollama (v0.12.11+ native, compat path inconsistent — gate on `engine_version`).

## Empirical promotion criterion (Round-2 §E)

A field graduates from `experimental.*` to the stable `correctness`/`performance` tree only after it has explained observed correctness variance in ≥1 controlled experiment. **Make this structural, not prose:** unproven fields are physically nested under `stack_fingerprint.experimental.*` (so "experimental" is a queryable fact, and nothing downstream can consume a field as load-bearing before promotion). The entire `hardware` / `software.drivers` tree ships there. Promotion = move the field into the stable tree + record the justifying experiment (commit/link), mirroring the `framework_versions` audit-trail discipline. Without the namespace the criterion is decorative.

## MVP proof experiment (Round-2 §G — do before any hardware probe)

Minimal field set: `engine, engine_version, model_digest, quant_method, chat_template, sampling(seed/temperature), deterministic_kernels`. A/B over a single axis (engine OR quant), everything else fixed, N=10–20 repeats per cell.

**Confound controls (the proof is worthless without these):**
- **Prompt choice — NOT the qwen3 case.** The project's own notes flag qwen3:8b as a *ceiling-effect / VRAM-pressure / thinking-mode-timeout* anomaly ([[backlog_qwen3_8b_anomaly]]; the 895-row qwen3 spread was a *timeout artifact*) — building an existence proof on it would measure capability/latency, not stack divergence. Choose a **deterministic-grader** test (strict-schema / numeric-reasoning / structured-extraction) whose grader is pure and exact (`SCHEMA_CHECKS`), so a cross-cell difference is attributable to sampling, not grader semantics.
- **Exclude latency artifacts.** Drop any run that hits `TIMEOUT`/`EMPTY_RESPONSE` (90s wall) from the exact-match and pass-rate computations; report timeout rate *separately*. A timeout on the heavier cell must never be read as divergence (9.3% of runs are hard DoS).
- **Grader independence.** Lead with **exact-output / canonical-JSON mismatch** (grader-free). Treat the **pass-rate gap as corroborating only** — the injection/jailbreak token-adoption graders carry a ~44–72% error band, so a pass/fail flip can come from the grader's boundary, not the stack. Do NOT lead with pass-rate on heuristic-graded tests.

**Success criteria:** self-divergence ≈ floor (near-0 exact-mismatch within a cell), cross-cell exact-mismatch > 0, pass-rate gap (on a deterministic-graded test) exceeding the measured noise band. This demonstrates existence of the effect; hardware/driver/PCIe probing is attribution-resolution optimization that only earns its place afterward.

## Population strategy (topology-aware, layered)

Per field, take the first available source in priority order:

1. **hermia-agent** (if a node-side agent response is present) — richest, universal. [future; schema-ready now]
2. **local-probe** — ONLY when the Ollama host is confirmed local (see below). Runs `nvidia-smi`/`rocm-smi`/`system_profiler`/`systemd-detect-virt`/`platform`. Describes the real inference machine.
3. **Ollama HTTP API** — always available: `/api/version`, `/api/show` (model identity/quant/arch), `/api/ps` (`size`/`size_vram` → offload proxy).
4. **declared** — fleet YAML `stack:` block; override / remote-node fallback.
5. else `null` with `_source: null`.

### Locality gate (the bug fix) — corrected
**A loopback check is NOT sufficient** — SSH tunnels make `localhost:PORT` a *remote* node (the active bug above). Locality must be **declared, not inferred**:
- Any host that appears in the **fleet config is remote by definition** — even on a `localhost:` tunnel port. The fleet path passes `is_local=False` explicitly; local-probe hardware/OS/virt and `peak_*` sampling are suppressed; those fields come from `declared` or stay `null`.
- The loopback heuristic (`detect_mode`) survives ONLY as the fallback for the **standalone single-host** invocation (no fleet config), where `localhost` genuinely is this machine.
- Concretely: thread an explicit `locality` (`local | remote`) from the run context into `run_test` instead of recomputing it from the host string; `fleet.py` sets `remote` for every YAML host. This replaces the `detect_mode`-derived `is_local`.

`run_context.gpu_shared`/throttle telemetry likewise only meaningful (and only recorded) when genuinely local by this declared rule.

### Offload proxy (HTTP, 0.2.0)
`/api/ps`: `residency_ratio = size_vram / size`. `==1` → `gpu`; `0<r<1` → `partial`; `==0` → `cpu`. Exact `gpu_layers/cpu_layers` is agent/log-only (confirmed: not exposed over HTTP).
**Defensive parsing (Ollama issue #4840):** older Ollama **OMITS `size_vram` entirely when it is 0** (the pure-CPU case) rather than returning `0` — treat a *missing* `size_vram` as `0` (→ `cpu`), and guard `size==0` against division. Record Ollama `engine_version` (behavior is version-dependent). The Testing section's "cpu case" fixture must reflect **field-omission**, not `size_vram:0`.

### Cold/warm (0.2.0, replaces the hardcoded stub)
Per (host, model): ensure model unloaded (Ollama `keep_alive:0` / unload), run the first test **cold** (`is_cold=true`, capture load+gen timing), then warm for the remainder; compute `cold_warm_delta_tps`. Removes the `is_cold=False / delta=None` hardcode at `fleet.py:222–223` (confirmed still present 2026-06-14).

### Determinism — implementation checklist (0.2.0, the #1 item)
The narrative "pin temp=0 + seed + single-stream and record sampling config" is NOT yet actionable — today both transports plumb **only** `temperature` (`ollama.py:43`, `openai_compat.py:59` build a one-key dict via `opts.get("temperature", 0.1)`), `_play_turns`/`run_test` forward only `temperature`, and `run_test:312` passes `temperature=None` for the single-turn path (28/30 tests → the 0.1 default). Concrete edits:
1. Extend **both** transport payloads to merge an opts-supplied sampling dict (`temperature, seed, top_p, top_k, repeat_penalty, num_predict, num_ctx`) — honoring the per-engine field divergence noted in the schema (OpenAI `/v1` has no `top_k`/`repeat_penalty`).
2. Thread the sampling dict through `_play_turns` (`runner.py:252–255`) and `run_test`.
3. **Fix `runner.py:312`** so the *single-turn* path also receives the pinned config (temp=0, fixed seed) — this is the actual variance source; setting temperature only and leaving the rest defaulted re-creates the bug.
4. **Add the ~7 sampling fields to the result-row dict** (`runner.py` return, ~`:375–408`) — this IS a row-schema change; call it out in the changelog/backfill.
5. Pin `seed` to a fixed constant (provenance + temp>0 cells), but rely on **temp=0** for greedy determinism (seed is a no-op at temp=0).

### Single-stream vs server concurrency (Round-2 §A, corrected)
**Client-side eval is already single-stream per host** — `fleet.py` runs `model → test → repeat` sequentially and the `ThreadPoolExecutor` parallelizes only *distinct hosts*; so for a single-host MVP cell **no eval-loop change is needed**. The correctness-critical variable (batch-invariance) is **server-side** effective batch (`OLLAMA_NUM_PARALLEL` / engine `num_parallel`), which the eval loop *cannot* pin — recording `num_parallel=1` on the row does NOT make the server run batch-1. Therefore: launch the server with `OLLAMA_NUM_PARALLEL=1` (or engine equivalent) and record it as a **declared run-context precondition** of the cell, not something the client enforces.

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
- **Stamp the pre-determinism regime (Round-2 §A):** `run_context.sampling` = `{temperature: 0.1 (single-turn) / 0.0 (multi-turn), seed: null, ...}` with `_source: inferred` (recovered from code, not from the row); `reproducibility` absent. These rows are valid for aggregate pass-rate ONLY — flag them so no downstream consumer cites them for token-level divergence.
- **Scrub the misattributed telemetry (Problem §1):** rows from **tunnelled remote nodes** (the `localhost:PORT` fleet hosts) had `is_local=True` → their `peak_cpu_pct/peak_ram_used_gb/peak_gpu_pct/peak_vram_used_gb` are the **orchestrator client's**, not the node's. Null these `peak_*` on every fleet-remote row (and any genuinely-local rows keep them). Check the actual run YAMLs (`~/hermia-run-*.yaml`) to confirm which hosts were tunnelled vs direct-IP before scrubbing.

## Components / isolation

- `fingerprint/locality.py` — `is_local_ollama(host)`.
- `fingerprint/probes/` — **per-engine** API probes behind one interface (`detect(host) -> bool`, `probe(host) -> dict`): `ollama.py`, `vllm.py`, `llamacpp.py`, `sglang.py`, `tgi.py`. Each maps its own endpoints to the shared `runtime`/`model`/`offload` slots; pure, testable against captured fixtures. Engine detection = probe signature (`/api/version` vs `/props` vs `/metrics` vs `/info`) with a fleet-YAML `engine:` override. v0.2.0 ships `ollama`; the other four land across 0.2.x.
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
