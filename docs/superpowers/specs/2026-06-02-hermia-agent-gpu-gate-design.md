# hermia-agent — GPU Gaming-Gate Endpoint (v1)

**Date:** 2026-06-02
**Status:** Approved design — ready for implementation plan
**Workstream:** v0.2 Workstream B (hermia-agent sidecar)
**Scope of this spec:** First cut. The `GET /gpu` gaming-gate endpoint only.
`GET /fingerprint` is explicitly deferred to a later iteration.

---

## 1. Purpose

`hermia-agent` is a lightweight static Go binary that runs on each fleet node. Its first
and only endpoint in this iteration answers one question for the orchestration layer:

> **Is the owner of this machine actively gaming right now?**

If yes, the fleet should skip dispatching inference work to that node. This lets Scott
lean harder on the local fleet for inference without risking a visible stutter during
someone's gaming session — a production-grade replacement for the coarse Ollama-liveness
proxy used today (windows_exporter's native GPU collector was tried and rejected: it
crashes the 3090 service).

### The validated signal

Windows PDH GPU Engine counters break GPU utilization out **per engine type**. Empirical
three-state capture on the target box (`.20`, AMD RX 7800 XT, ROCm, Ollama 0.24) confirmed:

| State | `engtype_3D` avg | `engtype_Compute` avg |
|-------|------------------|------------------------|
| Idle (model loaded, no generation) | 0.1% | ~0% |
| Inference (active ROCm generation) | 0.1% | ~1.75M% (cooked) |
| Gaming (benchmark) | 93.6% | ~2k% variable |

**Decision rule:** `engtype_3D > 10%` → owner is gaming → skip dispatch. The 10% threshold
gives a ~9.9-point margin above the inference noise floor. ROCm/HIP inference registers as
`engtype_Compute`, leaving `3D` flat — so 3D-engine % cleanly separates gaming from
inference. (Source: `project_gaming_gate_prototype` memory; capture tool
`hometech/gpu_engine_capture.ps1`.)

---

## 2. Scope & Non-Goals

### In scope (v1)
- A single authenticated `GET /gpu` endpoint
- On-demand PDH query (no background polling)
- Per-engine-type utilization aggregation
- Gaming gate boolean derived from `engtype_3D` vs a configurable threshold
- Bearer-token auth (constant-time compare)
- Configurable port, bind address, threshold, error mode, node id
- Static Windows amd64 binary, isolated Go module under `cmd/hermia-agent/`
- Fail-closed / fail-open error modes

### Explicitly NOT in scope (v1)
- `GET /fingerprint` (GPU model, VRAM, driver, ROCm/CUDA/Ollama versions) — next iteration
- TLS / transport encryption — cleartext on isolated VLAN only; see
  `backlog_hermia_agent_tls` (HARD GATE before any non-lab deployment)
- Per-GPU isolation on multi-GPU nodes — global sum for v1; parse retains the
  `phys_N`/`gpu_N` discriminator so per-GPU is a later enhancement, not a rewrite
- Background sampling / caching — deliberately rejected (see §6)
- Non-Windows builds — Linux/macOS agents come with the fingerprint work
- The Python receiver/consumer side in Hermia — separate task after the API is proven

---

## 3. Architecture

### Directory layout
```
cmd/hermia-agent/
├── main.go              — flags/env, server setup, auth middleware, signal handling
├── gpu_windows.go       — PDH query, engine aggregation, gate decision (//go:build windows)
├── gpu_aggregate_test.go — table-driven tests for the pure aggregation function
├── gpu_aggregate.go     — pure aggregation functions (cross-platform)
├── auth.go              — bearer middleware (crypto/subtle), platform-agnostic
├── auth_test.go         — auth middleware tests
├── go.mod               — own module; one external dep: golang.org/x/sys
└── go.sum
```

The Go module is independent of the Python package — no toolchain crossover. Python CI
ignores it; a dedicated `agent.yml` workflow handles the Go build.

### Component boundaries
- **`gpu_windows.go`** knows PDH and engine math. It does **not** know about HTTP. It
  exposes a function returning the engine map + gate decision, plus a **pure**
  `aggregateEngineCounters([]pdhSample) map[string]float64` that is unit-testable without
  Windows.
- **`auth.go`** is a stdlib `http.Handler` middleware. Platform-agnostic, independently
  testable.
- **`main.go`** wires flags → server → middleware → handler. Owns the response schema and
  the fail-closed/fail-open policy.

### Request flow (`GET /gpu`)
```
request → auth middleware (constant-time bearer check)
        → [401 if invalid, BEFORE any PDH work]
        → PDH on-demand query (see §4)  [per-request independent handle; no mutex needed]
        → aggregate engines, compute gaming = 3D > threshold
        → write JSON response per error mode
```

Auth is checked **before** any PDH work, so an unauthenticated flood is rejected at
constant-time-compare cost and never reaches the 1-second PDH sleep.

---

## 4. PDH Query (on-demand, per request)

Ported from the validated `gpu_engine_capture.ps1` logic. Uses
`golang.org/x/sys/windows` and **`windows.NewLazySystemDLL("pdh.dll")`** — the System-DLL
variant forces the loader to `%SystemRoot%\System32`, closing the DLL-hijacking hole that
plain `NewLazyDLL` leaves open (working-directory search).

1. `PdhOpenQuery`
2. `PdhAddEnglishCounterW` — `\GPU Engine(*)\Utilization Percentage`
3. `PdhCollectQueryData` — **baseline** (establishes counter state; values discarded)
4. `time.Sleep(1 * time.Second)` — required for the rate counter to compute a valid delta
5. `PdhCollectQueryData` — actual reading
6. `PdhGetFormattedCounterArrayW` — all instances as doubles
7. Parse each instance name; sum `CookedValue` per engine type
8. `PdhCloseQuery` (always, via `defer`)
9. `gaming = engines["3D"] > threshold`

### Instance-name parsing
A typical instance looks like:
`pid_4132_luid_0x00..._phys_0_gpu_0_engtype_3D`

- Extract engine type after `engtype_` → buckets: `3D`, `Compute`, `Copy`, `VideoDecode`,
  `VideoEncode`, anything else → `Other`.
- **Retain** the `phys_N` / `gpu_N` discriminator in the parsed struct even though v1 sums
  globally. This makes per-GPU isolation (multi-GPU nodes: iGPU + dGPU) a future
  enhancement without reworking the parser. Documented known-limitation for v1: a node
  gaming on GPU 0 and idle on GPU 1 reports a single global gaming=true.

### Concurrency
A package-level `sync.Mutex` serializes PDH collections so two overlapping requests share
a single query rather than firing parallel PDH work. Correctness is not at stake (each
query handle is independent) — this is contention insurance and avoids redundant driver work.

---

## 5. HTTP API

### `GET /gpu`

**Auth:** `Authorization: Bearer <token>` required.

**Success (200):**
```json
{
  "status": "ok",
  "node_id": "fleet-node-20",
  "gaming": true,
  "gate_threshold_pct": 10.0,
  "engines": {
    "3D": 94.2,
    "Compute": 1847.3,
    "Copy": 1.1,
    "VideoDecode": 0.0,
    "VideoEncode": 0.0
  },
  "sampled_at": "2026-06-02T14:23:01Z"
}
```

**PDH failure — `fail-closed` mode (200):** safe default — assume gaming so the fleet
never dispatches into an unread signal.
```json
{
  "status": "ok",
  "node_id": "fleet-node-20",
  "gaming": true,
  "gate_threshold_pct": 10.0,
  "engines": {},
  "sampled_at": "2026-06-02T14:23:01Z",
  "error": "pdh_query_failed",
  "error_detail": "PdhCollectQueryData returned 0xC0000BC4"
}
```

**PDH failure — `fail-open` mode (503):** caller decides what to do with a missing signal.
```json
{
  "status": "error",
  "node_id": "fleet-node-20",
  "gaming": false,
  "gate_threshold_pct": 0,
  "engines": null,
  "error": "pdh_query_failed",
  "error_detail": "PdhCollectQueryData returned 0xC0000BC4",
  "sampled_at": "2026-06-02T14:23:01Z"
}
```
> **Datacenter-scale caveat:** at 2,000–100,000 nodes the 503 body may be stripped by
> proxies/load balancers in the path. Not a concern on the direct-VLAN lab path. Tracked
> in `backlog_hermia_agent_503_body`.

**Auth failure (401):**
```json
{ "status": "error", "error": "unauthorized" }
```

### Design rationale: agent has no fleet policy
The agent answers "is the owner gaming?" — it does **not** decide dispatch. Fail-closed vs
fail-open is a per-environment knob, not a hardcoded opinion. The orchestration layer owns
retry budgets, node priority, and run criticality; the sidecar must not. Local lab runs
fail-closed (never accidentally dispatch into a gaming session); production uses the most
secure variant of fail-open so the orchestrator can manage fleet-wide policy.

---

## 6. Rejected Alternative: Background Sampler

A background goroutine polling PDH every ~2s with the handler returning a cached snapshot
was considered (and was Gemini's headline recommendation). **Rejected** for two reasons:

1. **Wrong scale model.** The agent runs on each node; 2,000 nodes = 2,000 agents each
   handling **one** request per run — not one agent holding 2,000 connections. There is no
   connection-pool exhaustion to design around. The 1-second hold is a single node
   answering its own occasional query.
2. **Passive-endpoint principle.** This runs on someone's personal gaming machine. A
   process that wakes the GPU performance counters every second in perpetuity is exactly
   the impolite background activity we are trying to avoid. The agent should do work
   **only when a dispatch decision is actually pending** — checked once per run, not on a
   perpetual timer.

The on-demand model is correct for "check liveness/readiness/hardware once per run." The
1-second PDH baseline cost is a non-issue at that call frequency.

---

## 7. Configuration

| Flag | Default | Env override |
|------|---------|--------------|
| `--port` | `11435` | `HERMIA_AGENT_PORT` |
| `--bind` | `0.0.0.0` | `HERMIA_AGENT_BIND` |
| `--token-env` | `HERMIA_AGENT_TOKEN` | — |
| `--threshold` | `10.0` | `HERMIA_AGENT_THRESHOLD` |
| `--error-mode` | `fail-closed` | `HERMIA_AGENT_ERROR_MODE` |
| `--node-id` | OS hostname | `HERMIA_AGENT_NODE_ID` |

- `--token-env` names the env var holding the token — **never** the token value itself
  (AGENTS.md rule #11). If that env var is unset at startup, the binary exits with a fatal
  error rather than serving unauthenticated.
- `--error-mode` accepts `fail-closed` | `fail-open`.
- HTTP server: explicit `ReadTimeout` and a `WriteTimeout` set safely above the 1s PDH
  sleep (e.g. 5s). Graceful shutdown on SIGINT/SIGTERM.

---

## 8. Security Posture (v1)

- **Cleartext bearer over HTTP, isolated VLAN only.** The token is sniffable in transit.
  Acceptable for local-lab hardware testing on `.20` and nothing else.
- The binary prints a **prominent startup warning** when serving without TLS.
- README and this spec carry an "isolated-VLAN-only — not for untrusted networks" banner.
- **HARD GATE:** production transport security (TLS, without forcing Tailscale) must be
  solved before any non-lab deployment. Tracked in `backlog_hermia_agent_tls`, including
  the commander-as-CA deployment idea.
- Constant-time token comparison via `crypto/subtle` — same cost regardless of where the
  token first differs (timing-attack mitigation).
- Auth evaluated before any PDH work (cheap rejection of unauthenticated requests).

---

## 9. Build

```bash
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -o hermia-agent.exe ./cmd/hermia-agent
```

- One external dependency: `golang.org/x/sys` — Go-team maintained, effectively extended
  stdlib (the safe dependency per AGENTS.md rule #1). Everything else is stdlib.
- `CGO_ENABLED=0` → fully static binary, `scp`-and-run, no runtime deps.

---

## 10. Testing

### Unit (cross-platform, run in CI)
- **`aggregateEngineCounters`** (pure): table-driven cases — gaming signal, inference
  signal, idle, all-zeros, missing `3D` key, multi-instance same-engine sum, multi-GPU
  instances, and the gate boundary at exactly `10.0%`.
- **Instance-name parser:** real PDH instance strings → correct engine bucket and retained
  `phys/gpu` discriminator; malformed names fall to `Other` without panicking.
- **Auth middleware:** valid token passes; wrong token 401; missing header 401; verifies
  constant-time path is used.
- **Config:** flag/env precedence; fatal exit when the token env var is unset; error-mode
  parsing.

### Not unit-tested (deploy-and-verify on `.20`)
The live `pdh.dll` syscalls require Windows. Exercised by deploying the binary to `.20`
and running all three states (idle / inference / gaming), confirming the gate flips
correctly at the 10% threshold against real hardware.

### CI
`agent.yml` on a `windows-latest` runner: `go vet` + `go build` to catch compile/vet
errors on PRs. No live PDH tests in CI (no GPU on hosted runners) — that is the
deploy-and-verify step.

---

## 11. Acceptance Criteria

1. `go build` produces a static `hermia-agent.exe` with no CGO and only `golang.org/x/sys`
   as an external dep.
2. `GET /gpu` with a valid bearer token returns the §5 success schema with live per-engine
   values from the box.
3. On the `.20` box: idle and inference states report `gaming: false`; a running game/
   benchmark reports `gaming: true`. The flip occurs at the configured threshold.
4. Invalid/missing token → 401, no PDH work performed.
5. Simulated PDH failure → fail-closed returns 200 + `gaming: true` + `error`; fail-open
   returns 503 + structured error body.
6. Unset token env var at startup → fatal exit, no server started.
7. All unit tests pass; `agent.yml` CI build is green.
8. Startup without TLS prints the security warning.

---

## 12. References
- `project_gaming_gate_prototype` — three-state capture results and decision rule
- `project_hermia_probe` — hermia-agent component overview, schema, graceful degradation
- `hometech/gpu_engine_capture.ps1` — the validated PDH capture logic this ports
- `backlog_hermia_agent_tls` — production TLS hard gate + commander-as-CA idea
- `backlog_hermia_agent_503_body` — fail-open body-stripping at datacenter scale
- Roadmap: `docs/roadmap.md` → v0.2 Workstream B
