# Contributing to Hermia

Thanks for your interest. Hermia is a security evaluation tool — contributions that
expand coverage, improve correctness, or sharpen the framework mappings are especially
welcome.

---

## Before You Start

Read [AGENTS.md](AGENTS.md). It covers the behavioral rules, module boundary table,
and the review gate sequence this project enforces. These apply to all contributions,
human or AI.

---

## Dev Setup

**Requirements:** Python 3.11+, [Ollama](https://ollama.ai) running locally.

```bash
git clone https://github.com/scottblydotcom/hermia
cd hermia
pip install -e ".[dev]"

# Verify everything passes before you change anything
pytest
ruff check src/
mypy src/
```

---

## Branching Model

```
feature/* or fix/* or chore/*
    ↓  PR → CI (ruff, mypy, pytest)
   dev  ← target for all feature PRs
    ↓  PR → CI + security gate + Gemini review
  main  ← branch protection active; releases cut from here
```

- Branch from `dev`, not `main`
- Name your branch: `feature/short-description`, `fix/what-you-fixed`, `chore/what-you-cleaned`
- One logical change per branch

---

## Making Changes

**New eval test cases** (`test-datasets/agentic-tasks.json` + `src/hermia/schemas.py`):
- Follow the existing test case structure — `id`, `dimension`, `description`, `system`, `prompt`
- Add a corresponding schema checker in `schemas.py` using the `_keys_ok()` helper
- Map the test to at least one framework reference (OWASP, ATLAS, MAESTRO, or NIST AI RMF)
- Include a unit test in `tests/unit/test_schemas.py` with at least one extra-key case

**Bug fixes:**
- Confirm the bug with a failing test first, then fix
- Stay within the module boundary for the fix — see the table in `AGENTS.md`
- CLI entrypoints must be tested via direct invocation, not just function calls

**New dependencies:**
- Open a GitHub Issue to discuss before writing any code that uses a new library
- stdlib-only solutions are always preferred
- If approved, add to `pyproject.toml` with a minimum version pin

---

## Commit Messages

```
type(scope): short description

Examples:
  feat(schemas): add indirect-injection-tool-output checker
  fix(runner): handle empty model list from Ollama
  ci(security): pin trivy action to SHA
  docs(readme): update framework coverage table
```

Types: `feat`, `fix`, `refactor`, `test`, `ci`, `docs`, `chore`

---

## Pull Requests

- Target `dev`, not `main`
- Fill out the PR template — it exists for a reason
- CI must be green before requesting review
- Gemini Code Assist will review your PR automatically; the maintainer will
  not merge until that review is complete
- Reference the GitHub Issue number in your PR description

---

## What Gets Reviewed

Every PR gets:
1. CI — ruff, mypy, pytest
2. Gemini Code Assist — logic and architecture review
3. Maintainer review — security correctness, framework mapping accuracy,
   schema checker quality

For changes touching eval logic, schema validation, or the CI pipeline,
expect a deeper review pass. This is a security tool; correctness matters.

---

## Code Style

- Ruff enforces formatting and linting — run it before pushing
- mypy strict mode is enabled — type annotations are required
- Line length: 100 characters
- No wildcard imports, no bare `except`, no global variables

---

## Questions

Open a GitHub Issue with the `question` label. If you're unsure whether
a contribution fits the project's direction, ask before building it.
