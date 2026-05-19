# Hermia

[![CI](https://github.com/scottblydotcom/hermia/actions/workflows/ci.yml/badge.svg)](https://github.com/scottblydotcom/hermia/actions/workflows/ci.yml)
[![Security](https://github.com/scottblydotcom/hermia/actions/workflows/security.yml/badge.svg)](https://github.com/scottblydotcom/hermia/actions/workflows/security.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Structured behavioral eval for local LLMs. The model binary is not the unit of analysis — the inference stack is.

---

You selected a model by benchmark score. That benchmark ran on somebody else's hardware,
their driver stack, their runtime version. Not yours.

A ROCm update can flip a security test from PASS to FAIL. Hermia catches it — because it
runs on your stack, not a cloud proxy.

<video src="assets/demo.mp4" autoplay loop muted playsinline width="100%" aria-label="Hermia demo: running behavioral evals across a local LLM fleet"></video>

---

## What It Does

Hermia runs structured behavioral evaluation against local Ollama models and scores results
for correctness across security, reasoning, and tool-use dimensions. Results map directly to
established AI security frameworks so findings have documented provenance — not just "it
seemed fine."

Live system metrics (CPU, RAM, GPU, VRAM, tokens/sec) run alongside every eval. Cold-load
benchmarking measures actual model load time from a clean VRAM state, not cached inference.
Because "how fast is it really" is a different question than "how fast is it after it's
already warm."

**v0.1 scope:** single-turn, deterministic structural eval against Ollama-compatible local
endpoints. Nuanced intent evaluation and multi-turn support land in v0.3.

**Fleet mode** (`--fleet FILE`) runs headless multi-host eval from a YAML config — same
test suite, multiple Ollama endpoints in parallel. Compare CUDA vs. Metal on the same
model. See where your inference stack diverges.

---

## Why Hermia Exists

[Garak](https://github.com/NVIDIA/garak) is built by NVIDIA — you know, the company
currently valued at roughly the GDP of a medium-sized country. It has hundreds of probes,
years of community contributions, serious research backing, and a team of people whose
full-time job is this. You should use it.

Hermia is built in a consultancy lab. Different scale. Genuinely different problem.

Garak asks: *is this model vulnerable to known attack patterns?*

Hermia asks: **does this model behave correctly on your inference stack — and what is your
hardware actually doing while it runs?**

- Will it refuse a forbidden action — consistently, not just when it feels like it?
- Does it maintain a security boundary when a structured workflow nudges toward crossing it?
- Will it leak a system prompt credential if the user asks cleverly enough?
- Does it correctly route a request that looks safe but isn't?

These aren't hypothetical. They're the questions a security practitioner asks before
deploying a model in an environment where it has real tools and real permissions.

Garak scans for vulnerabilities. Hermia evaluates behavioral correctness against structured
pass/fail criteria mapped to frameworks you can actually cite in a risk assessment. They do
different things. Run both.

The practitioner origin is a feature, not a bug — this was built by a security consultant
who runs models across a distributed inference fleet, cares about hardware costs, and needs
evals that work without sending data to a cloud API. If that sounds like you, Hermia was
built for your context.

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

## Hardware Support

| Platform | GPU | Status |
|---|---|---|
| Linux | AMD ROCm (gfx900 / RX series) | ✅ Tested |
| Linux | NVIDIA CUDA (sm_89 / RTX series) | ✅ Tested* |
| macOS | Apple Silicon (M1 / M2 / M3 / M4) | ✅ Tested |
| Linux | Intel iGPU | ⚠️ Best-effort |
| Linux / macOS | CPU-only (no discrete GPU) | ✅ Supported |
| Windows | Any | ❌ Not yet |

*NVIDIA metrics tested on Linux eval client. Windows Ollama servers are supported as fleet
targets via `--host`; running Hermia itself on Windows is not yet supported.

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
and press **Run**. Results appear live alongside system metrics. Each run writes
`results/eval_TIMESTAMP.jsonl` and `results/eval_TIMESTAMP.csv`.

See the [Getting Started Guide](docs/usage.md) for a full walkthrough: result
interpretation, `--repeat N` consistency scoring, fleet mode, regression detection,
and Postgres export.

---

## Roadmap

**v0.2 — Endpoint Bus** (target ~2026-06-15): Hermia evaluates anything that speaks
OpenAI-compatible — LiteLLM, OpenAI, Anthropic, Google, Bedrock, plus local Ollama. Fleet
config file for multi-host runs; backend stack tagging by GPU arch and runtime version.

**v0.3 — Eval Bus** (target ~2026-08): Hermia becomes the platform other tools build into.
Probe adapters for Garak, PyRIT, and HarmBench pull their results into Hermia's
hardware-correlated, framework-mapped view alongside Hermia's own probes. LLM-as-judge
scoring; Sink interface for custom output destinations (Prometheus, webhook, S3).

See [docs/roadmap.md](docs/roadmap.md) for the full plan.

---

## Project Status

**v0.1.0** — stable and tested. The core eval suite, fleet mode, audit trail, and findings
analysis pipeline are all shipping. The security pipeline (gitleaks, trivy, bandit,
pip-audit, ruff, mypy) is more rigorous than a research tool strictly needs to be. That
was intentional.

PyPI publication is planned after v0.1.0 stabilizes in the wild.

---

## Name

**Hermia** = **Hermes** (Greek messenger god, trickster, patron of travelers — thief of
Apollo's cattle) + **Pythia** (the Oracle of Delphi, who spoke for Apollo).

The tool steals answers from the Oracle and tells you which one to trust.

---

## Documentation

- [Getting Started Guide](docs/usage.md) — install, run, interpret results, fleet mode, Postgres export
- [Roadmap](docs/roadmap.md) — v0.2 endpoint bus, v0.3 eval bus, full backlog

---

## Security

Hermia communicates with Ollama via `/api/tags`, `/api/generate`, and `/api/ps`.
It never uploads model files and is not affected by model-upload CVEs
(CVE-2026-7482, CVE-2026-5757).

**Protect your Ollama instance:**

- Run Ollama bound to `127.0.0.1` (the default) — never expose port 11434 publicly
- Keep Ollama upgraded; 0.17.1+ patches CVE-2026-7482 (CVSS 9.1, heap memory
  disclosure via crafted GGUF upload, nicknamed "Bleeding Llama")
- CVE-2026-5757 (same attack class, no upstream patch as of May 2026) — restrict
  `/api/create` access at the network or firewall layer
- Fleet deployments: use `hermia-fleet.yaml` `auth` blocks or a Tailscale overlay
  to prevent unauthenticated access to remote Ollama endpoints

Hermia surfaces known Ollama version vulnerabilities at run time in the preflight
log as `SEC ⚠` warnings.

---

## Contributing

Contributions welcome. Please read [AGENTS.md](AGENTS.md) before opening a PR — it covers
the behavioral rules, module boundary table, and review gate sequence this project enforces.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details on how to get involved.

---

## License

MIT — see [LICENSE](LICENSE).
