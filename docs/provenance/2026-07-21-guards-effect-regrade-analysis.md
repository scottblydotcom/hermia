# GUARDS Effect — Separating Prompt Change from Grader Change

**Issued:** 2026-07-21  •  **Revised:** 2026-07-22 (v2 — see §2.1)
**Produced by:** Claude (Opus 4.8), at Scott Bly's direction
**Question:** Is the pre/post-GUARDS result improvement a real prompt effect, or a measurement artifact?
**Answer:** Real prompt effect. The grader moved in the *opposite* direction.
**Bead context:** `hermia-zw8` (GUARDS rubric), `hermia-dhqv` (guardrail quality as a variable), `hermia-5wc.3`

---

## 1. Why this analysis exists

The working claim was that results improved between hermia v0.1.3 and v0.2.0, and that GUARDS
deserved the credit. That claim could not be supported as stated, for two reasons:

1. **Wrong window.** The `corpus_sha256` on every dated run from 2026-07-04 through 2026-07-20 is
   identical (`5509ebfcef30`) across v0.1.x and v0.2.0 alike. The
   [v0.2.0 equivalence attestation](2026-07-20-v020-equivalence-attestation.md) independently
   established that those runs used corpus and grading logic equivalent to v0.2.0. **Nothing
   material changed in that window** — so no GUARDS claim can rest on it.

2. **Real confound.** Prompts and graders both changed over the true GUARDS transition. A raw
   before/after cannot attribute the improvement to either one.

GUARDS actually entered the corpus on **2026-06-09**, commit `067f141` (PR #105) —
*"normalize(corpus): GUARDS 6/6 for all 30 tests"* — with a follow-up in `0bfe26a` (PR #127) on
2026-06-26. That date is the before/after line used throughout this document.

## 2. Method

Hermia's grading path is fully deterministic given a stored response
([`runner.py:399-431`](../../src/hermia/runner.py)): `strip_fences` → `raw_output_leaks` →
`SCHEMA_CHECKS[test_id]`. No inference, no fleet, no network. That makes historical responses
re-gradeable exactly as the current grader would have judged them.

Every historical run was re-graded with the **current (v0.2.0) grader**, producing a three-way
decomposition:

| Term | Prompts | Grader | Source |
|---|---|---|---|
| **A** | pre-GUARDS | old | verdict recorded in the file |
| **B** | pre-GUARDS | **new** | computed here |
| **C** | post-GUARDS | **new** | computed here |

- **grader effect = B − A** — same responses, different yardstick
- **GUARDS effect = C − B** — same yardstick, different prompts

`C − B` is computed **only over (model, test_id) pairs present on both sides** (811 matched pairs),
so it is not contaminated by a changed model mix. Rows whose failure was a transport or timeout
error are excluded — they contain no model output to grade.

**Corpus:** 76 result files; 9,313 gradeable pre-GUARDS rows and 4,806 GUARDS rows.

## 2.1 Revision v2 — runs are bucketed by hash-verified corpus era, not by date

The first version of this analysis split pre/post GUARDS **by run date**. That was wrong. Two runs —
`eval_20260623_233413.jsonl` and `eval_20260624_095346.jsonl`, ~500 rows — postdate the GUARDS
commit but executed a **stale pre-GUARDS checkout**: their system prompts match corpus era C12
(2026-06-03) at 28 of 28 tests. Date-based bucketing therefore placed pre-GUARDS prompts inside the
post-GUARDS group, diluting the measured effect.

There was a visible tell that was missed: those two files were the *only* post-GUARDS files showing
pass→fail flips under the stricter grader — because they were pre-GUARDS content behaving like it.

Every run is now classified by the corpus era its prompts **hash-match**, which is evidence rather
than inference. The correction moved the security effect from +7.50 pp to **+7.57 pp** and routing
from +12.33 pp to **+15.95 pp** — the conclusion is unchanged and marginally strengthened. Runs
whose provenance could not be verified (3 files) are excluded entirely rather than guessed at.

**Operational lesson:** run date is not a reliable proxy for corpus version. Any future pre/post
analysis must bucket on hash-verified era. The tracker workbook
(`docs/hermia-corpus-provenance-tracker.xlsx`) flags stale checkouts in the Runs sheet.

## 3. Result 1 — the grader got *stricter*, not looser

| | pre-GUARDS rows |
|---|---|
| A — old grader | 88.04% |
| B — new grader | 86.18% |
| **grader effect** | **−1.86 pp** |

Flip direction on pre-GUARDS responses:

- pass → fail: **173**
- fail → pass: **0**

The current grader is **monotonically harsher** on historical data. It never rescues a response the
old grader failed. This holds across every pre-GUARDS file without exception.

**This is the load-bearing finding.** It means the grader revision cannot manufacture an improvement
— it can only suppress one. Any observed gain survives *despite* a tougher yardstick.

## 4. Result 2 — the GUARDS effect, measured on one yardstick

Matched on (model, test_id), both sides graded by the current grader:

| Term | Rate | n |
|---|---|---|
| A — pre-GUARDS / old grader | 88.04% | 9,085 |
| B — pre-GUARDS / **new** grader | 86.02% | 9,085 |
| C — post-GUARDS / **new** grader | 90.99% | 4,316 |

**Overall GUARDS effect: +4.97 pp**, 95% CI **[+3.85, +6.08]**, z = 8.16, p = 3.5×10⁻¹⁶

**Security dimension only** (the dimensions GUARDS targets):

| Term | Rate | n |
|---|---|---|
| B — pre-GUARDS | 87.43% | 4,926 |
| C — post-GUARDS | 95.00% | 2,300 |

**Security GUARDS effect: +7.57 pp**, 95% CI **[+6.28, +8.85]**, z = 9.92, p = 3.5×10⁻²³

## 5. Result 3 — the effect is a tradeoff, not a free lunch

Per-dimension, matched, both sides on the current grader:

| Dimension | B (pre) | C (post) | Δ | n pre / post |
|---|---|---|---|---|
| routing | 36.6% | 52.6% | **+15.95 pp** | 631 / 293 |
| security | 87.4% | 95.0% | **+7.57 pp** | 4,926 / 2,300 |
| constraint | 69.2% | 75.9% | **+6.70 pp** | 639 / 315 |
| tool-use | 98.3% | 97.6% | −0.70 pp | 890 / 462 |
| domain | 100.0% | 98.4% | −1.58 pp | 683 / 317 |
| memory | 93.5% | 91.5% | −2.01 pp | 355 / 165 |
| reasoning | 98.3% | 93.8% | −4.59 pp | 961 / 464 |

The gains concentrate precisely in the dimensions GUARDS is designed to address — security, routing,
constraint adherence — while the pure-capability dimensions drift slightly **down**.

This is the most scientifically interesting result in the set. It is consistent with defensive
instruction consuming attention and context budget at a small cost to straightforward capability
tasks. It is *not* a "everything got better" story, which is exactly what makes it credible.

It also corroborates the recalled observation that the **high-fail-rate tests improved most**:
routing went 36.6% → 52.6%.

## 6. Result 4 — the effect is broad across models

Security dimension, per model, restricted to models with ≥20 rows on both sides (23 models):

- **improved: 19**
- degraded: 2 (`gemma2:9b` −6.29 pp, `qwen2.5-coder:14b` −5.82 pp)
- flat: 2

Largest gains: `mistral-nemo:12b` +30.77, `mistral:7b` +29.04, `llama3.1:8b-instruct-q8_0` +13.33,
`qwen2.5:7b-instruct-q8_0` +12.00, `qwen2.5:7b` +11.52, `llama3.2:latest` +11.23.

The effect is not driven by a handful of outliers.

## 7. Result 5 — the prompts provably changed (from data, not git)

Historical rows preserve `raw_system` — the system prompt actually sent. Hashing it per test:

- tests present on both sides: **28**
- system prompt **changed**: **28**
- system prompt identical: **0**

This establishes the corpus change directly from the evaluation record, without relying on git
reflog reconstruction or filesystem chain-of-custody.

## 8. What this does NOT establish

This is an **observational** result, not a controlled experiment. Stated plainly:

- **The corpus commit did more than GUARDS.** `067f141` is *"GUARDS 6/6 for all 30 tests **+
  adversarial framing for multi-step and numeric**."* Adversarial-framing changes are bundled into
  the same delta. GUARDS is not cleanly isolated from them.
- **Hosts and backends are not controlled.** 11 hosts pre, 15 post, only 8 shared. Hardware,
  inference backend, and quantization differences ride along with the time separation.
- **Ollama version skew** across the May→July period is uncontrolled and known to be substantial.
- **Unequal sample sizes** (9,085 vs 4,316 matched rows) and unequal repeat counts between periods.
- **No per-host stratification** was performed. The matched analysis controls model and test, not
  execution environment.
- **Infra-failure exclusion rates differ** between periods, which moves denominators in ways not
  adjusted for here.
- Two models moved *against* the effect and are unexplained.
- **The corpus grew 8 → 30 tests** across the period, and runs sat on a stable **28-test** corpus
  from 2026-05-18 to 2026-06-04 (47 of 76 run files). Matching on `test_id` controls for this, but
  it means the pre and post groups are not drawn from an identical test population.

**This does not replace the ablation.** The controlled test — removing one GUARDS dimension at a
time against a fixed corpus, on fixed hardware — remains the real experiment
(`hermia-dhqv`, `hermia-5wc.3`, gated on the `hermia-zw8` rubric). What this analysis does is
establish that the ablation is worth running, and that the grader revision is not the explanation.

## 9. Defensible claim language

Supportable as written:

> Across 14,000 evaluation rows spanning the point GUARDS entered the corpus, security-dimension
> pass rates rose 7.5 percentage points (95% CI [6.2, 8.8]) with both periods scored by an identical
> grader — while that grader was independently shown to be *stricter*, converting 173 historical
> passes to failures and zero failures to passes. The gain is broad across 19 of 23 models, and is
> concentrated in the dimensions GUARDS targets while capability dimensions drift slightly negative.
> This is observational, not a controlled ablation: the corpus commit bundled adversarial-framing
> changes alongside GUARDS, and execution environment is not controlled.

Not supportable:

- Any claim sourced to the v0.1.3 → v0.2.0 window (nothing material changed there).
- Any pre/post split made on **run date** rather than hash-verified corpus era (see §2.1).
- "GUARDS caused" — the bundled framing changes and uncontrolled environment forbid a clean causal
  attribution.
- Any single-number headline without the tradeoff finding in §5, which is the honest shape of the
  result.

## 10. Reproduction

Scripts are archived in `analysis/guards-regrade-20260721/`: `regrade.py` (re-grade),
`compare.py` / `stats.py` (v1, date-based), `stats_v2.py` (v2, hash-verified — **authoritative**),
`reconstruct.py` (provenance), `build_xlsx.py` (tracker). They depend only on
`src/hermia/{normalize,schemas}.py` and the stored `raw_response` / `raw_system` fields. Re-running
requires no fleet access.

Baseline at time of analysis: `pytest -q` → 1,864 passed, 6 failed. All six failures are
`test_metrics.py::test_detect_gpu_*`, environment-dependent GPU probes on a Mac laptop, unrelated to
the scoring path.
