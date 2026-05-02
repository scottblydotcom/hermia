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
pytest
ruff check src/
mypy src/
```

## Architecture

Open-source LLM security eval TUI. `textual` UI, eval test datasets in `test-datasets/`, schema checks in `src/hermia/schemas.py`. See `docs/security-framework-research.md` for framework mappings (OWASP LLM Top 10, MITRE ATLAS, CSA MAESTRO, NIST AI RMF).
