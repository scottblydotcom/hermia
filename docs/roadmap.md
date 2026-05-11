# Hermia Roadmap

**Status:** Living document. Updated as decisions change.
**Last revised:** 2026-05-10
**Owner:** @scottblydotcom

This document is the strategic plan. Beads are the tactical execution. Each leaf entry below is shaped to map 1-to-1 to a `bd add` invocation when work begins. Don't pre-create beads — they go stale before you touch them.

---

## North Star

**Hermia is the independent reference implementation for LLM evaluation.** Practitioner-built, vendor-neutral, hardware-aware, audit-grade, MIT-licensed, no commercial agenda. The position the vendors structurally cannot occupy because they all answer to one Olympian.

Three claims that nobody else can credibly make:

1. **We don't sell anything.** The methodology is not also a sales channel for inference, training, or services.
2. **We test the stack, not just the model.** Hardware telemetry, backend tagging, cross-backend divergence — model behavior depends on the inference stack underneath, and nobody else captures it.
3. **Our scores are reproducible by anyone with the hardware.** Local-first, deterministic-where-possible, full corpus and rubric in the repo.

### The eval-bus thesis

Hermia v0.1 is an application — does one thing end-to-end with hardcoded inputs and outputs. The strategic pivot through v0.2 and v0.3 turns it into a **platform**: a stable core with three plugin points (Probe, Transport, Sink) where the rest of the ecosystem builds in. Hermia becomes the place where Garak, PyRIT, HarmBench, and CyberSecEval results converge — alongside Hermia's own probes — into one hardware-correlated, framework-mapped, audit-ready view.

This is not "out-Garak Garak." Garak has NVIDIA's headcount; we don't compete on probe count. We compete by being the bus everyone routes through.

### Mythology

Hermes built the lyre and gave it to Apollo, then carried the Oracle's word between worlds. Hermia carries your questions to many oracles — local models, cloud APIs, third-party probes — and tells you which answers to trust.

The eval-bus pivot strengthens the framing: Hermes was the only Greek god who moved freely between Olympus, Earth, and Hades. The single-oracle framing in the original README undersold what the myth describes. Pythia herself was plural. Hermes is the herald who knows them all.

---

## Conventions

### Priority

- **P0** — Launch-blocking. Cannot ship v0.1 without this.
- **P1** — Strongly desired in milestone. Slippage is acceptable but costly.
- **P2** — Planned in milestone. First to be cut if scope tightens.
- **P3** — Backlog within milestone. Ship if time permits.
- **P4** — Nice-to-have / opportunistic.

### Bead template (for v0.1 items — full templates)

```
### Title
**Priority:** P0–P4
**Depends on:** (other bead titles, if any)
**Permitted scope:** (files this bead can touch — per AGENTS.md Module Boundary Table)
**Acceptance:** (testable, observable conditions)
**Estimate:** (rough working days)
**Why:** (one-line strategic justification)
```

### Bead-shaped sketches (for v0.2 items)

Same shape, lighter on acceptance criteria — to be tightened when the milestone opens.

### Themes (for v0.3 items)

Description of the work and the strategic intent. Bead breakdown happens when the milestone opens.

---

## v0.1 — Launch (target 2026-05-23)

**Theme:** Ship a credible, honest, well-tested first release. Set expectations for what comes next.

### Strike LiteLLM and other overstatements from the competitive briefing
**Priority:** P0
**Depends on:** —
**Permitted scope:** `docs/llm-benchmark-landscape-2026.md`
**Acceptance:**
- "Fleet-first via LiteLLM" / "tests run against the live LiteLLM gateway" struck from §8.1, §8.3 differentiation table, and §7 competitive matrix
- "Live GPU/VRAM telemetry" caveated with "(AMD GPU; NVIDIA + Apple Silicon support shipping in v0.1)"
- "MITRE-mapped" caveated with "tagged in test metadata; structured taxonomy export shipping in v0.1"
- §8.3 "Nobody" claims softened with "(among open-source operational eval tools)" qualifiers
**Estimate:** 0.5 days
**Why:** The briefing will be read. Truth-in-advertising before launch.

### Multi-vendor metrics — NVIDIA support
**Priority:** P0
**Depends on:** —
**Permitted scope:** `src/hermia/metrics.py`, `tests/unit/test_metrics.py`
**Acceptance:**
- `nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits` parsed when available
- `detect_gpu()` returns vendor-tagged info: `vendor: "nvidia" | "amd" | "apple" | "intel" | "none"`
- Result rows still populate `peak_gpu_pct` / `peak_vram_used_gb` correctly when running on NVIDIA
- Unit tests cover NVIDIA-detected, NVIDIA-missing, NVIDIA-error paths
- **Smoke test note:** Eric's 5090 and Marcus's 3090 are Windows-only Ollama servers — Hermia does not run on them. Hardware smoke test deferred to the first Linux + NVIDIA eval client. Unit test coverage accepted as sufficient for v0.1.
**Estimate:** 1 day
**Why:** Most of the user's own fleet is NVIDIA. Today's silent zeros are a correctness bug.

### Multi-vendor metrics — Apple Silicon support
**Priority:** P0
**Depends on:** NVIDIA support (shared `vendor` tagging)
**Permitted scope:** `src/hermia/metrics.py`, `tests/unit/test_metrics.py`
**Acceptance:**
- macOS detection via `platform.machine() == "arm64"` and presence of `/usr/sbin/system_profiler SPDisplaysDataType`
- VRAM reported as the unified-memory portion the GPU is consuming (best-effort; document the metric clearly)
- `powermetrics --samplers gpu_power -n 1` (sudo required) optional path documented; `system_profiler` fallback works without sudo
- `peak_gpu_pct` / `peak_vram_used_gb` populated on macOS arm64
- Unit tests with mocked `subprocess.run` for both detection and capture paths
- Verified on the M3 Pro 18 GB work Mac
**Estimate:** 1 day
**Why:** All four of your Macs have Apple Silicon. No competing tool reports honest unified-memory pressure. Unique differentiator.

### Multi-vendor metrics — Intel iGPU + Nvidia mobile + CPU fallback
**Priority:** P1
**Depends on:** NVIDIA support
**Permitted scope:** `src/hermia/metrics.py`, `tests/unit/test_metrics.py`
**Acceptance:**
- Intel iGPU detection scaffolded: Linux `intel_gpu_top` if installed (best-effort), macOS `system_profiler` reports Intel HD/Iris, Windows out of scope
- Nvidia mobile (GT/Quadro/MX) covered by the same `nvidia-smi` path; documented as such
- CPU-only fallback: when no GPU is detected, `peak_gpu_pct = 0` / `peak_vram_used_gb = 0` and a `gpu_vendor: "none"` field
- README hardware support matrix documents: AMD ROCm ✅ tested, NVIDIA CUDA ✅ tested, Apple Silicon ✅ tested, Intel iGPU ⚠️ best-effort, Windows ❌ not yet
**Estimate:** 0.5 days
**Why:** Schema completeness; users on untested hardware get honest "data unavailable" rather than silent zeros.

### Promote framework tags to first-class metadata
**Priority:** P0
**Depends on:** —
**Permitted scope:** `test-datasets/agentic-tasks.json`, `src/hermia/runner.py`, `src/hermia/screens.py`, `src/hermia/export.py`, `tests/unit/test_runner.py`, `tests/unit/test_export.py`, plus a Postgres migration script in `scripts/`
**Acceptance:**
- Every test in `agentic-tasks.json` has a `frameworks` field with structured keys: `owasp_llm_top10_2025`, `mitre_atlas_v5_1`, `csa_maestro`, `nist_ai_rmf`
- `runner.run_test()` carries the field through to the result dict
- `screens` stamping plumbs it onto each result row
- `export._PG_COLUMNS` includes `framework_owasp`, `framework_mitre`, `framework_maestro`, `framework_nist` (text arrays or JSONB)
- Postgres migration script in `scripts/` adds the columns idempotently
- A Grafana query "show me all OWASP LLM01 failures across all models" works without parsing description strings
**Estimate:** 1 day
**Why:** Highest delta on perceived rigor. Today, "MITRE-mapped" is prose; this makes it queryable.

### Wire robustness module + cold-vs-warm tracking
**Priority:** P0
**Depends on:** —
**Permitted scope:** `src/hermia/robustness.py`, `src/hermia/runner.py`, `src/hermia/screens.py`, `src/hermia/export.py`, `tests/security/test_robustness.py`, `tests/unit/test_runner.py`
**Acceptance:**
- `hermia` TUI accepts a `--repeat N` flag (default 1)
- `screens.RunnerScreen` calls `run_test` N times per (model, test_id), stamping `run_index` (1..N) on each
- `is_cold` (bool) marks the very first invocation against a freshly-loaded model; subsequent invocations are warm
- Result rows gain three new columns: `run_index`, `is_cold`, `cold_warm_delta_tps` (computed in screens or as a Grafana view)
- Postgres migration adds columns
- `robustness.run_n_times` is invoked per (model, test_id) at end of run; `consistency_pct` and `pass_count` exported
- README documents the `--repeat` flag and the cold-vs-warm semantic
**Estimate:** 1.5 days
**Why:** TAU-bench-style reliability scoring. Reward-hacking-resistant story. Nobody else reports cold/warm delta.

### Add empty judge_score / judge_reasoning columns now
**Priority:** P1
**Depends on:** Framework metadata (same migration)
**Permitted scope:** `src/hermia/export.py`, `scripts/` (Postgres migration), `tests/unit/test_export.py`
**Acceptance:**
- `_PG_COLUMNS` includes `judge_score` (int, nullable) and `judge_reasoning` (text, nullable)
- All v0.1 rows write NULL for these
- v0.3 LLM-as-judge work populates them; no migration needed at that point
**Estimate:** 0.5 days
**Why:** Schema migrations on populated tables are painful. Declare the field today.

### TUI test coverage via Textual Pilot
**Priority:** P0
**Depends on:** —
**Permitted scope:** `tests/unit/test_screens.py` (NEW), `pyproject.toml` dev deps
**Acceptance:**
- SelectionScreen tests: model checkboxes default-checked, test checkboxes default-checked, "Select All Models" / "Select All Tests" buttons toggle correctly, run button blocked when nothing selected and emits status text
- RunnerScreen tests: progress bar advances per (model × test) pair, log lines append in correct order, summary renders with at least one model
- Back binding from RunnerScreen pops the screen without crashing mid-run
- `screens.py` coverage rises from 27% to ≥70%
**Estimate:** 0.5 days
**Why:** TUI is user-facing. 27% is too low. Textual ships `Pilot` for exactly this.

### Determinism / stability harness
**Priority:** P0
**Depends on:** Fake-Ollama fixture
**Permitted scope:** `tests/integration/test_determinism.py` (NEW)
**Acceptance:**
- One end-to-end test: same model + same test_id + same fake-Ollama response → identical `json_valid`, `schema_compliant`, `framework_*` fields, identical computed `score`
- `tokens_per_sec` allowed to vary within ±5% (timing jitter); everything else bytewise stable
- `run_id` and `run_timestamp` excluded from the equality check
**Estimate:** 0.5 days
**Why:** This is the credibility-defining test for an eval tool. "Trust our scores" requires "the scores are stable."

### Fake-Ollama integration test fixture
**Priority:** P0
**Depends on:** —
**Permitted scope:** `tests/integration/conftest.py` (NEW), `tests/integration/test_runner_e2e.py` (NEW)
**Acceptance:**
- A `pytest` fixture spins up an HTTP server (stdlib `http.server` in a thread, or `pytest-httpserver` if dev-dep approved) responding to `/api/generate` and `/api/tags` with canned JSON
- One full pipeline test: `runner.run_test` against the fake server produces a correct result row
- One Ollama-API-drift test: when the fake server returns an unknown field, parsing still succeeds and the unknown field is ignored
- One error path test: timeout, 500, malformed JSON each produce sensible result rows with non-empty `failure_reason`
**Estimate:** 1 day
**Why:** Today every test mocks `requests.post` at function granularity. An Ollama API change would silently break the live tool. This catches it forever.

### Property-based tests on schema checkers via hypothesis
**Priority:** P0
**Depends on:** —
**Permitted scope:** `tests/unit/test_schemas_properties.py` (NEW), `pyproject.toml` dev deps
**Acceptance:**
- `hypothesis` added to dev deps (validate at PyPI per AGENTS.md hard-rule #1 before committing)
- Three properties tested per checker in `SCHEMA_CHECKS`:
  - **Total:** `@given(st.recursive(st.one_of(...)))` never causes the checker to raise
  - **Required-keys-present + benign-extras passes:** the checker accepts a synthesized response with required keys + a `thinking` extra
  - **Required-keys-missing fails:** the checker rejects synthesized responses missing any required key
- All 19 checkers parametrized through the same property suite
**Estimate:** 1 day
**Why:** Schema checkers are the central eval logic. Property-based testing catches the edge case nobody thought of: NaN floats, unicode keys, deeply nested dicts, integer overflow.

### SQL injection round-trip test
**Priority:** P1
**Depends on:** —
**Permitted scope:** `tests/unit/test_export.py`
**Acceptance:**
- A test with `model = "'; DROP TABLE hermia_results;--"` and `test_id = "<script>alert(1)</script>"` round-trips through `execute_batch` (mocked at the cursor level) and the resulting parameter dict contains the values verbatim — never interpolated into the SQL string
**Estimate:** 0.25 days
**Why:** Closes the auditor's first checkbox. Confirms the parameterization works.

### JSONL injection round-trip test
**Priority:** P1
**Depends on:** —
**Permitted scope:** `tests/unit/test_results.py`
**Acceptance:**
- `append_result` writes a row whose `output_preview` contains an embedded `\n{"malicious": true}` and `load_jsonl` reads the file back as exactly one row (the embedded JSON did not become a second record)
**Estimate:** 0.25 days
**Why:** The audit trail must be tamper-resistant against hostile model output.

### Local vs. fleet mode detection + Ollama server metrics
**Priority:** P1
**Depends on:** —
**Permitted scope:** `src/hermia/metrics.py`, `src/hermia/runner.py`, `src/hermia/export.py`, `scripts/` (Postgres migration), `tests/unit/test_metrics.py`, `tests/unit/test_runner.py`, `tests/unit/test_export.py`
**Acceptance:**
- Mode detection: if the configured Ollama host resolves to `localhost` / `127.0.0.1`, mode is `"local"`; any other host is `"fleet"`
- In fleet mode, local hardware collection (GPU%, VRAM via sysfs/nvidia-smi, CPU%, RAM via psutil) is suppressed — result rows write `null` for these fields rather than reporting the eval client's idle Mac hardware
- `/api/ps` queried against the Ollama host in both modes; `size_vram` captured as `vram_server_gb` (what the inference server reports the model is consuming)
- Result rows gain two new fields: `mode` (text, `"local"` or `"fleet"`) and `vram_server_gb` (float, nullable)
- Postgres migration adds both columns idempotently
- v0.1 host config: single `--host` CLI flag (default `http://localhost:11434`) or `HERMIA_HOST` env var; no fleet config file yet (that is v0.2)
- Unit tests cover: local-mode collection, fleet-mode suppression, `/api/ps` parse, `/api/ps` unavailable (graceful null)
**Estimate:** 1 day
**Why:** In fleet mode, Hermia currently reports the eval client's idle Mac GPU — actively misleading. `size_vram` from `/api/ps` is the only inference-server metric available without additional deployment; it is also the most useful one for capacity planning. Running Hermia requires only Ollama in both modes; no sidecar, no SSH.

### TUI: mode-aware metrics display
**Priority:** P1
**Depends on:** Local vs. fleet mode detection
**Permitted scope:** `src/hermia/screens.py`, `tests/unit/test_screens.py`
**Acceptance:**
- Header or status bar shows a `LOCAL` or `FLEET` badge derived from the detected mode
- In fleet mode: CPU%, RAM, GPU%, local VRAM panels display `—` or `fleet mode` rather than misleading eval-client values; `vram_server_gb` shown where local VRAM would be
- In local mode: all panels behave exactly as today
- Existing Pilot tests updated if they assert on the metrics panel content
- At least one new Pilot test: fleet-mode layout shows the `FLEET` badge and suppressed local panels
**Estimate:** 0.5 days
**Why:** Without the visual indicator, users cannot tell which metrics are meaningful. The display change is what makes the mode distinction legible.

### Launch visual assets — TUI screenshots and GIF demo
**Priority:** P1
**Depends on:** All v0.1 functional items (run against a real or stable fake Ollama)
**Permitted scope:** `docs/assets/` (NEW directory), `README.md`
**Acceptance:**
- At least two static terminal screenshots: SelectionScreen and RunnerScreen mid-run; saved as PNG in `docs/assets/`
- One animated GIF (via `asciinema` + `agg`, or `vhs`, or screen capture): full happy-path run from model selection through results summary, ≤60 seconds
- README `## Demo` section added with the GIF inline and a link to the screenshots
- Filenames are descriptive (`selection-screen.png`, `runner-screen.png`, `hermia-demo.gif`)
**Estimate:** 0.5 days
**Why:** A TUI with no screenshot is a black box to anyone evaluating it. The GIF is the single highest-ROI trust signal for a first-time visitor.

### Getting Started Guide
**Priority:** P1
**Depends on:** All v0.1 functional items
**Permitted scope:** `docs/usage.md` (NEW), `README.md`
**Acceptance:**
- `docs/usage.md` covers: installation, prerequisites (Ollama + a pulled model), running a local eval, interpreting results, running against a remote host (`--host`), exporting to Postgres
- Each section includes the exact command to run and expected output (text or screenshot reference)
- README "Documentation" section links to `docs/usage.md`
- Broken `docs/security-framework-research.md` reference resolved: file created as a stub with framework mapping rationale, or CLAUDE.md updated to reflect planned status (already done 2026-05-11)
**Estimate:** 0.5 days
**Why:** Report and external reviewer both flagged this gap. First-time users have nowhere to go after `pip install`.

### GitHub launch checklist
**Priority:** P1
**Depends on:** README scope clarifications (hermia-cix)
**Permitted scope:** GitHub repository settings (no code changes)
**Acceptance:**
- GitHub repository topics set: `llm-security`, `ai-evaluation`, `ollama`, `tui`, `security-testing`, `red-teaming`
- GitHub release created for `v0.1.0` matching the CHANGELOG entry; release notes reference the CHANGELOG
- Release tagged from `main` after dev→main promotion PR merges
**Estimate:** 0.25 days
**Why:** Discoverability and credibility. A repo with no release tag looks abandoned; topics surface it in GitHub search.

### README scope clarifications + roadmap section
**Priority:** P0
**Depends on:** All v0.1 functional items
**Permitted scope:** `README.md`, `CHANGELOG.md`
**Acceptance:**
- README "What It Does" notes single-turn evaluation against Ollama-compatible local endpoints
- README "Hardware Support" matrix table added
- README "Roadmap" section names v0.2 (endpoint bus) and v0.3 (eval bus) with one-line descriptions
- CHANGELOG entry for v0.1.0
- New tagline: "Hermia carries your questions to many oracles — local models, cloud APIs, third-party probes — and tells you which answers to trust." (deferred to v0.2 README rewrite if scope is tight)
**Estimate:** 0.5 days
**Why:** Pre-empts "where's multi-turn?" and "where's cloud API support?" on day one.

---

## v0.2 — Endpoint Bus (target ~2026-06-15)

**Theme:** Hermia evaluates anything that speaks OpenAI-compatible. LiteLLM, OpenAI, Anthropic, Google, Bedrock, plus local Ollama. Backend stack identity becomes a queryable dimension. Tier 2 testing locks in.

### Transport interface + OpenAI-compatible client
**Priority:** P0
**Depends on:** —
**Permitted scope:** `src/hermia/transport/` (NEW package), `src/hermia/runner.py`, tests
**Acceptance (sketch):**
- `Transport` protocol/ABC with `generate(model, system, prompt, **opts) -> Response`
- `OllamaTransport` and `OpenAICompatTransport` concrete implementations
- `runner.run_test` takes a `transport` argument; default is `OllamaTransport` for backward compat
- Auth tokens accepted via env var reference only — never stored in config files, never logged, never written to result rows (AGENTS.md hard rule #11)
- Cold-load metrics flagged "N/A" when transport is API-mode, not local-stack
- **Fleet config file** (`hermia-fleet.yaml`) introduced here:
  ```yaml
  fleet:
    - name: "Eric 5090"
      host: "http://100.71.60.30:11434"
    - name: "LiteLLM Gateway"
      host: "https://scottai.tailc7d860.ts.net:4000"
      auth:
        type: bearer
        key_env: LITELLM_DISPATCH_KEY   # env var name — never the value
  ```
- `--fleet hermia-fleet.yaml` flag runs the full eval suite against every host; results tagged with `host_name`
- Each host entry gets its own optional `auth` block; Ollama nodes need none
- Config file is safe to commit; credentials live only in the environment
**Why:** The architectural change that makes Hermia a bus instead of a tool. The fleet config is the user-facing expression of "run against all of these" without requiring SSH or sidecar deployment on inference nodes.

### Backend stack tagging
**Priority:** P1
**Depends on:** —
**Permitted scope:** `src/hermia/backend.py` (NEW), runner integration
**Acceptance (sketch):**
- Capture per-run: Ollama version (`/api/version`), GPU arch (gfx900, sm_89, M3, etc.), CUDA / ROCm / Vulkan / Metal stack version, llama.cpp build hash if exposed
- Postgres columns: `backend_stack`, `gpu_arch`, `runtime_version`
- Grafana can answer "did pass rate change after the ROCm 6.2 → 6.3 upgrade?"
**Why:** Level A from the backend-analysis discussion. Nobody else reports this.

### XSTest-style over-refusal dimension
**Priority:** P2
**Depends on:** —
**Permitted scope:** `test-datasets/agentic-tasks.json`, `src/hermia/schemas.py`, tests
**Acceptance (sketch):**
- 10–20 benign prompts that well-calibrated models should NOT refuse (e.g., "How do I kill a Linux process?")
- New `dimension: "calibration"` and a checker that asserts non-refusal + valid response
- Documented in README as "false-refusal coverage"
**Why:** Over-refusal is as much a failure mode as under-refusal for production fleet models.

### Refactor — extract scoring from screens
**Priority:** P1
**Depends on:** —
**Permitted scope:** `src/hermia/scoring.py` (NEW), `src/hermia/screens.py`, tests
**Acceptance (sketch):**
- `_compute_scores` moves to `scoring.py` as a pure function
- Direct unit tests on the scoring module
- `screens.py` imports from `scoring`
- `screens.py` coverage rises further; scoring coverage 100%
**Why:** Domain logic out of the presentation layer. Pays off testing dividends.

### Tier 2 testing infrastructure
**Priority:** P1
**Depends on:** v0.1 testing landed
**Permitted scope:** `.github/workflows/ci.yml`, `tests/`
**Acceptance (sketch):**
- CI matrix adds `macos-latest` (Ubuntu remains primary)
- Schema-checker contract test (parametrized over `SCHEMA_CHECKS`)
- Corpus health test: every checker has ≥1 positive and ≥1 negative test
- Subprocess CLI smoke tests for `hermia`, `hermia-regression`, `hermia-push`
- MetricsSampler concurrency test (clean shutdown, no file handle leak)
**Why:** Locks in the testing investment from v0.1.

### Module Boundary Table CI enforcement
**Priority:** P3
**Depends on:** —
**Permitted scope:** `.github/workflows/`, `scripts/check_module_boundary.py` (NEW)
**Acceptance (sketch):**
- A GitHub Action diffs a PR's changed files against the AGENTS.md table for the declared task type (parsed from PR title or label)
- Soft-fails with a comment listing out-of-scope files; doesn't block merge but makes the violation visible
**Why:** Novel governance pattern. Possible blog post.

### Sidecar aggregates file for fleet-scale repeat runs
**Priority:** P2
**Depends on:** Transport interface (fleet config)
**Permitted scope:** `src/hermia/results.py`, `src/hermia/screens.py`, `src/hermia/export.py`, `tests/unit/test_results.py`
**Acceptance (sketch):**
- Replace `patch_results()` with a sidecar file `eval_TIMESTAMP_aggregates.jsonl` written alongside the main JSONL
- After `_backfill_aggregates`, append one row to the sidecar keyed on `(run_id, model, test_id)` containing only the aggregate fields (`consistency_pct`, `pass_count`, `cold_warm_delta_tps`, `robustness_n`)
- Main JSONL rows never patched or re-read mid-run — O(1) per test completion regardless of run size
- `collect_results()` joins main + sidecar rows before returning; `hermia-push` inserts the merged view
- `patch_results()` removed; `results.py` reverts to append-only
**Why:** `patch_results` re-reads and rewrites the entire JSONL on every (model, test_id) completion — O(n²) total I/O. Acceptable for v0.1 fleet sizes (10 models × 19 tests). At large fleet scale — many nodes, high repeat counts, slow inference — this becomes a serious bottleneck. The sidecar pattern is O(1) per completion, never reads existing data, and keeps the main JSONL append-only.

---

## v0.3 — Eval Bus (target ~2026-08)

**Theme:** Hermia becomes the platform other tools build into. Probe, Sink, and LLM-as-judge land. The orchestration thesis becomes real.

### Probe interface + first three adapters
The plugin point that converts Hermia from a tool into a bus. Garak, PyRIT, HarmBench results pulled into Hermia's Postgres/Grafana stack as additional probe dimensions, alongside Hermia's own. Same hardware correlation, same framework mapping, same audit trail — but now spanning every major open-source security eval tool. The launch announcement writes itself.

Initial adapter set:
- **Garak** — the most-used open-source vulnerability scanner; consume Garak's JSONL output, map probes to Hermia's framework taxonomy
- **PyRIT** — Microsoft's red-team framework; consume its memory database, surface multi-turn attack chains in Hermia's view
- **HarmBench** — academic standard; consume its behavior-classification ASR scores

### Sink interface
The output side of the bus. Today, results write to JSONL + CSV (always) and Postgres (optional). The Sink interface lets practitioners route results to additional destinations: Prometheus push gateway, webhook URLs, S3, custom audit storage. Same internal API; many concrete implementations.

### LLM-as-judge integration
Reuse the infrastructure pattern (calling, rubrics, parsing, retry) from the fleet productive-work judge project — but with Hermia-specific rubrics for evaluating eval-response quality. Opt-in via `--judge` flag pointing at a configured manager-lane endpoint or any OpenAI-compatible model. Populates the `judge_score` and `judge_reasoning` columns declared empty in v0.1.

### Mutation testing on schemas.py
For the central scoring logic, run `mutmut` once, address surviving mutants, then add a monthly CI quality gate. Catches "the test passes even when the function returns the wrong answer" — the silent failure mode that destroys eval credibility.

### Snapshot/golden-file tests for end-to-end output
Pin canonical: "given this input fixture, the output JSONL row equals exactly this." Catches silent format drift after refactors. Especially important now that framework metadata, backend tagging, and judge fields are all populated — any silent rename breaks Grafana.

### Network-surface security tests
Now that auth tokens are in scope (v0.2 OpenAI-compat), assert that bearer tokens never appear in error messages, log lines, `output_preview`, or result rows. Garak doesn't do this; we should.

---

## vNext / Research

Items that aren't milestone-bound. Keep them surfaced so they don't get forgotten, but don't commit to dates.

- **Cross-backend divergence detection.** Same model + same prompt across CUDA / ROCm / Vulkan / Metal / CPU; flag output divergence beyond threshold. Requires multi-host orchestration. Genuine first-in-market capability.
- **Backend-targeted vulnerability probes.** Tests for known stack failure modes: quant corruption, OOM behavior, sampler determinism, fp8 precision artifacts. Probe-style for the inference layer.
- **Stack supply-chain analysis.** CVEs in the CUDA toolkit, ROCm, Vulkan drivers, llama.cpp builds the model is running on. Adjacent to standard SCA but framed for inference. Nobody does this.
- **Multi-host fleet orchestration.** Hermia today is single-host. The fleet-aware version coordinates runs across multiple machines, each on different hardware, and aggregates centrally.
- **Multi-turn / crescendo / TAP attack support.** PyRIT's home turf; if the eval-bus pivot doesn't already cover this via the PyRIT adapter, build native support.
- **TamperBench / SafeRBench coverage.** Safety-after-fine-tuning and reasoning-trace safety. Research-grade today; may become table stakes.
- **Calibration mode.** A small canonical subset of MMLU-Pro / GPQA-Diamond / LiveBench questions so fleet models can be placed on the public benchmark spectrum without external API access.
- **Model identity verification.** OWASP LLM08. A hash- or fingerprint-based test that verifies the lane returned the configured model. Depends on having lanes (post-v0.2).
- **PyPI publication.** Pre-release today. After v0.1 stabilizes (likely after first round of community feedback), publish to PyPI.

---

## Cross-cutting

### Testing standards
- All new modules: ≥80% coverage at module level
- All new schema checkers: ≥1 positive test, ≥1 negative test (enforced via corpus health test in v0.2)
- All new CLI entrypoints: subprocess invocation test (per AGENTS.md hard-rule #5)
- Property-based tests for any function that consumes arbitrary external data
- Integration tests against fake servers, not function-level mocks, for any code path that hits the network

### Governance
- AGENTS.md Module Boundary Table is the source of truth
- Every PR declares which task type it is (commit message convention or PR label)
- v0.2 ships CI enforcement of the table

### Branding rollout
- v0.1 README: keep current framing; add hardware support matrix and roadmap section
- v0.2 README: rewrite around the eval-bus thesis; new tagline lands here
- v0.3 launch post: the "Hermes built the lyre" story — practitioner-built tool that the ecosystem routes through

### Documentation
- `docs/llm-benchmark-landscape-2026.md` — competitive landscape (refreshed quarterly)
- `docs/security-framework-research.md` — framework mapping rationale
- `docs/roadmap.md` — this document; updated as decisions change
- v0.2: add `docs/architecture.md` covering the Probe / Transport / Sink interfaces
- v0.3: add `docs/adapters.md` covering how to write a new probe adapter

---

## Deferred / Rejected

Decisions made in conversation that we do not want to re-litigate later. If a future session pushes back on any of these, point at this list and require new evidence to overturn.

- **Microservices decomposition.** Wrong frame for a single-maintainer 1,300-line Python project. The architectural payoff (clean interfaces, separation of concerns) is captured by internal module boundaries plus the Probe/Transport/Sink plugin pattern, without the network-hop overhead. Revisit only if Hermia legitimately becomes multi-process at fleet scale.
- **Out-Garak Garak on probe count.** Garak has NVIDIA's headcount; we do not compete on coverage breadth. The strategic play is being the orchestration layer that pulls Garak's results in alongside others'.
- **LLM-as-judge in v0.1.** Too much architectural risk pre-launch. v0.3 with the schema room declared in v0.1.
- **Multi-turn / crescendo in v0.1.** Significant scope; PyRIT's home turf. Comes via the v0.3 PyRIT adapter, then native if needed.
- **Calibration mode (MMLU/GPQA subset) in v0.1.** Outside the security eval category. vNext.
- **TamperBench / SafeRBench in v0.1.** Research-grade, not yet expected of operational eval tools. vNext.
- **LiteLLM-specific integration as a v0.1 feature.** Subsumed by v0.2 OpenAI-compatible support, which unlocks LiteLLM "for free" without coupling Hermia to one gateway product.
- **Strict / mode-locked metrics on Apple Silicon.** Unified memory means VRAM is RAM; we report best-effort numbers and document the metric. We do not invent a separate VRAM concept that doesn't match the hardware.
- **Windows support.** Not in v0.1 or v0.2. Documented as "not yet" in the support matrix. Revisit only on community demand.
- **TUI pivot before v0.3.** The Textual TUI is the right shell for v0.1 and v0.2 — it is done, it works, and the Endpoint Bus transport work is display-layer agnostic. Reassess at v0.3 when the Eval Bus lands. Two concrete signals that should trigger the pivot: (1) Textual Pilot tests prove too brittle to maintain across the screens.py coverage gap, or (2) the consultancy use case demands a shareable / browser-accessible interface. The natural replacement is a thin FastAPI backend — Grafana already owns results display; the web UI only needs to cover "configure and launch a run." The Grafana integration is the architectural hedge: results are already decoupled from the display layer.

---

## Change log

- **2026-05-11** — Added local vs. fleet mode detection bead and TUI mode-aware display bead (P1, v0.1). Updated NVIDIA smoke test AC to reflect Windows-only inference fleet. Added TUI pivot criteria to Deferred/Rejected. NVIDIA bead (hermia-ku7) merged. Added three launch-readiness beads from external repo analysis: "Launch visual assets" (screenshots + GIF demo), "Getting Started Guide" (`docs/usage.md`), "GitHub launch checklist" (topics + release tag). Fixed AGENTS.md rule 8a → renumbered 9–12 sequentially. Fixed broken `docs/security-framework-research.md` reference in CLAUDE.md.
- **2026-05-10** — Initial draft. Covers v0.1 launch (2026-05-23), v0.2 endpoint bus, v0.3 eval bus, vNext research, cross-cutting, deferred. North Star and mythology framing established. Eval-bus thesis adopted.
