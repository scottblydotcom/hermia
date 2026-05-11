# Changelog

All notable changes to Hermia are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

See [docs/roadmap.md](docs/roadmap.md) for the full plan.

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
- CI pipeline — ruff, mypy, pytest (410 tests, 89% branch coverage) on all branches and PRs
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
