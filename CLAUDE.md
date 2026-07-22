# Project Instructions for AI Agents

## ⚠️ THIS REPOSITORY IS PUBLIC

`github.com/scottblydotcom/hermia` is public. **Everything you commit is world-readable** — file contents, file names, and commit messages alike, forever, whether or not it is later deleted.

**"Internal" and "in this repo" are mutually exclusive.** Before committing anything that is not code, tests, or public-facing documentation, ask: *would I be comfortable with the subject of this reading it?* If not, it does not go here.

**Never commit to this repo:**
- **Anything about a named person or organisation** — meeting preparation, how to approach or handle someone, assessments of their likely reactions, negotiating posture, who to leverage for distribution.
- **Infrastructure detail** — private/tailnet IPs, hostnames, network topology, machine ownership, security incidents involving anyone's machines.
- **Commercial strategy** — pricing, positioning against named competitors, partner plans.
- Credentials of any kind (there are pre-commit hooks for this; **do not `--no-verify` past them** — fix the finding or exclude the file).

**Where internal material goes instead:** `~/Git/hermia-research/` (there is a `meeting-prep/` subdirectory). Beads are safe for internal detail — `.beads/` is not tracked — and so is the Claude memory system.

**Checks that are actually load-bearing:**
- Verify the **source**, not the rendered artifact. An HTML comment is invisible in a PDF and fully readable on GitHub.
- Verify **commit messages** too. They are as public as the diff.
- Grep the real thing before pushing: `git show <sha> | grep -iE "<names>|192\.168\.|100\.[0-9]+\."`

*Grounded in a real near-miss (2026-07-22): a meeting-prep document naming an external collaborator, characterising their likely sensitivities, and describing what to withhold from them was committed to `docs/`. It was caught only because Scott asked whether `docs/` was public. Three separate leaks were involved — the file body, an HTML comment header in a file that had been declared clean, and two commit messages. Nothing had been pushed. `.gitignore` now carries a guard for `docs/GUARDS-cheatsheet.*` and `docs/*-prep.*`, but the guard only covers the names we already know.*

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
bd create "<title>"   # File a new issue
```

- Use `bd` for task tracking in this repo — not markdown TODO lists
- Use `bd remember` for hermia-specific persistent facts
- Global cross-project memory still lives in the Claude memory system (MEMORY.md) — both coexist
- Git pushes are Scott's call — do NOT auto-push at session end
<!-- END BEADS INTEGRATION -->

## Build & Test

```bash
pip install -e ".[dev]"
pytest -q
ruff check src/
mypy src/
```

## Architecture

Open-source LLM security eval TUI. `textual` UI, eval test datasets in `src/hermia/test-datasets/`, schema checks in `src/hermia/schemas.py`. See `docs/security-framework-research.md` for framework mappings (OWASP LLM Top 10, MITRE ATLAS, CSA MAESTRO, NIST AI RMF).

## Behavioral Rules

See `AGENTS.md` for the full never-do/always-do rule set, module boundary table, and review gate sequence. Rules are grounded in real git history. Read it before writing any code.

## Session Start Protocol

At the start of every session, before writing any code, complete these steps in order and show output for each:

1. **Check for previous session notes.** Look for `session-notes/` files or recent `bd note` entries. If none exist from the last session, flag it before proceeding.
2. **Establish task scope.**
   - *Internal (bd installed):* Run `bd prime` and report the active bead ID and description.
   - *External contributor (no bd):* Confirm the GitHub Issue number and title in scope.
3. **Confirm branch.** Run `git branch --show-current`. The branch name must match the task. If it does not, create a correctly named feature branch before touching anything.
4. **Establish test baseline.** Run `pytest -q` and show the output. Do not write a single line of code until the baseline is confirmed.
5. **Confirm module scope.** State which files are permitted for this task per the Module Boundary Table in `AGENTS.md`. Flag any anticipated out-of-scope touches before starting.

Do not write any code until all five steps are complete.

## Session Close Protocol

Before ending any session, produce a state summary covering:
- What was completed
- What is in progress and where it stands
- Any tricky bits or known gotchas for the next session
- Active branch and its current state
- Any open review gates not yet cleared

**Primary path:** `bd note` on the active bead (lowest friction).
**Fallback:** Save as `session-notes/YYYY-MM-DD.md`.
Git pushes are Scott's call — do NOT auto-push at session end.
