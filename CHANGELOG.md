# Changelog

All notable changes to Hermia are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Planned
- Grafana metrics exporter — eval pass rates as Prometheus gauges
- Expanded domain coverage — healthcare agent, financial agent, DevOps CI secrets
- Fleet output quality scoring
- PyPI publication

---

## [0.1.0] — 2026-05-03

First stable eval suite. Core TUI, security test coverage, and CI pipeline established.

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
- CI pipeline — ruff, mypy, pytest on all branches and PRs
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
