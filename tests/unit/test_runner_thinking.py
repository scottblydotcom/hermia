"""hermia-cv5z: runner threads the reasoning 'thinking' channel into result rows.

The row gains raw_thinking (mirrors raw_response: blanked on transport error).
Grading stays content-only — thinking never changes a pass/fail verdict — EXCEPT
that an empty content with a non-empty thinking channel is flagged as its own
failure_reason so a reasoning model that put everything in the scratchpad and
nothing in the answer is not silently indistinguishable from a dead-empty reply.
"""
from unittest.mock import MagicMock, patch

from hermia.runner import run_test
from hermia.transport.base import Response as TransportResponse

_BASE_TEST = {
    "id": "tool-calling-basic",
    "dimension": "tool-use",
    "description": "basic tool call",
    "system": "You are a helpful assistant.",
    "prompt": "Call the get_weather tool for London.",
}
_PS_EMPTY = {"vram_server_gb": None, "model_size_server_gb": None}


def _mock_sampler() -> MagicMock:
    s = MagicMock()
    s.peak.return_value = {
        "cpu_pct": 10.0, "ram_used_gb": 8.0, "gpu_pct": 85.0, "vram_used_gb": 20.0,
    }
    return s


def _run(text: str, thinking: str) -> dict:
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text=text,
        thinking=thinking,
        tokens=10,
        elapsed_sec=1.0,
        orchestration="ollama",
        orchestration_version="0.24.0",
        is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        return run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)


def test_raw_thinking_captured_on_clean_path() -> None:
    row = _run('{"action": "get_weather", "city": "London"}', "chain of thought here")
    assert row["raw_thinking"] == "chain of thought here"


def test_empty_content_with_thinking_flagged() -> None:
    row = _run("", "reasoned at length but emitted no answer")
    assert row["failure_reason"] == "EMPTY_CONTENT_WITH_THINKING"
    # thinking is preserved on this failure so it can be inspected / re-graded
    assert row["raw_thinking"] == "reasoned at length but emitted no answer"


def test_empty_content_no_thinking_still_empty_response() -> None:
    row = _run("", "")
    assert row["failure_reason"] == "EMPTY_RESPONSE"


def test_nonempty_content_grading_unchanged() -> None:
    # tool-calling-basic + {"action": "get_weather", ...} is valid JSON but wrong
    # schema -> SCHEMA_FAIL, and a non-empty thinking channel must NOT change that.
    row = _run('{"action": "get_weather", "city": "London"}', "some reasoning")
    assert row["failure_reason"] == "SCHEMA_FAIL"
    assert row["raw_thinking"] == "some reasoning"


def test_whitespace_content_with_thinking_flagged() -> None:
    # A reasoning model that emits only whitespace in the answer (all its budget
    # spent in the scratchpad) must be EMPTY_CONTENT_WITH_THINKING, not
    # JSON_PARSE_ERROR — the runner previously gated on `output` truthiness, so
    # "\n" wrongly entered the JSON path (hermia-cv5z follow-up).
    row = _run("  \n  ", "reasoned but produced only whitespace")
    assert row["failure_reason"] == "EMPTY_CONTENT_WITH_THINKING"
    assert row["raw_thinking"] == "reasoned but produced only whitespace"


def test_whitespace_content_no_thinking_still_empty_response() -> None:
    row = _run("   ", "")
    assert row["failure_reason"] == "EMPTY_RESPONSE"


def test_none_thinking_does_not_crash() -> None:
    # A mock/custom transport that hands back Response.thinking=None must not
    # crash the runner's .strip() at the consumption point (hermia-cv5z).
    row = _run("", None)  # type: ignore[arg-type]
    assert row["failure_reason"] == "EMPTY_RESPONSE"
    assert row["raw_thinking"] == ""
