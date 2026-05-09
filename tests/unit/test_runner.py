"""Unit tests for runner.py — model management and test execution."""

from unittest.mock import MagicMock, patch

import requests

from hermia.runner import (
    get_available_models,
    get_model_size_gb,
    load_tests,
    run_test,
    unload_model,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

MODEL_LIST = [
    {"name": "qwen2.5:32b", "size": 20 * 1024**3},
    {"name": "llama3:8b", "size": 5 * 1024**3},
]

_BASE_TEST = {
    "id": "tool-calling-basic",
    "dimension": "tool-use",
    "description": "basic tool call",
    "system": "You are a helpful assistant.",
    "prompt": "Call the get_weather tool for London.",
}


def _mock_sampler(
    cpu: float = 10.0, ram: float = 8.0, gpu: float = 85.0, vram: float = 20.0
) -> MagicMock:
    s = MagicMock()
    s.peak.return_value = {
        "cpu_pct": cpu,
        "ram_used_gb": ram,
        "gpu_pct": gpu,
        "vram_used_gb": vram,
    }
    return s


# ── get_available_models ──────────────────────────────────────────────────────

def test_get_available_models_returns_list() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": MODEL_LIST}
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        result = get_available_models()
    assert result == MODEL_LIST


def test_get_available_models_returns_empty_on_connection_error() -> None:
    with patch("hermia.runner.requests.get", side_effect=requests.exceptions.ConnectionError):
        assert get_available_models() == []


def test_get_available_models_returns_empty_on_missing_key() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        assert get_available_models() == []


# ── get_model_size_gb ─────────────────────────────────────────────────────────

def test_get_model_size_gb_found() -> None:
    result = get_model_size_gb("qwen2.5:32b", MODEL_LIST)
    assert abs(result - 20.0) < 0.01


def test_get_model_size_gb_not_found() -> None:
    assert get_model_size_gb("unknown:7b", MODEL_LIST) == 0.0


def test_get_model_size_gb_missing_size_key() -> None:
    assert get_model_size_gb("no-size", [{"name": "no-size"}]) == 0.0


# ── unload_model ──────────────────────────────────────────────────────────────

def test_unload_model_does_not_raise_on_success() -> None:
    with patch("hermia.runner.requests.post"):
        unload_model("llama3:8b")  # should not raise


def test_unload_model_swallows_exception() -> None:
    with patch("hermia.runner.requests.post", side_effect=requests.exceptions.ConnectionError):
        unload_model("llama3:8b")  # should not raise


# ── load_tests ────────────────────────────────────────────────────────────────

def test_load_tests_filters_by_id() -> None:
    results = load_tests(["tool-calling-basic"])
    assert len(results) == 1
    assert results[0]["id"] == "tool-calling-basic"


def test_load_tests_returns_multiple_matching() -> None:
    all_results = load_tests(["tool-calling-basic", "security-boundary"])
    ids = [r["id"] for r in all_results]
    assert "tool-calling-basic" in ids
    assert "security-boundary" in ids


def test_load_tests_ignores_unknown_ids() -> None:
    results = load_tests(["tool-calling-basic", "does-not-exist"])
    assert all(r["id"] != "does-not-exist" for r in results)


def test_load_tests_empty_selection() -> None:
    assert load_tests([]) == []


# ── run_test ──────────────────────────────────────────────────────────────────

def test_run_test_success_json_valid() -> None:
    payload = '{"action": "get_weather", "city": "London"}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 50, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["json_valid"] is True
    assert result["failure_reason"] == ""
    assert result["tokens"] == 50
    assert result["model"] == "qwen2.5:32b"
    assert result["dimension"] == "tool-use"


def test_run_test_schema_pass_when_checker_returns_true() -> None:
    payload = '{"action": "get_weather"}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 20, "error": ""}
    fake_checker = MagicMock(return_value=True)
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.SCHEMA_CHECKS", {"tool-calling-basic": fake_checker}):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["schema_compliant"] is True


def test_run_test_schema_fail_when_checker_returns_false() -> None:
    payload = '{"wrong": "shape"}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 10, "error": ""}
    fake_checker = MagicMock(return_value=False)
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.SCHEMA_CHECKS", {"tool-calling-basic": fake_checker}):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["json_valid"] is True
    assert result["schema_compliant"] is False


def test_run_test_no_schema_checker_leaves_schema_false() -> None:
    payload = '{"any": "json"}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.SCHEMA_CHECKS", {}):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["json_valid"] is True
    assert result["schema_compliant"] is False


def test_run_test_invalid_json_response() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "not json at all", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["json_valid"] is False
    assert result["schema_compliant"] is False


def test_run_test_timeout() -> None:
    with patch("hermia.runner.requests.post", side_effect=requests.exceptions.Timeout):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["failure_reason"].startswith("TIMEOUT")
    assert result["tokens"] == 0
    assert result["json_valid"] is False


def test_run_test_ollama_error_in_response() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "", "eval_count": 0, "error": "model not found"}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["failure_reason"].startswith("OLLAMA_ERROR")
    assert result["json_valid"] is False


def test_run_test_generic_exception() -> None:
    with patch("hermia.runner.requests.post", side_effect=RuntimeError("boom")):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["failure_reason"].startswith("ERROR")
    assert result["json_valid"] is False


def test_run_test_peak_metrics_in_result() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 5, "error": ""}
    sampler = _mock_sampler(cpu=42.0, ram=16.5, gpu=90.0, vram=22.3)
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        result = run_test("qwen2.5:32b", _BASE_TEST, sampler)
    assert result["peak_cpu_pct"] == 42.0
    assert result["peak_ram_used_gb"] == 16.5
    assert result["peak_gpu_pct"] == 90.0
    assert result["peak_vram_used_gb"] == 22.3


def test_run_test_tokens_per_sec_computed() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 100, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.time.time", side_effect=[0.0, 2.0]):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["tokens_per_sec"] == 50.0
    assert result["elapsed_sec"] == 2.0
