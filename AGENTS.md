# AGENTS.md — Hermia Behavioral Guardrails

Hermia is an open-source LLM security eval TUI (Python/textual) that runs structured
agentic test cases against local Ollama models and scores them against OWASP LLM Top 10,
MITRE ATLAS, CSA MAESTRO, and NIST AI RMF. All contributions — human or AI — are held
to the same standards below.

Session Start and Close protocols live in `CLAUDE.md` and are auto-read by Claude Code.

---

## NEVER DO (Hard Rules)

These are grounded in actual git history. Violations have caused real rework.

1. **Never use exact-match key sets in schema validators.**
   Always use the `_keys_ok()` helper already established in `schemas.py`.
   Reasoning models (o-series, QwQ, DeepSeek-R1) return extra keys like
   `thinking`, `reasoning_content`, or `scratchpad` that are benign. Strict
   matching fails all reasoning model responses.
   *(Commits: d2903fc, 4269d25, f5fc788)*

2. **Never add a dependency without explicit user approval.**
   `pyproject.toml` is the canonical dependency list. Propose the library and
   wait for approval before writing any code that uses it. stdlib-only solutions
   are always preferred.

3. **Never claim a task is complete because CI is green.**
   CI passing is necessary but not sufficient. The full review gate sequence
   must complete (see below).

4. **Never test only the Python function when a CLI entrypoint exists.**
   If a module has an entry in `[project.scripts]` in `pyproject.toml`, the CLI
   invocation path must be tested directly — not just the internal function.
   *(Commit: 006e621)*

5. **Never touch files outside the task's permitted module scope in a single commit.**
   If a fix genuinely requires touching an unrelated module, stop, flag it, and
   get explicit approval before proceeding.

6. **Never iterate blindly on a failing fix.**
   If a fix requires more than one attempt, stop and re-spec before trying again.
   *(Evidence: fix/reasoning-model-extra-keys and fix/reasoning-model-extra-keys-v2
   both exist in history.)*

7. **Never assume Gemini re-review auto-triggers after a push.**
   It does not. After pushing fixes to an open PR, immediately post `/gemini review`
   as a PR comment. Do not proceed with other work until this is done.

8. **Never write CI/workflow jobs with assumed permissions.**
   Each job's permissions must be explicitly and minimally scoped. Verify job
   output confirms correct behavior — not just that the workflow ran.
   *(Commit: b9f1ff0)*

---

## ALWAYS DO (Required Behaviors)

### Before Writing Code
- Agree on the approach with the user before implementation. Produce a brief
  written spec or plan and get confirmation. Do not freestyle.
- For any task involving a new schema checker, confirm `_keys_ok()` pattern
  applies before writing any validation logic.
- If a task seems to require a new library, say so immediately and wait for
  approval. Do not write code that imports an unapproved library.

### While Writing Code
- Keep changes surgical. Smallest possible diff to achieve the goal.
- Commit message format: `type(scope): description`
  Examples: `fix(schemas): ...`, `feat(runner): ...`, `ci(security): ...`
- If touching a module outside permitted scope is necessary, flag it before
  doing it.
- Prefer refactor-after pattern: generate working code first, then in a
  separate explicit step refactor for elegance, readability, and minimalism.

### After Writing Code
- Run all tests and show actual output. Do not summarize — show the terminal.
- If any previously passing test now fails, stop immediately and flag it before
  doing anything else.
- Check for debug cruft: temp files, log statements, test branches, commented-out
  code. Clean it up or flag it explicitly.

### At Session End
See Session Close Protocol in `CLAUDE.md`. Primary path: `bd note` on the active
bead. Fallback: `session-notes/YYYY-MM-DD.md` (gitignored).

---

## Module Boundary Table

AI must stay within permitted scope per task type. Touching off-limits files
requires explicit user approval before any code is written.

| Task Type                   | Permitted Files                                               | Off-Limits Without Approval          |
|-----------------------------|---------------------------------------------------------------|--------------------------------------|
| New eval test               | `test-datasets/agentic-tasks.json`, `src/hermia/schemas.py`  | `runner.py`, `app.py`, `screens.py`  |
| Schema checker fix          | `src/hermia/schemas.py`, `tests/unit/test_schemas.py`        | Everything else                      |
| Regression module           | `src/hermia/regression.py`, `tests/test_regression.py`       | Everything else                      |
| UI/TUI changes              | `src/hermia/screens.py`, `src/hermia/app.py`                 | Core eval logic                      |
| Metrics / system monitoring | `src/hermia/metrics.py`, `src/hermia/preflight.py`           | Everything else                      |
| Results handling            | `src/hermia/results.py`, `tests/unit/test_results.py`        | Everything else                      |
| Robustness module           | `src/hermia/robustness.py`, `tests/security/test_robustness.py` | Everything else                   |
| CI/workflow changes         | `.github/workflows/`                                         | `pyproject.toml` deps without approval |

---

## Review Gate Sequence

A task is not done until every applicable gate below is cleared, in order.

```
1. Pre-push hook passes
   └─ Sends diff to fleet coder-lane model via LiteLLM
   └─ Hard-blocks on CRITICAL findings
   └─ Internal infrastructure — requires LiteLLM fleet via Tailscale
   └─ External contributors: this gate is skipped; CI (step 2) is your first gate
   └─ Skippable with --no-verify only with explicit user decision

2. CI is green (ci.yml)
   └─ ruff + mypy + pytest on feature/fix branches and PRs

3. Security CI is green (security.yml)
   └─ gitleaks + trivy + bandit + pip-audit
   └─ Runs on PRs to main and weekly

4. Gemini Code Assist review completed
   └─ Required on every PR — do NOT merge without it
   └─ Does NOT auto-trigger on post-PR pushes
   └─ After any push to an open PR: post /gemini review as a PR comment immediately

5. Opus on-demand review (for complex or security-sensitive changes)
   └─ Triggered via /review slash command in Claude Code
   └─ Use for any change touching eval logic, schema validation, or CI/security workflows

DONE. Not before.
```

---

## Schema Validation Rules

- Always use `_keys_ok()` from `schemas.py` — never raw set comparison or exact key matching
- Schema checkers must tolerate extra keys from reasoning models
- When adding a new schema checker, include at least one test case with an extra key present
- If a schema check fails on a reasoning model response that is otherwise correct,
  that is a bug in the checker — not in the model response

---

## Issue Tracking

**Internal sessions:** Use Beads (`bd prime` for context, `bd ready` for available work).
Commit messages should reference bead IDs where applicable.

**External contributors:** Use GitHub Issues. Reference issue numbers in commit messages
and PR descriptions. The project maintainer will mirror significant issues into Beads
for internal tracking.

---

## For External Contributors

This project uses a layered security review pipeline. Before submitting a PR:

- Run `ruff`, `mypy`, and `pytest` locally and confirm they pass
- Do not add dependencies without opening a GitHub Issue to discuss first
- Schema validators must use the `_keys_ok()` pattern — see `schemas.py` for reference
- CLI entrypoints must be tested via direct CLI invocation, not just function calls
- PRs require Gemini Code Assist review before merge — maintainer will trigger this

Welcome to the project. The eval framework is intentionally adversarial. That's the point.
