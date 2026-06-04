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
        "owasp_llm_top10_2025": [],
        "mitre_atlas_v5_1": [],
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
