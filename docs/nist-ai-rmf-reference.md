# NIST AI Risk Management Framework — Hermia Reference

**Status:** Authoritative internal reference for all Hermia → NIST AI RMF mappings.
**Primary source:** *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*, NIST AI 100-1, January 2023. <https://doi.org/10.6028/NIST.AI.100-1>
**Version reference:** Authoritative version string lives in `agentic-tasks.json::framework_versions.nist_ai_rmf`. Runtime field key is `nist_ai_rmf`.
**Companion resource:** *NIST AI RMF Playbook* (living document) — voluntary subcategory-level guidance. <https://www.nist.gov/itl/ai-risk-management-framework> · JSON copy on disk: `docs/nist_ai_rmf_playbook.json`

> **Reproduction note.** Function definitions, category names, and subcategory text below are reproduced from NIST AI 100-1 and the Playbook JSON as fetched 2026-06-06. Direct-quoted passages are in quotation marks. Where the framework is silent or implicit on cross-cutting concerns (tool calling, multi-turn, prompt injection), the placement guidance is Hermia's reasoned interpretation against the trustworthiness-characteristic axes.

---

## The 4 functions at a glance

| Function | Sub-cats | Purpose |
|---|---|---|
| **GOVERN** | 19 | Cross-cutting. Organizational culture, policies, accountability for AI risk. |
| **MAP** | 18 | Context-setting. Categorize the system, identify risks, define scope. Pre-test. |
| **MEASURE** | 22 | TEVV. Quantitatively/qualitatively evaluate trustworthiness characteristics. |
| **MANAGE** | 13 | Risk treatment. Prioritize, respond, recover, decommission. Operational. |

**For Hermia, MEASURE is the dominant function.** Hermia is a TEVV tool — every test it ships is an instance of "evaluating an AI system for trustworthy characteristics" (the MEASURE 2 category mandate). Hermia tests almost never map to GOVERN (organizational), MAP (context), or MANAGE (operational response).

---

## The 7 trustworthiness characteristics (NIST AI 100-1 §3)

These are the axes that MEASURE 2.x subcategories cover. Per the RMF (Figure 4), **Valid & Reliable** is the base; **Accountable & Transparent** is cross-cutting.

| # | Characteristic | Definition (paraphrased from §3) |
|---|---|---|
| 3.1 | **Valid & Reliable** | Accuracy + robustness/generalizability; performance under expected and unexpected conditions |
| 3.2 | **Safe** | *"Not under defined conditions, lead to a state in which human life, health, property, or environment is endangered"* — physical/environmental safety, not security |
| 3.3 | **Secure & Resilient** | Withstand adversarial examples, data poisoning, exfiltration; maintain confidentiality, integrity, availability |
| 3.4 | **Accountable & Transparent** | Information about the system and its outputs is available; provenance, audit |
| 3.5 | **Explainable & Interpretable** | Mechanisms (how) and meaning (why) of system outputs |
| 3.6 | **Privacy-Enhanced** | Safeguard human autonomy, identity, dignity (PII-grade) |
| 3.7 | **Fair — with Harmful Bias Managed** | Equality, equity; systemic/computational/human-cognitive bias managed |

**Critical scope distinction (caught in 2026-06 audit):**
- **Safe (3.2 / MEASURE 2.6)** = *physical or environmental* harm. Refusing to exfiltrate `/etc/passwd` is not a Safe test.
- **Secure & Resilient (3.3 / MEASURE 2.7)** = adversarial input, exfiltration, confidentiality/integrity boundary. This is where Hermia's prompt-injection / refusal tests live.
- **Privacy-Enhanced (3.6 / MEASURE 2.10)** = *human* autonomy / identity / dignity. Test API keys and synthetic credentials in a prompt are not Privacy tests; they're Security tests.

---

## All 72 subcategories — compact index

### GOVERN (19) — organizational, cross-cutting
GOVERN 1.1–1.7 (policies & process) · 2.1–2.3 (accountability) · 3.1–3.2 (workforce diversity, human-AI oversight) · 4.1–4.3 (safety-first culture, incident sharing) · 5.1–5.2 (external feedback) · 6.1–6.2 (third-party / supply chain)

### MAP (18) — context, categorization, risk identification
MAP 1.1–1.6 (context established) · 2.1–2.3 (system categorization & TEVV considerations) · 3.1–3.5 (capabilities/benefits/costs/scope/human oversight) · 4.1–4.2 (third-party legal & risk controls) · 5.1–5.2 (impacts & engagement)

### MEASURE (22) — **Hermia's primary home**
MEASURE 1.1–1.3 (methods & metrics selected) · **2.1–2.13 (trustworthy characteristics evaluation)** · 3.1–3.3 (risk tracking) · 4.1–4.3 (measurement-efficacy feedback)

### MANAGE (13) — operational response
MANAGE 1.1–1.4 (prioritization & response) · 2.1–2.4 (sustain value, recover, deactivate) · 3.1–3.2 (third-party monitoring) · 4.1–4.3 (post-deployment monitoring & incident comms)

---

## Hermia-relevant MEASURE subcategories — detail

These are the only subcategories any Hermia test should target. Verbatim from NIST AI 100-1 §5.3 + Playbook.

### MEASURE 2.4 — Functionality and behavior monitored in production
> *"The functionality and behavior of the AI system and its components – as identified in the MAP function – are monitored when in production."*

**Hermia mapping:** Rarely a per-test target. Hermia *is* the monitoring tool, not the thing-being-monitored. Possibly fits multi-turn tests where the question is "does behavior hold up across turns" — but MEASURE 2.5 (validity) usually fits better.

### MEASURE 2.5 — Valid and reliable
> *"The AI system to be deployed is demonstrated to be valid and reliable. Limitations of the generalizability beyond the conditions under which the technology was developed are documented."*

**Playbook:** *"An AI system that is not validated or that fails validation may be inaccurate or unreliable or may generalize poorly to data and settings beyond its training, creating and increasing AI risks and reducing trustworthiness. … Establish or identify, and document approaches to measure forms of validity, including: construct validity, internal validity, external validity, the use of experimental design principles and statistical analyses and modeling."*

**Hermia mapping:** **All capability tests.** A test that asks "does this model emit a schema-correct tool call / multi-step plan / correct arithmetic / correct routing" is a validity-and-reliability demonstration.

### MEASURE 2.6 — Safe (physical/environmental)
> *"AI system is evaluated regularly for safety risks – as identified in the MAP function. The AI system to be deployed is demonstrated to be safe, its residual negative risk does not exceed the risk tolerance, and can fail safely, particularly if made to operate beyond its knowledge limits."*

**Playbook:** *"Many AI systems are being introduced into settings such as transportation, manufacturing or security, where failures may give rise to various physical or environmental harms. AI systems that may endanger human life, health, property or the environment are tested thoroughly prior to deployment …"*

**Hermia mapping:** **None of the current 30.** Hermia does not exercise physical/environmental safety. A model refusing to exfiltrate `/etc/passwd` is not a Safe (2.6) test — that's a Security (2.7) test. Don't map here unless a future Hermia test exercises a physical-harm refusal (cyber-physical / industrial control / medical advice).

### MEASURE 2.7 — Security and resilience
> *"AI system security and resilience – as identified in the MAP function – are evaluated and documented."*

**Playbook:** *"AI systems, as well as the ecosystems in which they are deployed, may be said to be resilient if they can withstand unexpected adverse events or unexpected changes in their environment or use … Common security concerns relate to adversarial examples, data poisoning, and the exfiltration of models, training data, or other intellectual property through AI system endpoints. AI systems that can maintain confidentiality, integrity, and availability through protection mechanisms that prevent unauthorized access and use may be said to be secure. Use red-team exercises to actively test the system under adversarial or stress conditions."*

**Hermia mapping:** **All security tests.** The Playbook literally names "adversarial examples," "exfiltration," "confidentiality / integrity / availability," and "red-team exercises." Every prompt-injection variant, scope-escalation, credential-leak, system-prompt-extraction, and refusal-under-pressure test lives here.

### MEASURE 2.9 — Explained, validated, output interpreted in context
> *"The AI model is explained, validated, and documented, and AI system output is interpreted within its context – as identified in the MAP function – and to inform responsible use and governance."*

**Hermia mapping:** Edge case. Hermia produces interpretable per-run pass/fail with a rationale; this is the *meta* mapping for Hermia-as-a-tool, not for any individual test.

### MEASURE 2.10 — Privacy risk
> *"Privacy risk of the AI system – as identified in the MAP function – is examined and documented."*

**Playbook:** *"Privacy refers generally to the norms and practices that help to safeguard human autonomy, identity, and dignity. … typically address freedom from intrusion, limiting observation, or individuals' agency to consent to disclosure or control of facets of their identities (e.g., body, data, reputation)."*

**Hermia mapping:** **None of the current 30.** Test credentials (`sk-test-abc123xyz789`) and synthetic system prompts are not PII; protecting them is a Security (2.7) test, not a Privacy (2.10) test. Don't map here unless a future Hermia test exercises actual PII handling.

---

## Where the recurring Hermia concepts live

| Concept | Primary | Notes |
|---|---|---|
| Capability — tool call schema, multi-step plan, schema adherence, routing-correctness | **MEASURE 2.5** | Validity = framework correctness demonstrated |
| Multi-turn context retention | **MEASURE 2.5** | Validity across turns |
| Adversarial input / jailbreak / prompt injection | **MEASURE 2.7** | Playbook names "adversarial examples" explicitly |
| Structured-field / indirect injection | **MEASURE 2.7** | Confidentiality/integrity boundary |
| Refusal of harmful task (cyber-security) | **MEASURE 2.7** | Security boundary, not Safe (2.6) |
| Refusal of physical-harm task (future) | **MEASURE 2.6** | When/if Hermia adds cyber-physical tests |
| System-over-user precedence | **MEASURE 2.7** | Privilege-boundary test |
| Credential / system-prompt confidentiality | **MEASURE 2.7** | Not Privacy (2.10) — test secrets aren't PII |
| Multi-turn refusal persistence | **MEASURE 2.7** | Resilience under sustained pressure |

---

## Decision tree for mapping a new Hermia test

```
1. Is the test exercising capability (correctness, validity of output) under benign conditions?
   → MEASURE 2.5

2. Is the test exercising the model under adversarial input, attempted exfiltration,
   instruction override, scope escalation, or any confidentiality/integrity boundary?
   → MEASURE 2.7

3. Does the test exercise refusal of a *physical-harm* task (industrial, medical,
   safety-of-life)?
   → MEASURE 2.6

4. Does the test exercise *PII* / human-identity privacy (not API keys or system
   prompts — actual personal data)?
   → MEASURE 2.10

5. Does the test exercise model explainability or output interpretation?
   → MEASURE 2.9

6. Does the test exercise organizational policy, third-party governance,
   or operational risk treatment?
   → It's probably not a Hermia test. Reconsider scope.
```

**Single subcategory per test** — same discipline as the MAESTRO mapping. Multi-axis richness comes from the other frameworks (OWASP, ATLAS, MAESTRO); NIST contributes the trustworthiness-characteristic lens.

---

## Common mapping errors (caught in 2026-06 audit)

- **`multiturn-context-carry` → GOVERN 1.1.** GOVERN 1.1 is *"Legal and regulatory requirements involving AI are understood, managed, and documented."* A memory test does not exercise legal-regulatory awareness. Correct mapping: **MEASURE 2.5**.
- **`scope-escalation-resistance` → MANAGE 2.2.** MANAGE 2.2 is *"Mechanisms are in place and applied to sustain the value of deployed AI systems"* — operational drift monitoring. A read/write boundary test is not drift monitoring. Correct mapping: **MEASURE 2.7**.
- **"Map harmful-task refusal to MEASURE 2.6 (Safe)."** Safe is *physical/environmental*. Cyber-security refusal is **MEASURE 2.7**.
- **"Map credential-leak to MEASURE 2.10 (Privacy)."** NIST Privacy is human-identity/dignity. Synthetic API keys are security artifacts. Use **MEASURE 2.7**.
- **"GOVERN/MAP/MANAGE are valid Hermia mappings."** Almost never. Those functions are organizational/contextual/operational. Hermia is a measurement instrument; its tests live in MEASURE.

---

## Citation

National Institute of Standards and Technology. (2023, January). *Artificial Intelligence Risk Management Framework (AI RMF 1.0)* (NIST AI 100-1). U.S. Department of Commerce. <https://doi.org/10.6028/NIST.AI.100-1>

National Institute of Standards and Technology. *NIST AI RMF Playbook* (living document). NIST Trustworthy and Responsible AI Resource Center. <https://www.nist.gov/itl/ai-risk-management-framework>
