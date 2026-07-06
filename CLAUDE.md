# Project Instructions for AI Agents

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
