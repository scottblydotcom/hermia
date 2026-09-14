# hermia-omz5 — a grader bug must never produce a clearance

**Bead:** `hermia-omz5` — a grader exception yields a false 'resisted' clearance in regrade.py.
**Stacks on:** PR #174 (`hermia-rwe4`, the compromise funnel). The code being fixed is the code
#174 restructured; branching off `dev` would mean patching a version that is about to change.

## The defect

`security_verdict` documents its own invariant: the refusal rescue is checked *after* the
compromise gate "so a refusal signal can never rescue a row that actually leaked." That
protects against a row we KNOW leaked. It does not protect against a row we know **nothing**
about.

When a schema checker raises, `regrade.py` catches it and sets `schema_ok = False` — which is
indistinguishable from a legitimate envelope failure. The row is stamped `SCHEMA_FAIL`,
`explicit_refusal` still returns True on the body, and the rescue fires:

```
checker raises      -> schema_ok = False
reason              -> "SCHEMA_FAIL"      (looks like an ordinary failure)
explicit_refusal    -> True
security_verdict(..., "SCHEMA_FAIL", refused=True) -> "resisted"
```

**A bug in our grader is reported as the model having defended itself.** On a security tool
that is the worst possible failure direction, and `schemas.py` elsewhere calls a false
clearance "the worst outcome this tool can produce".

Three modules, three behaviours for one event:

| Module | `checker(parsed)` raises |
|---|---|
| `regrade.py` | caught → SCHEMA_FAIL → **can become `resisted`** |
| `runner.py` | **unguarded — aborts the eval run** |
| `corpus_audit/confusion.py` | **unguarded — aborts the audit** |

## Measured first — this is LATENT, not active

Over the 3,567 security rows of the 2026-07-23 sweep that carry a raw response (3,452 parsed):

```
SCHEMA_CHECKS raised    : 0
SEMANTIC gate raised    : 0
explicit_refusal True   : 2,660   <- positive control, the harness ran
checker raised AND refusal (the clearance) : 0
```

**No real row has ever triggered this.** Stated plainly so nobody reads this fix as "we have
been clearing compromised models" — we have not, on this corpus.

It is still worth fixing, for reasons that do not depend on the count:
- It fails OPEN on a security tool. A latent fail-open is still a fail-open.
- The corpus is cooperative models answering benignly. The tool's entire purpose is grading
  *adversarial* output, which is exactly the input most likely to hit an unhandled shape.
- The crash half (runner, confusion) is the more likely of the two to bite, and it destroys a
  long eval run rather than one row.

## The change

1. **`GRADER_ERROR`** — a new `failure_reason` meaning *the grader could not decide*. Distinct
   from `SCHEMA_FAIL` (the model's envelope was wrong) precisely because conflating them is
   the bug.
2. **`security_verdict`** returns `not_evaluable` for it, checked **before** the refusal
   rescue. A refusal signal may rescue a malformed envelope; it may not rescue an unknown.
3. **`regrade.py`** stamps `GRADER_ERROR` on a checker exception. A real compromise still
   outranks it — evidence beats absence of evidence.
4. **`runner.py`** guards the checker and stamps `GRADER_ERROR` instead of aborting the run.
5. **`corpus_audit/confusion.py`** guards the checker and fails closed (False), matching how
   it already treats an unknown test id.

## Explicitly NOT in scope

- `analyze.py` carries a **SQL copy** of the compromise definition
  (`failure_reason IN ('CONTENT_LEAK','SECURITY_FAIL')`) and an infra-noise filter that
  excludes `TIMEOUT%`/`RETRY_EXHAUSTED%`. `GRADER_ERROR` is neither, so it will count as an
  ordinary failure row in analysis. Arguably it should be filtered as noise — that is a
  reporting decision, and a fifth copy of the compromise definition is its own bead.
- `hermia-qqbc` (regression.py trusts stored grades) and `hermia-jpf4` remain open.

## Module scope

`AGENTS.md`'s table has no row for a cross-cutting verdict change. Touches `schemas.py`,
`regrade.py`, `runner.py`, `corpus_audit/confusion.py` and their tests — the same four the
bead names.
