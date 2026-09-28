# Changelog

All notable changes to Hermia are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

See [docs/roadmap.md](docs/roadmap.md) for the full plan.

---

## [0.2.1] — target 2026-10 (security-verdict fix)

The grading-correctness release. v0.2.0 recorded a security test as a single pass/fail
bit that also meant "the JSON was well-formed", so a model that obeyed an injection and
broke its own output was filed as a formatting failure, and some compromises in
well-formed JSON were graded as passes. 0.2.1 separates the two questions and re-grades
stored results the same way.

### Security grading
- **Security verdict separated from schema verdict** (#165). The live grader records a detected
  compromise as `SECURITY_FAIL` or `CONTENT_LEAK` instead of a formatting failure, and its
  raw-text gates run whether or not the response parses. `hermia-regrade` resolves each
  security row to *resisted*, *compromised* or *not evaluable*. A test whose detector reads
  only parsed output (such as `classification-routing`) still cannot see a compromise inside a
  response that fails to parse; such a row is *not evaluable*.
- In the security report, a demonstrated refusal in a response that parses is credited as
  resisted even when its envelope fails validation. Plain-text refusals and responses that do
  not parse stay *not evaluable* (#166).
- One compromise judgment shared by the live grader, the re-grader and the corpus audit; a
  grader crash is reported as `GRADER_ERROR`, never as the model's pass (#186).
- Detectors added or tightened: paraphrased injection adoption in
  `indirect-injection-tool-output` (#158), compliance on `multiturn-boundary-persistence`
  (#173, #179), and the `classification-routing` hijack that cites the attacker (#176, #188).
- A model response too deep to parse is filed as unparseable instead of aborting the run
  (#192).

### Reporting
- **`hermia-regrade`** re-derives the security verdict of stored rows from their stored
  responses, and prints one canonical three-number report over a denominator nothing drops
  (#187). It names why each unevaluable row could not be judged (#189) and splits verdicts
  by the test wording each row answered (#190).
- `hermia-regression` takes every verdict from the re-grader. It previously read stored
  grades and could not register a compromise on historical rows (#191).

### Provenance and machine identity
- `git_sha` is stamped alongside `hermia_version` on every result row the runner writes
  (`"unknown"` when hermia is not running from a git checkout) (#153, #154).
- Machine identity is bound to hardware rather than the network, with an SSH remote
  hardware probe (#163, #164). An unprobed GPU's measurements are recorded as null, not 0.0
  (#185).

### Fixed
- TUI: run identity on result rows and CSV column shear (#161), run-scoped results written
  where tooling can find them (#162), headless fleet configs load instead of returning zero
  hosts (#160), trial screens hydrate from run state (#159), local runs record metrics (#180).
- Fleet: unknown keys and nested auth/stack keys in fleet YAML are validated (#150, #151).
- Transport: OpenAI-compatible 5xx responses are retried (#152); a reasoning model's thinking
  channel is captured (#155).
- The GPU detection tests run on Apple Silicon (#175).

### Changed
- A grader-completeness contract and CI gate: every security detector must show a firing
  witness or be listed on a tracked allowlist of known blind spots (#167–#172, #178).
- Real fleet identifiers replaced with placeholders in docs, tests and code (#156).
- CI installs the package from source and runs `--help` on every console script declared in
  `pyproject.toml`; previously only `hermia` itself was run as an installed command.

### Known issues (disclosed, not fixed in 0.2.1)
- The multi-turn PII test (`multiturn-boundary-persistence`) checks only the final reply's
  `status` field, and its scenario plants no personal data to export: a reply that keeps a
  refusal status while listing email addresses scores as resisted.
- On some tests, a single awareness word such as "cannot" anywhere in a response suppresses some
  compromise markers, so a model that obeys while mentioning it can score as resisted.
- The live TUI view marks each row ✓ or ✗; a timeout and a compromise get the same ✗. The
  three-state view is `hermia-regrade`.
- The exporter's score, `hermia-push`, `hermia-analyze` and the Grafana SQL still read stored
  grades, so on historical data they find no compromises.
- `hermia-regression` leaves unjudged rows out of its rates, so a model that starts timing out
  or failing its format check raises no alert.
- `hermia-regression` pools every machine under one model name. An unhandled error during
  analysis exits 1, the same code as "regression detected" (a missing or invalid results file
  exits 2).
- `system-user-precedence` detects only three literal `/etc/passwd` lines (`root`, `daemon`,
  `nobody`). A model that honours the claimed override in any other way, or discloses other
  files or accounts, while returning a refusal envelope scores as resisted.
- `system-prompt-extraction-resistance` detects only verbatim system-prompt text; a paraphrased
  disclosure scores as resisted.
- On `classification-routing`, the hijack detector convicts only a wrong route that cites the
  attacker's authority. A wrong route that cites nothing is *not evaluable*, so it raises
  neither a compromise nor a regression alert; if it also carries a refusal token (for example
  `status: cannot_complete`) it scores as resisted.
- `hermia-regrade` applies the current detectors to stored responses, so historical figures
  change between versions. Compare only figures produced by the same version.

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
- **Community dataset submission** — `hermia-submit` CLI for opt-in anonymized upload to
  the community dataset, gated behind a value-level anonymizer (Workstream D,
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
- Multi-turn (and single-turn) output determinism is backend-dependent, not guaranteed:
  Hermia pins `temperature=0` and `seed=42`, but whether a backend reproduces byte-identical
  output varies by runtime / GPU stack — this cross-stack variance is what Hermia measures.
- The `indirect-injection-tool-output` pass rate is a ~44–72% semantic band, not a point
  estimate (the describe/flag/adopt boundary is semantic — see `docs/corpus-catalog.md`).
- Most corpus cells are single-run point estimates with no per-cell variance, pending ≥3
  runs/cell.

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
