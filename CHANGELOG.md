# Changelog

All notable changes to Hermia are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

See [docs/roadmap.md](docs/roadmap.md) for the full plan.

---

## [0.2.0] — target 2026-07 (Fleet + TUI)

The "Endpoint Bus" release. Hermia grows from a single-host application into a
platform: headless fleet mode for multi-host eval from a YAML config, a
full-featured TUI for launch/configure/run/inspect, a pluggable Transport layer
that evaluates anything OpenAI-compatible, and an audited 30-test corpus with a
published methodology catalog and framework matrix.

### Added
- **Fleet mode** (`--fleet FILE`) — headless multi-host eval from a YAML config;
  the same suite runs across multiple endpoints in parallel, powered by a new
  concurrent runner (Workstream C, #93).
- **Fleet TUI** — host discovery and model selection; live multi-host run view
  across runner (L1), per-trial (L2), and detail (L3) screens; breadcrumb
  navigation; first-run and probe-failure empty-state guidance (#122–#129).
- **Transport abstraction** — pluggable Ollama and OpenAI-compatible transports;
  evaluate LiteLLM, OpenAI, Anthropic, Google, Bedrock, or local Ollama through
  one interface (Workstream A, #87), with `models: auto` endpoint
  auto-discovery (#112).
- **Sink interface + opt-in anonymized submission** — `hermia-submit` CLI for the
  community dataset, gated behind a value-level anonymizer (Workstream D,
  #95, #111).
- **Deterministic multi-turn evaluation** (Workstream E, #96).
- **Backend stack tagging** — GPU architecture, runtime version, and execution
  path (GPU vs spill) stamped on every result row.
- **Configurable per-test timeout** — CLI flag and per-host YAML key, for
  thinking-mode models (#126).
- **Corpus methodology catalog** — `docs/corpus-catalog.md`: per-test purpose,
  exact prompts, grading logic, four-framework control-ID mappings with
  rationale, and known limitations for all 30 tests, assembled from a
  machine-checked single source (`catalog-meta/`) with a CI-enforced security
  policy sign-off gate (Track 5, #99/#101/#103/#105).
- **GUARDS framework** — six-dimension standard for LLM guardrail construction,
  published (#104).
- **Packaging** — Docker image + ghcr.io publish workflow (#130), Homebrew tap
  with release-time formula bump (#136), and a docs-as-tested CI matrix that runs
  the README's install commands literally across 5 methods × OS × Python (#137).

### Changed
- Corpus normalized to GUARDS 6/6 across all 30 tests, with adversarial framing
  added to the multi-step-reasoning and numeric-correctness tests (#105).
- Extracted the aggregate scorer into `scoring.py` (`compute_scores` +
  `backfill_aggregates`).
- README and usage docs brought to v0.2 reality; added a 5-minute
  getting-started path (#128).

### Fixed
- Corpus grader corrections surfaced by the Track 5 audit: the
  `indirect-injection-tool-output` binary grader no longer false-passes on
  structure alone (content validation added); `instruction-override-resistance`
  now scores a refusal as a security pass and aligns its prompt to the oracle
  (#127); status-field semantics clarified (#102).
- Anonymizer now performs value-level sanitization of the `frameworks` field,
  stripping identifying strings smuggled inside custom-dataset framework values
  (#107).
- TUI: fleet YAML compatibility and a probe-subscription race (#125),
  trial-hang timeout, and Rich markup escaping (#124).

### Security
- Inner-branch negative-example tests for the security schema checkers, ensuring
  each grader rejects its documented failure cases, not just accepts its passes
  (#108).
- The scanning pipeline (gitleaks, trufflehog, trivy, bandit, pip-audit, ruff,
  mypy, guarddog) runs on every push and pull request.

### Known limitations
- Cross-stack reproducibility evidence (Metal × CUDA × ROCm) is being captured as
  an ongoing dataset published across the v0.2.x series, not as a single launch
  snapshot.
- Documented residual grader limitations (e.g. a ~1.1% false-positive band on
  `instruction-override-resistance` for out-of-fence leaks) are catalogued in
  `docs/corpus-catalog.md`.
- Dependencies are declared with **minimum-version floors** (`>=`) in
  `pyproject.toml`; no fully-pinned lockfile ships in v0.2.x. A resolver picking
  a newer transitive version can in principle change behavior. A committed
  lockfile is planned for v0.3.
- Row-level provenance today is corpus-hash stamping only (an unkeyed SHA-256
  of `agentic-tasks.json`). It detects accidental data drift given an
  authoritative reference; it is **not** cryptographic row-signing and does
  **not** cover the grading code in `schemas.py`. Row-signing and hashing the
  eval code are planned for v0.3. See `src/hermia/runner.py` (`corpus_sha256`).

---

## [0.1.0] — target 2026-05-23

First stable eval suite. Core TUI, multi-vendor GPU metrics, robustness scoring,
integration test infrastructure, and a rigorous CI/security pipeline.

### Added
- Interactive TUI (`textual`) — model selection, eval dimension selection, live run view
- Live system metrics — CPU, RAM, GPU%, VRAM during eval execution
- Cold-load benchmarking — measures model load time from clean VRAM state
- Eval test suite — 20+ structured agentic test cases across 7 dimensions:
  - `security`: injection resistance, credential protection, scope escalation refusal,
    system prompt extraction resistance, structured field injection, adversarial robustness
  - `tool-use`: tool invocation, tool selection, compound multi-step sequencing
  - `reasoning`: multi-step decomposition, error recovery, partial failure handling
  - `constraint`: schema compliance, numeric correctness, adversarial input robustness
  - `routing`: classification routing, lane routing evasion
  - `memory`: cross-turn context retention
  - `domain`: home automation agent, structured data extraction
- Framework mapping — OWASP LLM Top 10 (2025), MITRE ATLAS v5.1, CSA MAESTRO, NIST AI RMF
- Schema validation via `_keys_ok()` helper — tolerates reasoning model extra keys
- Regression detection script (`hermia-regression`) — detects behavioral drift across runs
- NVIDIA GPU metrics — `nvidia-smi` integration; vendor-tagged `detect_gpu()` result
  (hermia-ku7, PR #33)
- Apple Silicon GPU metrics — `ioreg` integration for unified-memory VRAM reporting on
  macOS arm64 (hermia-c3f, PR #34)
- Robustness module + `--repeat N` flag — multi-run consistency scoring, `is_cold` / warm
  tracking, `cold_warm_delta_tps`, `patch_results()` aggregate backfill (hermia-0ws, PR #35)
- TUI test coverage via Textual `Pilot` — SelectionScreen + RunnerScreen happy-path and
  edge-case tests; `screens.py` coverage 31% → 94% (hermia-tun, PR #36)
- Fake-Ollama integration test fixture — stdlib HTTP server in `tests/integration/`;
  covers happy path, API drift, timeout, 500, malformed JSON, tags endpoint
  (hermia-w59, PR #37)
- Determinism / stability harness — end-to-end test asserting identical scored fields
  for identical inputs; timing fields excluded from equality check (hermia-gx8, PR #38)
- Property-based tests on all 19 schema checkers via `hypothesis` — total, required-keys-
  present, and required-keys-missing properties; 64 tests; `schemas.py` coverage 76% → 97%
  (hermia-xjj, PR #39)
- CI pipeline — ruff, mypy, pytest (474 tests, 89% branch coverage) on all branches and PRs
- Security CI pipeline — gitleaks, trivy, bandit, pip-audit on PRs to main + weekly
- Gemini Code Assist wired for PR review
- Branch protection active on `main`

### Security
- All schema checkers patched to tolerate benign extra keys from reasoning models
  (o-series, QwQ, DeepSeek-R1) — three separate fix iterations before stable pattern
  established (`_keys_ok()` helper)
- CLI entrypoint `hermia-regression` tested via direct invocation after regression.py
  `main()` bug discovered in review (commit 006e621)
- Security CI workflow permissions minimally scoped after gitleaks permissions
  and pip-audit isolation issues resolved (commit b9f1ff0)
