# AGENTS.md — Hermia Behavioral Guardrails

Hermia is an open-source LLM security eval TUI (Python/textual) that runs structured
agentic test cases against local Ollama models and scores them against OWASP LLM Top 10,
MITRE ATLAS, CSA MAESTRO, and NIST AI RMF. All contributions — human or AI — are held
to the same standards below.

Session Start and Close protocols live in `CLAUDE.md` and are auto-read by Claude Code.

---

## NEVER DO (Hard Rules)

These are grounded in actual git history. Violations have caused real rework.

1. **Never import a new library without validating it first.**
   Before writing any code that imports a package not already in `pyproject.toml`,
   run a web search against a reputable source (PyPI, official docs, GitHub) to confirm:
   (a) the package name is spelled correctly, (b) it is a real, maintained library,
   (c) it is not a hallucinated name or a typo-squatted variant of a legitimate package.
   Document the validation result in the session notes or PR description before proceeding. This rule exists because AI-assisted
   coding is a known vector for slopsquatting attacks — a plausible-sounding package name
   that resolves to a malicious or nonexistent package.

2. **Never use exact-match key sets in schema validators.**
   Always use the `_keys_ok()` helper already established in `schemas.py`.
   Reasoning models (o-series, QwQ, DeepSeek-R1) return extra keys like
   `thinking`, `reasoning_content`, or `scratchpad` that are benign. Strict
   matching fails all reasoning model responses.
   *(Commits: d2903fc, 4269d25, f5fc788)*

3. **Never add a dependency without explicit user approval.**
   `pyproject.toml` is the canonical dependency list. Propose the library and
   wait for approval before writing any code that uses it. stdlib-only solutions
   are always preferred.

4. **Never claim a task is complete because CI is green.**
   CI passing is necessary but not sufficient. The full review gate sequence
   must complete (see below).

5. **Never test only the Python function when a CLI entrypoint exists.**
   If a module has an entry in `[project.scripts]` in `pyproject.toml`, the CLI
   invocation path must be tested directly — not just the internal function.
   *(Commit: 006e621)*

6. **Never touch files outside the task's permitted module scope in a single commit.**
   If a fix genuinely requires touching an unrelated module, stop, flag it, and
   get explicit approval before proceeding.

7. **Never iterate blindly on a failing fix.**
   If a fix requires more than one attempt, stop and re-spec before trying again.
   *(Evidence: fix/reasoning-model-extra-keys and fix/reasoning-model-extra-keys-v2
   both exist in history.)*

8. **Never assume Gemini re-review auto-triggers after a push.**
   It does not. After pushing fixes to an open PR, immediately post `/gemini review`
   as a PR comment. Do not proceed with other work until this is done.

9. **Call diminishing returns on Gemini after the first substantive round.**
    Fix all HIGH-priority comments every round. After the first round, if subsequent
    rounds contain only MEDIUM or LOW items, use judgment: apply what's genuinely
    worth it, skip pure style nits, and merge rather than chasing infinite feedback.
    Gemini will loop forever on style. One or two rounds of MEDIUMs is fine; more
    than that is diminishing returns — merge.

10. **Never write CI/workflow jobs with assumed permissions.**
   Each job's permissions must be explicitly and minimally scoped. Verify job
   output confirms correct behavior — not just that the workflow ran.
   *(Commit: b9f1ff0)*

11. **Never store credentials in config files — always reference env var names.**
    Fleet config files (`hermia-fleet.yaml` and any future config format) must
    never contain API keys, bearer tokens, passwords, or any secret value.
    Use `key_env: MY_VAR_NAME` — the name of the environment variable — never
    `key: sk-xxx`. The config file is safe to commit; the secret stays in the
    environment. This applies to all auth types: bearer, basic, header, custom.
    If a code path reads a config and would write a credential value into a result
    row, log line, or error message, that is a bug — fix it before merging.

12. **Never open a PR against `main` from a work branch — always target `dev`.**
    The only PR that should ever target `main` is the dev→main promotion PR.
    All other workflows: any work branch → PR → `dev` → PR → `main`.
    When using `gh pr create`, always pass `--base dev` explicitly; the default
    is the repo's default branch (`main`), which will bypass the dev gate and
    cause `main` to diverge ahead of `dev`, requiring rebase or merge judo to fix.
    *(Cause of PR #19 conflict, 2026-05-08)*

---

## ALWAYS DO (Required Behaviors)

### Branch Workflow
```
work branches (feature/, fix/, chore/, docs/, refactor/, ci/, test/, etc.) → dev → main
```
- Create all work branches from `dev` (always `git checkout dev && git pull origin dev` first, then `git checkout -b <prefix><branch-name>`). Use the appropriate prefix from the workflow diagram above when branching.
- Work branch PR: `gh pr create --base dev`
- Promotion PR (only): `gh pr create --base main --head dev`
- `main` must never get ahead of `dev`. If it does, sync: `git checkout dev && git pull origin dev && git pull origin main && git push origin dev` (resolve any conflicts before pushing).
- If on a work branch when this happens, rebase afterward: `git checkout <branch> && git rebase dev && git push origin <branch> --force-with-lease`.

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
| New eval test               | `test-datasets/agentic-tasks.json`, `src/hermia/schemas.py`  | Everything else                      |
| Schema checker fix          | `src/hermia/schemas.py`, `tests/unit/test_schemas.py`        | Everything else                      |
| Regression module           | `src/hermia/regression.py`, `tests/test_regression.py`       | Everything else                      |
| UI/TUI changes              | `src/hermia/tui/`, `src/hermia/screens.py`, `src/hermia/app.py`, `tests/unit/tui/`, `tests/fixtures/` | Core eval logic                      |
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
