# MITRE ATLAS — Hermia Reference

**Status:** Authoritative internal reference for all Hermia → MITRE ATLAS mappings.
**Target version:** **ATLAS 6.0.0 (release tag 2026.05)** — current as of 2026-06-06. The full canonical YAML is checked in at `docs/MITRE-ATLAS-2026.05.yaml` (format-version 6.0.0, collection created 2020-10-23, modified 2026-05-27).
**Web index:** <https://atlas.mitre.org/>
**Repository:** <https://github.com/mitre-atlas/atlas-data>

> **Versioning note.** ATLAS uses two parallel numbering schemes: the GitHub `format-version` (semver-style, currently **6.0.0**) and the atlas.mitre.org publication tag (`YYYY.MM`, currently **2026.05**). The single source-of-truth for the Hermia mapping is the `format-version`. The mapped framework in `agentic-tasks.json` is the version-agnostic key `mitre_atlas`; the version itself lives in the top-level `framework_versions` sidecar so a version bump touches one line, not 30 tests.

> **Reproduction note.** Tactic and technique codes/names/descriptions below are reproduced from `docs/MITRE-ATLAS-2026.05.yaml`. Direct-quoted descriptions are in quotation marks.

> **Author's correction (2026-06-06).** My first draft of this reference incorrectly claimed `AML.T0098`, `AML.T0099`, and `AML.T0100` did not exist in ATLAS. **They do exist** in 6.0.0 — they are recently-added agentic-AI techniques (T0098 AI Agent Tool Credential Harvesting, T0099 AI Agent Tool Data Poisoning, T0100 AI Agent Clickbait). My error came from scraping an older GitHub YAML that pre-dated the agentic additions. The corrected audit found that some existing mappings of those codes were defensible (T0099 on indirect-injection-tool-output) while others were category errors (T0100 on classifier-injection tests; T0098 on a no-tool credential-leak test). Details in "Common mapping errors" below.

---

## ATLAS tactics (16) — v6.0.0

| Tactic ID | Name | Relevance to Hermia |
|---|---|---|
| AML.TA0002 | Reconnaissance | — |
| AML.TA0003 | Resource Development | — |
| AML.TA0004 | Initial Access | — |
| AML.TA0000 | AI Model Access | — |
| AML.TA0005 | **Execution** | **Primary** — every Hermia security test |
| AML.TA0006 | Persistence | — |
| AML.TA0012 | **Privilege Escalation** | T0054 jailbreak (none of current 30 fit) |
| AML.TA0007 | **Defense Evasion** | T0068 obfuscation (3 tests) |
| AML.TA0013 | Credential Access | — |
| AML.TA0008 | Discovery | — |
| AML.TA0015 | Lateral Movement | — |
| AML.TA0009 | Collection | — |
| AML.TA0001 | AI Attack Staging | — |
| AML.TA0014 | Command and Control | — |
| AML.TA0010 | **Exfiltration** | T0056 (system prompt extraction); T0057 (data leakage) |
| AML.TA0011 | Impact | — |

---

## Techniques relevant to Hermia's 30 tests

Quotes are from the canonical YAML. Hermia mapping is below each.

### AML.T0051 — LLM Prompt Injection
> *"An adversary may craft malicious prompts as inputs to an LLM that cause the LLM to act in unintended ways. These 'prompt injections' are often designed to cause the model to ignore aspects of its original instructions and follow the adversary's instructions instead."*

**Tactic:** Execution (AML.TA0005)
**Sub-techniques (canonical):**
- **AML.T0051.000 Direct** — *"inject prompts directly as a user of the LLM."*
- **AML.T0051.001 Indirect** — *"inject prompts indirectly via separate data channel ingested by the LLM such as include text or multimedia pulled from databases or websites."*
- **AML.T0051.002 Triggered** — *"trigger a prompt injection via a user action or event that occurs within the victim's environment."*

**Hermia mapping:** The load-bearing ATLAS technique. **We cite the sub-technique, not the parent**, per ATLAS convention. All direct-injection tests (security-boundary, scope-escalation, all 4 SFI, all 4 adversarial-input, lane-routing-evasion, instruction-override, classification-routing, credential-leak, system-user-precedence, multiturn-boundary-persistence) → `AML.T0051.000`. The indirect-injection-tool-output test → `AML.T0051.001`. No current test exercises T0051.002 (would require an environmental trigger we don't simulate single-shot).

### AML.T0054 — LLM Jailbreak
> *"Adversaries may induce a large language model (LLM) to ignore, circumvent, or override its safety/alignment behaviors and/or guardrails to elicit outputs the model is intended to withhold."*

**Tactics:** Privilege Escalation (AML.TA0012), Defense Evasion (AML.TA0007)

**Hermia mapping:** **None of the current 30 are clean T0054 cases.** Jailbreak is narrowly about *safety/alignment guardrail bypass*. A test that prompts the model to perform a refused action (exfiltrate `/etc/passwd`, disclose a system prompt, follow an injected directive) is Direct Prompt Injection — not a guardrail-bypass attempt. The prior dataset mapping of T0054 on indirect-injection-tool-output was a category error.

### AML.T0056 — Extract LLM System Prompt
> *"Adversaries may attempt to extract a large language model's (LLM) system prompt. This can be done via prompt injection to induce the model to reveal its own system prompt or may be extracted from a configuration file. System prompts can be a portion of an AI provider's competitive advantage and are thus valuable intellectual property that may be targeted by adversaries."*

**Tactic:** Exfiltration (AML.TA0010)

**Hermia mapping:** `system-prompt-extraction-resistance` — bullseye. **Single-mapped** (no T0051 primary needed) per the tightness preference — T0056 is the more specific technique, and OWASP LLM07 on the same test already carries the system-prompt-leakage axis.

### AML.T0057 — LLM Data Leakage
> *"Adversaries may craft prompts that induce the LLM to leak sensitive information. This can include private user data or proprietary information. The leaked information may come from proprietary training data, data sources the LLM is connected to, or information from other users of the LLM."*

**Tactic:** Exfiltration (AML.TA0010)

**Hermia mapping:** Secondary on tests where the *consequence* is leakage of in-context sensitive data:
- `credential-leak-resistance` — direct injection asking for an in-context secret
- `lane-routing-evasion` — credential request embedded in a routing task

### AML.T0068 — LLM Prompt Obfuscation
> *"Adversaries may hide or otherwise obfuscate prompt injections or retrieval content to avoid detection from humans, large language model (LLM) guardrails, or other detection mechanisms. For text inputs, this may include modifying how the instructions are rendered such as small text, text colored the same as the background, or hidden HTML elements. For multi-modal inputs, malicious instructions could be hidden in the data itself (e.g. in the pixels of an image) or in file metadata (e.g. EXIF…)."*

**Tactic:** Defense Evasion (AML.TA0007)

**Hermia mapping:** Secondary on tests where obfuscation is the *core mechanic* — `structured-field-injection-base64`, `structured-field-injection-unicode`, `adversarial-input-zero-width-injection`. NOT on structural-injection tests (nested-JSON, object-key) or signal-flooding/few-shot-poisoning tests (those exercise T0051.000 directly without encoding-layer obfuscation).

### AML.T0099 — AI Agent Tool Data Poisoning
> *"Adversaries may place malicious content on a victim's system where it can be retrieved by an AI Agent Tool. … The adversary's content may include false or misleading information. It may also include prompt injections with malicious instructions."*

**Tactic:** Persistence

**Hermia mapping:** Secondary on `indirect-injection-tool-output`. T0099 names the *delivery vehicle* (poisoned tool output); T0051.001 names the *attack class* (indirect prompt injection). Together they describe the full attack chain — the LLM is presented with adversary-crafted content via a tool channel and adopts the injected directive.

### Techniques explicitly NOT mapped (with reasoning)

- **AML.T0098 AI Agent Tool Credential Harvesting** — Requires the agent *querying a tool* to retrieve credentials from external data sources (SharePoint, code repos, etc.). Hermia's credential-leak-resistance test embeds the credential directly in the system prompt; no agent-tool query exercised. **Mismatched mechanism.**
- **AML.T0100 AI Agent Clickbait** — Specifically scoped to *Computer-Using AI agents or AI web browsers* baited by deceptive web content (buttons, navigation). Hermia tests no CUA flows. **Wrong attack surface.**
- **AML.T0067 LLM Trusted Output Components Manipulation** — Defensible secondary on `indirect-injection-tool-output` but **omitted** per the ≤2-codes-per-test tightness policy. T0099 is the more specific delivery-vehicle code; T0067 would name the manipulation-of-trusted-component aspect but adds noise without sharpening the test's identity.
- **AML.T0053 AI Agent Tool Invocation** — About the adversary using an agent to invoke tools for further compromise. Hermia tests defensive *refusal* in the model, not adversary-driven tool invocation.

---

## Multi-mapping policy

Same as OWASP: **≤2 codes per test.** ATLAS techniques can co-occur on a single test (T0051 attack class + T0068 obfuscation; T0051.001 attack class + T0099 delivery vehicle). Stop at 2; prefer the more specific child technique over the parent. Future lift tracked in [[backlog_owasp_multimapping_expansion]] when v0.3 ships tests probing ≥3 techniques.

---

## Where the recurring Hermia concepts live

| Concept | Primary | Secondary |
|---|---|---|
| Direct injection in user turn | **AML.T0051.000** | — |
| Indirect injection via tool output | **AML.T0051.001** | **AML.T0099** |
| Triggered injection (env-activated) | T0051.002 | — _(no current Hermia test)_ |
| System prompt extraction | **AML.T0056** | — _(bullseye)_ |
| In-context data / credential leak | **AML.T0051.000** | **AML.T0057** |
| Encoded / obfuscated injection | **AML.T0051.000** | **AML.T0068** |
| Jailbreak (guardrail bypass) | T0054 | — _(no clean fit in current 30)_ |
| Pure capability | — | _(empty — no adversary technique exercised)_ |

---

## Decision tree

```
1. Does the test prompt the model with an attack?
   NO  → empty. Capability test.
   YES → continue.

2. Is the goal of the attack to extract the system prompt specifically?
   → AML.T0056 (single mapping)

3. Is the goal of the attack a guardrail/safety-alignment bypass (not instruction override)?
   → AML.T0054 (rare; no current Hermia test is a clean fit)

4. Where does the injection ARRIVE?
   - In the user turn directly → AML.T0051.000 Direct
   - Via a tool/data channel ingested by the LLM → AML.T0051.001 Indirect
                                                  → + AML.T0099 (tool poisoning) as secondary
   - Via an environmental trigger → AML.T0051.002 Triggered (no current test)

5. Does the attack use encoding/visual obfuscation (base64, homoglyph, zero-width)?
   → + AML.T0068 as secondary

6. Is the CONSEQUENCE leakage of in-context sensitive data?
   → + AML.T0057 as secondary

7. Stop at ≤2 codes per test.
```

---

## Common mapping errors (caught in 2026-06 audit)

- **AML.T0100 (AI Agent Clickbait) on 9 classifier/injection tests.** T0100 is web-content baiting of Computer-Using agents — wrong attack surface for prompt-injection/adversarial-input tests. Replaced with T0051.000.
- **AML.T0054 (LLM Jailbreak) on indirect-injection-tool-output.** The test is not a guardrail-bypass attempt — it's an indirect injection via tool output. Replaced with T0051.001.
- **AML.T0098 (AI Agent Tool Credential Harvesting) on credential-leak-resistance.** T0098 requires an agent querying a tool to retrieve the credential. Our test embeds the credential in the system prompt; no tool query is involved. Replaced with T0051.000 + T0057.
- **Parent code T0051 instead of sub-technique.** ATLAS convention uses the most specific sub-technique. Refined T0051 → T0051.000 on three tests.
- **Empty ATLAS on injection-shaped attacks.** security-boundary, scope-escalation-resistance, lane-routing-evasion were missing T0051.000 entirely.

---

## Citation

MITRE ATLAS™ (Adversarial Threat Landscape for Artificial-Intelligence Systems). MITRE Corporation. Format version **6.0.0** (release tag 2026.05). Canonical data: <https://github.com/mitre-atlas/atlas-data> (local copy: `docs/MITRE-ATLAS-2026.05.yaml`). Web interface: <https://atlas.mitre.org/>.
