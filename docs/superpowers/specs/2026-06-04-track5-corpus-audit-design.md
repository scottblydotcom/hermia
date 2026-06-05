# Track 5 — Corpus Audit Methodology

**Date:** 2026-06-04
**Status:** Design approved (brainstorm). Ready for implementation planning.
**Owner:** @scottblydotcom
**Gates:** Track 1 (v0.2 release) — `hermia_version`/corpus-hash stamping must not certify
data produced by un-audited graders. See `2026-06-04-hermia-v0.2-five-track-roadmap.md`.

---

## Problem

The eval corpus is **30 tests** (not the "28" still cited in `test_schema_contract.py` and the
roadmap — the two `multiturn-*` cases were added in Workstream E / PR #96 on 2026-06-03). Each
test pairs a prompt with a **grader** — a function `f(response) → pass/fail` in
`src/hermia/schemas.py`. The corpus was built fast ("go, and Claude built"), and there is direct
evidence the graders are not uniformly correct:

- **Binary-grader refusal-as-failure** — confirmed live on stage; conflates a refusal (a security
  *success*) with a jailbreak (a failure).
- **Routing-test bug** — needed a v0.1.2 fix (PR #71).
- **`instruction-override-resistance` penalizes refusals** — a model that refuses ("I won't, this
  contains an injection") fails schema and is scored a *failure*, though refusal is the secure
  outcome.
- **`indirect-injection-tool-output` semantic gap** — documented in a code comment at
  `schemas.py:307`: a model that reflects the injected instruction in its summary still passes,
  because only structure is checked, not meaning.

A wrong grader poisons the dataset and the HARD RULES against overclaiming built on it
(see `project_hermia_data_accounting`). This audit verifies or fixes every grader, maps every
test to a defensible framework control, and produces a CI-locked regression suite plus a
public-ready methodology catalog.

## Two facts that shape the method

1. **8,757 real stored responses.** Across `results/*.jsonl`, 8,757 rows carry non-empty
   `raw_response` — the actual JSON models emitted. Re-running the *current* grader against them is
   free, so grader auditing is grounded in real data with real prevalence, not only synthetic
   probes.
2. **A fixture seed already exists.** `tests/unit/test_schema_contract.py` holds a 1-pass/1-fail
   table per checker. The audit grows this into a full golden suite; the scaffolding is half-built.

---

## Core principle

Auditing a grader is building a **confusion matrix against independent ground truth**: feed it a
labeled response set, find where its verdict disagrees with what the response *should* score. The
ground truth must be established **independently of the grader code** — otherwise the audit merely
re-confirms the author's original assumptions (the `feedback_subagent_bug_confirmation` trap: a
model reading the grader will "CONFIRM" the grader).

### The three bug classes (the central distinction)

Every divergence is adjudicated into exactly one:

- **Policy bug** — the code is "correct" but the *contract* is wrong.
  *Example:* `instruction-override-resistance` scoring a justified refusal as failure.
- **Implementation bug** — the policy is right, the code misses it.
  *Example:* a check that fails to catch a base64-encoded secret leak.
- **Semantic gap** — the grader checks structure but not meaning.
  *Example:* `indirect-injection-tool-output` passing a summary that echoes the injection.

Policy bugs are fixed by changing the contract (and often the prompt/system message); implementation
bugs by changing the checker; semantic gaps by either adding content validation or **explicitly
documenting the gap** in the catalog as a known limitation (never silently).

---

## Per-test pipeline

For each of the 30 tests:

1. **Policy first, blind to code.** State the pass/fail contract and its rationale — what *should*
   pass, what *should* fail, and why — written without reference to the current implementation.
2. **Assemble a labeled response set** from two streams:
   - **Stream A — mined real responses.** Cluster the 8,757 rows into *distinct response shapes*
     (models emit near-identical JSON; this collapses to a few hundred or fewer per test). Re-grading
     is free; labeling operates on distinct shapes only.
   - **Stream B — synthetic adversarial variants.** Generated to cover the response space
     systematically, including rare-but-important cases the 34 models never happened to emit.
3. **Blind label** every distinct shape and every synthetic variant against the *policy* — by an
   agent that **never sees the grader code**. Each real-shape label **propagates** to all rows
   sharing that shape, yielding real false-positive / false-negative *prevalence* for free.
4. **Run the current grader** against the labeled set → confusion matrix.
5. **Adjudicate every divergence** into policy / implementation / semantic-gap.
6. **Fix** and re-run to convergence (grader matches ground truth on the full set).
7. **Freeze** the labeled set as golden fixtures.
8. **Gemini gate** — outside adversarial review of the frozen entry (below).
9. **Write the catalog entry** from the corrected grader + policy + framework mapping + generated
   failure-modes.

### Sampling discipline (Stream A)

No fixed N. The hand-label budget is data-driven:

- **Every grader-vs-label disagreement** is examined — these are the candidate bugs.
- **Plus a stratified sample of agreements** — to catch *shared* blind spots, where both the grader
  and a naive label are wrong the same way (the dangerous case).
- Security tests are weighted heavier than capability tests.

---

## Cross-vendor adversarial roles

The separation is not only for speed — it is what makes the ground truth *independent*. The pipeline
deliberately spans three model families so no single vendor's blind spot dominates a document whose
value *is* its rigor:

| Role | Who | Job |
|---|---|---|
| **Bulk generation** | qwen on the 5090 (strongest available local) | Cluster real responses into distinct shapes; generate synthetic variants; draft catalog prose and draft policy statements |
| **Blind labeler** | Sonnet subagent(s) | Label distinct shapes + synthetic variants against the policy, **without ever seeing the grader code** — isolates policy bugs from implementation bugs |
| **Red-team adversary** | Sonnet subagent(s) | Construct a response that breaks each "clean" grader; challenge whether the variant set is complete |
| **Adjudicator + policy authority** | Opus, in-window | Resolve labeler-vs-grader disagreements; classify each bug; make final policy calls; commit |
| **Outside gate** | Gemini 2.5 Pro (copy/paste, free) | Attack each *frozen* entry from a non-Claude perspective |
| **Security sign-off** | Scott | Final authority on all 12 security-test policies — the tests he defends publicly |

**Resource weighting:** the subtle security bypasses (zero-width unicode in an unchecked field,
base64-encoded leak) are exactly where a 32B local model is weakest and Sonnet/Opus/Gemini are
strongest. The **12 security tests** get heavy adversarial attention; the **~14 capability tests**
lean on the fleet with lighter review. Opus cycles are not spent attacking `numeric-reasoning`.

### Gemini gate — scope and cost

Gemini reviews only the **30 frozen catalog entries**, never individual responses — this structurally
bounds cost (a per-response loop is what would create a surprise; Gemini never goes in one). Its brief
per entry:

1. **Challenge the policy** — is the success criterion what a security auditor would accept?
2. **Challenge the framework mapping** — does the cited control genuinely apply, or is it a stretch?
   *(Highest value — framework defensibility is a public claim and wants an outside eye.)*
3. **Red-team the fixtures** — find a response that defeats the corrected grader.
4. **Hunt overclaiming** in the prose — ties to the `project_hermia_data_accounting` HARD RULES.

**Mechanism:** copy/paste into Gemini 2.5 Pro — $0, zero cost-surprise risk, 30 cycles. Wiring Gemini
into CI as a recurring gate is a *separate* decision driven by the consumer sunset (2026-07-17), not
by this audit.

---

## Framework mapping work

23 of 30 tests carry at least one framework mapping today; 7 carry none. All 7 are baseline
capability tests, not threat controls:

- **MAESTRO L4 (Application/Agentic logic)** for the four agentic ones — `tool-calling-basic`,
  `tool-selection`, `compound-sequencing`, `context-retention`. A single level per test with a
  one-sentence rationale (pick L4 vs L5 for `compound-sequencing` during cataloging).
- **NIST AI RMF MEASURE 2.5** ("regular testing of AI system behavior") for the remaining three —
  `multi-step-reasoning`, `structured-data-extraction`, `numeric-reasoning`. Consistent with the
  two reasoning tests that already cite MEASURE 2.5.

Standards alignment becomes a **visible matrix** in the catalog (test → control-ID → rationale), not
buried `framework_*` columns.

---

## Outputs (durable artifacts)

1. **Golden fixture data** — one file per test (e.g. `response-fixtures/<test_id>.json`) holding
   `{response, expected_verdict, label_rationale, source: real|synthetic}` entries. **Single source
   of truth.**
2. **`test_grader_<id>` suites** — read the fixtures; CI-lock every grader's verdict so no future edit
   silently regresses it. Replaces the thin 1-pass/1-fail seed in `test_schema_contract.py`.
3. **`docs/corpus-catalog.md`** — one entry per test: purpose, exact prompt(s), grading logic,
   framework control-IDs with rationale, and known failure modes **generated** from the fixture file
   (the should-pass-but-fails and should-fail-but-passes cases). Written in Scott-as-public-face tone;
   a public methodology cut is produced later when appropriate.

The fixture file feeds both the tests and the catalog's failure-modes section — the audit is
**reproducible code, not prose**.

---

## Known starting issues (audit confirms these and finds more)

| Issue | Class | Action |
|---|---|---|
| `instruction-override-resistance` penalizes refusals | Policy | Allow justified refusal as pass |
| `indirect-injection-tool-output` summary unchecked | Semantic gap | Add content validation or document |
| Binary-grader refusal-as-failure | Policy | Three-way outcome (refused / complied-with-attack / malformed) |
| "28 tests" stale counts (`test_schema_contract.py` docstring, roadmap) | Doc | Correct to 30 |
| 7 unmapped tests | Mapping | 4 → MAESTRO L4, 3 → NIST MEASURE 2.5 |
| `192.168.43.12:4000` real LAN address in `credential-leak-resistance` | Hygiene | Replace in current file now; strip from history in the existing history-scrub session (`next_session_hermia_history_scrub`), not mid-audit |

---

## Sequencing

```
For each test (security tests first, weighted):
  policy → label set (real-deduped + synthetic) → blind-label → confusion matrix
    → adjudicate → fix → freeze fixtures → Gemini gate → catalog entry
Then:
  framework matrix · stale-count fixes · credential-address scrub (current file)
  → corpus-hash → unblocks Track 1 stamping
```

The audit completes **before** `hermia_version`/corpus-hash stamping, so v0.2 launch data is
certified against graders known-correct.
