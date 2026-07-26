"""E — deterministic multi-turn playback tests.

E1: Red-first playback and back-compat tests.
E3: Determinism test (identical canned turns → identical result).
"""

from unittest.mock import MagicMock

from hermia.runner import run_test
from hermia.transport.base import Response


def _fake_transport(replies):
    """Return a fake transport and its call-record list.

    The fake records the exact ``messages`` list passed to each generate call
    so tests can inspect conversation history.
    """
    calls = []
    t = MagicMock()
    t.is_api_mode = True  # avoids local sampling + /api/ps in run_test
    seq = iter(replies)

    def gen(model, messages, **opts):
        calls.append([dict(m) for m in messages])
        return Response(
            text=next(seq),
            tokens=5,
            elapsed_sec=0.1,
            orchestration="ollama",
            orchestration_version=None,
            is_api_mode=True,
        )

    t.generate.side_effect = gen
    t._calls = calls
    return t


_MT_TEST = {
    "id": "mt-demo",
    "dimension": "multi-turn",
    "description": "d",
    "system": "SYS",
    "prompt": "",
    "turns": ["hello", 'now reply {"ok": true}'],
    "frameworks": {
        "owasp_llm_top10": [],
        "mitre_atlas": [],
        "csa_maestro": [],
        "nist_ai_rmf": [],
    },
}


# ---------------------------------------------------------------------------
# E1.1 — playback: all turns played, history accumulated, tokens summed
# ---------------------------------------------------------------------------


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
    base = {**_MT_TEST}
    base.pop("turns")
    base["prompt"] = "just one"
    res = run_test("m", base, MagicMock(), transport=tr)
    assert tr.generate.call_count == 1
    assert tr._calls[0] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "just one"},
    ]
    assert res["turn_count"] == 1


def test_multiturn_keeps_only_final_turn_thinking():
    # _play_turns propagates ONLY the final turn's thinking (thinking=last.thinking),
    # never an earlier turn or a concatenation. Correct today; pin it against a
    # future refactor that mirrors the token/elapsed summation (hermia-cv5z).
    thinks = iter(["FIRST turn reasoning", "SECOND turn reasoning"])
    texts = iter(["intermediate reply", '{"ok": true}'])
    t = MagicMock()
    t.is_api_mode = True

    def gen(model, messages, **opts):
        return Response(
            text=next(texts),
            tokens=5,
            elapsed_sec=0.1,
            orchestration="ollama",
            orchestration_version=None,
            is_api_mode=True,
            thinking=next(thinks),
        )

    t.generate.side_effect = gen
    res = run_test("m", _MT_TEST, MagicMock(), transport=t)
    assert res["raw_thinking"] == "SECOND turn reasoning"
    assert "FIRST" not in res["raw_thinking"]


# ---------------------------------------------------------------------------
# E3 — determinism: same canned replies → identical result dict
# ---------------------------------------------------------------------------


def _result_fields_for_determinism(res: dict) -> dict:
    """Extract the stable subset of run_test result fields for determinism comparison.

    Excludes timing fields (elapsed_sec, tokens_per_sec) since float accumulation
    can differ by floating-point rounding between runs in theory, and any run-id
    or timestamp fields that may be added in future.
    """
    return {
        k: v
        for k, v in res.items()
        if k not in ("elapsed_sec", "tokens_per_sec")
    }


# ---------------------------------------------------------------------------
# E4 — snapshot isolation: each generate call receives an independent copy
# ---------------------------------------------------------------------------


def test_play_turns_passes_independent_message_snapshots() -> None:
    """Each generate call must receive a snapshot of the conversation AT THAT
    POINT — not a reference that later reflects appended turns. Guards the
    list(messages) snapshot in _play_turns."""
    retained: list[list[dict]] = []
    t = MagicMock()
    t.is_api_mode = True
    seq = iter(["reply-1", '{"ok": true}'])

    def gen(model, messages, **opts):
        retained.append(messages)  # RETAIN the reference, do NOT copy
        return Response(
            text=next(seq),
            tokens=1,
            elapsed_sec=0.0,
            orchestration="ollama",
            orchestration_version=None,
            is_api_mode=True,
        )

    t.generate.side_effect = gen

    test = {
        "id": "mt",
        "dimension": "multi-turn",
        "description": "d",
        "system": "SYS",
        "prompt": "",
        "turns": ["first", "second"],
        "frameworks": {
            "owasp_llm_top10": [],
            "mitre_atlas": [],
            "csa_maestro": [],
            "nist_ai_rmf": [],
        },
    }
    run_test("m", test, MagicMock(), transport=t)

    # If the same mutable list were passed each call, BOTH retained refs would
    # now have the final length (4: system+user+assistant+user). With per-call
    # snapshots, the first retains length 2 and the second length 4.
    assert len(retained[0]) == 2, "first call must snapshot [system, user-1]"
    assert [m["role"] for m in retained[0]] == ["system", "user"]
    assert len(retained[1]) == 4
    assert [m["role"] for m in retained[1]] == ["system", "user", "assistant", "user"]


# ---------------------------------------------------------------------------
# E5 — None response from transport → EMPTY_RESPONSE, no exception
# ---------------------------------------------------------------------------


def test_play_turns_returns_none_when_generate_returns_none():
    """A transport whose generate returns None must cause run_test to produce
    an EMPTY_RESPONSE result without raising."""
    t = MagicMock()
    t.is_api_mode = True
    t.generate.return_value = None

    test = {
        "id": "mt-none",
        "dimension": "multi-turn",
        "description": "d",
        "system": "SYS",
        "prompt": "",
        "turns": ["hello"],
        "frameworks": {
            "owasp_llm_top10": [],
            "mitre_atlas": [],
            "csa_maestro": [],
            "nist_ai_rmf": [],
        },
    }
    result = run_test("m", test, MagicMock(), transport=t)
    assert result["failure_reason"] == "EMPTY_RESPONSE"
    assert result["raw_response"] == ""


# ---------------------------------------------------------------------------
# E6 — single-turn test with no prompt key does not raise KeyError
# ---------------------------------------------------------------------------


def test_single_turn_missing_prompt_does_not_crash():
    """A single-turn test dict with no 'prompt' key must use '' and not raise."""
    tr = _fake_transport(['{"ok": true}'])
    test = {
        "id": "no-prompt",
        "dimension": "single-turn",
        "description": "d",
        "system": "SYS",
        # intentionally no "prompt" key
        "frameworks": {
            "owasp_llm_top10": [],
            "mitre_atlas": [],
            "csa_maestro": [],
            "nist_ai_rmf": [],
        },
    }
    run_test("m", test, MagicMock(), transport=tr)
    # Should not raise; single generate call with empty prompt string
    assert tr.generate.call_count == 1
    assert tr._calls[0][1]["content"] == ""  # user message used ""


# ---------------------------------------------------------------------------
# E7 — None text in first reply → coerced to "" in second call's messages
# ---------------------------------------------------------------------------


def test_play_turns_coerces_none_assistant_text_to_empty_string():
    """If the first assistant reply has text=None (defensive; real transports return str),
    the next generate call's messages must carry '' not None, and run_test must not raise."""
    # Use MagicMock as a Response-like object so we can set text=None without
    # fighting the frozen dataclass type annotation.
    first_reply = MagicMock()
    first_reply.text = None
    first_reply.tokens = 3
    first_reply.elapsed_sec = 0.1
    first_reply.orchestration = "ollama"
    first_reply.orchestration_version = None
    first_reply.is_api_mode = True

    second_reply = Response(
        text='{"ok": true}',
        tokens=5,
        elapsed_sec=0.1,
        orchestration="ollama",
        orchestration_version=None,
        is_api_mode=True,
    )

    calls: list[list[dict]] = []
    t = MagicMock()
    t.is_api_mode = True
    seq = iter([first_reply, second_reply])

    def gen(model, messages, **opts):
        calls.append([dict(m) for m in messages])
        return next(seq)

    t.generate.side_effect = gen

    test = {
        "id": "mt-none-text",
        "dimension": "multi-turn",
        "description": "d",
        "system": "SYS",
        "prompt": "",
        "turns": ["hello", 'now reply {"ok": true}'],
        "frameworks": {
            "owasp_llm_top10": [],
            "mitre_atlas": [],
            "csa_maestro": [],
            "nist_ai_rmf": [],
        },
    }
    # Must not raise even with None text in first reply
    result = run_test("m", test, MagicMock(), transport=t)

    # Second call's messages: system + user + assistant(coerced) + user
    assert len(calls) == 2
    assistant_msg = calls[1][2]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "", (
        f"Expected '' but got {assistant_msg['content']!r} — None was not coerced"
    )
    # run_test must complete normally (schema check runs on second reply)
    assert result["failure_reason"] == "" or result["failure_reason"] == "SCHEMA_FAIL"


# ---------------------------------------------------------------------------


def test_multiturn_determinism_identical_canned_turns_yield_identical_result():
    """Running the same multi-turn test twice with identical canned replies
    must produce byte-identical results on all stable fields."""
    replies = ["turn1 reply", '{"ok": true}']

    tr1 = _fake_transport(list(replies))
    res1 = run_test("m", _MT_TEST, MagicMock(), transport=tr1)

    tr2 = _fake_transport(list(replies))
    res2 = run_test("m", _MT_TEST, MagicMock(), transport=tr2)

    stable1 = _result_fields_for_determinism(res1)
    stable2 = _result_fields_for_determinism(res2)

    assert stable1 == stable2, (
        f"Determinism violated. Differing keys: "
        f"{[k for k in stable1 if stable1[k] != stable2.get(k)]}"
    )
    # Spot-check the fields the plan explicitly names
    assert res1["turn_count"] == res2["turn_count"]
    assert res1["tokens"] == res2["tokens"]
    assert res1["raw_turns"] == res2["raw_turns"]
    assert res1["json_valid"] == res2["json_valid"]
    assert res1["schema_compliant"] == res2["schema_compliant"]
