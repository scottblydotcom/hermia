# Workstream E — Deterministic Multi-Turn (lean plan)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Generation delegated to the fleet (`coder-biggest-5090`); the Sonnet implementer integrates, runs gates, commits. Steps use `- [ ]`.

**Goal:** Let a test case define a multi-turn conversation (an ordered list of user turns) that `run_test` plays deterministically against the model, schema-checking the final assistant response — while keeping every existing single-turn case byte-for-byte unchanged.

**Architecture:** Build on the v0.2 `Transport` (already message-list / `/api/chat`) merged via Workstream A + C. Extract `_play_turns(transport, model, system, user_turns, timeout, temperature=None) -> Response` in `runner.py`: it builds the conversation incrementally (system, then for each user turn: append the user message, call `transport.generate`, append the assistant reply), and returns a synthetic `Response` whose `text` is the FINAL assistant reply, `tokens`/`elapsed_sec` are summed across turns, and orchestration fields come from the last reply. `run_test` derives `user_turns` from `test["turns"]` (new optional list field) or falls back to `[test["prompt"]]`. **Single-turn path stays identical** (one generate, transport's default temperature). **Multi-turn uses temperature 0** for orchestration determinism.

**Determinism scope:** the ORCHESTRATION is fully deterministic — fixed turn order, identical message construction, no randomness in how turns are assembled. Model-level determinism additionally depends on the backend (temperature 0 + seed support varies); this is documented, not promised.

**Tech Stack:** Python 3.11+, the existing `Transport`/`Response`, `pytest`.

## Fleet delegation protocol (every task)
The Sonnet implementer delegates test-body GENERATION to the fleet's `coder-biggest-5090` lane via the LiteLLM gateway (dispatch helper/endpoint/credentials live in the **ailab ops repo**, never here), then critically reviews/adapts/verifies/commits. Never commit fleet output unread. Author the `runner.py` changes (Task E2) yourself; fleet is reference only for that core change.

## File Map
| Action | Path | Responsibility |
|--------|------|----------------|
| MODIFY | `src/hermia/runner.py` | `_play_turns` helper; `run_test` derives turns; `turn_count` in result |
| MODIFY | `src/hermia/test-datasets/agentic-tasks.json` | add 2 multi-turn cases (with `turns`) |
| MODIFY | `src/hermia/schemas.py` | checkers for the 2 new multi-turn cases |
| CREATE | `tests/unit/test_multiturn.py` | playback, determinism, back-compat tests |
| MODIFY | `tests/unit/test_corpus_health.py` | tolerate optional `turns` field |

---

## Task E1: Multi-turn playback test (red first)
**Files:** `tests/unit/test_multiturn.py`

- [ ] **E1.1** Write `tests/unit/test_multiturn.py`. Use a fake transport that returns canned per-call replies and records the `messages` it was called with:
```python
from unittest.mock import MagicMock
from hermia.transport.base import Response
from hermia.runner import run_test

def _fake_transport(replies):
    calls = []
    t = MagicMock()
    t.is_api_mode = True  # avoids local sampling + /api/ps in run_test
    seq = iter(replies)
    def gen(model, messages, **opts):
        calls.append([dict(m) for m in messages])
        return Response(text=next(seq), tokens=5, elapsed_sec=0.1,
                        orchestration="ollama", orchestration_version=None, is_api_mode=True)
    t.generate.side_effect = gen
    t._calls = calls
    return t

_MT_TEST = {"id": "mt-demo", "dimension": "multi-turn", "description": "d",
            "system": "SYS", "prompt": "", "turns": ["hello", "now reply {\"ok\": true}"],
            "frameworks": {"owasp_llm_top10_2025": [], "mitre_atlas_v5_1": [],
                           "csa_maestro": [], "nist_ai_rmf": []}}

def test_multiturn_plays_all_turns_and_accumulates_history():
    tr = _fake_transport(["intermediate reply", '{"ok": true}'])
    res = run_test("m", _MT_TEST, MagicMock(), transport=tr)
    # two generate calls (one per user turn)
    assert tr.generate.call_count == 2
    # second call's messages include system + 1st user + 1st assistant + 2nd user
    second = tr._calls[1]
    roles = [m["role"] for m in second]
    assert roles == ["system", "user", "assistant", "user"]
    assert second[2]["content"] == "intermediate reply"  # prior assistant reply carried forward
    # final assistant reply is what gets schema-checked / stored
    assert res["turn_count"] == 2
    assert res["tokens"] == 10  # 5 per turn summed

def test_single_turn_unchanged_no_turns_field():
    tr = _fake_transport(['{"x": 1}'])
    base = {**_MT_TEST}; base.pop("turns"); base["prompt"] = "just one"
    res = run_test("m", base, MagicMock(), transport=tr)
    assert tr.generate.call_count == 1
    assert tr._calls[0] == [{"role": "system", "content": "SYS"},
                            {"role": "user", "content": "just one"}]
    assert res["turn_count"] == 1
```
- [ ] **E1.2** Run → fail (`turn_count` missing / turns not played). Record failure.

## Task E2: Implement `_play_turns` + wire into `run_test` (author yourself)
**Files:** `src/hermia/runner.py`

- [ ] **E2.1** Add `_play_turns` above `run_test`:
```python
def _play_turns(
    transport: Any, model: str, system: str, user_turns: list[str],
    timeout: int, temperature: float | None = None,
) -> Response:
    """Play an ordered list of user turns as one conversation; return a Response
    whose text is the FINAL assistant reply, with tokens/elapsed summed across
    turns. Single-turn (len==1) with temperature=None reproduces the prior
    one-shot behavior exactly."""
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    total_tokens = 0
    total_elapsed = 0.0
    last: Response | None = None
    for turn in user_turns:
        messages.append({"role": "user", "content": turn})
        opts: dict[str, Any] = {"timeout": timeout}
        if temperature is not None:
            opts["temperature"] = temperature
        last = transport.generate(model, messages, **opts)
        messages.append({"role": "assistant", "content": last.text})
        total_tokens += last.tokens
        total_elapsed += last.elapsed_sec
    assert last is not None  # user_turns is always non-empty
    return Response(
        text=last.text, tokens=total_tokens, elapsed_sec=total_elapsed,
        orchestration=last.orchestration, orchestration_version=last.orchestration_version,
        is_api_mode=last.is_api_mode,
    )
```
- [ ] **E2.2** In `run_test`, replace the fixed `messages = [...]` + single `transport.generate(...)` call. Derive turns and call `_play_turns` inside the existing try/except (so timeout/TransportError handling is unchanged):
```python
    raw_turns = test.get("turns")
    user_turns = [str(t) for t in raw_turns] if isinstance(raw_turns, list) and raw_turns else [test["prompt"]]
    is_multi = len(user_turns) > 1
    ...
    # inside the try:
        response = _play_turns(
            transport, model, test["system"], user_turns, TEST_TIMEOUT,
            temperature=0.0 if is_multi else None,
        )
```
- [ ] **E2.3** Add `"turn_count": len(user_turns)` to the result dict. Keep `raw_prompt` as `test["prompt"] or ""` (back-compat); for multi-turn also store the turns: add `"raw_turns": user_turns` to the result (so the audit trail captures the conversation).
- [ ] **E2.4** Run E1's tests → green. Run the FULL suite → green (single-turn cases must be unaffected). ruff + mypy clean. Commit: `feat(runner): deterministic multi-turn playback via _play_turns`

## Task E3: Determinism test
**Files:** `tests/unit/test_multiturn.py`

- [ ] **E3.1** Add a determinism test: with a fake transport returning the SAME canned per-turn replies, run the same multi-turn test twice; assert the two result dicts are equal on `json_valid, schema_compliant, score-relevant fields, turn_count, tokens, raw_turns` (exclude any timing field like `elapsed_sec`/`tokens_per_sec` and any run id/timestamp). Confirms the orchestration is reproducible.
- [ ] **E3.2** Green; ruff + mypy. Commit: `test(multiturn): determinism — identical canned turns yield identical result`

## Task E4: Two multi-turn corpus cases + checkers
**Files:** `src/hermia/test-datasets/agentic-tasks.json`, `src/hermia/schemas.py`, `tests/unit/test_corpus_health.py`

- [ ] **E4.1** Add 2 cases with a `turns` list (e.g. a context-carry case: turn 1 establishes a constraint, turn 2 asks the model to honor it and emit JSON; and a refusal-persistence case: turn 1 benign, turn 2 attempts to walk back a safety boundary — the model should hold). Each has `id, dimension, description, system, prompt:"" , turns:[...], frameworks`. Give them ids like `multiturn-context-carry`, `multiturn-boundary-persistence`.
- [ ] **E4.2** Add a `SCHEMA_CHECKS` entry for each new id validating the final-turn response shape.
- [ ] **E4.3** Update `tests/unit/test_corpus_health.py`: the required-keys check must allow `prompt` to be empty WHEN `turns` is present (a multi-turn case has `prompt:""`), and require that a case has EITHER a non-empty `prompt` OR a non-empty `turns` list. Keep checker-parity (every id still has a checker).
- [ ] **E4.4** Full suite green (corpus health + schema contract still pass with the new cases); ruff + mypy. Commit: `feat(corpus): two multi-turn test cases + checkers`

## Task E5: Docs + manifest + gates
- [ ] Full suite, ruff, mypy green. Document multi-turn (`turns` field, determinism scope, temperature-0) in README + docs/usage.md. Update `docs/WORKSTREAMS.md` E row → in review + PR #. Commit: `docs: document deterministic multi-turn`

## Self-review
- Spec coverage: multi-turn playback ✓ (E2), determinism ✓ (E3 + temperature 0 + fixed order), corpus cases ✓ (E4). Single-turn back-compat ✓ (E1.2 test + temperature=None path).
- Type consistency: `_play_turns(...) -> Response` used once in run_test; `turn_count`/`raw_turns` added to result; `user_turns: list[str]`.

## Coordination
E builds on merged C (touches `run_test`'s message construction, a different region than C's `_ps_cache` lock and `_run_host_eval` extraction). Branched off `dev` after C merged — no rebase needed. Does not touch D's `sink/` or F's tests.
