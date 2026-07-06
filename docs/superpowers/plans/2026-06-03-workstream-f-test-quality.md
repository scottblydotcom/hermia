# Workstream F — Test Quality + Framework Coverage (lean plan)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Generation is delegated to the fleet (`coder-biggest-5090`); the Sonnet implementer integrates, runs gates, commits. Steps use `- [ ]`.

**Goal:** Lock in test-suite quality for the corpus and schema checkers, and validate framework taxonomy tags — all test-only additions, no production code changes.

**Architecture:** Pure test additions under `tests/unit/`. Ground truth: corpus at `src/hermia/test-datasets/agentic-tasks.json` (28 cases; entry keys `id, dimension, description, system, prompt, frameworks`; `frameworks` keys `owasp_llm_top10_2025, mitre_atlas_v5_1, csa_maestro, nist_ai_rmf`). `SCHEMA_CHECKS` in `hermia.schemas` has 28 checkers. `test_schemas_properties.py` already exists (hypothesis property tests) — **extend, do not duplicate**. CLI entrypoints: `hermia`(app:main), `hermia-regression`, `hermia-push`(export:main), `hermia-analyze`.

**Tech Stack:** pytest, hypothesis, `subprocess`, stdlib json.

## Fleet delegation protocol (every task)
For each task the Sonnet implementer:
1. Reads the relevant current code/tests.
2. Delegates test GENERATION to the fleet's `coder-biggest-5090` lane via the LiteLLM
   gateway (the dispatch helper, endpoint, and credentials live in the **ailab ops repo**,
   never in this public repo). Prompt: the precise task spec, temperature 0.2.
3. Reviews the fleet output critically, adapts it to repo conventions, writes the file.
4. Runs the test (red where applicable), then green; runs `ruff` + `mypy`; commits.
   Never commits fleet output unread.

---

## Task F1: Corpus health test
**Files:** Test: `tests/unit/test_corpus_health.py` (NEW)

- [ ] Generate (via fleet) + integrate a test module asserting, over every case in `agentic-tasks.json`:
  - all 6 required keys present and non-empty (`id, dimension, description, system, prompt, frameworks`);
  - `id` values are unique across the corpus;
  - `frameworks` is a dict containing all 4 taxonomy keys, each a list (possibly empty) of strings;
  - every corpus `id` has a corresponding checker in `SCHEMA_CHECKS` and vice-versa (no orphans either direction).
- [ ] Load the corpus the same way the package does (via `hermia.runner.load_tests_all` or the packaged path) — do not hardcode a relative path that breaks under pytest.
- [ ] Run: `python -m pytest tests/unit/test_corpus_health.py -q --no-cov -p no:cacheprovider` → green. ruff + mypy clean.
- [ ] Commit: `test(corpus): add corpus health checks (keys, unique ids, framework taxonomy, checker parity)`

## Task F2: Schema-checker contract test
**Files:** Test: `tests/unit/test_schema_contract.py` (NEW). First READ `tests/unit/test_schemas_properties.py` and `tests/unit/test_schemas.py` to avoid duplicating existing coverage.

- [ ] Generate + integrate a parametrized contract test over `SCHEMA_CHECKS.items()`:
  - **Totality:** each checker returns a bool (never raises) for a set of adversarial inputs (`{}`, `{"x": None}`, deeply nested dict, list, `""`, unicode keys) — reuse hypothesis if `test_schemas_properties.py` doesn't already cover totality for all 28.
  - **Positive/negative presence:** assert that for each checker there exists at least one positive example (a dict it accepts) and one negative (a dict it rejects) — encoded as a per-checker fixture table the test fills in, or derived. If a checker can't be exercised, fail with its id so the gap is visible.
- [ ] Green; ruff + mypy clean.
- [ ] Commit: `test(schemas): parametrized checker contract — totality + positive/negative per checker`

## Task F3: Framework taxonomy validation
**Files:** Test: `tests/unit/test_framework_coverage.py` (NEW)

- [ ] Generate + integrate a test that:
  - validates every `frameworks` value across the corpus is a list of strings under one of the 4 known keys (no unknown keys; no non-string entries);
  - emits (via a `capsys`-captured print or a returned summary) a coverage tally: how many corpus cases tag each of the 4 frameworks, and the distinct OWASP/MITRE codes used — assert the tally is non-empty (the corpus actually exercises frameworks).
- [ ] Green; ruff + mypy clean.
- [ ] Commit: `test(frameworks): validate taxonomy keys + coverage tally over corpus`

## Task F4: CLI subprocess smoke tests
**Files:** Test: `tests/unit/test_cli_smoke.py` (NEW). First READ `tests/unit/test_app.py` to see which entrypoints already have smoke coverage (3 references exist) — only cover the gaps.

- [ ] Generate + integrate subprocess smoke tests for each console script that lacks one (`hermia-regression`, `hermia-push`, `hermia-analyze`, and `hermia` if not covered): invoke `python -m hermia.<module> --help` (and `--version` where supported) via `subprocess.run`, assert exit code 0 and non-empty stdout. Use the module-invocation form so it works without an installed console script in CI.
- [ ] Green; ruff + mypy clean.
- [ ] Commit: `test(cli): subprocess smoke tests for hermia entrypoints`

## Task F5: Full gates + manifest
- [ ] `python -m pytest -q --no-cov -p no:cacheprovider` (full suite green), `ruff check src tests`, `mypy src/hermia`.
- [ ] Update `docs/WORKSTREAMS.md`: F row → in review, branch `feat/workstream-f-test-quality`, PR #.
- [ ] Commit: `docs: mark Workstream F in review`

## Coordination
F is independent of C/D/E (test-only, touches no shared production file). Safe to run in parallel.
