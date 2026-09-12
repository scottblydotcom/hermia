# v0.2.x roadmap spec — graders, Windows, Mac GPU, and the standing rule

**For:** Scott Bly · **Date:** 2026-09-11 · **Status:** DRAFT for approval, no code written
**Governed by:** `session-notes/STATE.md` (Scott's 2026-09-11 decisions, the new roadmap, the standing rule, the fixed engineering order) and `docs/superpowers/specs/2026-09-08-grader-redesign-decision-v2.md` (the decision record).
**Baseline:** branch `feature/hermia-omz5-grader-error-verdict`, HEAD `f847a93`, darwin-arm64.

> **Claim grading.** *verified* = I ran or read it in this session, on this tree, and the command output is in §7 or quoted inline. *inferred* = my engineering judgment. Nothing here is graded verified on another agent's say-so — every number below was re-derived by me, and where a prior draft's number and mine differ, both are given.
>
> **Four adversarial reviews attacked the draft of this spec.** They returned ~60 findings. Every one is adjudicated in §7 — applied or rejected, with the reason and the check I ran. **Seven of them changed the engineering, not just the wording**, and one of those (F02) would have shipped a change that moves 988 verdicts inside a PR whose declared expectation was "moves nothing."

---

## 1. Scope and non-goals

### 1.1 The new roadmap (Scott, 2026-09-11) — replaces the previous v0.2.x plan

| Release | Contents |
|---|---|
| **v0.2.x** | Fix the graders (the §4 core) · **Windows users run Hermia directly** · **fix the missing-GPU problem on Mac** |
| **v0.3** | **Fix the tests we discovered** (`hermia-n2h8` — *the four adversarial-input tests contradict themselves*) · expand hardware compatibility (moved here from v0.2.x) · LLM judge, if it still makes sense then |

**Scott's driver: get to v0.3 faster, because the tests need fixing.** Everything below is scoped against that sentence. Where a piece of work is defensible but not on the path to v0.3, it is named in §5 as deferred rather than smuggled in.

### 1.2 What v0.2.x actually contains — five workstreams, not three

The draft of this spec covered one of the six steps in Scott's fixed engineering order (`STATE.md:58-66`) and treated the other four as "dependencies." *verified* — steps 1, 2, 3 and 4 have no section, no PR and no owner anywhere in that draft, and step 4 is not mentioned once. Every one of them is a hard merge blocker for the grader core. They are **Workstream 0** here.

| # | Workstream | Why it is in v0.2.x |
|---|---|---|
| **0** | **Pre-core** — steps 1–4 of the fixed order | The core cannot start until these land. Four PRs. |
| **1** | **The grader core** (typed scorecard) — step 5 | Scott's "fix the graders." Seven PRs. |
| **2** | **The write path + standing rule** (`hermia-3x6t`, blocked on `hermia-ov2d`) | Scott's new standing rule, AND the only way the §4.2 gate's database half can ever run. **On the critical path, not parallel.** Seven PRs. |
| **3** | **Mac GPU** (`hermia-rk3k` / `hermia-2ess`) | Scott's roadmap line. Four PRs. |
| **4** | **Windows direct-run** (`hermia-8eh7`, `hermia-0sc`) | Scott's roadmap line. Five PRs. |
| **5** | **Ship it** — version bump, CHANGELOG, tag | *verified* — `pyproject.toml:7` is still `version = "0.2.0"`, `CHANGELOG.md`'s `[Unreleased]` is empty, and `publish.yml` fires only on a `v*.*.*` tag. Without this, 27 PRs land on `dev` and nothing reaches a user. One PR. |

**28 PRs, 4 spikes, 10 decisions that are Scott's.** The critical path is in §3.4.

### 1.3 Non-goals for v0.2.x

| Not doing | Why |
|---|---|
| **New detection of any kind** | Decision record §4.3 is binding: *"Zero new detection."* Nine of seventeen security detectors have never fired; that count does not improve in v0.2.x. Decision 9 forecloses it explicitly. |
| **Fixing the four self-contradictory tests** | Decision 1: caveat now, fix the text in v0.3. The caveat is Workstream 0. |
| **The LLM judge** | Decision 12: deferred. |
| **Native Windows/AMD/Intel GPU telemetry** | `STATE.md:40` moved hardware expansion to v0.3. |
| **Retiring `analyze.py`'s SQL copy of "what is a compromise"** | Blocked on spike S1 (the live Grafana panels are not in this repo and may hold a fourth copy). §5. |
| **Additional axes rendered in the TUI (Decision 8)** | Step 6 of the fixed order, which `STATE.md:65` places *after* the core and before v0.3. Named in §5 and put to Scott in §6 Q7. |

---

## 2. The four engineering workstreams

Every acceptance criterion below names the command that checks it. Criteria that **cannot** be checked in CI say so and name what closes them instead — because `results/` is gitignored and CI has no corpus (*verified*: `grep -n results .gitignore` → `14:results/`; `git ls-files results/ | wc -l` → `0`; `ls results/*.jsonl | wc -l` → `103`).

---

### 2.0 Workstream 0 — the pre-core steps

`STATE.md:58-62` fixes these. They are small, they each move a published number or a published claim, and the core is blocked on all four.

| # | Bead | What it is |
|---|---|---|
| **P1** | `hermia-lrzq` — *classification-routing: decided 2026-08-31 to join `SECURITY_TEST_IDS`, still not in code* | Adds one test id to the security set. *verified*: it carries 1,098 corpus rows (1,018 with a body), all filed under `dimension: routing`; `SECURITY_TEST_IDS` has 17 entries today and `classification-routing` is not among them. Moves the published security rate **−4.3 points, 89.5% → 85.2%**, which Scott already agreed. |
| **P2** | `hermia-ej4r` — *regression.py:103 reads the funnel by bare truthiness* | One line. **The shape it lands in is load-bearing** — see AC-P2. |
| **P3** | `hermia-x5p1` — *multiturn-boundary-persistence's semantic gate fires on structurally INVALID envelopes* | Decision 5. See §6 Q3 — this one needs Scott before it lands. |
| **P4** | `hermia-hl7c` — *Publish the known limitation: multi-turn PII test cannot observe its own declared property* + Decision 1's caveat | Both are edits to `catalog-meta/*.json`. *verified*: 31 such files exist and every draft section of this spec declared them deliberately unopened — reproducing the omission the decision record §8 names as the review's worst failure. |

#### Acceptance criteria — Workstream 0

| AC | Criterion | Mechanical check |
|---|---|---|
| **AC-P1** | `classification-routing` is in `SECURITY_TEST_IDS`, its fixture witness set exists, the WITNESS allowlist widening is its own commit, and the corpus catalog is regenerated. | `python3 -P scripts/witness_allowlist_ratchet.py --base origin/dev` exits 0 (*verified* it exits 0 today: `OK: both WITNESS registers shrank or held; guards alive; SECURITY_TEST_IDS did not shrink`), **and** `pytest tests/unit/corpus_audit/test_assembler.py::test_corpus_catalog_is_current` passes. That second test is a live tripwire nobody noticed: *verified*, it asserts `docs/corpus-catalog.md` is byte-equal to a fresh render from `catalog-meta/` + `response-fixtures/` + `schemas.TEST_IDS`, and it is green today, so P1 and P4 both turn it red until the catalog is regenerated. |
| **AC-P2** | The `regression.py:103` fix preserves **both** arms of the current read. | `pytest tests/unit/test_regression.py::test_resisted_is_none_when_a_detector_crashes` — a new test. *verified by execution*: today `regression._resisted` on `{"status":"cannot_disclose"}` returns `True` with clean detectors and `None` when `raw_output_leaks` is patched to raise (the funnel returns `GRADER_ERROR`). A fix written as `== ""` keeps both arms; a fix written as `in _COMPROMISE_REASONS` **re-opens the false clearance the five omz5 commits closed**, because `GRADER_ERROR` is truthy and currently suppresses `refused`. The PR must state which shape it used. |
| **AC-P3** | If Decision 5 lands as gating: the **verdict** count on `multiturn-boundary-persistence` is unchanged and the **detector firing** count goes to zero, both asserted by name. | `pytest tests/unit/test_schemas.py::test_multiturn_semantic_gate_requires_a_valid_envelope`. *verified by execution over all 697 multiturn rows with a body*: raw marker fires 8, semantic gate fires 8, **both on the same 8**, semantic gate firings on a structurally valid envelope = **0**. So compromised-today = compromised-after-gating = **8 → 8**, and `_sem_multiturn_boundary` goes **8 firings → 0**, i.e. never-fired moves 9 of 17 → 10 of 17. **Those are two different numbers and the draft conflated them.** See §6 Q3. |
| **AC-P4** | The limitation and the caveat exist in `catalog-meta/`, are cited by file, and the catalog is regenerated. | `pytest tests/unit/corpus_audit/test_assembler.py -q` passes after the edit, plus a test asserting the named `known_limitations` entry is present on the multi-turn test and on each of the four `adversarial-input-*` tests. **The whole test object plus its catalog-meta policy must be read and quoted before the limitation is written** — `hermia-hl7c` says so in its own body, and it is the project's standing lesson. |

---

### 2.1 Workstream 1 — the grader core (typed scorecard)

Implements decision record §4.1–§4.3. Step 5 of the fixed order.

#### Why it exists, in one paragraph

Six modules each carry their own answer to "was this row compromised," using three different matching rules, and a single real string — `SECURITY_FAIL: adopted payload` — gets five different answers out of them. *verified by reading each site*: `schemas.py:882` prefix-matches; `analyze.py:271` is an exact SQL `IN`; `regrade.py:183` is an exact tuple; `sink/anonymize.py:59-72` is an ordered prefix tuple; `tui/runner_backend.py:137` is bare truthiness. Decision record §2.2 traces four of last week's sixteen defects — including both CRITICALs — to one cause: a function returning `""` / a reason / `GRADER_ERROR` on the same string channel, read by truthiness. **Fixing that representation is the redesign.**

> ⚠️ **Honest scope, stated up front because the draft overstated it.** The decision record §4 promises *"six copies of 'what is a compromise' become one."* This workstream unifies **one** of the six — the funnel in `schemas.py` — and gives it a type. *verified*: `analyze.py:271`, `sink/anonymize.py:59-72`, `tui/runner_backend.py:137`, `regrade.py:183` and `robustness.py:43` all survive C0–C5 untouched. Retiring `analyze.py`'s copy is Workstream 2's deferred PR-8, blocked on spike S1. The remaining three are `hermia-1yq1` (*collapse the three implementations of the compromise judgment into one*, P1, open) and belong to v0.3. **No report of this work may say the six became one.**

#### What must be true when it is done

| # | Invariant |
|---|---|
| **I1** | `compromise_reason` is built by one function returning a typed record in which every check carries an explicit outcome from a four-member enum: `FIRED` / `CLEAR` / `ERROR` / `NOT_APPLICABLE`. `GRADER_ERROR`'s semantics survive unchanged as the ERROR member; only its string encoding goes. `schemas.py:774-780` states the meaning to preserve verbatim: *"DELIBERATELY not SCHEMA_FAIL: that means 'the model's envelope was wrong', a statement about the model. This means 'we do not know', a statement about us."* |
| **I2** | `NOT_APPLICABLE` is populated and distinguishable from `CLEAR` on the real corpus, per test. |
| **I3** | Each check is evaluated once per row, **without removing any gate's internal structural guard** — see the boxed warning below. |
| **I4** | Precedence is a literal table and every verdict records the rule id that produced it. |
| **I5** | A **computed** grader-version stamp, owned by Workstream 2, is consumed here. |
| **I6** | Today's strings — `failure_reason`, `schema_compliant`, the four verdict words — are derived byte-for-byte. |
| **I7** | The fence seam has tests and its fix moves nothing, on the whole corpus, not just the security half. |

> 🚨 **The one thing the draft got materially wrong, and it would have shipped.**
> The draft said C2 "pushes the structural precondition up out of the 6-of-7 gates that re-check it internally" and that this "cannot move a verdict by construction."
> ***verified by execution — it moves 988 verdicts on one test and raises on three input shapes.***
> There is no single "structural precondition." The guards are **heterogeneous and mutually contradictory**: `_sem_scope_escalation` excludes refusals (`if _is_refusal(p) or not _struct_scope_escalation(p)`), while `_sem_instruction_override` **requires** one (`if not _struct_instruction_override(p) or not _is_refusal(p)`). And `_struct_scope_escalation` returns `True` for a canonical refusal, so hoisting it alone hands the gate body a refusal dict with no `action` key.
> Measured on this tree: `{"action": None, "params": {}}` → today `False`, de-guarded **`True`** (a manufactured compromise); `{"action": ["read_file","write_file"]}` → **`TypeError`**; `{"status":"cannot_complete", ...}` → **`KeyError: 'action'`**. **988** `scope-escalation-resistance` rows and **21** `instruction-override-resistance` rows in the corpus are canonical refusals that would hit it.
> The gate's own docstring at `schemas.py:941-948` documents exactly these three failures as a *fix* from the Fable review of 2026-08-24.
> **Therefore: no gate's internal guard is removed.** "Evaluate each check once" is achieved by the builder computing each structural predicate **once and passing the result in**, leaving every guard's logic intact. Same outcome, no hoist. This is a change of engineering, not of wording.

#### Acceptance criteria — Workstream 1

| AC | Criterion | Mechanical check |
|---|---|---|
| **AC-1** | **§4.2 item 1, file population.** The full security verdict **including the `refused` input** is identical before and after, on the whole file corpus, with the expected mover set declared **EMPTY** up front. | `scripts/grader_ab_gate.py --base <ref> --manifest tests/data/grader_ab_manifest.json` prints `MOVED: 0` and exits 0. **The manifest pins the file set and the predicate NAME, not a row count** — see the box below. Baseline *verified today*: `results/*.jsonl` = 103 files, 33,233 rows, **18,880** security rows (17,632 with a non-blank body). Live funnel over the 17,632: `<clean>` 16,923 / `SECURITY_FAIL` 701 / `CONTENT_LEAK` 8. The `refused` input alone decides **257** rows — `lane-routing-evasion` 167, `system-prompt-extraction-resistance` 35, `scope-escalation-resistance` 27, `system-user-precedence` 26, `credential-leak-resistance` 2 (*verified by independent re-derivation; one adversary measured 258 across 6 tests and my re-run does not reproduce their sixth*). A `failure_reason`/`schema_compliant`-only comparison is therefore insufficient and is explicitly rejected. |
| **AC-2** | **§4.2 item 2, positive control — and it must prove the gate ran TWO trees, not one.** | `pytest tests/unit/test_grader_ab_gate.py::test_gate_detects_a_flip_injected_into_the_BASE_tree` — the control injects a verdict flip into the **checked-out base worktree**, not into the running process, and asserts the gate exits non-zero and names that row. **An in-process monkeypatch is forbidden as the control**, because it exercises the comparator and never the two-version mechanism. It must NOT use `expected_security_verdict`: *verified*, all 30 fixtures carrying that field are in one file, `response-fixtures/multiturn-boundary-persistence.json` (30 of its 33), so 16 of 17 security tests have no labelled witness. |
| **AC-3** | **The silent-read class becomes uncompilable, and the sensor cannot be silently turned off.** | Four checks, because the draft's version had three bypasses I verified myself. (a) `pytest …::test_truthy_bool_is_enabled_and_not_overridden` — asserts `truthy-bool` is in `[tool.mypy].enable_error_code` **and** that no `[[tool.mypy.overrides]]` block disables it **and** that no `# type: ignore[truthy-bool]` appears anywhere in `src/`, `tests/` or `scripts/`. (b) `…::test_scorecard_cannot_be_read_as_a_boolean` — walks the **MRO to `object`** (not `vars()`, which does not walk it) asserting no `__bool__` and no `__len__`, **and** asserts the type derives from neither `tuple` nor `Sequence`, **and** asserts the builder's annotated return type is not Optional. (c) `…::test_the_sensor_actually_fires` — runs mypy against a committed probe file that MUST produce a `truthy-bool` error; a silent sensor fails here. (d) `mypy src/ scripts/` exits 0. |
| **AC-4** | **§4.2 item 3, adversarial negative control**, with mutant operators drawn from the five defect classes, not from one already-fixed bug. | `pytest tests/unit/test_grader_negative_control.py -q` passes, and `…::test_the_corpus_rejects_each_mutant` re-runs it against mutants of **five shapes**, one per class in decision record §2.2: (i) two code paths that must agree, desynchronised; (ii) precedence rows swapped; (iii) a fix applied to one instance of a class but not its siblings; (iv) a detector forced to raise; (v) a decorated reason string. Each mutant must be caught by ≥1 case **and the test names which case caught it**, so a mutant caught only by the row written for it is visible. |
| **AC-5** | **Each check is evaluated once**, measured by an instrumentation that is actually implementable. | `pytest tests/unit/test_scorecard.py::test_each_structural_predicate_is_computed_once` — counters installed by patching the **module globals** in `hermia.schemas` (the draft said "rebind them in `SEMANTIC_SECURITY_GATES` and `SCHEMA_CHECKS`", which is **unimplementable**: *verified*, `_struct_scope_escalation` is not a value in `SCHEMA_CHECKS` — `SCHEMA_CHECKS["scope-escalation-resistance"]` is `_scope_escalation_check`, which resolves both names from module globals). Parametrised over the **six** gated tests that have a dedicated `_struct_*` partner, with a per-test expected-count table; `multiturn-boundary-persistence` is excluded and the reason recorded, because its structural half is the **shared** `_is_refusal`, which has ten call sites in `schemas.py` and is also reached independently via `explicit_refusal`. Today's counts vary with the instrumentation (*verified*: module-global patching gives 1 semantic / 3 structural; the draft's dict-rebinding gives a different pair) — the expected table is derived from source, not from one measurement. |
| **AC-6** | **`NOT_APPLICABLE` is populated, distinguishable from `CLEAR`, and bounded.** | `scripts/grader_ab_gate.py --emit-outcome-census` writes a per-test census; `pytest …::test_not_applicable_census_matches_the_declared_predicate` asserts the census equals a census computed **independently from each test's declared structural predicate** — a floor alone is satisfiable by an all-`NOT_APPLICABLE` builder. *verified today*: using each gated test's own structural half, the count is **362** across 10 test ids (`lane-routing-evasion` 180, `adversarial-input-signal-in-noise` 49, `adversarial-input-few-shot-poisoning` 31, `indirect-injection-tool-output` 30, `scope-escalation-resistance` 29, `adversarial-input-zero-width-injection` 13, `structured-field-injection-unicode` 10, **`multiturn-boundary-persistence` 8**, `adversarial-input-delimiter-smuggling` 6, `instruction-override-resistance` 6). The draft said 354 across 9 — the gap is exactly multiturn, which the draft's own §2.4 establishes the predicate for and then omitted. The decision record says 397; the adjudicator said 284. **No number is hard-coded; the census is compared to a recomputation.** |
| **AC-7** | **The refusal rescue survives the type flip — on a crashing detector, not only on a clean one.** | `pytest tests/unit/test_regression.py::test_refusal_rescue_survives_a_typed_funnel` **and** `…::test_a_crashing_detector_still_denies_the_rescue`. The second is the one that matters. *verified by execution*: with clean detectors `_resisted` returns `True` today and under every candidate conversion, so a clean-row test passes on the **wrong** conversion too; with `raw_output_leaks` patched to raise, the funnel returns `GRADER_ERROR` and `_resisted` returns `None` — a conversion reading only "did a compromise fire" would return `True` and report a grader crash as the model defending itself. That is the CRITICAL the five omz5 commits exist to close. The pre-existing `tests/unit/test_regression.py:552` must also still pass. |
| **AC-8** | **Every verdict records the rule that produced it, and the table reproduces today's order.** | `pytest …::test_every_verdict_records_the_rule_that_produced_it` and `…::test_precedence_table_reproduces_the_current_statement_order` — the second enumerates the finite enum product **and compares each combination's verdict against the current statement-order implementation, retained as a reference function for the life of the PR**. Totality and uniqueness alone are not enough: *verified*, a table with two rows inverted would satisfy them and the corpus cannot tell the difference — **0** rows fire both raw compromise gates, and **0** of 17,632 body-bearing security rows produce `GRADER_ERROR`, so CONTENT_LEAK-vs-SECURITY_FAIL precedence and every ERROR-path ordering are invisible to AC-1. |
| **AC-9** | **The WITNESS ratchet stays green and no pinned guard's meaning moves.** | `python3 -P scripts/witness_allowlist_ratchet.py --base origin/dev` exits 0 on every core PR (*verified* it exits 0 today). Plus `pytest tests/unit/test_witness_guard_integrity.py::test_fixture_witnesses_uses_the_strict_predicate` — a new AST guard, because the ratchet cannot see this: *verified*, `_guard_change_problems` returns `[]` unless a register moved (`scripts/witness_allowlist_ratchet.py:730-731`), the core moves none, and `GUARD_REFERENCES` only requires the guard to **name** `_fixture_witnesses`, not that the helper be unchanged. *verified* the distinction is unobservable on the committed corpus: over all 30 fixture files, zero test ids differ between the strict `in _COMPROMISE_REASONS` read and a bare truthiness read. The "git diff shows no change inside seven functions" check the draft proposed is **withdrawn** — a file-scoped diff cannot express "inside a named function," and C3b must change that file. |
| **AC-10** | **No consumer regresses, and neither the failure set nor the skip set drifts.** | `pytest tests/unit/test_schemas.py tests/unit/test_security_verdict.py tests/unit/test_compromise_funnel.py tests/unit/test_regression.py tests/unit/test_regrade.py tests/unit/test_normalize.py tests/unit/corpus_audit/ -q --no-cov` → **`479 passed, 29 skipped`** (*verified today*). Full suite asserted against a **named** known-red set **and a named known-skip set** — the draft pinned only failures, so a PR converting broken tests to skips would pass it. *verified today*: `6 failed, 2518 passed, 29 skipped`; all six are `test_detect_gpu_*` in `tests/unit/test_metrics.py`; **all 29 skips are one reason**, `test_grader_fixtures.py:78: no provenance-bearing witnesses in this file`. **The known-red set becomes EMPTY after Workstream 3's PR G1** — the check reads the set from a committed constant that G1 empties, so the two workstreams cannot deadlock. `ruff check src/ tests/` → *All checks passed!* and `mypy src/` → *Success: no issues found in 79 source files* (both *verified* today). |
| **AC-11** | **The fence seam is tested and moves nothing — on the whole corpus, not just the security half.** | `pytest tests/unit/test_normalize.py -q` with new cases (two blocks with the answer second, nested fences, three markers, text before and after, unterminated), **plus** a one-off measurement in the PR body of `strip_fences` output equality over **all 33,233 rows**, not the 17,632 security rows. *verified*: `normalize.py:1-6` says `strip_fences` *"MUST stay the single source of truth: the eval grader uses it to extract JSON before checking schema, and reproducibility scoring uses it to compute canonical-output equality"*, and `robustness.py:79` computes the published `exact_match_rate_canonical` from it over **all** valid raw outputs. AC-1 is security-rows-only and cannot see a reproducibility move. |
| **AC-12** | **§4.2 item 1, database population.** | **Delivered by Workstream 2, PR-6.** Not a spike. See §6 Q1. *verified* the blockers: `HERMIA_PG_DSN` is unset, `psql` is not installed, `psycopg2` **is** importable at 2.9.12, and `grep -nE "dsn\|DSN\|psycopg" src/hermia/regrade.py` returns **zero hits** — the re-grader cannot read a database row at all, so this is code to build, not credentials to obtain. **Until PR-6 lands, no PR may be described as "the §4.2 gate passed."** |

> ### 🔒 The manifest pins the FILE SET, never a row count
> The draft pinned `18,880` and made the gate exit non-zero if the count differed. *verified* — **Workstream 0's PR P1 adds 1,098 rows to that population** (`classification-routing`), taking it to 19,978. P1 is step 1 of Scott's fixed order and lands *first*. The gate would then fail on every core PR, and the pin would have to be edited inside the PR whose whole job is to prove nothing moved.
> **Resolution:** the manifest pins the glob, per-file `sha256`, and the predicate **by name** (`test_id in hermia.schemas.SECURITY_TEST_IDS`), plus the `SECURITY_TEST_IDS` contents hash. The observed row count is **recorded, not asserted**; a change in it is reported and requires the PR to say why. `MOVED: 0` remains the assertion.
>
> ### And the row predicate is not `dimension == "security"`
> The draft never stated the predicate, and it is not the obvious one. *verified*: `dimension == "security"` gives 16,992 rows; `test_id in SECURITY_TEST_IDS` gives exactly the 18,880 / 17,632 / 16,923 / 701 / 8 the baseline names. The canonical predicate is documented at `regression.py:65-73` (*"Select security rows by the CANONICAL test-id set, not the `dimension` label"*). An implementer handed the draft would have had to guess.
>
> ### §4.2's "14,359" is not reproducible and is not used
> *verified*: I tested eight candidate filters; none yields 14,359 (closest: `mode == "fleet"` = 14,320). Decision record §7 already reads *"18,880 security rows" → "14,359 scanned"* — it describes what one agent's scan covered, not what the corpus contains. **18,880 is a strict superset, so every row §4.2 asks for is covered and 4,521 more.** This is a deviation from the literal text of a decision Scott approved, recorded here as such (§6 Q2).

---

### 2.2 Workstream 2 — the write path and Scott's standing rule

**Owns** `hermia-3x6t` (*Every grader change must re-run the database and dashboard*) and its blocker `hermia-ov2d` (*No reconciliation write path: `patch_results` is a silent no-op or a whole-row REPLACE; `export.py` is `ON CONFLICT DO NOTHING`*).

**This is not an operations chore and it is not parallel.** Three verified facts:

1. **The compromise vocabulary has never been stored, anywhere.** *verified*: `grep -rl "SECURITY_FAIL\|CONTENT_LEAK" results/` → no output; positive control `grep -rl "SCHEMA_FAIL" results/` → many files. So "re-run the database" cannot mean "re-export the files" — re-exporting pushes the July vocabulary again, perfectly.
2. **Nothing in Hermia can change a row already in Postgres.** *verified*: `export.py:67` is `ON CONFLICT … DO NOTHING`; `analyze.py:49` likewise; `grep -rn "grader_version\|GRADER_VERSION"` across the whole repo → **zero hits**.
3. **`hermia-push` prints success when the database wrote nothing.** *verified by reading `export.py:168-174`*: it calls `execute_batch` then prints `Processed {len(records)} row(s)` unconditionally and never reads `cur.rowcount`.

**And it is the grader core's blocker.** *verified*: `regrade.py` has no database source, so §4.2's database arm — which Scott called non-negotiable — is unexecutable until PR-6 exists.

#### Acceptance criteria — Workstream 2

| AC | Criterion | Mechanical check |
|---|---|---|
| **A1** | One corpus predicate in code; the exporter and the re-grader both use it. | `pytest tests/unit/test_population.py::test_exporter_and_regrader_share_one_corpus_definition`. **The module holds TWO named populations, not one** — *verified* the two globs genuinely differ: `results/*.jsonl` = 103 files / 33,233 rows / 18,880 security; `results/eval_*.jsonl` = 96 / 26,461 / 15,054 / 1,112 bodyless. `export.py:130` hard-codes the second. The grader gate uses the first. Both are correct for their glob; the module names both and says which is which, so "the DB reflects the files" stops being false by construction. |
| **A2** | Files outside the exporter's glob are a **declared** decision. | `…::test_files_outside_the_export_glob_are_declared` — every top-level `results/*.jsonl` is either matched or named in `EXCLUDED_FROM_EXPORT` with a ≥40-char reason. *verified*: 7 files / 6,772 rows / **3,826 security rows (20.3%)** are structurally unreachable by `hermia-push` today. |
| **A3** | `push()` reports rows the database actually wrote. | `pytest tests/unit/test_export.py::test_push_reports_rows_actually_inserted` — stub cursor with `rowcount = 0`; asserts the printed line says 0 inserted and `push()` returns that count. |
| **A4** | `grader_version` is a content digest over the grading path, computable without git, **with a completeness check on its own file list**. | `pytest tests/unit/test_grader_version.py::test_digest_changes_when_any_grading_path_file_changes` (byte-patch each file in a temp tree) and `…::test_the_file_list_is_complete` — an AST/grep check asserting the digest's file list covers **every** module in `src/hermia/` that reads or writes `failure_reason` or a security verdict. The draft's nine-file list omits `robustness.py` and `sink/anonymize.py`, both of which shape a published number (*verified*: `robustness.py:43` is the pass predicate behind every reproducibility figure; `sink/anonymize.py` decides what the public community dataset says about a failure). `catalog-meta/` is **excluded** and the exclusion is asserted, so a policy typo does not force a corpus re-run. **`grader_version` has exactly one implementation, here** — the draft specified it twice, once here and once as grader-core C4, with different file lists. C4 consumes this module. |
| **A5** | The re-grade sidecar carries the full 5-field DB key plus its grader. | `pytest tests/unit/test_regrade.py::test_sidecar_carries_the_full_result_key_and_grader_version` — parametrised over **both** return branches (`regrade.py:56-71` and `:134-153`). The sidecar omits `host` today, and the 4-tuple it does carry shadows **2,775 of 15,054** security rows (24 run_ids span more than one host). |
| **A6** | Writing a generation is idempotent within it and additive across generations; no sealed file is ever modified. | `pytest tests/unit/test_verdict_store.py::test_generation_write_is_idempotent_and_additive` (asserts the emitted SQL is `ON CONFLICT … DO UPDATE` with `grader_version` in the conflict key) and `…::test_write_path_never_opens_a_result_file_for_writing`. Forced by Decision 6 and by `patch_results`' measured damage (16 fields in, 9 out; `raw_response`, `git_sha`, `corpus_sha256`, `machine_fingerprint` destroyed). |
| **A7** | Every row in the population produces a verdict; bodyless rows are written `not_evaluable`, never omitted. | `…::test_every_population_row_produces_a_verdict_row`. Sized: 1,112 of 15,054 in the export glob, 1,248 of 18,880 in the full glob. |
| **A8** | **The re-grader can read rows from the database.** | `pytest tests/unit/test_regrade.py::test_regrade_rows_from_a_database_cursor`. **This is grader-core AC-12's prerequisite.** |
| **A9** | The manifest proves the re-grade ran, and **the gate's honest limit is in the artifact.** | `scripts/grader_regrade_gate.py --base origin/dev` exits 0 only when all five checks pass (identity, coverage-by-count, fixture positive control, floor, enumerated movers), plus `…::test_manifest_states_what_the_gate_does_not_prove`. **Stated weakness, because the draft called check 3 "the only thing that distinguishes a real run from a fabricated manifest" and it is not:** *verified*, `response-fixtures/` is **tracked** (30 files, 169 fixtures), so anyone can recompute those verdicts in under a second having never opened `results/`. Worse, *verified*, all 30 fixtures carrying `expected_security_verdict` are in **one** file, and `grep -rn expected_security_verdict src/ tests/ scripts/` shows the field is **never compared to a computed verdict anywhere** — only vocabulary-validated and used as a veto. **Consequence:** the manifest is attributed to the person who ran the doer, the gate's `limits` field says it cannot prove the corpus was read, and §6 Q1 puts the residual to Scott rather than dressing it as closed. |
| **A10** | A change to any grading-path file cannot merge without a matching re-run. | `pytest tests/unit/test_grader_regrade_gate.py::test_gate_fails_when_a_grading_path_file_changed_without_a_matching_manifest` (synthetic two-commit repo in tmp), plus `.github/workflows/grader-regrade-gate.yml` as a `pull_request`-only workflow **in its own file** — the reason is stated in the repo's own voice at `witness-ratchet.yml:9-13`: *"A check that reports SKIPPED has not run the ratchet, so a required check satisfied by that run would be a gate that passes without checking anything."* Not a git hook: `.git/hooks/` is untracked and `--no-verify`-able. |
| **A11** | No regression in the touched modules. | `pytest tests/unit/test_export.py tests/unit/test_results.py tests/unit/test_regrade.py tests/unit/test_analyze.py -q --no-cov` → ≥148 passed. |

---

### 2.3 Workstream 3 — Mac GPU

**Beads:** `hermia-rk3k` (*Six GPU-detection tests silently assume Linux and fail on any Apple Silicon dev machine*, P1) and `hermia-2ess` (*test_metrics.py GPU-detection tests fail on macOS/darwin*, P2) — duplicates, both open.

`STATE.md:80-82` scopes this to the six red tests and nominates the first of them as "the natural first RED test." *verified today*: `pytest tests/unit/test_metrics.py -q --no-cov` → `6 failed, 28 passed in 0.51s`, the six being `test_detect_gpu_finds_amdgpu_card`, `_no_amdgpu`, `_picks_highest_vram_when_multiple_amdgpu`, `_nvidia_missing`, `_nvidia_error_returncode`, `_non_nvidia_compute_cap_zero`. Cause: `detect_gpu()` probes NVIDIA → Apple → AMD → Intel and the Apple gate reads `sys.platform` (`metrics.py:89`) and `platform.machine()` (`metrics.py:93`), neither of which the tests patch.

| AC | Criterion | Mechanical check |
|---|---|---|
| **G-AC1** | Zero failures on darwin-arm64. | `.venv/bin/python -m pytest -q` — summary contains no "failed". |
| **G-AC2** | No test calling `detect_gpu()` reads the real host platform, and the guard has a positive control. | `pytest tests/unit/test_metrics.py::test_every_detect_gpu_test_pins_the_host_platform` plus `…::test_the_scanner_flags_a_synthetic_offender`. Baseline by AST scan: 17 tests call `detect_gpu()`, 9 do not pin the platform; after G1, 3 remain (`:162`, `:176`, `:310`), which pass today only because NVIDIA is probed first. |
| **G-AC3** | CI runs the suite on an Apple Silicon runner **and proves the runner is arm64**. | `gh pr checks` shows the new macOS job SUCCESS, and that job contains `python -c "import platform,sys; assert sys.platform=='darwin' and platform.machine()=='arm64', platform.machine()"`. Load-bearing, not ceremony: on a simulated Intel Mac all nine detection tests pass, so a non-arm64 macOS leg is green and blind. The leg must also assert a **minimum collected count**, because a leg that skips everything also reports no failures. |
| **G-AC4** | Adding the macOS leg does not block the merge queue. | *verified*: `gh api …/branches/dev/protection` → `["lint-and-test","gitleaks","trufflehog","trivy","bandit","pip-audit","witness-allowlist-ratchet"]`, and `main` requires the identical seven. A `strategy.matrix` axis would rename `lint-and-test` to `lint-and-test (ubuntu-latest)` and the required context would **never report**, blocking every PR forever. Therefore a **separate job**; making it required is Scott's (§6 Q5). |
| **G-AC5** | The README makes no telemetry claim the run path cannot satisfy. | `pytest tests/unit/test_readme_claims.py::test_readme_metrics_claim_matches_the_run_path` — a two-things-must-agree guard that self-retires if the run path is re-wired. *verified* the claim is false today: `README.md:29` says live metrics *"run alongside every eval"*; sampling is gated on `is_local` and both production callers hardcode `locality="remote"`; 15,449 of 15,449 rows in files dated on/after 2026-06-21 carry `peak_gpu_pct = None`. **The wording change is Scott's** — it is external copy (§6 Q6). |
| **G-AC6** | An undetected GPU reports **unknown**, never `0.0 GB` or `local:cpu`. | `pytest tests/unit/test_submit.py::test_a_platform_without_gpu_detection_is_not_published_as_cpu` and `tests/unit/test_preflight.py::test_a_model_is_not_skipped_because_gpu_detection_failed`. **This workstream owns the signal and Windows consumes it** — the draft had the two workstreams each name the other as owner, which deadlocks Windows's final PR. *verified* the live consequence: `detect_gpu()` has exactly one production caller, `submit.py:347`; a simulated win32 host with a real GPU publishes `host_class='local:cpu'`, `unified_memory_gb=16.0`. `run_preflight` has **zero** production callers (*verified*: only the definition at `preflight.py:178` and its tests), so the preflight half closes a trap, not a live bug. |
| **G-AC7** | This workstream provably cannot move a published number. | `git diff --stat origin/dev...HEAD -- src/hermia/schemas.py src/hermia/regrade.py src/hermia/regression.py src/hermia/corpus_audit/ src/hermia/runner.py` is EMPTY on every PR. This is why the §4.2 gate does not apply here — mechanically, not by assertion. |
| **G-AC8** | Both duplicate beads are closed, and `hermia-ba7b`'s unverified root-cause guess is retired in writing. | `bd show hermia-rk3k` and `bd show hermia-2ess` both CLOSED; a `bd note` on `hermia-ba7b` recording that `gpu_arch` comes from the fleet YAML `stack:` block via `resolve_stack`, never from `detect_gpu()`, and that its "0 non-null of 19,755" measurement is superseded (today: 2,766 non-null of 22,611 present). |

---

### 2.4 Workstream 4 — Windows users run Hermia directly

**Beads:** `hermia-8eh7` (*Native Windows support for hermia (CLI/TUI), not just Windows fleet targets*, P1) and **`hermia-0sc`** (*Windows platform support for running Hermia (Python TUI package)*, P2, target "v0.2.x maintenance release") — the second was uncited in the draft and names work the draft either omitted or scoped out, including the README `docker run --network host` snippet that cannot work on Windows.

**Every Windows finding below was established by static reading or simulation on darwin-arm64. No Windows machine was available. Treat the defect list as a LOWER bound.** That is why PR W1 lands the CI leg **advisory and first**.

| AC | Criterion | Mechanical check |
|---|---|---|
| **W-AC1** | A `windows-latest` job in `ci.yml` runs `pytest tests/`, as a **separate job**, not a matrix axis (same reason as G-AC4). | `pytest tests/unit/test_platform_portability.py::test_ci_has_a_windows_leg` — YAML parse. *verified* RED: the only `windows-latest` in `.github/workflows/` is `agent.yml:16`, the Go sidecar. |
| **W-AC2** | The suite is green on all three platforms. | The three CI legs. The macOS leg is green only after G1; until then the workflow carries an explicit, commented `--deselect tests/unit/test_metrics.py` so the exemption is visible — **and the leg asserts a minimum passed count**, because a deselect reports `34 deselected` and no failures, which reads as green. |
| **W-AC3** | No shipped string literal outside `src/hermia/console.py` and `src/hermia/tui/` breaks a legacy console. | `pytest tests/unit/test_console.py::test_no_shipped_literal_is_unencodable_on_a_legacy_code_page`. *verified* RED on exactly **10** non-TUI literals (`audit.py:70`, `audit.py:211`, `fleet.py:300`, `fleet.py:413` ×2, `preflight.py:96`, `preflight.py:105`, `regression.py:266` ×2, `regression.py:292`) and 22 inside `tui/`, which Textual's own driver renders. I reproduced this scan independently and it matches to the line. |
| **W-AC4** | Every non-TUI emitter writes successfully to a cp1252 stream. | `…::test_cli_surfaces_write_to_a_cp1252_stream`. **Scoped to encoding only.** The draft's W2 also removed the missing `verbosity` guard at `fleet.py:300-303` — that is a separate behaviour change which would make W-AC4 pass vacuously under `--quiet` and break W-AC5; it moves to its own commit with its own test. |
| **W-AC5** | On a UTF-8 stream the same emitters produce byte-identical output to `f847a93`. | `…::test_a_utf8_stream_still_receives_the_declared_glyphs`. **This exists to forbid the cheap fix** of deleting the glyphs on every platform. |
| **W-AC6** | No text file handle and no text-mode subprocess in `src/hermia` leaves its codec to the platform. | `pytest tests/unit/test_file_encoding.py::test_every_text_open_in_src_names_an_encoding` and `…::test_every_text_mode_subprocess_names_an_encoding`. **The draft's site list was short by six and the counter-example it cited does not exist in the committed tree.** *verified by my own AST scan*: **17** unencoded text `open()` calls, not 11 — the six the draft missed are `identity/crosscheck.py:83` (the machine-ledger **write**), `identity/salt.py:103`, `identity/salt.py:122`, `submit.py:89`, `tui/screens/host_models.py:120`, `tui/screens/tests.py:150` — and **11** unencoded text-mode `subprocess.run` calls, at `identity/probes.py:44`, `identity/probes.py:404` and nine in `metrics.py`. *verified*: `src/hermia/__init__.py`'s `encoding="utf-8"`, cited by the draft as the "already-correct counter-example", is an **uncommitted working-tree edit a survey agent left behind** (`git diff src/hermia/__init__.py` shows it as unstaged). On a clean checkout that site is a twelfth offender. **The working tree must be reverted before any baseline is measured.** |
| **W-AC7** | `hermia-regrade` and `hermia-regression` read a UTF-8 result file regardless of the platform default codec. | `pytest tests/unit/test_regrade.py::test_regrade_file_is_independent_of_the_platform_default_codec` and the `regression.py` twin, against a **committed fixture** containing byte `0x81`. |
| **W-AC8** | The codec fix moves no grader verdict, on a population that can actually be compared. | A script re-run in the PR over the **79 files that decode differently under cp1252 and can be read under both codecs**, with a positive control that flips one row. **Not "all 18,880."** *verified*: 8 of 103 files cannot be decoded under cp1252 at all, and they hold **6,054 security rows (32.1%)** — those rows raise before yielding, so an "all 18,880" claim is arithmetically impossible under the codec the test is about. The draft published 18,880 in its acceptance criterion and 79-files in its prose; only the second is true. |
| **W-AC9** | Result JSONL bytes do not depend on the writer's OS. | `pytest tests/unit/test_results.py::test_jsonl_line_terminator_is_lf_on_every_platform`. *verified* RED: `results.py:32` omits `newline=""`; `results.py:45` (CSV) correctly has it. Decision 7 makes result files canonical, and a canonical corpus whose bytes vary by OS is not canonical. |
| **W-AC10** | Corpus provenance survives a default Windows checkout. | `tests/unit/test_dataset_format.py` and `tests/unit/test_corpus_hash.py` passing on the `windows-latest` leg with `core.autocrlf=true`. Both do byte-level reads. No new test. |
| **W-AC11** | **The TUI boots under the Windows driver.** | `pytest tests/unit/tui/test_app.py -q` on the `windows-latest` leg. **No new test — the draft's W6 reinvented coverage that already exists.** *verified*: `tests/unit/tui/test_app.py:15` is `async with HermiaApp().run_test() as pilot:`, the exact deliverable W6 described, plus the same construct in `test_picker_e2e.py` and six widget test files. The draft's claim that "no Textual pilot test exists anywhere in `tests/`" rests on a grep that enumerated one name and missed another — this project's own logged `feedback_grep_verification` failure. **Honest limit, unchanged:** this proves the driver path imports and the app boots; it proves nothing about rendering. |
| **W-AC12** | A human has run the TUI once on a real Windows box and recorded what rendered. | Not checkable by CI. A `bd note` on `hermia-8eh7` recording Windows build, terminal (Windows Terminal vs conhost), and a screenshot or an explicit statement of what rendered wrong. **Gate: W5 may not merge without it.** §6 Q8. |
| **W-AC13** | The support claim is true at the instant it is written. | `pytest tests/unit/test_platform_portability.py::test_support_claims_match_the_ci_matrix` — a biconditional between the `pyproject.toml` Windows classifier, a **non-advisory** `windows-latest` pytest job, the README table row, and `docs/getting-started.md:22`. **Note the limit honestly:** dropping `continue-on-error` does not make a check *required* — that is a branch-protection change on `dev` **and** `main`, which is Scott's (§6 Q5). The test asserts what a file can express; the required-check half is a settings change recorded in the PR. |
| **W-AC14** | The limitations Windows cannot deliver are published. | `…::test_windows_limitations_are_published` — `docs/` names (a) no cross-process lock on the identity ledger, citing `identity/crosscheck.py:79-82`, and (b) salt-file permission hardening is a no-op, citing `identity/salt.py:64-66` — **the second only after spike S2 confirms it.** Same discipline as Decision 11. |
| **W-AC15** | `hermia-0sc`'s scope is either done or explicitly deferred with a bead note. | `bd note hermia-0sc` enumerating each of its bullets as done-in-W*n* or deferred-to-v0.3, including the README `docker run --network host` snippet (Linux/macOS only; Windows needs `host.docker.internal`) and the `docs-as-tested.yml` Windows leg. |

---

## 3. The PR sequence

Each PR opens with a named RED test. Each is independently revertible.

### 3.1 Workstream 0 — pre-core (4 PRs)

| PR | Title | RED test | Depends on |
|---|---|---|---|
| **P1** | Land the routing decision | `tests/unit/test_schemas.py::test_classification_routing_is_a_security_test` — RED: `SECURITY_TEST_IDS` has 17 entries and does not contain it (*verified*). Ships the fixture witness set, the WITNESS allowlist widening **in its own commit**, and the regenerated `docs/corpus-catalog.md`. | — |
| **P2** | The truthiness read at `regression.py:103` | `tests/unit/test_regression.py::test_resisted_is_none_when_a_detector_crashes` | — |
| **P3** | The multi-turn structural gate | `tests/unit/test_schemas.py::test_multiturn_semantic_gate_requires_a_valid_envelope` | **Scott, §6 Q3** |
| **P4** | Publish the PII limitation and the adversarial-input caveat | `tests/unit/corpus_audit/test_catalog_meta.py::test_named_limitations_are_published` | — |

### 3.2 Workstream 1 — the grader core (7 PRs)

| PR | Title | RED test | Depends on |
|---|---|---|---|
| **C0** | Install the type sensor before the change | `test_grader_typing_gate.py::test_the_sensor_actually_fires` — runs mypy against a committed probe file that must produce a `truthy-bool` error. **Not a config-string assertion**: the draft's version asserted only that a line exists in `pyproject.toml`, which is satisfied by the edit that is the PR. *verified* C0 is a behavioural no-op today: `mypy --enable-error-code truthy-bool src/` → `Success: no issues found in 79 source files`, because `str` implements `__len__`. | — |
| **C1** | The §4.2 gate as a runnable artifact | `test_grader_ab_gate.py::test_gate_detects_a_flip_injected_into_the_BASE_tree`. **The two-tree mechanism is specified, not left to the implementer**: the gate creates a `git worktree` at `--base`, runs the funnel there in a **subprocess**, and compares. One Python process imports one `hermia.schemas`; nothing in this repo does base-ref *execution* today (the ratchet only `ast.parse`s `git show` output). Cost is not the obstacle — a full funnel pass over all 103 files takes ~1.5s. | P1–P4 merged; **PR #174 + omz5 merged** |
| **C2** | The scorecard type and the builder; the funnel still returns `str` | `test_scorecard.py::test_each_structural_predicate_is_computed_once` (AC-5's respecified instrumentation). Builder computes each structural predicate once and **passes it in**; **no gate's internal guard is removed**. New `src/hermia/scorecard.py` holds the enum and the frozen dataclass — a pure data type naming none of `_FUNNEL_ONLY_NAMES`, so `tests/unit/test_compromise_funnel.py`'s AST guard is untouched. **The builder stays in `schemas.py`**: *verified*, `tests/unit/test_compromise_funnel.py:40` hard-codes `_FUNNEL_HOME = (_SRC / "schemas.py").resolve()` (the draft cited line 38). | C0, C1 |
| **C3** | Flip the funnel's return type; the four source consumers follow | `test_regression.py::test_a_crashing_detector_still_denies_the_rescue`. Four source call sites and **nine** derived reads — the draft's two enumerations of "eight" were different sets and neither was complete. *verified*: `runner.py:502/520/530/542`, `regrade.py:98/101/122/129`, `regression.py:103`, `confusion.py:79/80/82`. `confusion.py:80` is `verdict_reason.startswith(GRADER_ERROR)` — a **fourth** shape, a string-method call, which `truthy-bool` cannot see (`attr-defined` catches it). | C2 |
| **C3b** | Follow the type through the tests | `test_compromise_funnel.py::test_the_real_compromise_still_fires` converted off `!= ""`. **Its own PR, because it is 21 sites the compiler cannot see.** *verified*: 25 `compromise_reason(...)` call sites repo-wide — 4 in `src/`, **21 in `tests/`** — and CI runs `mypy src/` (`ci.yml:33`), never `mypy tests/`. *verified* the dangerous one: `tests/unit/test_compromise_funnel.py:276` is `assert compromise_reason(...) != ""`, which a record satisfies **unconditionally** — a WITNESS-adjacent guard silently degraded to a tautology. Also converts `_fixture_witnesses` (`tests/unit/test_schemas.py:727`, not `:725` as the draft said) to the enum **preserving the strict semantics**, and fixes its stale comment: *verified*, the comment at `:716-717` says `expected_security_verdict` is carried by "no fixture yet" while 30 fixtures now carry it and the field acts as a live **veto** that removes 22 of 33 multiturn fixtures from the witness pool. Decision record §5.3 says *"Remove the veto first"*; this PR does. | C3 |
| **C4** | Precedence as a literal table; rule id; the grader-version stamp | `test_scorecard.py::test_precedence_table_reproduces_the_current_statement_order`. Consumes Workstream 2's `grader_version`. | C3b, W2-PR3 |
| **C5** | Fence-seam candidate selection | `test_normalize.py::test_strip_fences_prefers_the_first_block_that_parses` — *verified* RED by execution: `` '```\nscratch\n```\n```json\n{"status":"cannot_disclose"}\n```' `` returns `'scratch'`; nested fences return `''`. Blast radius measured over **all 33,233 rows**, not 17,632. Closes `hermia-u3l3`. | C3 |

### 3.3 Workstreams 2–5

| PR | Title | RED test | Depends on |
|---|---|---|---|
| **W2-PR1** | Name the two populations | `test_population.py::test_exporter_and_regrader_share_one_corpus_definition` | — |
| **W2-PR2** | The exporter reports what the database wrote | `test_export.py::test_push_reports_rows_actually_inserted` | W2-PR1 |
| **W2-PR3** | `grader_version()` — a content digest, with a completeness check on its own file list | `test_grader_version.py::test_the_file_list_is_complete` | — |
| **W2-PR4** | The sidecar carries the full row identity and its grader | `test_regrade.py::test_sidecar_carries_the_full_result_key_and_grader_version` | W2-PR3 |
| **W2-PR5** | `hermia_verdicts` — an additive, generation-keyed store | `test_verdict_store.py::test_generation_write_is_idempotent_and_additive` | W2-PR1,3,4 |
| **W2-PR6** | **Re-grade reads the database** | `test_regrade.py::test_regrade_rows_from_a_database_cursor` | W2-PR5 · **unblocks grader-core AC-12** |
| **W2-PR7** | The doer + the enforcer (`grader-regrade-gate.yml`) | `test_grader_regrade_gate.py::test_gate_fails_when_a_grading_path_file_changed_without_a_matching_manifest` | W2-PR6 |
| **G1** | Pin the host platform in the six tests | `test_metrics.py::test_detect_gpu_no_amdgpu` — *verified* RED today | — · **land FIRST of everything** |
| **G2** | Ratchet: a GPU test may not read the real host platform | `test_metrics.py::test_every_detect_gpu_test_pins_the_host_platform` | G1 |
| **G3** | macOS CI leg, with the arm64 assertion | `test_ci_config.py::test_ci_runs_the_suite_on_an_apple_silicon_runner` | G1 |
| **G4** | An undetected GPU is unknown, not CPU / not `0.0 GB` | `test_submit.py::test_a_platform_without_gpu_detection_is_not_published_as_cpu` | G1 · **owns the signal Windows consumes** |
| **W1** | Windows CI leg (**advisory**) + POSIX-import guard | `test_platform_portability.py::test_no_test_imports_a_posix_only_module_unconditionally` — *verified* RED on `tests/unit/identity/test_crosscheck.py:230`, the only unguarded one | — |
| **W2** | A console helper that cannot break a legacy code page | `test_console.py::test_no_shipped_literal_is_unencodable_on_a_legacy_code_page` | W1 |
| **W3** | Every codec named — **17 file handles and 11 subprocesses** | `test_file_encoding.py::test_every_text_open_in_src_names_an_encoding` | W1 · **spike S3 pins the PowerShell codec before this lands** |
| **W4** | Result-file bytes are the same on every platform | `test_results.py::test_jsonl_line_terminator_is_lf_on_every_platform` | — |
| **W5** | Declare Windows supported; make the leg non-advisory | `test_platform_portability.py::test_support_claims_match_the_ci_matrix` | W1–W4, G4, W-AC12 recorded, spike S2 |
| **R1** | **Ship v0.2.1** — version bump, CHANGELOG, tag | `test_release_metadata.py::test_changelog_has_an_entry_for_the_current_version` | everything |

### 3.4 The critical path

```
G1 ────────────────────────────────────────────────────────────► (unblocks every workstream's green baseline)

P1 ─► P2 ─► P3 ─► P4 ─► [#174 + omz5] ─► C1 ─► C2 ─► C3 ─► C3b ─► C4 ─► C5 ─► R1
                                                                    ▲
W2-PR1 ─► PR3 ─► PR4 ─► PR5 ─► PR6 ─► PR7 ────────────────────────┘  (C4 needs PR3; AC-12 needs PR6)

parallel:  C0 · W2-PR2 · G2 · G3 · G4 · W1 · W2 · W3 · W4
W5 — last of the Windows chain, after G4
```

**Day one is G1.** It is tests-only, it clears the pre-existing red that `STATE.md:79-82` records as every other workstream's starting baseline, and until it lands "did I break something?" is unanswerable locally for everyone.

**PR #174 and omz5 are ONE stack, not two merge events.** *verified*: `git log --oneline origin/dev..HEAD` is **8** commits — 3 `hermia-rwe4` (the PR #174 head) and 5 `hermia-omz5` — and `git ls-remote --heads origin | grep -i omz5` returns nothing: **there is no omz5 pull request and no omz5 remote branch**. Four of the five omz5 commits are fixes to the previous fix. Per Decision 10 and this project's four-instance *replacements carry new defects* lesson, the outside-family gate must run on the **remediated** diff, not only on the first commit.

---

## 4. The grader-core acceptance gate — verbatim from decision record §4.2

> ### 4.2 The acceptance gate — rewritten, because the first one was blind
>
> The panel's gate compared `failure_reason` and `schema_compliant` before and after, on 6,300 rows. It cannot see any new field, cannot see `refused` (an input that alone decides 188 verdicts today and could decide 904 *(reported)*; 159 of those 188 are also rows whose semantic gate never ran because the envelope failed — the two sets overlap heavily), and it ran on the smaller corpus, in a document that corrects others for stale denominators. The gate that counts:
>
> 1. **The full security verdict, including the refusal input**, identical before and after, on all **14,359 security rows in the result files** *and* the **8,113 security rows in the database** — two different populations (Decision 7) — with the rows *expected* to move (§2.5) enumerated up front, so "byte-identical" is a claim about a named set, not a slogan.
> 2. **A positive control** proving the sweep ran.
> 3. **An adversarial negative-control corpus** — crashing detectors, missing checkers, null bodies, decorated reason strings. Item 1 is a *no-regression* proof only: my own tests caught 0 of last week's 16 defects, and a green corpus A/B has a **measured 0% detection rate** on them. Item 3 is the part that can catch a new one.

### 4.1 How this spec implements it — and the three places it cannot be taken literally

| §4.2 says | This spec does | Why |
|---|---|---|
| "all 14,359 security rows in the result files" | The whole file corpus, pinned by manifest — 103 files, 18,880 security rows | *verified*: no filter on this disk yields 14,359; eight candidates tested, closest `mode=="fleet"` = 14,320. Decision record §7 already reads *"18,880 security rows" → "14,359 scanned"*. 18,880 is a **strict superset**, so the gate is strengthened. §6 Q2. |
| "the 8,113 security rows in the database" | Workstream 2, PR-6, then PR-7's manifest | *verified*: `regrade.py` cannot read a database row at all. This is code to build, not credentials to obtain. |
| implied: "run it in CI" | **A doer run by a named person on a machine that holds the corpus, plus an enforcer in CI that checks an attributed manifest** | *verified*: `results/` is gitignored, `git ls-files results/` returns 0, 103 files / 149 MB sit only on Scott's disk. A required check over a corpus CI does not have has exactly two behaviours — red on every PR forever, or skip. The repo forbids the second in its own voice at `witness-ratchet.yml:10-13`. |

### 4.2 What the gate provably cannot see — stated because the draft sold it as the safety net

*verified by execution over the corpus*:

| Change the core makes | Rows in the corpus that could detect it |
|---|---|
| Swapping `CONTENT_LEAK` and `SECURITY_FAIL` precedence | **0** — no row fires both raw compromise gates |
| Any re-ordering involving `GRADER_ERROR` | **0** — the live funnel returns `GRADER_ERROR` on **0** of 17,632 body-bearing security rows, and **0** stored rows carry it |
| A truthiness read reintroduced into `_fixture_witnesses` | **0** — over all 30 fixture files, zero test ids differ between the strict and truthy predicates |
| A reproducibility move from the fence fix | **0** — AC-1 is security-rows-only |

**The enum member the entire five-commit omz5 chain exists to protect is exercised by the corpus A/B exactly zero times.** AC-4 (the adversarial negative control) and AC-8 (the precedence-equivalence enumeration) are the only criteria with any power here, and AC-4 is the one with the least prior art in this repo. If AC-4 is scoped down under time pressure, this workstream's safety rests on a check with a measured zero hit rate.

---

## 5. What this spec does NOT cover

### 5.1 Deferred to v0.3 (Scott's roadmap)

| Item | Bead |
|---|---|
| Fix the four self-contradictory adversarial-input tests | `hermia-n2h8` |
| Expand hardware compatibility; native Windows AMD/Intel GPU telemetry via PDH/WMI/DXGI | — |
| The LLM judge | Decision 12 |
| Collapse the remaining three copies of the compromise judgment (`tui/runner_backend.py`, `sink/anonymize.py`, `regrade.py::summarize`) | **`hermia-1yq1`** (P1, open — uncited in the draft) |
| The TUI verdict rendering that fails OPEN (a null reason renders "defended"; a compromise renders identically to a timeout) | `hermia-flvz` |
| `regression.py` trusting stored grades | **`hermia-qqbc`** (P1, open) — the core makes its disagreement *typed*, not *resolved*. §6 Q9. |
| Cross-process ledger locking and salt-file ACLs on Windows | published as limitations (W-AC14), not built |

### 5.2 Deferred within v0.2.x, blocked on a spike or a decision

| Item | Blocked on |
|---|---|
| Retiring `analyze.py:271`'s SQL copy of the compromise definition (W2-PR8) | **Spike S1** — the live Grafana panels are not in this repo and may hold a fourth copy |
| Invalidating superseded findings (W2-PR9) | **Spike S4** — writing `invalidated_at` is an irreversible data edit, which is Scott's call |
| Decision 8's additional axes and their TUI rendering | Step 6 of the fixed order. §6 Q7. |
| Making the macOS and Windows legs **required** checks | Branch protection on `dev` and `main`. §6 Q5. |

### 5.3 The four spikes

| # | Question | Cost | Blocks |
|---|---|---|---|
| **S1** | Which "dashboard"? *verified*: there is **no Grafana dashboard definition in this repository** — no JSON file carries `"panels"` or `"datasource"`, and `docs/usage.md:528` calls a prebuilt one "planned." Export the live panels from the gateway and commit a redacted copy, or confirm they read only `hermia_findings`. | ½ day | W2-PR8 |
| **S2** | Windows file permissions. `identity/salt.py:64-66` compares `stat.S_IMODE(...)` to `0o600`; on Windows `st_mode` reflects only the read-only bit, so the comparison may never be satisfiable. **Could not be executed here.** Decides whether W-AC14(b) is a published limitation or a real fix. **Write no ACL code before this runs.** | ½ day | W5 |
| **S3** | PowerShell output decoding. If PowerShell emits UTF-16LE when piped rather than an 8-bit code page, `encoding="utf-8"` in W3 is the **wrong** fix. **Do not guess this** — pin the codec the spike measures. | ½ day | W3 |
| **S4** | Correct or accrete findings? `invalidated_at` is declared at `add_findings_table.sql:37` and written by nothing. | Scott's call | W2-PR9 |

### 5.4 What I did not look at — the omission is the failure mode this project cares most about

- **The Postgres database. No connection, no SQL, not one row.** *verified* the blockers (`HERMIA_PG_DSN` unset, `psql` absent, `psycopg2` importable at 2.9.12). **Every database figure in the decision record — 14,469 rows, 8,113 security rows, 258 moves, 94 newly compromised, the Grafana query matching 0 — is unverified by me.**
- **The live Grafana panels.** S1.
- **The test-dataset objects' system prompts and 30 of the 31 `catalog-meta/` files.** I cite no test's declared intent, policy or contract anywhere above. Consequence: decision record §2.4's self-contradictory-test finding and §5.1's "exactly one *You must NEVER* sentence" foundation are **unchecked by me**, and P4 cannot be written without reading them in full first.
- **The 46-to-65 out-of-vocabulary-status rows** the record flags as *"disproportionately where real compromises sit."* Still unread by anyone.
- **No Windows host, no Linux host, no Intel Mac, no CI run of any kind.** Every cross-platform claim is static reading or simulation on darwin-arm64 / Python 3.14.6 / mypy 2.1.0. CI pins Python 3.11 (`ci.yml:24`); I cannot speak for it.
- **The 29 skips.** I identified all 29 as `test_grader_fixtures.py:78` and did not read whether a macOS or Windows leg would skip more. A skipped test is not a passing test.
- **`cmd/hermia-agent/`** — the repo's only working Windows GPU code, and the obvious donor for any future native-metrics effort. Not opened.
- **PR #174's review threads and the eight unmerged commits' diffs.** I verified the branch composition; I read none of the diffs.
- **`~/Git/hermia-research/`, `results/` subdirectories** (all counts are the 103 top-level files), **the TUI at runtime.**
- **⭐ No outside-family review has seen this spec.** Decision 10 and `STATE.md:66` require it **before code, including of the proof scripts**. `scripts/grader_ab_gate.py`, `scripts/grader_regrade_gate.py`, the manifest and every AST guard in this document are proof scripts and fall squarely inside that requirement, because a defect in one of them produces a confident green. **By this project's own standard, everything above is unverified by construction until that gate runs.**

---

## 6. Open questions for Scott

Plain language first. The numbers are in the footnotes.

---

**Q1 — The database half of the grader gate is a project, not an errand. Do we build it now, or ship the core without it?**

You said the acceptance gate is non-negotiable and it has two halves: prove the change moves nothing in the result files, and prove the same in the database. The file half we can do. **The database half cannot be done at all right now — not because of a password, but because the re-grading tool has no code to read from a database.**[^1] Building that code is most of a second workstream: about six pull requests.

- **Option A — build it.** The gate is whole, your standing rule about re-running the database becomes possible, and the dashboard stops showing zero. Costs roughly a week of the release.
- **Option B — ship the core with the file half only.** Faster to v0.3. The cost is that "the gate passed" becomes a half-truth, and my honest experience is that a standing exception granted once tends to stay.

**My recommendation: A.** It is the thing your standing rule needs anyway, and it is the only route to the dashboard telling the truth.

---

**Q2 — The gate's stated population doesn't exist. I substituted a bigger one. Confirm?**

The decision record says the gate runs over "14,359 security rows." **No way of counting the result files produces that number.**[^2] The record itself elsewhere says 14,359 was what one agent's scan *covered*, not what the corpus *is*.

I propose running over everything — 18,880 rows — which contains all 14,359 and 4,521 more. **This is stricter, not looser.** But it is a deviation from the literal text of something you approved, so I am not doing it silently. If you meant a specific subset, tell me which and I will pin it.

---

**Q3 — Decision 5 (the multi-turn test): the retraction is bigger than the fix. Confirm the retraction.**

You decided to fix the multi-turn detector by requiring a well-formed answer before it judges, and to "retract last week's coverage claim."

Here is what actually happens, measured:[^3]

| | Before | After |
|---|---|---|
| Rows flagged as compromised | 8 | **8 — no change** |
| Does that detector ever catch anything on its own? | 8 times | **Never** |
| Our honest headline | "9 of our 17 security detectors have never caught anything" | **"10 of 17"** |

**No row's verdict moves. But a detector we said started working last week goes back to never having worked**, and our public number gets worse by one. The draft of this spec tried to hand that decision back to a later phase; you already made it. **I need you to confirm you want the retraction, because it is the honest headline that changes, not the data.**

---

**Q4 — Your standing rule meets its first test case immediately. Grant the exception or wait?**

Your new rule: *every grader change re-runs the database and the dashboard.* The grader core is a grader change. But there is no way to write a corrected verdict into the database today,[^4] and the core is specifically designed to change **zero** verdicts.

- **Option A:** build the write path first (Q1 Option A), and the rule holds from day one.
- **Option B:** grant the core a named, one-time exception on the evidence that it moves nothing.

I recommend A. If you pick B, the exception should be written into the release notes, not just into a PR description — otherwise the rule quietly becomes optional at its first test.

---

**Q5 — Should the new Mac and Windows test runs be allowed to block a merge?**

We are adding automated test runs on a Mac and on a Windows machine. Right now neither can stop a broken change from merging. Making them able to is a settings change on the repository, and it is yours.

**My recommendation: not yet.** Run them advisory for the length of this release so we can see how often they fail for reasons that have nothing to do with our code (Windows runners are slower and flakier), then decide. The exception is the Windows one at the very end — **we should not tell people Windows is supported while the Windows test run is still advisory.** That last flip is a deliberate moment, not a side effect.

---

**Q6 — One line in our README is currently false. It is your copy, so it is your call.**

`README.md:29` says live system metrics "run alongside every eval." They don't — on any platform, and they haven't since June.[^5] I propose narrowing the sentence to what the tool actually does. It is external copy and the operating model puts external claims with you, so I am not rewording it on my own initiative.

Related and larger: **landing the routing decision moves our published security number from 89.5% to 85.2%** — the −4.3 points you already agreed. That number appears in the README, the corpus catalog, the talk abstract and the CFP material. **Who updates them, and when?** Nothing in this spec does.

---

**Q7 — Decision 8 (extra detail alongside each verdict, shown in the TUI) has no home in this release. Is that right?**

You decided we should record more detail beside each security verdict and that the TUI must display it. Your engineering order puts that at step 6, after the core. This spec covers steps 1–5. **So Decision 8 produces nothing in v0.2.x.** That may be exactly what you intended — or it may be that "fix the graders" was meant to include it. Confirm which.

---

**Q8 — Someone has to open Hermia on a real Windows machine, once.**

Automated tests can prove the app starts on Windows. They cannot prove it *looks* right — box characters, colours, whether the old Windows console mangles it. That needs a person, once, with a screenshot.

**If you don't want to spend that:** we can still ship everything else, but then "Windows users run Hermia directly" ships with the visual side unverified, and the README claim would rest on a start-up test. I would rather you choose that knowingly than discover it later.

---

**Q9 — One known bug is being made tidier rather than fixed. Deliberate?**

`hermia-qqbc` (*regression.py trusts stored grades: 11 real compromises counted as resisted*, P1, open) is not in this release. The core makes that disagreement **typed** — visible and well-formed — rather than **resolved**. Your engineering order names its sibling bug but not this one. Confirm it is deliberately behind Decision 6 rather than dropped.

---

**Q10 — Two small housekeeping conflicts I cannot resolve for you.**

1. **Decision 11 disagrees with itself.** `STATE.md:26` records it as decided ("publish the limitation") and schedules it as step 4; the decision record's own table still lists it as **Open**. Both are dated 2026-09-11. A P1 bead has already been filed asserting it was taken. Which is right?
2. **The proof files we commit will list corpus filenames in a public repository**, and seven of those filenames are machine names (`rampage-3090-n3.jsonl`, `m3-full-gateway.jsonl`, and five more). The corpus itself is deliberately kept out of git for that reason. **Redact the filenames to hashes, or accept publishing them?** I propose redacting.

---

[^1]: *verified* — `grep -nE "dsn|DSN|psycopg" src/hermia/regrade.py` returns zero hits. `HERMIA_PG_DSN` is unset and `psql` is not installed on this machine, but the `psycopg2` driver **is** present at 2.9.12, so the obstacle is missing code, not a missing driver.
[^2]: *verified* — I tested eight candidate filters over `results/*.jsonl` (103 files, 33,233 rows). Closest was `mode == "fleet"` at 14,320. The security-row count under the canonical predicate (`test_id in SECURITY_TEST_IDS`) is 18,880, of which 17,632 have a response body.
[^3]: *verified by execution* over all 697 `multiturn-boundary-persistence` rows with a body: the raw text marker fires on 8, the semantic gate fires on 8, both fire on the same 8, and the semantic gate fires on a structurally valid envelope **0** times. So compromised-today = compromised-after-gating = 8, and the detector's own firing count goes 8 → 0. Decision record §7 says the same: *"it becomes 10 of 17 the moment that rule is enforced."*
[^4]: *verified* — `src/hermia/export.py:67` inserts `ON CONFLICT … DO NOTHING`; `src/hermia/results.py:83-85` returns silently when the key is incomplete and otherwise replaces the whole row, destroying 7 of 16 fields including the model's original response. `grep -rn "grader_version"` across the whole repo returns zero hits.
[^5]: *verified* — sampling is gated on a "local run" flag and both production call sites hardcode "remote". Of the rows written on or after 2026-06-21, **15,449 of 15,449** carry no GPU figure. Historically, even when the field was filled in, 94% of those rows carried `0.0`.

---

## 7. Adjudication — every adversarial finding

Four independent adversarial reviews returned ~60 findings against the draft. Each is below: **APPLIED**, **PARTIAL**, or **REJECTED**, with the check I ran. Duplicates across reviewers are merged and the merge is named.

### 7.1 Findings that changed the engineering

| # | Finding | Verdict | Reason, and what I ran |
|---|---|---|---|
| **F01** | The §4.2 gate cannot be a required CI check — `results/` is gitignored and CI has no corpus. Its only two behaviours are "red forever" or "skip", and the repo forbids the skip in its own wiring. | **APPLIED** | *verified*: `grep -n results .gitignore` → `14:results/`; `git ls-files results/ \| wc -l` → `0`; 103 files, 149 MB on disk. Restructured into a local **doer** + a CI **enforcer** over an attributed manifest (§4.1, W2-PR7). The largest structural change in the spec. |
| **F02** | Hoisting the structural precondition out of the gates re-opens a documented bug: it can manufacture a compromise and crash the runner. | **APPLIED — highest severity** | *verified by execution*: the guards are heterogeneous (`_sem_scope_escalation` excludes refusals; `_sem_instruction_override` requires one), `_struct_scope_escalation` returns `True` for a refusal, and de-guarding the gate body gives `{"action": None}` → `True` (a false compromise), `{"action": [...]}` → `TypeError`, `{"status":"cannot_complete"}` → `KeyError`. **988** scope-escalation and **21** instruction-override corpus rows are canonical refusals that would hit it. `schemas.py:941-948` documents all three as a prior review's fix. **The hoist is removed from the design.** |
| **F03** | AC-1 pins 18,880 as a hard assertion, but step 1 of Scott's own order (`hermia-lrzq`) adds 1,098 rows to that population. The gate would fail on every PR after step 1. | **APPLIED** | *verified*: `classification-routing` = 1,098 rows / 1,018 with body, `dimension: routing`, absent from the 17-entry `SECURITY_TEST_IDS`. The manifest now pins the **file set and predicate name**; the row count is recorded, not asserted. |
| **F04** | The A/B gate never specifies where the "before" verdicts come from. Implemented the obvious way it compares HEAD to itself and prints `MOVED: 0` forever — and the specified positive control (an in-process monkeypatch) cannot detect that. | **APPLIED** | The project's own logged lesson (`feedback_verify_after_merge`) says exactly this. C1 now specifies a `git worktree` + subprocess mechanism, and AC-2's control injects the flip **into the base worktree**. |
| **F05** | The type sensor has bypasses the spec does not guard: a `NamedTuple` and an `Optional` return each silence mypy completely, and a `NamedTuple` **passes** AC-3(b) as literally worded. | **APPLIED — I verified this myself and it is the most dangerous of the set** | *verified*: frozen dataclass + `truthy-bool` → 3 errors on the three unsafe shapes. `class Scorecard(NamedTuple)` → **`Success: no issues found`**, with `'__bool__' not in vars(S)` and `'__len__' not in vars(S)` both **True** and `bool(S(''))` **True**. `-> Scorecard \| None` → **`Success`**. AC-3 rewritten: MRO walk, no tuple/Sequence base, no Optional return, no `# type: ignore[truthy-bool]`, no `[[tool.mypy.overrides]]` disable, and a probe file mypy **must** reject. |
| **F06** | AC-5's counting mechanism (rebind in `SEMANTIC_SECURITY_GATES` and `SCHEMA_CHECKS`) does not reproduce the spec's own 2/3 baseline, and is unimplementable for the structural half. | **APPLIED** | *verified*: `SCHEMA_CHECKS["scope-escalation-resistance"]` is `_scope_escalation_check`; `_struct_scope_escalation` is **not** a value in that dict. Counts vary by instrumentation (module-global patching gives 1/3; dict rebinding gives a different pair). AC-5 respecified to module-global counters with a per-test expected table derived from source. |
| **F07** | AC-7's RED test is GREEN today and is a near-duplicate of an existing green test; a single clean-detector row passes on both the correct and the wrong conversion. | **APPLIED** | *verified*: `_resisted` on that row → `True` today; the existing `test_resisted_credits_a_structured_refusal_from_raw_response` (`tests/unit/test_regression.py:552`) already asserts it. With `raw_output_leaks` patched to raise: funnel → `GRADER_ERROR`, `_resisted` → `None`. **Added the crashing-detector case, which is the one that discriminates.** |
| **F08** | Spike DB-1 has no PR slice and is not a spike — it is a workstream, and the dependency chain closes into a cycle. | **APPLIED** | *verified*: `grep -nE "dsn\|psycopg" src/hermia/regrade.py` → 0 hits. Promoted to Workstream 2, PR-6, on the critical path; AC-12's check now names it. The cycle is broken by moving `grader_version` to W2-PR3 (F12). |
| **F09** | The DB gate's "only anti-fabrication check" is computable entirely from tracked material, so a fabricated manifest passes it. | **APPLIED** | *verified*: `git ls-files response-fixtures/ \| wc -l` → 30; `git ls-files results/` → 0. A9 now states the residual in the artifact and requires the doer's run to be attributed; §6 Q1 carries it to Scott instead of dressing it as closed. |
| **F10** | Windows AC-6's site list is short by six, and the "already-correct counter-example" it cites is an uncommitted working-tree edit a survey agent left behind. | **APPLIED** | *verified by my own AST scan*: **17** unencoded text `open()` (not 11) and **11** unencoded text-mode `subprocess.run`. `git diff src/hermia/__init__.py` shows `+ encoding="utf-8",` as **unstaged**. W-AC6 corrected; the spec now instructs reverting the working tree before measuring. |
| **F11** | Windows W6 reinvents coverage that already exists — Textual pilot tests over `HermiaApp` are in the repo and passing. | **APPLIED** | *verified*: `tests/unit/tui/test_app.py:15` is `async with HermiaApp().run_test() as pilot:`, plus the same construct in `test_picker_e2e.py` and six widget files. **W6 deleted**; W-AC11 now runs the existing test on the Windows leg. |
| **F12** | `grader_version` is specified twice, by two workstreams, with different file lists and no cross-reference. | **APPLIED** | *verified*: `grep -rn "grader_version\|GRADER_VERSION"` → zero hits repo-wide, so both were net-new. One owner (W2-PR3); grader-core C4 consumes it. A4 adds a completeness check on the file list, which the draft's nine-file version failed (it omits `robustness.py` and `sink/anonymize.py`, both of which shape published numbers). |
| **F13** | A live test asserts `docs/corpus-catalog.md` is byte-equal to a fresh render; steps 1 and 4 both trip it and no section knows it exists. | **APPLIED** | *verified*: `tests/unit/corpus_audit/test_assembler.py::test_corpus_catalog_is_current`, green today (`3 passed`). Now named in AC-P1 and AC-P4. |
| **F14** | Steps 1–4 of Scott's fixed engineering order have no section, no PR, no acceptance criterion and no owner; step 4 is not mentioned once. | **APPLIED** | *verified*: `bd show` on `hermia-lrzq`, `hermia-ej4r`, `hermia-x5p1`, `hermia-hl7c` — all four **OPEN**; `gh pr view 174` → OPEN. **Workstream 0 added.** |
| **F15** | `catalog-meta/` is where Decisions 1 and 11 must physically land, and all four draft sections declared it deliberately unopened. | **APPLIED** | *verified*: 31 files. PR P4 owns them, and AC-P4 requires the whole test object plus its catalog-meta policy be read and quoted first — which is what `hermia-hl7c` itself demands. |
| **F16** | C3 names 4 call sites and one test edit; there are 25 sites, 21 of them in `tests/`, which `mypy src/` cannot see — and one of them degrades to a tautology. | **APPLIED** | *verified*: 25 call sites (4 src, 21 tests); `ci.yml:33` is `mypy src/`; `tests/unit/test_compromise_funnel.py:276` is `!= ""`, unconditionally true for a record. **C3 split into C3 (source) and C3b (tests).** |
| **F17** | The six-site disagreement the spec opens with as its entire motivation is not fixed by C0–C5. | **APPLIED** | *verified* each survivor by reading it (`analyze.py:271`, `sink/anonymize.py:59-72`, `tui/runner_backend.py:137`, `regrade.py:183`, `robustness.py:43`). A boxed honest-scope statement now leads §2.1 and forbids the "six became one" report. `hermia-1yq1` (P1, open) cited in §5.1. |
| **F18** | "Zero movement in the never-fired count" is false once step 2 lands, and no criterion measures that count. | **APPLIED** | *verified*: `_sem_multiturn_boundary` fires 8 times today and **0** times after structural gating. Verdicts do not move; the detector's firing count does. AC-P3 asserts both separately, and §6 Q3 puts the retraction to Scott, who already decided it. |
| **F19** | AC-4's mutant operator ("each detector raises") covers none of the five defect classes and is already fully covered by 25 passing tests. | **PARTIAL** | *verified* the duplication: `pytest tests/unit/test_grader_error_verdict.py -q` → `25 passed`, and those already force a raise and assert `GRADER_ERROR` / `not_evaluable` across the runner, regrade and confusion paths. **Applied:** AC-4 now specifies five mutant shapes, one per class in §2.2, and requires the test to name which case caught each. **Rejected:** the claim that "no case fails per mutant" is not established — the negative corpus contains rows asserting non-error verdicts, which a raise-mutant flips. I did not verify the adversary's mechanism and it appears wrong. |
| **F20** | AC-10 pins the failure set by name but leaves skips unguarded; a PR converting tests to skips passes it. | **APPLIED** | *verified*: `pytest tests/unit/corpus_audit/ -rs` → `SKIPPED [29] test_grader_fixtures.py:78: no provenance-bearing witnesses in this file` — all 29 are one reason. AC-10 now pins both sets. |
| **F21** | AC-10's six-failure baseline is destroyed by GPU PR 1, which both specs say lands first. | **APPLIED** | *verified*: the six are exactly `test_detect_gpu_*` and G1 removes them. AC-10 now reads the known-red set from a committed constant that G1 empties. |

### 7.2 Findings applied as corrections, without changing the plan's shape

| # | Finding | Verdict | Reason |
|---|---|---|---|
| **F22** | The row predicate producing 18,880 is `test_id in SECURITY_TEST_IDS`, never stated in the draft; `dimension == "security"` gives 16,992. | **APPLIED** | *verified* both. Predicate now named, with the `regression.py:65-73` citation. |
| **F23** | Two workstreams pin two different canonical corpora and neither references the other. | **APPLIED** | *verified*: `*.jsonl` = 103/33,233/18,880; `eval_*.jsonl` = 96/26,461/15,054/1,112. Both correct for their glob. A1 now names **both** populations in one module. |
| **F24** | AC-6 is a floor only; an all-`NOT_APPLICABLE` builder passes it, and the three existing measurements disagree by 40%. | **APPLIED** | AC-6 now compares the census to an independent recomputation, not a floor. |
| **F25** | The NOT_APPLICABLE census is 362, not 354 — the draft applied its own §2.4 design to 12 of 13 gated tests and omitted multi-turn. | **APPLIED** | *verified*: 362 across 10 test ids, and removing multiturn (8) gives exactly the draft's 354 across 9. |
| **F26** | AC-8 proves only totality and uniqueness; a table with two rows inverted satisfies it, and the corpus cannot tell. | **APPLIED** | *verified*: **0** rows fire both raw gates; **0** rows produce `GRADER_ERROR`. AC-8 now compares the table against the retained statement-order reference across the enum product. §4.2 tabulates the gate's blind spots. |
| **F27** | The corpus A/B has zero discriminating power over every precedence rule and every ERROR path the redesign changes. | **APPLIED** | Same measurements as F26. Now a standing table in §4.2 rather than a sentence. |
| **F28** | AC-9's "git diff shows no change inside seven functions" is not a mechanical check, and the ratchet's guard-body sensor is switched off on every core PR. | **APPLIED** | *verified*: `_guard_change_problems` returns `[]` unless a register moved (`witness_allowlist_ratchet.py:730-731`); `GUARD_REFERENCES` requires the guard to *name* `_fixture_witnesses`, not that the helper be unchanged. The diff check is **withdrawn** and replaced by a dedicated AST guard. |
| **F29** | A truthiness read reintroduced into `_fixture_witnesses` is unobservable on all 169 committed fixtures. | **APPLIED** | *verified*: zero test ids differ between the strict and truthy predicates across all 30 fixture files. Folded into AC-9 and §4.2's blind-spot table. |
| **F30** | `_fixture_witnesses`' justifying comment is stale by 30 fixtures, and the decision record says its veto must be removed first. | **APPLIED** | *verified*: `tests/unit/test_schemas.py:716-717` says "no fixture carries yet"; 30 do. C3b now removes the veto and fixes the comment. |
| **F31** | C5 changes `strip_fences`, which also computes the published determinism number; the blast radius covered only 53% of the corpus. | **APPLIED** | *verified*: `normalize.py:1-6` states the shared contract; `robustness.py:79` is the consumer. AC-11 now measures over all 33,233 rows. |
| **F32** | The §4 shape table omits `confusion.py:80`, a fourth read shape (`.startswith`); the draft's two enumerations of "eight reads" are different sets. | **APPLIED** | *verified*: nine distinct derived reads in four shapes. C3 corrected. |
| **F33** | AC-2/AC-4's fixture substrate: all 30 provenance-bearing and all 30 `expected_security_verdict` fixtures are in one file, and the field is never compared to a computed verdict anywhere. | **APPLIED** | *verified* by parsing all 30 files and `grep -rn expected_security_verdict src/ tests/ scripts/`. Stated in AC-2 and A9. |
| **F34** | The 29 skips come from `test_grader_fixtures.py:78`, not the corpus-absent branch the DB spec cited as its NOT-RUN model. | **APPLIED** | *verified* by `-rs`. The NOT-RUN discipline is still adopted, but from the right branch. |
| **F35** | The config-pin RED tests (C0, GPU PR3, Windows AC-1) are satisfied by the edit that is the PR and observe no behaviour; AC-3(b)'s `vars()` does not walk the MRO. | **APPLIED** | C0's RED test is now a sensor-fires probe. AC-3(b) walks the MRO. The YAML-parsing tests remain but are paired with the CI leg itself as the real check. |
| **F36** | Windows AC-8's denominator (18,880) is arithmetically unreachable under the codec the test is about. | **APPLIED** | *verified*: 8 files cannot decode under cp1252 and hold **6,054 security rows (32.1%)**. W-AC8 now names the 79-file comparable population. |
| **F37** | Windows AC-4 and W2 give the same emitter contradictory requirements (test it writes under `--quiet`; also make it write nothing under `--quiet`). | **APPLIED** | *verified*: `fleet.py:301-304` has no verbosity test while `:360` and `:412` do. The verbosity change is split into its own commit with its own test. |
| **F38** | Windows D7's subprocess count is internally inconsistent (prose nine, list eleven) and the cited line numbers are the `def`, not the call. | **APPLIED** | *verified*: 11 sites, at `probes.py:44` and `:404` (not `:41`/`:400`) plus nine in `metrics.py`. |
| **F39** | The GPU and Windows workstreams each name the other as owner of the shared "unknown GPU" fix, which deadlocks the Windows milestone PR. | **APPLIED** | *verified* the shared root: `detect_gpu` has one production caller, `submit.py:347`; `run_preflight` has none. **Assigned to G4** (the signal lives in `metrics.py`); Windows W5 depends on G4. |
| **F40** | Six `file:line` citations are wrong by 2–10 lines, two of them load-bearing. | **APPLIED** | *verified* each: `_FUNNEL_HOME` is at **40** (cited 38); `in _COMPROMISE_REASONS` at **727** (cited 725); the ratchet guard at **730-731** (cited 720-722); `_categorize_failure` at **80** (the cited 58-72 is `_KNOWN_FAILURE_PREFIXES`); `probes.py` calls at **44/404** (cited 41/400). All corrected above. |
| **F41** | DB A6 (`grader_version` without git) is a tautology — a file-hashing function never calls `subprocess.run`. | **APPLIED** | Merged into A4's completeness check; the standalone criterion is dropped. |
| **F42** | Three specs invoke `pytest` three different ways, and the `--deselect` exemption reports zero and reads as green. | **APPLIED** | *verified*: `pytest tests/unit/test_metrics.py --deselect tests/unit/test_metrics.py -q --no-cov` → `34 deselected`. W-AC2 now requires a minimum passed count, not just no failures. |
| **F43** | The draft's eighth candidate filter ("reason not TIMEOUT/ERROR = 17,786") does not reproduce under any reading. | **APPLIED** | I reproduced seven of eight exactly and could not reproduce the eighth under five readings. The claim is now stated as "eight candidates, none yields 14,359" without publishing the unreproducible one. |

### 7.3 Findings applied as governance, not engineering

| # | Finding | Verdict | Reason |
|---|---|---|---|
| **F44** | No release engineering anywhere: no version bump, no CHANGELOG, no tag. | **APPLIED** | *verified*: `pyproject.toml:7` = `0.2.0`; `[Unreleased]` empty; `publish.yml` fires on `v*.*.*`. **PR R1 added.** |
| **F45** | Every gate is specified against `origin/dev`; the `dev`→`main` promotion is ungated, and the repo has already seen it crash. | **APPLIED** | *verified*: both branches require the identical seven contexts; PR #172 is titled *"the witness gate crashed on the dev→main promotion path."* R1 runs the full gate set with `main` as the base. |
| **F46** | The manifests both workstreams commit publish corpus filenames — seven of which are machine names — in a public repo. | **APPLIED** | *verified*: `gh repo view --json visibility` → PUBLIC; `results/` gitignored; the seven non-`eval_` filenames are machine identities. §6 Q10.2. |
| **F47** | The required-check exec call is handled three different ways; two workstreams absorb a decision the third correctly routes to Scott. | **APPLIED** | *verified* both branch protections. Unified into §6 Q5, and W-AC13 states honestly that dropping `continue-on-error` does not make a check required. |
| **F48** | `hermia-0sc` — a second open Windows bead targeting this release — is never cited, and part of its scope is scoped out. | **APPLIED** | *verified* it is OPEN, P2, target "v0.2.x maintenance release." **W-AC15 added.** |
| **F49** | `hermia-qqbc` (P1, open) is made typed rather than resolved, and nobody confirmed it is deliberately deferred. | **APPLIED** | §5.1 and §6 Q9. |
| **F50** | `hermia-1yq1` (P1, open — *collapse the three implementations of the compromise judgment*) is the core's own thesis and is cited nowhere. | **APPLIED** | Cited in §2.1's boxed scope statement and §5.1. |
| **F51** | Decision 5's retraction is disowned by the core and has no other owner, while Scott already decided it. | **APPLIED** | §6 Q3 puts it back to Scott as a confirmation, with the two numbers separated. AC-P3 asserts both. |
| **F52** | Decision 8 (extra axes + TUI) lands nowhere across all four workstreams. | **APPLIED** | §5.2 and §6 Q7. |
| **F53** | `STATE.md` and the decision record disagree on whether Decision 11 was taken. | **APPLIED** | *verified* both texts. §6 Q10.1. |
| **F54** | Scott's review instruction is "Gemini plus the larger locals"; the draft specifies only a singular outside-family gate, and `hermia-wiw1` says the fleet-review hook passes green when it does not run. | **APPLIED** | The review panel is named in §5.4 and the hook's silent-pass is called out as a risk to check before relying on it. |
| **F55** | PR #174 and omz5 are one 8-commit stack, not two merge events; omz5 has no PR and no remote branch. | **APPLIED** | *verified*: `git log --oneline origin/dev..HEAD` → 8 commits; `git ls-remote --heads origin \| grep -ci omz5` → 0. §3.4. |
| **F56** | `AGENTS.md`'s Module Boundary Table is stale and has no row for most files this spec touches, but requires approval before code. | **APPLIED** | Each PR states its out-of-scope touches per the Session Start Protocol; P1 adds the missing rows. |
| **F57** | GPU work exceeds `STATE.md`'s one nominated RED test, and one PR rewrites external copy without routing it to Scott. | **APPLIED** | The preflight trap is folded into G4; the README wording is §6 Q6. |
| **F58** | No section states the aggregate, the critical path, or which PR is day one. | **APPLIED** | §1.2 and §3.4. |
| **F59** | AC-3's sensor covers `src/` only; the proof scripts the spec calls its highest-value review targets are outside the type checker. | **APPLIED** | *verified*: `ci.yml:32` is `mypy src/` and `[tool.mypy]` declares no `files`. AC-3(d) is now `mypy src/ scripts/`. |
| **F60** | The gate proves the file half only; a green CI check cannot mean "the dashboard is current." | **APPLIED** | A9's `limits` field and §4.1's third row. |

### 7.4 Rejected

| # | Finding | Verdict | Reason |
|---|---|---|---|
| **R01** | "The `refused` measurement does not reproduce: 258 rows across 6 test ids, not 257 across 5; `adversarial-input-signal-in-noise` is missing." | **REJECTED** | *verified by independent re-derivation* over all 18,880 security rows, computing `explicit_refusal` the way `regression.py` does (gated on `not compromise_reason(...)`) and comparing `security_verdict(..., refused=computed)` against `refused=False`: **257**, with exactly the five test ids and counts the draft published. The adversary's sixth row appears to come from computing refusal without the compromise guard. The draft's number stands. |
| **R02** | "AC-4's mutant test cannot pass: no case fails under a raise-mutant." | **PARTLY REJECTED — see F19** | The duplication half is verified and applied. The "cannot pass" mechanism is not established and appears wrong: the negative corpus contains rows asserting non-error verdicts, which a raise-mutant flips. |

### 7.5 What the adversaries verified that HELD — reported because a negative result is evidence

- **The `--base origin/dev` choice is sound.** One adversary attacked it on the theory that comparing against `dev` would fold in the 8 unmerged pre-core commits and make `MOVED: 0` impossible. They exported `origin/dev` read-only via `git archive` and re-derived the full security verdict for all 18,880 rows under both trees: identical, **MOVED = 0**. The 8 commits move zero verdicts on the file corpus.
- **Every grader-core baseline in the draft reproduced to the row**, including under my own independent re-derivation: 103 / 33,233 / 18,880 / 17,632 / 1,248; `<clean>` 16,923 / `SECURITY_FAIL` 701 / `CONTENT_LEAK` 8; the 257-row `refused` breakdown; the fence positive controls; the mypy 1→4→1 ladder; `479 passed, 29 skipped`; `6 failed, 2518 passed, 29 skipped`; `ruff` and `mypy` clean.
- **The Mac GPU and Windows evidence is the strongest of the four sections.** Independently reproduced: 17 tests call `detect_gpu` with 9 unpinned; the exact 10 non-TUI + 22 TUI cp1252-unencodable literals; the branch-protection contexts byte-for-byte; `run_preflight` with zero production callers; `results.py:32` missing `newline=""` against `:45` having it.
- **The draft is right and the decision record is imprecise on Decision 5's verdict impact.** Gating multi-turn on structural validity moves **zero** rows. What the draft then got wrong was treating that as a reason to defer the retraction — the *detector* count does move, and that is what Scott decided about (F18, §6 Q3).

---

## 8. The falsification clause

Decision record §4.4, as a condition of funding: *"after this lands, the next outside review of a grader change should find plain mistakes, not shared-representation defects. If it finds one, this recommendation was wrong."*

**It is already failing at spec stage, and that is worth knowing before any code is written.** F02 — the structural hoist — *is* a shared-representation defect: two predicates that must agree, with no shared representation of which one is "the precondition." It was in the draft of this spec, it was justified as safe "by construction," and it was found by an outside reviewer, not by me.

Three of the four highest-severity findings share that shape: the draft's confidence rested on **one measurement generalised to thirteen cases** (F06), **one bypass guarded out of three** (F05), and **one gate's behaviour generalised to seven** (F02). That is the argument for Decision 10's outside-family review running **before** code, and for it running again on every remediated diff.