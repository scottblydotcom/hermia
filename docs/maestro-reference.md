# CSA MAESTRO Framework — Hermia Reference

**Status:** Authoritative internal reference for all Hermia → MAESTRO mappings.
**Source:** Huang, Ken. *"Agentic AI Threat Modeling Framework: MAESTRO."* Cloud Security Alliance, Industry Insights, 6 February 2025. <https://cloudsecurityalliance.org/blog/2025/02/06/agentic-ai-threat-modeling-framework-maestro>
**Version reference:** Authoritative version string lives in `agentic-tasks.json::framework_versions.csa_maestro`. Runtime field key is `csa_maestro`.
**Companion tool (open source):** <https://github.com/CloudSecurityAlliance/MAESTRO> — Next.js + Genkit web app; AI-generated per-layer threat analysis from an architecture description. No programmatic API as of 2026-06.

> **Reproduction note.** Layer names, descriptions, and threat lists below are reproduced from the CSA paper as fetched 2026-06-06. Direct-quoted definitions are marked with quotation marks and attributed to Huang (2025). Where the paper is silent or implicit on cross-layer concerns (tool calling, memory, routing, prompt injection), the placement guidance below is Hermia's reasoned interpretation, not a CSA pronouncement.

---

## The 7 layers at a glance

| # | Layer | One-line scope |
|---|---|---|
| L1 | Foundation Models | The model itself — its weights, behaviors, and the threats that target model inference |
| L2 | Data Operations | Stores and pipelines that feed the agent: RAG, vector DBs, databases |
| L3 | Agent Frameworks | The orchestration logic — frameworks, toolkits, conversational scaffolding, tool selection, state |
| L4 | Deployment & Infrastructure | Where the agent *runs* — cloud, on-prem, containers, orchestration |
| L5 | Evaluation & Observability | How the agent is *measured* and monitored |
| L6 | Security & Compliance (**vertical**) | Cross-cutting layer; specifically about AI agents *used as security tools* |
| L7 | Agent Ecosystem | The marketplace and integration boundary: agent-to-agent, agent-to-tool, agent-to-app |

L1–L5 and L7 are horizontal layers a single test typically targets. **L6 is vertical and specifically scoped to AI agents acting as defenders.** Hermia tests evaluation subjects, not defenders — L6 is rarely a Hermia mapping.

---

## Layer-by-layer detail

### L1 — Foundation Models
**Definition (Huang 2025):** *"The core AI model on which an agent is built. This can be a large language model (LLM) or other forms of AI."*

**Threats named in the paper:** Adversarial Examples · Model Stealing · Backdoor Attacks · Membership Inference Attacks · Data Poisoning (Training Phase) · Reprogramming Attacks · Denial of Service (DoS) Attacks.

**Hermia maps here when:** the test targets model-level behavior independent of orchestration — adversarial inputs, message-hierarchy adherence (system-over-user), system-prompt extraction at the model layer, jailbreak resistance as a model property.

---

### L2 — Data Operations
**Definition (Huang 2025):** *"This is where data is processed, prepared, and stored for the AI agents, including databases, vector stores, RAG (Retrieval Augmented Generation) pipelines, and more."*

**Threats named:** Data Poisoning · Data Exfiltration · Denial of Service on Data Infrastructure · Data Tampering · Compromised RAG Pipelines.

**Hermia maps here when:** the test exercises a corpus, RAG store, or persistent data plane. **Not** for in-prompt memory or conversation state — that is framework state (L3).

---

### L3 — Agent Frameworks
**Definition (Huang 2025):** *"This layer encompasses the frameworks used to build the AI agents, for example toolkits for conversational AI, or frameworks that integrate data."*

**Threats named:** Compromised Framework Components · Backdoor Attacks · Input Validation Attacks · Supply Chain Attacks · Denial of Service on Framework APIs · Framework Evasion.

**Per CSA's own framing, L3 is the home of:**
- **Tool use, tool calling, tool selection** ("toolkits for conversational AI")
- **Input validation** — including instruction-override and structured-field injection
- **Framework evasion** — including prompt-injection bypasses of the framework's safety controls

**Hermia maps here when:** the test exercises orchestration, multi-step planning, refusal logic, tool-call schema, routing decisions, memory/state, or framework-level input validation. **This is the most common Hermia mapping** because Hermia evaluates the agent's structured response — which is a framework artifact.

---

### L4 — Deployment & Infrastructure
**Definition (Huang 2025):** *"This layer involves the infrastructure on which the AI agents run (e.g., cloud, on-premise)."*

**Threats named:** Compromised Container Images · Orchestration Attacks · Infrastructure-as-Code (IaC) Manipulation · Denial of Service Attacks · Resource Hijacking · Lateral Movement.

**Hermia maps here when:** the test targets the substrate the model runs on — runtime, container, GPU stack, serving framework. Hermia's **stack-aware availability** measurements (CUDA/ROCm/Vulkan/Metal divergence, timeout/error rates, VRAM offload) are the natural L4 surface — but **none of the 30 capability/security tests are L4 tests.** Mapping a tool-call or routing test to L4 is a category error: it conflates "application semantics" with "deployment substrate."

---

### L5 — Evaluation & Observability
**Definition (Huang 2025):** *"This layer focuses on how AI agents are evaluated and monitored, including tools and processes for tracking performance and detecting anomalies."*

**Threats named:** Manipulation of Evaluation Metrics · Compromised Observability Tools · Denial of Service on Evaluation Infrastructure · Evasion of Detection · Data Leakage through Observability · Poisoning Observability Data.

**Hermia maps here when:** the test is *about the evaluation pipeline itself* — grader manipulation, observability leakage, metric tampering. **Hermia tests subjects, it does not test eval substrate, so L5 is rarely a per-test mapping.** Hermia *as a tool* targets L5; Hermia's *tests* target L1/L3/L7.

Mapping a multi-turn or multi-step test to L5 is a category error — those exercise framework state (L3), not observability infrastructure.

---

### L6 — Security & Compliance *(vertical)*
**Definition (Huang 2025):** *"This vertical layer cuts across all other layers, ensuring that security and compliance controls are integrated into all AI agent operations. This layer assumes that AI agents are also used as a security tool."*

**Threats named:** Security Agent Data Poisoning · Evasion of Security AI Agents · Compromised Security AI Agents · Regulatory Non-Compliance by AI Security Agents · Bias in Security AI Agents · Lack of Explainability in Security AI Agents · Model Extraction of AI Security Agents.

**Hermia rarely maps here.** L6's premise is "an AI agent used as a defender" (e.g. an LLM running a SIEM rule). Hermia evaluates agents-as-subjects. L6 is only relevant if Hermia adds a test where the subject is *itself* performing a security task (e.g. a triage agent that must refuse poisoning).

---

### L7 — Agent Ecosystem
**Definition (Huang 2025):** *"The ecosystem layer represents the marketplace where AI agents interface with real-world applications and users. This encompasses a diverse range of business applications, from intelligent customer service platforms to sophisticated enterprise automation solutions."*

**Threats named:** Compromised Agents · Agent Impersonation · Agent Identity Attack · **Agent Tool Misuse** · Agent Goal Manipulation · Marketplace Manipulation · **Integration Risks** · Horizontal/Vertical Solution Vulnerabilities · Repudiation · Compromised Agent Registry · **Malicious Agent Discovery** · Agent Pricing Model Manipulation · Inaccurate Agent Capability Description.

**Hermia maps here when:** the test exercises the agent's boundary with external systems — tool misuse at the application layer, scope escalation into protected systems, indirect injection via untrusted tool output (the canonical L7 + L3 combo), routing into the wrong specialist.

---

## Where the recurring Hermia concepts actually live

| Concept | Primary | Also relevant |
|---|---|---|
| Tool calling / tool selection (correctly invoking a tool) | **L3** | L7 if exercising the ecosystem (untrusted tool discovery) |
| Tool misuse / agent overreach via tools | **L7** | L3 (framework boundary) |
| Multi-step planning / orchestration | **L3** | — |
| Memory / context retention (in-conversation) | **L3** | L2 only if backed by a persistent store |
| Routing decisions | **L3** | L7 (if routing across an agent ecosystem) |
| Prompt injection — direct | **L3** (framework input validation) | L1 (model-level resistance) |
| Prompt injection — indirect via tool output | **L3** + **L7** | — |
| Adversarial input / jailbreak at the model layer | **L1** | L3 (framework filters) |
| System-over-user precedence | **L1** | L3 (framework enforcement) |
| Refusal logic / scope boundary | **L3** | L1 (model disposition); L7 for ecosystem-boundary refusals |
| Multi-turn persistence | **L3** | — |
| Stack/throughput/timeout (availability) | **L4** | L5 (if framed as observability) |

---

## Decision tree for mapping a new Hermia test

```
1. Does the test exercise the model's behavior independent of orchestration?
   (jailbreak, system-over-user, adversarial input, system-prompt extraction at model layer)
   → L1

2. Does the test exercise the framework — schema, tool call, routing, refusal,
   memory, multi-step plan, instruction hierarchy, input validation?
   → L3   (this catches most Hermia tests)

3. Does the test cross the agent's external boundary —
   tool *misuse*, scope escalation into protected systems, indirect injection
   via untrusted tool/data output, routing across specialists?
   → add L7 (often alongside L3)

4. Does the test target persistent data infrastructure —
   RAG store, vector DB, training data?
   → L2

5. Does the test target the runtime substrate —
   container, GPU stack, framework version drift?
   → L4   (typically a Hermia availability/stack metric, NOT a per-test mapping)

6. Does the test target the evaluation pipeline itself — grader, observability?
   → L5   (rarely a per-test mapping for Hermia)

7. Is the subject of evaluation acting as a security defender?
   → L6   (rarely applicable to current Hermia tests)
```

**Capability tests (numeric-reasoning, multi-step-reasoning, etc.) that have no security or boundary-crossing dimension may legitimately map to no MAESTRO layer.** Empty mapping is honest; forcing a layer is overclaiming.

---

## Common mapping errors (caught in 2026-06 audit)

- **"L4 because the test is in the application layer."** L4 is *infrastructure*, not *application*. Application/framework semantics are L3.
- **"L5 because the test is multi-step."** L5 is about *measuring* the agent, not *executing* a multi-step plan. Planning is L3.
- **"L1 only for prompt injection."** Prompt injection per CSA explicitly spans L3 (framework input validation) and L7 (ecosystem boundary). L1-only is incomplete.
- **"No mapping because it's not obviously security."** Tool-calling capability is L3 — framework correctness *is* a security property because failures cascade.

---

## Citation

Huang, K. (2025, February 6). *Agentic AI Threat Modeling Framework: MAESTRO.* Cloud Security Alliance Industry Insights. <https://cloudsecurityalliance.org/blog/2025/02/06/agentic-ai-threat-modeling-framework-maestro>

CSA MAESTRO Threat Analyzer (companion tool). Cloud Security Alliance. <https://github.com/CloudSecurityAlliance/MAESTRO>
