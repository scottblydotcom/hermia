"""Unit tests for runner.py — model management and test execution."""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

import hermia.runner as _runner_mod
from hermia.runner import (
    get_available_models,
    get_model_size_gb,
    load_tests,
    run_test,
    unload_model,
)


@pytest.fixture(autouse=True)
def _clear_vram_cache() -> None:
    _runner_mod._vram_cache.clear()
    yield
    _runner_mod._vram_cache.clear()

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


def _mock_ps_empty() -> MagicMock:
    """Mock /api/ps returning no loaded models."""
    m = MagicMock()
    m.json.return_value = {"models": []}
    return m


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
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
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
            with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
                result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["schema_compliant"] is True


def test_run_test_schema_fail_when_checker_returns_false() -> None:
    payload = '{"wrong": "shape"}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 10, "error": ""}
    fake_checker = MagicMock(return_value=False)
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.SCHEMA_CHECKS", {"tool-calling-basic": fake_checker}):
            with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
                result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["json_valid"] is True
    assert result["schema_compliant"] is False


def test_run_test_no_schema_checker_leaves_schema_false() -> None:
    payload = '{"any": "json"}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.SCHEMA_CHECKS", {}):
            with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
                result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["json_valid"] is True
    assert result["schema_compliant"] is False


def test_run_test_invalid_json_response() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "not json at all", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["json_valid"] is False
    assert result["schema_compliant"] is False


def test_run_test_timeout() -> None:
    with patch("hermia.runner.requests.post", side_effect=requests.exceptions.Timeout):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["failure_reason"].startswith("TIMEOUT")
    assert result["tokens"] == 0
    assert result["json_valid"] is False


def test_run_test_ollama_error_in_response() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "", "eval_count": 0, "error": "model not found"}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["failure_reason"].startswith("OLLAMA_ERROR")
    assert result["json_valid"] is False


def test_run_test_generic_exception() -> None:
    with patch("hermia.runner.requests.post", side_effect=RuntimeError("boom")):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["failure_reason"].startswith("ERROR")
    assert result["json_valid"] is False


def test_run_test_peak_metrics_in_result() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 5, "error": ""}
    sampler = _mock_sampler(cpu=42.0, ram=16.5, gpu=90.0, vram=22.3)
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, sampler)
    assert result["peak_cpu_pct"] == 42.0
    assert result["peak_ram_used_gb"] == 16.5
    assert result["peak_gpu_pct"] == 90.0
    assert result["peak_vram_used_gb"] == 22.3


def test_run_test_tokens_per_sec_computed() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 100, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            with patch("hermia.runner.time.time", side_effect=[0.0, 2.0]):
                result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["tokens_per_sec"] == 50.0


def test_run_test_carries_frameworks_from_test() -> None:
    fw = {
        "owasp_llm_top10_2025": ["LLM01:2025"],
        "mitre_atlas_v5_1": ["AML.T0100"],
        "csa_maestro": [],
        "nist_ai_rmf": [],
    }
    test_with_fw = {**_BASE_TEST, "frameworks": fw}
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", test_with_fw, _mock_sampler())
    assert result["frameworks"] == fw


def test_run_test_frameworks_defaults_to_empty_dict() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["frameworks"] == {}


def test_load_tests_includes_frameworks_field() -> None:
    results = load_tests(["system-prompt-extraction-resistance"])
    assert len(results) == 1
    fw = results[0]["frameworks"]
    assert "LLM01:2025" in fw["owasp_llm_top10_2025"]
    assert "AML.T0100" in fw["mitre_atlas_v5_1"]


# ---------------------------------------------------------------------------
# hermia-0ws: repeat-field absence from run_test
# ---------------------------------------------------------------------------

def test_run_test_result_has_no_repeat_fields() -> None:
    """run_test() must NOT stamp run_index, is_cold, or cold_warm_delta_tps.

    Those fields are the responsibility of screens.py, not the runner.
    """
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert "run_index" not in result
    assert "is_cold" not in result
    assert "cold_warm_delta_tps" not in result


# ── get_ollama_host ───────────────────────────────────────────────────────────

def test_get_ollama_host_default() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HERMIA_HOST", None)
        from hermia.runner import get_ollama_host
        assert get_ollama_host() == "http://localhost:11434"


def test_get_ollama_host_from_env() -> None:
    with patch.dict(os.environ, {"HERMIA_HOST": "http://100.71.60.30:11434"}):
        from hermia.runner import get_ollama_host
        assert get_ollama_host() == "http://100.71.60.30:11434"


# ── detect_mode ───────────────────────────────────────────────────────────────

def test_detect_mode_localhost() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://localhost:11434") == "local"


def test_detect_mode_loopback() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://127.0.0.1:11434") == "local"


def test_detect_mode_remote_ip() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://100.71.60.30:11434") == "fleet"


def test_detect_mode_remote_hostname() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://erics-origin-neuron:11434") == "fleet"


def test_detect_mode_ipv6_loopback() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://[::1]:11434") == "local"


def test_detect_mode_no_scheme() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("127.0.0.1:11434") == "local"


# ── fetch_server_vram ─────────────────────────────────────────────────────────

def test_fetch_server_vram_found() -> None:
    from hermia.runner import fetch_server_vram
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5:32b", "size_vram": 19_271_950_336},
        ]
    }
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        result = fetch_server_vram("http://localhost:11434", "qwen2.5:32b")
    assert result is not None
    assert abs(result - 19_271_950_336 / (1024 ** 3)) < 0.01


def test_fetch_server_vram_model_not_found() -> None:
    from hermia.runner import fetch_server_vram
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": "other:7b", "size_vram": 5_000_000_000}]}
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        assert fetch_server_vram("http://localhost:11434", "qwen2.5:32b") is None


def test_fetch_server_vram_empty_models() -> None:
    from hermia.runner import fetch_server_vram
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": []}
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        assert fetch_server_vram("http://localhost:11434", "qwen2.5:32b") is None


def test_fetch_server_vram_connection_error() -> None:
    from hermia.runner import fetch_server_vram
    with patch("hermia.runner.requests.get", side_effect=requests.exceptions.ConnectionError):
        assert fetch_server_vram("http://100.71.60.30:11434", "qwen2.5:32b") is None


def test_fetch_server_vram_missing_size_vram_key() -> None:
    from hermia.runner import fetch_server_vram
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": "qwen2.5:32b"}]}  # no size_vram key
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        assert fetch_server_vram("http://localhost:11434", "qwen2.5:32b") is None


# ── run_test — mode and vram_server_gb fields ─────────────────────────────────

def test_run_test_has_mode_field_local() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["mode"] == "local"


def test_run_test_has_vram_server_gb_field() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert "vram_server_gb" in result
    assert result["vram_server_gb"] is None  # empty models list → None


def test_run_test_fleet_mode_suppresses_local_metrics() -> None:
    """In fleet mode, all local hardware fields must be None."""
    mock_post = MagicMock()
    mock_post.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    mock_get = MagicMock()
    mock_get.json.return_value = {"models": []}
    with patch("hermia.runner.requests.post", return_value=mock_post):
        with patch("hermia.runner.requests.get", return_value=mock_get):
            result = run_test(
                "qwen2.5:32b", _BASE_TEST, _mock_sampler(),
                host="http://100.71.60.30:11434"
            )
    assert result["mode"] == "fleet"
    assert result["peak_cpu_pct"] is None
    assert result["peak_ram_used_gb"] is None
    assert result["peak_gpu_pct"] is None
    assert result["peak_vram_used_gb"] is None


def test_run_test_fleet_mode_sampler_not_started() -> None:
    """In fleet mode, sampler.start() must never be called."""
    mock_post = MagicMock()
    mock_post.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    sampler = _mock_sampler()
    with patch("hermia.runner.requests.post", return_value=mock_post):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            run_test("qwen2.5:32b", _BASE_TEST, sampler, host="http://100.71.60.30:11434")
    sampler.start.assert_not_called()
    sampler.stop.assert_not_called()


# ---------------------------------------------------------------------------
# hermia-rpr: raw_prompt and raw_response capture
# ---------------------------------------------------------------------------


def test_run_test_has_raw_prompt_equal_to_test_prompt() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": '{"ok": true}', "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["raw_prompt"] == _BASE_TEST["prompt"]


def test_run_test_has_raw_response_equal_to_full_output() -> None:
    long_output = '{"action": "x"}' + "x" * 200
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": long_output, "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["raw_response"] == long_output
    assert len(result["raw_response"]) > 120


def test_run_test_raw_response_empty_on_timeout() -> None:
    with patch("hermia.runner.requests.post", side_effect=requests.exceptions.Timeout):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["raw_prompt"] == _BASE_TEST["prompt"]
    assert result["raw_response"] == ""


def test_run_test_raw_response_empty_on_error() -> None:
    with patch("hermia.runner.requests.post", side_effect=RuntimeError("boom")):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["raw_prompt"] == _BASE_TEST["prompt"]
    assert result["raw_response"] == ""


def test_run_test_raw_response_empty_on_ollama_error() -> None:
    """Ollama error in response body must zero out raw_response even if output is non-empty."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": "partial output", "eval_count": 0, "error": "model not found"
    }
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["failure_reason"].startswith("OLLAMA_ERROR")
    assert result["raw_response"] == ""


def test_run_test_fleet_mode_vram_server_gb_populated() -> None:
    """vram_server_gb comes from /api/ps even in fleet mode."""
    mock_post = MagicMock()
    mock_post.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    mock_get = MagicMock()
    mock_get.json.return_value = {
        "models": [{"name": "qwen2.5:32b", "size_vram": 10_737_418_240}]  # 10 GiB
    }
    with patch("hermia.runner.requests.post", return_value=mock_post):
        with patch("hermia.runner.requests.get", return_value=mock_get):
            result = run_test(
                "qwen2.5:32b", _BASE_TEST, _mock_sampler(),
                host="http://100.71.60.30:11434"
            )
    assert result["vram_server_gb"] is not None
    assert abs(result["vram_server_gb"] - 10.0) < 0.01


def test_run_test_local_mode_still_collects_metrics() -> None:
    """In local mode, local hardware fields are not None."""
    mock_post = MagicMock()
    mock_post.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    sampler = _mock_sampler(cpu=42.0, ram=16.5, gpu=90.0, vram=22.3)
    with patch("hermia.runner.requests.post", return_value=mock_post):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test(
                "qwen2.5:32b", _BASE_TEST, sampler,
                host="http://localhost:11434"
            )
    assert result["mode"] == "local"
    assert result["peak_cpu_pct"] == 42.0
    assert result["peak_ram_used_gb"] == 16.5
    assert result["peak_gpu_pct"] == 90.0
    assert result["peak_vram_used_gb"] == 22.3


# hermia-aud: raw_system capture + None-guard
# ---------------------------------------------------------------------------


def test_run_test_has_raw_system_equal_to_test_system() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": '{"ok": true}', "eval_count": 5, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["raw_system"] == _BASE_TEST["system"]


def test_run_test_response_null_coerced_to_empty_string() -> None:
    """Ollama sends {"response": null} — must not crash; raw_response and output_preview are ""."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": None, "eval_count": 0, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["raw_response"] == ""
    assert result["output_preview"] == ""
