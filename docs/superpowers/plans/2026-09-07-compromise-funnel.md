# hermia-rwe4 — one funnel for the compromise judgment

**Bead:** `hermia-rwe4` — compromise_reason is unreachable from runner.py, a fourth
divergent compromise judgment.

## The defect

Four modules decide "was this row compromised" and none of them share a code path:

| Module | How it decides | Reaches `compromise_reason`? |
|---|---|---|
| `runner.py` (PRODUCTION) | inline: raw gates + semantic gate, hand-rolled | **no** |
| `regrade.py` | inline: a near-copy of runner's block | **no** |
| `regression.py` | calls `compromise_reason` | yes |
| `corpus_audit/confusion.py` | `SCHEMA_CHECKS` only — no raw gates at all | **no** |

Consequence, demonstrated on PR #173: a detector added to `compromise_reason` is live in
the audit path and **dead in production**. Green unit tests, zero production effect.

## Measurement first (done before any code was written)

Run over all 6,300 rows of the 2026-07-23 sweep (`~/Git/hermia-research/eval-results/`):

```
security rows                   : 3570
  parsed as JSON                : 3452
  with a semantic gate           : 2630

positive controls (a 0 here would mean the limb never ran)
raw_output_leaks fired          : 0
raw_output_compromised fired    : 40
semantic gate invoked           : 2630
semantic gate returned True     : 25

THE DIVERGENCE UNDER TEST
schema_ok AND gate fires        : 0      <- unification is behaviour-preserving
confusion.py misses raw gate    : 6      <- real disagreement, real rows
```

Two things this buys:

1. **`schema_ok AND gate fires == 0`.** `compromise_reason` consults the semantic gate
   whenever `parsed is not None`; runner/regrade consult it only when the checker already
   failed. runner's comment claims these are equivalent "by construction" (SCHEMA_CHECKS is
   composed `structural and not semantic`). That claim now has evidence: 2,630 real gated
   rows, zero disagreements — with the gate proven live (25 True). Pointing runner at the
   funnel does not move a single real grade.
2. **`confusion.py` is wrong on 6 real rows.** Its docstring says it "faithfully mirrors
   runner.run_test's grading". It does not apply the raw gates, so a row whose body leaks
   outside the JSON fence is graded PASS there and FAIL in production. This is the fourth
   copy the bead names, now with evidence rather than suspicion.

`raw_output_leaks` firing 0/3570 is a real zero, not a harness bug (`raw_output_compromised`
fired 40 on the same text). It is a known instance of `hermia-11wb` — out of scope here.

## The change

1. `compromise_reason(test_id, raw, parsed) -> str` becomes **the** funnel. Signature and
   semantics unchanged; it already returns the exact precedence runner wants
   (`CONTENT_LEAK` > `SECURITY_FAIL` > `""`).
2. `runner.py` — parse first, then one funnel call. `_security_failure_reason` collapses to
   `compromise or structural`.
3. `regrade.py` — same restructure; drops its private copy.
4. `corpus_audit/confusion.py` — `grade_response` applies the funnel. **Changes 6 real rows
   from PASS to FAIL.** This is the bug fix, not a regression.
5. **The invariant:** an AST guard over `src/hermia/` asserting no module except
   `schemas.py` references `raw_output_leaks`, `raw_output_compromised`, or
   `SEMANTIC_SECURITY_GATES`. This is the test that FAILS when a fifth consumer starts a
   fifth copy. Without it this fix decays the moment someone adds a consumer.

## Explicitly NOT in scope

- The 9 never-firing detectors (`hermia-11wb`).
- PII/export detection (`hermia-zhrw`).
- runner's unguarded `checker(parsed)` call, which can propagate an exception and kill a
  run where regrade guards it. Noted, left alone, filed separately — changing it here would
  hide a behaviour change inside a refactor.

## Module scope

`AGENTS.md`'s boundary table has no row for a cross-cutting grader refactor. This touches
`schemas.py`, `runner.py`, `regrade.py`, `corpus_audit/confusion.py` and their tests. The
bead text names all four as the consumers that must stop disagreeing; that is the approval.
