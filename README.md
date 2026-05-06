# Hermia

[![CI](https://github.com/scottblydotcom/hermia/actions/workflows/ci.yml/badge.svg)](https://github.com/scottblydotcom/hermia/actions/workflows/ci.yml)
[![Security](https://github.com/scottblydotcom/hermia/actions/workflows/security.yml/badge.svg)](https://github.com/scottblydotcom/hermia/actions/workflows/security.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Interactive LLM security eval TUI for local models.

---

## What It Does

Hermia runs structured agentic evaluation test cases against local Ollama models and scores
them for behavioral correctness across security, reasoning, and tool-use dimensions. Results
map directly to established AI security frameworks so findings have documented provenance.

Live system metrics (CPU, RAM, GPU, VRAM, tokens/sec) run alongside every eval. Cold-load
benchmarking measures actual model load time from a clean VRAM state — not cached inference.

---

## Why Hermia Exists

[Garak](https://github.com/NVIDIA/garak) is the right tool for LLM vulnerability scanning —
breadth of probes, established taxonomy, NVIDIA backing. Use it.

Hermia answers a different question: **does this model behave correctly as an agentic
component in a structured workflow?**

- Will it refuse a forbidden action — consistently, not just sometimes?
- Does it maintain a security boundary when a multi-step task nudges toward crossing it?
- Will it leak a system prompt credential if asked cleverly?
- Does it correctly route a request that looks safe but isn't?

Garak scans for known vulnerability patterns. Hermia evaluates agentic behavioral correctness
against structured pass/fail criteria, with framework-mapped findings you can cite.

They are complementary. This is not a replacement.

---

## Framework Coverage

| Framework | What Hermia Maps To |
|---|---|
| **OWASP LLM Top 10 (2025)** | LLM01 prompt injection (direct + indirect), LLM06 excessive agency / scope escalation |
| **MITRE ATLAS v5.1** | AML.T0051 direct injection, AML.T0054 indirect injection, AML.T0099 tool data poisoning, AML.T0100 structured field injection |
| **CSA MAESTRO** | L1 foundation model robustness, L3 agent framework routing and lane evasion |
| **NIST AI RMF** | Measure function: ME 2.3 deployment-similar benchmarking, ME 2.4 production monitoring, ME 3.1 regression detection |

---

## Eval Dimensions

| Dimension | What It Tests |
|---|---|
| `security` | Injection resistance, credential protection, scope escalation refusal, system prompt extraction resistance, structured field injection |
| `tool-use` | Valid tool invocation, correct tool selection, dependency-aware multi-step chaining |
| `reasoning` | Multi-step decomposition, error recovery and fallback planning, partial failure handling |
| `constraint` | Exact schema compliance, numeric correctness, adversarial input robustness |
| `routing` | Request classification, lane routing evasion detection |
| `memory` | Cross-turn context retention |
| `domain` | Home automation agent, structured data extraction |

---

## Requirements

- Python 3.11+
- [Ollama](https://ollama.ai) running locally (`ollama serve`)
- At least one model pulled: `ollama pull llama3.2` or any compatible model

No cloud API keys required. No data leaves your machine.

---

## Install

From source (pre-PyPI):

```bash
git clone https://github.com/scottblydotcom/hermia
cd hermia
pip install -e .
hermia
```

PyPI publication is on the roadmap. See [project status](#project-status).

---

## Quickstart

```bash
# Start Ollama if it isn't running
ollama serve

# Launch Hermia
hermia
```

Hermia opens a TUI. Select a model from the list, choose which eval dimensions to run,
and press **Run**. Results appear live alongside system metrics.

To run the regression detection script against a saved results file:

```bash
hermia-regression results/all-results.json
```

---

## Project Status

**Pre-release.** Core eval suite is stable and passing. The security test coverage maps to
OWASP, ATLAS, MAESTRO, and NIST RMF as documented above. Active development continues.

Pending before PyPI publication:
- Grafana metrics exporter (eval pass rates as Prometheus gauges)
- Expanded domain coverage (healthcare, financial, DevOps agent contexts)
- Fleet output quality scoring

---

## Name

**Hermia** = **Hermes** (Greek messenger god, trickster, patron of travelers — thief of
Apollo's cattle) + **Pythia** (the Oracle of Delphi, who spoke for Apollo).

The tool steals answers from the Oracle and tells you which one to trust.

---

## Contributing

Contributions welcome. Please read [AGENTS.md](AGENTS.md) before opening a PR — it covers
the behavioral rules, module boundary table, and review gate sequence this project enforces.

[CONTRIBUTING.md](CONTRIBUTING.md) is in progress.

---

## License

MIT — see [LICENSE](LICENSE).
