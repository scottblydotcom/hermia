# Fleet TUI — Unified Interactive Picker + Live Runner

**Status:** Design, pre-implementation
**Author:** Scott Bly (with Claude)
**Tracking bead:** `hermia-86g`
**Blocks:** `hermia-4e8` (Cut v0.2.0)
**Date:** 2026-06-18

---

## 1. Overview & Goals

Replace the existing single-host TUI (`screens.py`) with a unified Fleet TUI that handles single-host *and* multi-host evaluation through one coherent interface. Fleet mode today runs only from `hermia-fleet.yaml`; this design adds interactive host / model / test selection, live drill-down progress, and named saved fleets, while preserving the headless `--fleet path.yaml` flag for CI / scripted use.

### Goals

- One TUI for both single-host and multi-host workflows; no parallel implementations
- Interactive host discovery (seed-list-based for v1, active discovery on roadmap), model selection per host, and fleet-scoped test selection
- Live drill-down runner view: aggregate → per-trial table → streaming detail
- Named, saved fleets (`fleets/<name>.yaml`) — loadable, editable, reusable
- Universal navigation grammar (`enter`/`esc`/`/`/`tab`/`space`/`a`/`n`) consistent across every drill screen
- Mouse as a first-class peer to keyboard
- Architectural seams for v0.3+: `HostSource`, `ModelSource`, recommendation engine, MCP-sourced benchmark data

### Non-goals

- Replace `transport/`, `scoring.py`, `robustness.py`, or `fingerprint/` — this is a UI / orchestration change only
- Build the v0.3 recommendation engine (designed for, not built here)
- Coordinator + worker control plane (the v0.2 TUI design intentionally stops at ~200-500 hosts; see §4 scaling envelope)

---

## 2. Architecture & Module Layout

### New package: `src/hermia/tui/`

```
src/hermia/tui/
  __init__.py
  app.py                    # HermiaApp — Textual App subclass
  screens/
    __init__.py
    launch.py               # Load existing / New fleet / Quick local run
    config.py               # Fleet Config — drill home (Hosts ▸ + Tests ▸)
    hosts.py                # Hosts drill — list + add + probe state
    host_models.py          # Single host's model picker
    tests.py                # Fleet-scoped test picker with framework axis
    runner.py               # L1 aggregate
    runner_trials.py        # L2 trial table
    runner_detail.py        # L3 streaming detail
  widgets/                  # Reusable, domain-agnostic
    __init__.py
    drillable_list.py
    filter_axis.py
    search_bar.py
    status_badge.py
    progress_bar.py
  bus.py                    # SessionBus — runner publishes, screens subscribe
  state.py                  # FleetConfig + HostSource / ModelSource protocols
  fleet_io.py               # Load/save fleets/<name>.yaml
  probe.py                  # Async host probing wrapping transport/
```

### Boundaries

- `widgets/` knows nothing about hermia domain — pure Textual building blocks; reusable for any future TUI
- `screens/` composes widgets into hermia-specific screens
- `bus.py` is the **only** shared mutable state between runner and screens; no screen pokes runner internals
- `state.py`'s `FleetConfig` is the in-memory source of truth for the in-flight edit; `fleet_io.py` converts to/from YAML
- `probe.py` wraps existing `transport/` with TUI-shaped async / timeout / retry; no new transport code

### Deleted in the same PR

- `src/hermia/screens.py` (398 lines)
- `tests/unit/test_screens.py` (156 lines)
- `tests/unit/test_screens_pilot.py` (566 lines — patterns reused in new tests)

### Modified

- `src/hermia/app.py` — opens unified TUI; `--fleet path.yaml` headless path preserved for CI

### Extension protocols (defined now, implementations come later)

```python
class HostSource(Protocol):
    async def list_hosts(self) -> list[Host]: ...

class ModelSource(Protocol):
    async def list_models(self, host: Host) -> list[ModelChoice]: ...
```

v0.2 implementations:
- `SeedFileHostSource` — `~/.config/hermia/hosts.yaml`
- `ManualHostSource` — the "+ add host" affordance
- `ProbeModelSource` — host's `/v1/models` or `/api/tags`

Future implementations (v0.3+, file as bd beads, do not build now):
- `KwaainetRegistryHostSource`, `ConsulHostSource`, `KubernetesHostSource`, `TailscaleHostSource`
- `RecommendationModelSource`, `BenchmarkScoredModelSource`, `MCPBenchmarkSource`, `LocalCacheModelSource`

---

## 3. Data Model & YAML Schemas

### In-memory

```python
@dataclass
class FleetConfig:
    name: str                       # "kwaainet-baseline" — saved as fleets/<name>.yaml
    hosts: list[Host]
    tests: list[str]                # test IDs, fleet-scoped (every host × model runs every test)
    repeat: int = 1

@dataclass
class Host:
    name: str
    url: str
    engine: str                     # "ollama" | "openai-compat" | "vllm" | …
    auth_header_env: str | None = None
    hardware: str | None = None     # static fallback; sidecar override wins
    models: list[ModelChoice]

@dataclass
class ModelChoice:
    name: str
    selected: bool
    # cached from probe — not persisted to YAML
    size_bytes: int | None = None
    quant: str | None = None
    family: str | None = None
    modality: str | None = None
```

### Saved fleet: `fleets/<name>.yaml`

```yaml
name: kwaainet-baseline
created: 2026-06-18T16:32:14Z
hermia_version: 0.2.0

tests:
  - prompt-injection-1
  - jailbreak-1
  - leakage-1

hosts:
  - name: eric-5090
    url: https://eric.tail***.ts.net:11434
    engine: ollama
    hardware: RTX 5090
    auth_header_env: LITELLM_KEY
    models:
      - qwen3-coder:30b
      - qwen3:32b

repeat: 1
```

### User seed list: `~/.config/hermia/hosts.yaml`

```yaml
hosts:
  - name: eric-5090
    url: https://eric.tail***.ts.net:11434
    engine: ollama
    hardware: RTX 5090
    auth_header_env: LITELLM_KEY
```

User-level (not project-level) so it survives clones and isn't checked in by accident. New hosts added in the TUI offer to save to this file with a checkbox.

### Schema decisions

- `auth_header_env` stores the **env var name**, not the secret — YAML is safe to share with a Kwaainet participant
- `hardware` is a hint, not authoritative — sidecar agent overrides at runtime; static field is bootstrap fallback
- Model metadata not persisted in YAML — re-probed on load (cheap, always current)
- `hermia_version` stamp lets future code know which YAML format wrote a file

### Migration from `hermia-fleet.yaml`

On first TUI launch, if `hermia-fleet.yaml` exists at the repo root, offer to copy it to `fleets/hermia-fleet.yaml` (one-time, with a notice). No silent migration; no force-move.

---

## 4. Event Bus & Concurrency

### Bus

A single in-process `SessionBus` attached to `HermiaApp` at mount. Topic-based async pub/sub, `asyncio.Queue` per subscriber.

```python
class SessionBus:
    async def publish(self, topic: str, event: dict) -> None: ...
    def subscribe(self, topic: str) -> AsyncIterator[dict]: ...
```

### Topics

| Topic | Publisher | Subscribers |
|---|---|---|
| `probe.started` / `probe.completed` / `probe.failed` | `probe.py` | Hosts drill |
| `run.started` / `run.completed` / `run.paused` / `run.resumed` / `run.aborted` | `runner.py` | Runner L1 |
| `run.trial_started` / `run.trial_finished` | `runner.py` | All three runner levels |
| `run.trial_chunk` | `runner.py` | L3 only (focused trial) |

### Queue bounds

- Trial event queues: **unbounded** (sparse enough that bounded would never trigger)
- L3 chunk queue: **bounded at 64, drop-oldest** (only matters during streaming on a slow render path; "show me the tail" is the contract)

### Concurrency model

- **Probes:** Textual `@work` workers, bounded concurrency = 8 by default (tunable via `HERMIA_PROBE_CONCURRENCY` env), 8s timeout, cancellable, retry button re-queues
- **Run dispatch:** the existing concurrent runner in `fleet.py` publishes through the bus instead of writing rows to disk only
- **UI render:** Textual's reactive system + fixed throttle — L1 refreshes at most every 250 ms regardless of event volume; L2 appends at 60 fps; L3 streams as chunks arrive

### Pause / abort

- **Pause:** drain in-flight, no new dispatch. Resume re-arms dispatch. Mid-trial pause is not supported (inference APIs don't expose it)
- **Abort:** cancels all in-flight workers, writes partial results via existing sink, emits `run.aborted`. TUI shows `Aborting…` state on L1 during drain (10s hard cutoff)

### Cancellation contract

Abort *must* drain disk writes before exiting. The runner's existing sink layer (`sink/submission.py`) handles flush; TUI waits on the abort coroutine.

### Scaling envelope

The TUI design is correct up to ~200-500 hosts. Friction points along the way:

| Hosts | First friction | Fix |
|---|---|---|
| ~25 | Probe concurrency cap (8) — fleet setup waits | Bump `HERMIA_PROBE_CONCURRENCY` setting |
| ~100 | L1 per-host roll-up becomes noisy | "Compact mode" toggle (`c` collapses inactive hosts into a sparkline row) — file as `hermia-tui-scale-2` (P3) |
| ~200-500 | Single TUI process becomes the dispatch bottleneck | Topology change — see below |

### Topology evolution

Beyond ~500 hosts, the shape changes from single-process TUI to **operator console + control plane + workers** (same pattern as kubectl / Rancher / Fleet / Ansible Tower). At that scale:

- Rows represent clusters / regions, not individual hosts
- Dispatch fires from regional workers, not the TUI process
- The TUI subscribes to a coordinator's event stream instead of probing directly

**The widget library and drill idiom built here carry over unchanged** to that future topology. Only the data sources and worker layer change. The `HostSource` abstraction is the seam where coordinator-style registries plug in.

### Shared-node citizenship

For Kwaainet-scale shared-node deployments, hermia stays a polite citizen:

- Probe rate limit per host (200ms minimum gap to same URL)
- Transport-layer respect for 429 / 503 with exponential backoff (existing behavior preserved)
- Future `node.capacity` advisory — if a node publishes "I can take N concurrent trials," hermia respects it (file as v0.3 bd bead)

---

## 5. Screens: Drill Semantics & Navigation Contract

### Stack-based navigation

Textual's `push_screen` / `pop_screen` is the drill mechanism. Every drill is a push; every esc / back-click is a pop. No mode flags, no global state — the stack *is* the navigation state.

### Universal contract

| Input | Action |
|---|---|
| `enter` / row click | Push detail screen — drill in |
| `esc` / back-chip click | Pop — climb out, preserves parent's selection/filter |
| `space` | Toggle row's selected state (where applicable) |
| `/` | Open search input at footer — live filter |
| `tab` | Cycle filter axis (screens without an axis no-op) |
| `a` / `n` | Select all / none in current filter view |
| `↑↓` / mouse wheel / drag-scroll | Move cursor / scroll |
| `?` | Help overlay |
| `^C` | Cancel current async action. Behavior is screen-scoped: on Hosts drill cancels in-flight probes (no confirm); on Runner L1 aborts the run (confirm modal — destructive) |
| `q` (Launch screen only) | Quit app — confirm modal if any unsaved fleet edits exist in the stack |

### Breadcrumb

Every drillable screen has a breadcrumb header (`hermia · fleet · kwaainet-baseline ▸ hosts ▸ marcus`). Each `▸` segment is clickable for direct jump-back. Same affordance on the runner (L1 ▸ L2 ▸ L3).

### Lifecycle hooks

| Hook | Behavior |
|---|---|
| `on_mount` | Subscribe to bus topics; populate from state |
| `on_screen_resume` | Re-render — called when this screen becomes top of stack again |
| `on_screen_suspend` | Pause render work — called when a new screen pushes on top |
| `on_unmount` | Unsubscribe; cancel pending workers |

### State propagation

`FleetConfig` is the single in-memory source of truth. Picker screens read and write directly to it — no diff merging, no draft state. The Fleet Config screen shows `[unsaved changes]` in the header when in-memory state diverges from disk. The unsaved-changes confirm modal triggers at **app close** (`q` from Launch or window close), not on screen pops — Fleet Config remains in memory as the user navigates the drill stack, so popping doesn't lose work.

### Runner state across drills

Drilling L1 ▸ L2 ▸ L3 does not pause the run. Each level subscribes to bus events at its appropriate granularity. Popping back to L1 doesn't lose state because the bus has been streaming the whole time and L1 maintains aggregates from those events.

### Mouse parity

`DrillableList` binds row-click and `enter` to the same handler. Mouse and keyboard are siblings, not parallel implementations. All universal-contract bindings have mouse equivalents.

### Stack depth

Textual's default max is 20. Our deepest drill is Launch ▸ FleetConfig ▸ Hosts ▸ Host ▸ Models = 5. 4× headroom.

### UX decisions reference

Settled during brainstorming, recorded here for future reference:

**Status semantics:** `defended` / `refused` / `breached` / `error`
- `defended` — model produced compliant output (good security outcome)
- `refused` — model said no (valence depends on test direction; benign tests treat refusal as bad)
- `breached` — model produced non-compliant output (jailbroken, leaked, complied with injection)
- `error` — no usable output (TIMEOUT, EMPTY_RESPONSE, transport error)

**Icons:** `✓ ↺ ✗ !` (with `↺` → `⊘` as a fallback if terminal rendering of the arrow proves flaky in real-world fonts)

**Refusal color:** rendered per-test-direction. Harmful tests: refusal = green-ish (good). Benign tests (v0.3 BAM Benign): refusal = red-ish (over-refusal).

**Filter axes by screen:**
- Hosts: engine, lane
- Models: family, size class, quant, modality
- Tests: framework (OWASP / ATLAS / MAESTRO / NIST)

**Probe timeout:** 8s default with Retry button on failure.

**Repeats in L2:** when `repeat > 1`, each repetition is its own row in the L2 trial table (so the user can see per-rep variance). Robustness aggregates (`robustness.py`) are surfaced at L1 in the per-host roll-up summary, not in L2.

**Hardware tag display:** UI shows the value plain (no "(static)" / "(sidecar)" suffix) — source distinction is internal. Sidecar-supplied value always wins when present; static value renders only when sidecar is silent.

**Quick local run** Launch entry: pre-fills `http://localhost:11434` as a single host with the default test set, probes immediately, jumps to model selection. Preserves single-machine 2-click muscle memory.

---

## 6. Error Handling

Layered model: each failure has a defined surface and a defined recovery.

| Failure | Caught | UI behavior | Recovery |
|---|---|---|---|
| Probe timeout (8s) | `probe.py` worker | Badge `! timeout`; Retry inline | User clicks Retry |
| Probe auth failure (401/403) | `probe.py` | Badge `! auth`; hints to check `auth_header_env` | User edits → Retry |
| Probe transport error | `probe.py` | Badge `! offline`; no auto-retry | Retry button; user may remove host |
| Probe returns empty model list | `probe.py` validation | Badge `! no models`; warns "0 models → 0 trials" | User adds models or removes host |
| Trial timeout / transport error during run | `transport/` (existing) | Trial row → `! error`, counts toward error tally | Run continues; no per-trial retry from TUI |
| Host goes offline mid-run | First failed trial cascades | All in-flight on that host fail; remaining skip with `! host-offline` | Run continues on other hosts |
| YAML load: missing | `fleet_io.py` | Toast: "No fleet found at `<path>`" | User picks another or creates new |
| YAML load: malformed | `fleet_io.py` validation | Toast with parse error; "open in editor" | User fixes externally; reload via `r` |
| YAML save: permission denied | `fleet_io.py` | Toast with error; data stays in memory unsaved | User adjusts permissions |
| YAML save: dir doesn't exist | `fleet_io.py` | Creates `fleets/` on first save automatically | None needed |
| Bus subscriber lag | `bus.py` queue overflow | L3 chunk queue drops oldest (bounded 64); never blocks publisher | Invisible to user |
| Sidecar disagrees with static `hardware` | `state.py` reconcile | Sidecar wins silently; static shown grayed | None — sidecar authoritative when present |
| Screen exception | Textual error handler | Crash modal with traceback + report-issue link; pops to last-good state | User can continue or quit |
| App crash mid-run | Process exit | CSV has what completed (existing sink behavior) | Same recovery as today |

### Principles

1. **No silent failures.** Every error surfaces — badge on the offending row, toast for global errors, crash modal for unhandled exceptions
2. **Errors don't poison sibling state.** Failures are local to their scope
3. **Recoverable failures have Retry; unrecoverable have Replace.** No exponential-backoff auto-retry loops in the UI layer — that belongs in `transport/` where it already exists

### Out of scope for v1 (future bd beads)

- Auto-resume from partial CSV after crash
- Per-trial retry from L3 detail view
- Pluggable error reporters (Sentry, etc.)

---

## 7. Testing Strategy

Layered, no test depends on a live host. Fleet/network surface uses fakes; TUI surface uses Textual Pilot.

| Layer | What | How |
|---|---|---|
| Widgets | `DrillableList`, `FilterAxis`, `SearchBar`, `StatusBadge`, `ProgressBar` | Pure widget unit tests in a throwaway `App` |
| State | `FleetConfig` mutation, YAML round-trip, hosts.yaml load/save, fleet name validation, legacy migration | Plain unit tests — no Textual |
| Bus | Topic subscription, queue bounds, drop-oldest on chunk overflow, abort propagation | `pytest-asyncio` |
| Probe | Timeout, retry, auth failure, empty-model-list | Mock transport; assert correct `probe.*` events |
| Screens | Drill push/pop, breadcrumb jump, save/load, picker → runner handoff, error toasts | Textual Pilot tests |
| Runner integration | Picker → save → run → results, with fake transport scripting deterministic mix of pass/refuse/fail/error | One Pilot end-to-end per major flow |

### TDD

Per `superpowers:test-driven-development`. Each implementation slice: red → green → refactor.

### NOT tested

- Textual internals (frame timing, character-level render output)
- Live host network behavior (`transport/` has those tests)
- Existing scoring / robustness logic (`scoring.py`, `robustness.py` cover it)
- Pixel-level mockup appearance

### Tests retired

- `tests/unit/test_screens.py` → replaced by `tests/unit/test_tui_screens.py`
- `tests/unit/test_screens_pilot.py` → patterns retained, file replaced

### Shared fixture

`tests/fixtures/fake_transport.py` — a `FakeTransport` class implementing the real `transport/` protocol but scripting responses from a deterministic config (e.g., `{"prompt-injection-3 + qwen3:32b": "breached", "leakage-1 + qwen2.5:7b": "refused"}`). Single fixture for any test driving the full picker → run → results path without a real host.

---

## 8. Extension Points & v0.3+ Roadmap

The v0.2 design exposes these seams deliberately:

| Seam | v0.2 implementation | v0.3+ implementations (file as bd beads) |
|---|---|---|
| `HostSource` | `SeedFileHostSource`, `ManualHostSource` | `KwaainetRegistryHostSource`, `ConsulHostSource`, `KubernetesHostSource`, `TailscaleHostSource` |
| `ModelSource` | `ProbeModelSource` | `RecommendationModelSource`, `BenchmarkScoredModelSource`, `MCPBenchmarkSource`, `LocalCacheModelSource` |
| Launch screen entries | Load existing / New fleet / Quick local run | "Recommend models for my stack" entry that pre-populates FleetConfig from a recommendation engine |
| Widget library | `DrillableList`, `FilterAxis`, etc. | Reused by future operator-console at enterprise scale; reused by recommendation review screens |

### v0.3 bd beads to file after v0.2.0 ships

- `hermia-rec-data` — normalized cross-benchmark schema (PyRIT, Garak, MMLU, HumanEval, BigBench, MTEB)
- `hermia-rec-ingest` — pipeline for pulling + normalizing third-party benchmark data; cadence; license / attribution handling
- `hermia-rec-engine` — hardware × use-case → ranked model recommendations
- `hermia-rec-tui` — Launch-screen "Recommend models for my stack" entry + recommendation review screen
- `hermia-rec-mcp` — `MCPBenchmarkSource` for consuming benchmark data via MCP servers
- `hermia-rec-commercial` (note-only) — commercial strategy for the recommendation tier
- `hermia-tui-scale-1` — make probe concurrency a setting (env or per-fleet)
- `hermia-tui-scale-2` — L1 compact mode for fleets >50 hosts

### Open follow-up beads already filed

- `hermia-86g` — this design (the bead this spec was authored against)
- `hermia-coc` (P2) — VRAM-aware model recommendations per fleet node (data feeds the recommendation engine)
- `hermia-q52` (P2) — BAM Benign tier (over-refusal); the refusal-color logic in §5 is designed for this

---

## 9. Out of Scope

Explicitly not built in this design:

- Recommendation engine (v0.3 roadmap)
- Active host discovery — mDNS / Tailscale peer enum / subnet scan (v0.3 roadmap)
- Per-test cherry-pick UI (v1 has full multi-select; named test-set picker punted to v0.3 roadmap)
- Per-host model overrides on top of a global model set (v0.3 roadmap)
- Auto-resume from partial CSV after crash
- Per-trial retry from the TUI
- Pluggable error reporters
- Backwards-compat shim for `screens.py` callers (none exist outside `app.py`; clean break in same PR)
- Coordinator + worker control plane (enterprise topology; rebuild post-v0.5 if/when needed)
