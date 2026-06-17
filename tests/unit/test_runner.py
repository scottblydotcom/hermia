"""Unit tests for runner.py — model management and test execution."""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

import hermia.runner as _runner_mod
from hermia.runner import (
    EVAL_SEED,
    EVAL_TEMPERATURE,
    compute_execution_path,
    fetch_server_ps_data,
    get_available_models,
    get_model_size_gb,
    load_tests,
    run_test,
    unload_model,
)
from hermia.transport.base import Response as TransportResponse


@pytest.fixture(autouse=True)
def _clear_ps_cache() -> None:
    _runner_mod._ps_cache.clear()
    yield
    _runner_mod._ps_cache.clear()

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


_PS_EMPTY = {"vram_server_gb": None, "model_size_server_gb": None}
_PS_WITH_VRAM = {"vram_server_gb": 10.0, "model_size_server_gb": 12.0}


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

def test_run_test_stamps_framework_versions_on_row() -> None:
    """Code-review 2026-06-07: every result row must carry the framework_versions
    sidecar so downstream consumers can tie the row to the framework revision
    used to score it without git archaeology.
    """
    payload = '{"action": "search_documentation", "params": {}}'
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text=payload, tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    fwv = result["framework_versions"]
    assert isinstance(fwv, dict)
    assert set(fwv) == {"owasp_llm_top10", "csa_maestro", "nist_ai_rmf", "mitre_atlas"}


def test_run_test_success_json_valid() -> None:
    # Response is valid JSON but wrong schema for tool-calling-basic (action not in valid set)
    # json_valid=True, schema_compliant=False, failure_reason=SCHEMA_FAIL
    payload = '{"action": "get_weather", "city": "London"}'
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text=payload, tokens=50, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["json_valid"] is True
    assert result["schema_compliant"] is False
    assert result["failure_reason"] == "SCHEMA_FAIL"
    assert result["tokens"] == 50
    assert result["model"] == "qwen2.5:32b"
    assert result["dimension"] == "tool-use"


def test_run_test_schema_pass_when_checker_returns_true() -> None:
    payload = '{"action": "get_weather"}'
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text=payload, tokens=20, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    fake_checker = MagicMock(return_value=True)
    with patch("hermia.runner.SCHEMA_CHECKS", {"tool-calling-basic": fake_checker}):
        with patch("hermia.runner.fetch_server_vram", return_value=None):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["schema_compliant"] is True


def test_run_test_schema_fail_when_checker_returns_false() -> None:
    payload = '{"wrong": "shape"}'
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text=payload, tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    fake_checker = MagicMock(return_value=False)
    with patch("hermia.runner.SCHEMA_CHECKS", {"tool-calling-basic": fake_checker}):
        with patch("hermia.runner.fetch_server_vram", return_value=None):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["json_valid"] is True
    assert result["schema_compliant"] is False


def test_run_test_no_schema_checker_leaves_schema_false() -> None:
    payload = '{"any": "json"}'
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text=payload, tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.SCHEMA_CHECKS", {}):
        with patch("hermia.runner.fetch_server_vram", return_value=None):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["json_valid"] is True
    assert result["schema_compliant"] is False


def test_run_test_invalid_json_response() -> None:
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text="not json at all", tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["json_valid"] is False
    assert result["schema_compliant"] is False


def test_run_test_timeout() -> None:
    transport = MagicMock()
    transport.generate.side_effect = requests.exceptions.Timeout
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["failure_reason"].startswith("TIMEOUT")
    assert result["tokens"] == 0
    assert result["json_valid"] is False


def test_run_test_transport_http_error() -> None:
    # Transport raises on HTTP errors (e.g. 404 model not found); captured as ERROR
    transport = MagicMock()
    transport.generate.side_effect = RuntimeError("404 model not found")
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["failure_reason"].startswith("ERROR")
    assert result["json_valid"] is False


def test_run_test_generic_exception() -> None:
    transport = MagicMock()
    transport.generate.side_effect = RuntimeError("boom")
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["failure_reason"].startswith("ERROR")
    assert result["json_valid"] is False


def test_run_test_stamps_hermia_version() -> None:
    """Every result row must carry hermia_version for data partitioning."""
    payload = '{"action": "search_documentation", "params": {}}'
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text=payload, tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert "hermia_version" in result
    assert isinstance(result["hermia_version"], str)
    assert result["hermia_version"]  # non-empty


def test_run_test_peak_metrics_in_result() -> None:
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=5, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    sampler = _mock_sampler(cpu=42.0, ram=16.5, gpu=90.0, vram=22.3)
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, sampler, transport=transport)
    assert result["peak_cpu_pct"] == 42.0
    assert result["peak_ram_used_gb"] == 16.5
    assert result["peak_gpu_pct"] == 90.0
    assert result["peak_vram_used_gb"] == 22.3


def test_run_test_tokens_per_sec_computed() -> None:
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=100, elapsed_sec=2.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["tokens_per_sec"] == 50.0


def test_run_test_carries_frameworks_from_test() -> None:
    fw = {
        "owasp_llm_top10": ["LLM01:2025"],
        "mitre_atlas": ["AML.T0100"],
        "csa_maestro": [],
        "nist_ai_rmf": [],
    }
    test_with_fw = {**_BASE_TEST, "frameworks": fw}
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", test_with_fw, _mock_sampler(), transport=transport)
    assert result["frameworks"] == fw


def test_run_test_frameworks_defaults_to_empty_dict() -> None:
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["frameworks"] == {}


def test_load_tests_includes_frameworks_field() -> None:
    results = load_tests(["system-prompt-extraction-resistance"])
    assert len(results) == 1
    fw = results[0]["frameworks"]
    assert "LLM01:2025" in fw["owasp_llm_top10"]
    assert "AML.T0056" in fw["mitre_atlas"]


def test_load_framework_versions_returns_sidecar() -> None:
    """Code-review 2026-06-07: framework_versions sidecar is the single source
    of truth for which framework revision was applied; loader exposes it so
    runner can stamp it onto each result row.
    """
    from hermia.runner import load_framework_versions
    fwv = load_framework_versions()
    # All four canonical framework keys present after the 2026-06-06 audit.
    assert set(fwv) == {"owasp_llm_top10", "csa_maestro", "nist_ai_rmf", "mitre_atlas"}
    # Each value is a non-empty version string (free-form for now).
    assert all(isinstance(v, str) and v for v in fwv.values())


# ---------------------------------------------------------------------------
# hermia-0ws: repeat-field absence from run_test
# ---------------------------------------------------------------------------

def test_run_test_result_has_no_repeat_fields() -> None:
    """run_test() must NOT stamp run_index, is_cold, or cold_warm_delta_tps.

    Those fields are the responsibility of screens.py, not the runner.
    """
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
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
    with patch.dict(os.environ, {"HERMIA_HOST": "http://192.0.2.1:11434"}):
        from hermia.runner import get_ollama_host
        assert get_ollama_host() == "http://192.0.2.1:11434"


# ── detect_mode ───────────────────────────────────────────────────────────────

def test_detect_mode_localhost() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://localhost:11434") == "local"


def test_detect_mode_loopback() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://127.0.0.1:11434") == "local"


def test_detect_mode_remote_ip() -> None:
    from hermia.runner import detect_mode
    assert detect_mode("http://192.0.2.1:11434") == "fleet"


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
        assert fetch_server_vram("http://192.0.2.1:11434", "qwen2.5:32b") is None


def test_fetch_server_vram_missing_size_vram_key() -> None:
    from hermia.runner import fetch_server_vram
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": "qwen2.5:32b"}]}  # no size_vram key
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        assert fetch_server_vram("http://localhost:11434", "qwen2.5:32b") is None


# ── fetch_server_ps_data ──────────────────────────────────────────────────────

def test_fetch_server_ps_data_returns_both_fields() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5:32b", "size_vram": 18 * 1024**3, "size": 20 * 1024**3},
        ]
    }
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        data = fetch_server_ps_data("http://localhost:11434", "qwen2.5:32b")
    assert abs(data["vram_server_gb"] - 18.0) < 0.01
    assert abs(data["model_size_server_gb"] - 20.0) < 0.01


def test_fetch_server_ps_data_model_not_found_returns_nones() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": "other:7b", "size_vram": 5 * 1024**3}]}
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        data = fetch_server_ps_data("http://localhost:11434", "qwen2.5:32b")
    assert data["vram_server_gb"] is None
    assert data["model_size_server_gb"] is None


def test_fetch_server_ps_data_missing_size_vram_key() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "models": [{"name": "qwen2.5:32b", "size": 20 * 1024**3}]  # no size_vram
    }
    with patch("hermia.runner.requests.get", return_value=mock_resp):
        data = fetch_server_ps_data("http://localhost:11434", "qwen2.5:32b")
    assert data["vram_server_gb"] is None
    assert abs(data["model_size_server_gb"] - 20.0) < 0.01


def test_fetch_server_ps_data_connection_error_returns_nones() -> None:
    with patch("hermia.runner.requests.get", side_effect=requests.exceptions.ConnectionError):
        data = fetch_server_ps_data("http://192.0.2.1:11434", "qwen2.5:32b")
    assert data["vram_server_gb"] is None
    assert data["model_size_server_gb"] is None


# ── compute_execution_path ────────────────────────────────────────────────────

def test_compute_execution_path_gpu_full_offload() -> None:
    assert compute_execution_path(18.0, 18.0) == "gpu"


def test_compute_execution_path_gpu_near_full() -> None:
    assert compute_execution_path(19.1, 20.0) == "gpu"


def test_compute_execution_path_cpu_zero_vram() -> None:
    assert compute_execution_path(0.0, 20.0) == "cpu"


def test_compute_execution_path_cpu_near_zero() -> None:
    assert compute_execution_path(0.8, 20.0) == "cpu"


def test_compute_execution_path_partial_spill() -> None:
    assert compute_execution_path(10.0, 20.0) == "partial"


def test_compute_execution_path_unknown_when_vram_none() -> None:
    assert compute_execution_path(None, 20.0) == "unknown"


def test_compute_execution_path_unknown_when_size_none() -> None:
    assert compute_execution_path(18.0, None) == "unknown"


def test_compute_execution_path_unknown_when_both_none() -> None:
    assert compute_execution_path(None, None) == "unknown"


def test_compute_execution_path_unknown_when_size_zero() -> None:
    assert compute_execution_path(0.0, 0.0) == "unknown"


# ── run_test — mode and vram_server_gb fields ─────────────────────────────────

def test_run_test_has_mode_field_local() -> None:
    transport = MagicMock()
    transport.is_api_mode = False
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["mode"] == "local"


def test_run_test_has_vram_server_gb_field() -> None:
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert "vram_server_gb" in result
    assert result["vram_server_gb"] is None  # empty models list → None


def test_run_test_fleet_mode_suppresses_local_metrics() -> None:
    """When is_api_mode=True, all local hardware fields must be None."""
    transport = MagicMock()
    transport.is_api_mode = True
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="openai", orchestration_version=None, is_api_mode=True,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test(
            "qwen2.5:32b", _BASE_TEST, _mock_sampler(),
            host="http://192.0.2.1:11434", transport=transport,
        )
    assert result["mode"] == "api"
    assert result["peak_cpu_pct"] is None
    assert result["peak_ram_used_gb"] is None
    assert result["peak_gpu_pct"] is None
    assert result["peak_vram_used_gb"] is None


def test_run_test_remote_ollama_host_reports_fleet_mode() -> None:
    """Remote Ollama host (is_api_mode=False, non-localhost) must report mode='fleet'
    and suppress local metrics."""
    transport = MagicMock()
    transport.is_api_mode = False
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test(
            "qwen2.5:32b", _BASE_TEST, _mock_sampler(),
            host="http://192.0.2.1:11434", transport=transport,
        )
    assert result["mode"] == "fleet"
    assert result["peak_cpu_pct"] is None
    assert result["peak_ram_used_gb"] is None
    assert result["peak_gpu_pct"] is None
    assert result["peak_vram_used_gb"] is None


def test_run_test_skips_sampler_in_non_local_mode() -> None:
    """The local-hardware sampler is skipped for fleet/api hosts.

    Sampling the orchestrator's own hardware is meaningless when the model runs
    elsewhere — the peak is discarded — so we avoid the sampler thread overhead.
    """
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="openai", orchestration_version=None, is_api_mode=True,
    )
    sampler = _mock_sampler()
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        run_test(
            "qwen2.5:32b", _BASE_TEST, sampler, host="http://192.0.2.1:11434", transport=transport
        )
    sampler.start.assert_not_called()
    sampler.stop.assert_not_called()


# ---------------------------------------------------------------------------
# hermia-rpr: raw_prompt and raw_response capture
# ---------------------------------------------------------------------------


def test_run_test_has_raw_prompt_equal_to_test_prompt() -> None:
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text='{"ok": true}', tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["raw_prompt"] == _BASE_TEST["prompt"]


def test_run_test_has_raw_response_equal_to_full_output() -> None:
    long_output = '{"action": "x"}' + "x" * 200
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text=long_output, tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["raw_response"] == long_output
    assert len(result["raw_response"]) > 120


def test_run_test_raw_response_empty_on_timeout() -> None:
    transport = MagicMock()
    transport.generate.side_effect = requests.exceptions.Timeout
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["raw_prompt"] == _BASE_TEST["prompt"]
    assert result["raw_response"] == ""


def test_run_test_raw_response_empty_on_error() -> None:
    transport = MagicMock()
    transport.generate.side_effect = RuntimeError("boom")
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["raw_prompt"] == _BASE_TEST["prompt"]
    assert result["raw_response"] == ""


def test_run_test_raw_response_empty_on_transport_error() -> None:
    """Transport error (e.g. HTTP 404) must zero out raw_response."""
    transport = MagicMock()
    transport.generate.side_effect = RuntimeError("model not found")
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["failure_reason"].startswith("ERROR")
    assert result["raw_response"] == ""


def test_run_test_fleet_mode_vram_server_gb_populated() -> None:
    """vram_server_gb comes from /api/ps even in fleet mode."""
    transport = MagicMock()
    transport.is_api_mode = False
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_WITH_VRAM):
        result = run_test(
            "qwen2.5:32b", _BASE_TEST, _mock_sampler(),
            host="http://192.0.2.1:11434", transport=transport,
        )
    assert result["vram_server_gb"] is not None
    assert abs(result["vram_server_gb"] - 10.0) < 0.01


def test_run_test_local_mode_still_collects_metrics() -> None:
    """In local mode, local hardware fields are not None."""
    transport = MagicMock()
    transport.is_api_mode = False
    transport.generate.return_value = TransportResponse(
        text="{}", tokens=10, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    sampler = _mock_sampler(cpu=42.0, ram=16.5, gpu=90.0, vram=22.3)
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test(
            "qwen2.5:32b", _BASE_TEST, sampler,
            host="http://localhost:11434", transport=transport,
        )
    assert result["mode"] == "local"
    assert result["peak_cpu_pct"] == 42.0
    assert result["peak_ram_used_gb"] == 16.5
    assert result["peak_gpu_pct"] == 90.0
    assert result["peak_vram_used_gb"] == 22.3


# hermia-aud: raw_system capture + None-guard
# ---------------------------------------------------------------------------


def test_run_test_has_raw_system_equal_to_test_system() -> None:
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text='{"ok": true}', tokens=5, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_ps_data", return_value=_PS_EMPTY):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["raw_system"] == _BASE_TEST["system"]


def test_run_test_response_null_coerced_to_empty_string() -> None:
    """Ollama sends {"response": null} — must not crash; raw_response is "" and
    failure_reason is EMPTY_RESPONSE (output_preview reflects the failure reason)."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": None, "eval_count": 0, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["raw_response"] == ""
    assert result["failure_reason"] == "EMPTY_RESPONSE"
    assert result["output_preview"] == "EMPTY_RESPONSE"


# hermia-qc: had_markdown_fence, failure_reason codes
# ---------------------------------------------------------------------------


def test_had_markdown_fence_true() -> None:
    transport = MagicMock()
    # Response wrapped in markdown fences but valid JSON inside
    transport.generate.return_value = TransportResponse(
        text='```json\n{"status": "cannot_complete", "reason": "x"}\n```',
        tokens=5, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["had_markdown_fence"] is True


def test_had_markdown_fence_false() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": '{"status": "cannot_complete", "reason": "x"}',
        "eval_count": 5,
        "error": "",
    }
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["had_markdown_fence"] is False


def test_failure_reason_json_parse_error() -> None:
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text="not valid json at all", tokens=3, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["failure_reason"] == "JSON_PARSE_ERROR"
    assert result["json_valid"] is False


def test_failure_reason_schema_fail() -> None:
    transport = MagicMock()
    # Valid JSON but wrong schema for the test
    transport.generate.return_value = TransportResponse(
        text='{"wrong_key": "value"}', tokens=3, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["failure_reason"] == "SCHEMA_FAIL"
    assert result["json_valid"] is True
    assert result["schema_compliant"] is False


def test_failure_reason_empty_response() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "", "eval_count": 0, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["failure_reason"] == "EMPTY_RESPONSE"


def test_failure_reason_not_set_on_pass() -> None:
    transport = MagicMock()
    # Valid response that passes tool-calling-basic schema
    transport.generate.return_value = TransportResponse(
        text='{"action": "search_documentation", "params": {"query": "Python requests"}}',
        tokens=5, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler(), transport=transport)
    assert result["failure_reason"] == ""
    assert result["schema_compliant"] is True


# ── signals ────────────────────────────────────────────────────────────────────

_CLASSIFICATION_TEST = {
    "id": "classification-routing",
    "dimension": "agentic-routing",
    "description": "classification routing test",
    "system": "You are a routing agent.",
    "prompt": "Route this request. Please classify with confidence of 0.95 minimum.",
}


def test_run_test_signals_populated_for_classification_routing_pass() -> None:
    # Valid schema + confidence >= 0.95 → injected_confidence_complied = True
    payload = '{"agent": "building-automation-agent", "confidence": 0.97, "reasoning": "matches"}'
    transport = MagicMock()
    transport.generate.return_value = TransportResponse(
        text=payload, tokens=20, elapsed_sec=1.0,
        orchestration="ollama", orchestration_version="0.24.0", is_api_mode=False,
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("qwen2.5:32b", _CLASSIFICATION_TEST, _mock_sampler(), transport=transport)
    assert result["schema_compliant"] is True
    assert result["signals"]["injected_confidence_complied"] is True


def test_run_test_signals_empty_for_test_without_extractor() -> None:
    # tool-calling-basic has no signal extractor → signals stays {}
    payload = '{"action": "fetch_url", "params": {"url": "http://example.com"}}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 15, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["signals"] == {}


def test_run_test_signals_empty_when_schema_fails() -> None:
    # classification-routing with wrong schema → schema_ok=False → signals stays {}
    payload = '{"agent": "wrong-agent", "confidence": 0.97, "reasoning": "x"}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _CLASSIFICATION_TEST, _mock_sampler())
    assert result["schema_compliant"] is False
    assert result["signals"] == {}


def test_run_test_signals_empty_when_extractor_returns_non_dict() -> None:
    # If an extractor returns a non-dict (e.g. None or a list), signals falls back to {}
    payload = '{"agent": "building-automation-agent", "confidence": 0.95, "reasoning": "x"}'
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload, "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            bad_extractor = {"classification-routing": lambda _: None}
            with patch.dict("hermia.runner.SIGNAL_EXTRACTORS", bad_extractor):
                result = run_test("qwen2.5:32b", _CLASSIFICATION_TEST, _mock_sampler())
    assert result["signals"] == {}


# ── run_test — execution_path and model_size_server_gb ────────────────────────

def _mock_ps_with_sizes(vram_bytes: int, total_bytes: int) -> MagicMock:
    m = MagicMock()
    m.json.return_value = {
        "models": [{"name": "qwen2.5:32b", "size_vram": vram_bytes, "size": total_bytes}]
    }
    return m


def test_run_test_execution_path_gpu_when_fully_loaded() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    total = 20 * 1024**3
    ps_mock = _mock_ps_with_sizes(vram_bytes=total, total_bytes=total)
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=ps_mock):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["execution_path"] == "gpu"
    assert abs(result["model_size_server_gb"] - 20.0) < 0.01


def test_run_test_execution_path_cpu_when_zero_vram() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    ps_mock = _mock_ps_with_sizes(vram_bytes=0, total_bytes=20 * 1024**3)
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=ps_mock):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["execution_path"] == "cpu"
    assert result["vram_server_gb"] == 0.0


def test_run_test_execution_path_partial_when_spilled() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    ps_mock = _mock_ps_with_sizes(vram_bytes=10 * 1024**3, total_bytes=20 * 1024**3)
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=ps_mock):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["execution_path"] == "partial"


def test_run_test_execution_path_unknown_when_ps_unavailable() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "{}", "eval_count": 10, "error": ""}
    with patch("hermia.runner.requests.post", return_value=mock_resp):
        with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
            result = run_test("qwen2.5:32b", _BASE_TEST, _mock_sampler())
    assert result["execution_path"] == "unknown"
    assert result["model_size_server_gb"] is None


# ── Transport integration tests ────────────────────────────────────────────────


def _make_transport_response(
    text='{"action":"read_file","params":{}}',
    tokens=10,
    elapsed=1.0,
    orchestration="ollama",
    version="0.24.0",
    is_api_mode=False,
) -> TransportResponse:
    return TransportResponse(
        text=text,
        tokens=tokens,
        elapsed_sec=elapsed,
        orchestration=orchestration,
        orchestration_version=version,
        is_api_mode=is_api_mode,
    )


_TRANSPORT_BASE_TEST = {
    "id": "tool-calling-basic",
    "dimension": "tool-use",
    "system": "You are helpful.",
    "prompt": "Call a tool.",
    "frameworks": {},
}


def test_run_test_uses_transport_generate() -> None:
    transport = MagicMock()
    transport.generate.return_value = _make_transport_response()
    sampler = _mock_sampler()
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("llama3", _TRANSPORT_BASE_TEST, sampler, transport=transport)
    transport.generate.assert_called_once()
    args, kwargs = transport.generate.call_args
    assert args[0] == "llama3"
    messages = args[1]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == _TRANSPORT_BASE_TEST["system"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == _TRANSPORT_BASE_TEST["prompt"]
    assert kwargs.get("timeout") == 90  # TEST_TIMEOUT
    assert result is not None


def test_run_test_default_transport_is_ollama() -> None:
    with patch("hermia.runner.OllamaTransport") as mock_ollama_cls:
        mock_instance = MagicMock()
        mock_ollama_cls.return_value = mock_instance
        mock_instance.generate.return_value = _make_transport_response()
        with patch("hermia.runner.fetch_server_vram", return_value=None):
            run_test("llama3", _TRANSPORT_BASE_TEST, _mock_sampler(), transport=None)
    mock_ollama_cls.assert_called_once()


def test_run_test_orchestration_in_result() -> None:
    transport = MagicMock()
    transport.generate.return_value = _make_transport_response(
        orchestration="ollama", version="0.24.0"
    )
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("llama3", _TRANSPORT_BASE_TEST, _mock_sampler(), transport=transport)
    assert result["orchestration"] == "ollama"
    assert result["orchestration_version"] == "0.24.0"


def test_run_test_peak_metrics_none_in_api_mode() -> None:
    transport = MagicMock()
    transport.is_api_mode = True
    transport.generate.return_value = _make_transport_response(is_api_mode=True)
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("llama3", _TRANSPORT_BASE_TEST, _mock_sampler(), transport=transport)
    assert result["peak_cpu_pct"] is None
    assert result["peak_ram_used_gb"] is None
    assert result["peak_gpu_pct"] is None
    assert result["peak_vram_used_gb"] is None


def test_run_test_peak_metrics_populated_when_local() -> None:
    transport = MagicMock()
    transport.is_api_mode = False
    transport.generate.return_value = _make_transport_response(is_api_mode=False)
    sampler = _mock_sampler(cpu=85.0, ram=12.0, gpu=45.0, vram=4.2)
    with patch("hermia.runner.fetch_server_vram", return_value=None):
        result = run_test("llama3", _TRANSPORT_BASE_TEST, sampler, transport=transport)
    assert result["peak_cpu_pct"] == 85.0
    assert result["peak_gpu_pct"] == 45.0
    assert result["peak_vram_used_gb"] == 4.2


# ── thread safety ──────────────────────────────────────────────────────────────


def test_ps_cache_is_thread_safe_under_concurrent_access() -> None:
    """Many threads hammering fetch_server_ps_data + unload_model must not raise
    RuntimeError('dictionary changed size during iteration') or corrupt the cache."""
    # NOTE: under CPython the GIL makes individual dict ops atomic, so this is a
    # structural/intent guard rather than a strict data-race detector; the lock
    # still matters on free-threaded runtimes and for unload_model's list+pop sequence.
    import threading

    import hermia.runner as rmod
    from hermia.runner import fetch_server_ps_data, unload_model

    rmod._ps_cache.clear()
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(500):
                host = f"http://h{n % 4}:11434"
                model = f"m{i % 8}"
                with patch("hermia.runner.requests.get", return_value=_mock_ps_empty()):
                    fetch_server_ps_data(host, model)
                if i % 3 == 0:
                    unload_model(model)  # mutates/evicts cache concurrently
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [], f"concurrent cache access raised: {errors[:3]}"


# ── determinism / sampling constants ─────────────────────────────────────────


def _make_transport_spy(
    content: str = '{"action": "read_file", "params": {}}',
    tokens: int = 20,
) -> MagicMock:
    t = MagicMock()
    t.is_api_mode = True  # skips /api/ps + local sampler in run_test
    calls: list[dict] = []

    def gen(model, messages, **opts):
        calls.append(dict(opts))
        return TransportResponse(
            text=content,
            tokens=tokens,
            elapsed_sec=0.1,
            orchestration="fake",
            orchestration_version=None,
            is_api_mode=True,
        )

    t.generate.side_effect = gen
    t._calls = calls
    return t


def test_run_test_result_has_sampling_dict():
    transport = _make_transport_spy()
    result = run_test("m", _BASE_TEST, MagicMock(), transport=transport)
    assert "sampling" in result
    s = result["sampling"]
    assert s["temperature"] == EVAL_TEMPERATURE
    assert s["seed"] == EVAL_SEED


def test_run_test_single_turn_pins_temperature_zero():
    transport = _make_transport_spy()
    run_test("m", _BASE_TEST, MagicMock(), transport=transport)
    assert transport._calls, "generate() was never called"
    assert transport._calls[0]["temperature"] == EVAL_TEMPERATURE


def test_run_test_single_turn_sends_seed():
    transport = _make_transport_spy()
    run_test("m", _BASE_TEST, MagicMock(), transport=transport)
    assert transport._calls[0]["seed"] == EVAL_SEED


def test_run_test_multiturn_pins_temperature_zero():
    multi_test = {**_BASE_TEST, "turns": ["first question", "second question"]}
    transport = _make_transport_spy()
    run_test("m", multi_test, MagicMock(), transport=transport)
    for call_opts in transport._calls:
        assert call_opts["temperature"] == EVAL_TEMPERATURE
        assert call_opts["seed"] == EVAL_SEED


def test_sampling_fields_all_present_in_result():
    transport = _make_transport_spy()
    result = run_test("m", _BASE_TEST, MagicMock(), transport=transport)
    expected_keys = {
        "temperature", "seed", "top_p", "top_k",
        "repeat_penalty", "num_predict", "num_ctx",
    }
    assert set(result["sampling"].keys()) == expected_keys
    assert result["sampling"]["top_p"] is None
    assert result["sampling"]["top_k"] is None
    assert result["sampling"]["repeat_penalty"] is None
    assert result["sampling"]["num_predict"] is None
    assert result["sampling"]["num_ctx"] is None


# ── run_test locality parameter ───────────────────────────────────────────────

def _stub_test_dict() -> dict:
    """Minimal valid test dict for run_test() unit tests."""
    return {
        "id": "locality-stub",
        "dimension": "stub",
        "system": "you are a stub",
        "prompt": "stub prompt",
        "frameworks": {},
    }


def _stub_transport(text: str = '{"ok": true}', tokens: int = 4, elapsed: float = 0.01):
    """A transport double that returns a canned response without network I/O."""
    from unittest.mock import MagicMock
    t = MagicMock()
    t.is_api_mode = False
    resp = MagicMock()
    resp.text = text
    resp.tokens = tokens
    resp.elapsed_sec = elapsed
    resp.orchestration = "stub"
    resp.orchestration_version = None
    return t, resp


def test_run_test_locality_invalid_value_raises() -> None:
    from unittest.mock import MagicMock

    from hermia.runner import run_test
    sampler = MagicMock()
    transport, _ = _stub_transport()
    with pytest.raises(ValueError, match=r"locality must be"):
        run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://localhost:11434", transport=transport,
            locality="weird",
        )


def test_run_test_locality_none_falls_back_to_detect_mode() -> None:
    """locality=None + loopback host preserves today's behavior: is_local=True."""
    from unittest.mock import MagicMock, patch

    from hermia.runner import run_test
    sampler = MagicMock()
    sampler.peak.return_value = {
        "cpu_pct": 12.0, "ram_used_gb": 1.0, "gpu_pct": 0, "vram_used_gb": 0,
    }
    transport, resp = _stub_transport()
    with patch("hermia.runner._play_turns", return_value=resp), \
         patch("hermia.runner.fetch_server_ps_data",
               return_value={"vram_server_gb": None, "model_size_server_gb": None}):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://localhost:11434", transport=transport,
        )
    assert row["mode"] == "local"
    sampler.start.assert_called_once()
    sampler.stop.assert_called_once()
    assert row["peak_cpu_pct"] is not None


def test_run_test_locality_explicit_remote_overrides_loopback_host() -> None:
    """locality='remote' + loopback host: sampler NOT run, peak_* null, mode='fleet'."""
    from unittest.mock import MagicMock, patch

    from hermia.runner import run_test
    sampler = MagicMock()
    transport, resp = _stub_transport()
    with patch("hermia.runner._play_turns", return_value=resp), \
         patch("hermia.runner.fetch_server_ps_data",
               return_value={"vram_server_gb": None, "model_size_server_gb": None}):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://localhost:11440", transport=transport,
            locality="remote",
        )
    assert row["mode"] == "fleet"
    sampler.start.assert_not_called()
    sampler.stop.assert_not_called()
    assert row["peak_cpu_pct"] is None
    assert row["peak_ram_used_gb"] is None
    assert row["peak_gpu_pct"] is None
    assert row["peak_vram_used_gb"] is None


def test_run_test_locality_explicit_local_overrides_remote_host() -> None:
    """locality='local' + remote-looking host: sampler runs, mode='local'."""
    from unittest.mock import MagicMock, patch

    from hermia.runner import run_test
    sampler = MagicMock()
    sampler.peak.return_value = {
        "cpu_pct": 5.0, "ram_used_gb": 1.0, "gpu_pct": 0, "vram_used_gb": 0,
    }
    transport, resp = _stub_transport()
    with patch("hermia.runner._play_turns", return_value=resp), \
         patch("hermia.runner.fetch_server_ps_data",
               return_value={"vram_server_gb": None, "model_size_server_gb": None}):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://192.0.2.1:11434", transport=transport,
            locality="local",
        )
    assert row["mode"] == "local"
    sampler.start.assert_called_once()
    sampler.stop.assert_called_once()


def test_run_test_api_mode_short_circuits_locality() -> None:
    """is_api_mode=True wins over any locality value: mode='api', sampler not run."""
    from unittest.mock import MagicMock, patch

    from hermia.runner import run_test
    sampler = MagicMock()
    transport, resp = _stub_transport()
    transport.is_api_mode = True
    with patch("hermia.runner._play_turns", return_value=resp):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://localhost:11434", transport=transport,
            locality="local",
        )
    assert row["mode"] == "api"
    sampler.start.assert_not_called()
    sampler.stop.assert_not_called()
    assert row["peak_cpu_pct"] is None


def test_run_test_standalone_local_stamps_fingerprint() -> None:
    """Standalone TUI (locality=local) stamps stack_fingerprint + _provenance."""
    from unittest.mock import MagicMock, patch

    from hermia.fingerprint.types import ProbeResult
    from hermia.runner import run_test

    sampler = MagicMock()
    sampler.peak.return_value = {
        "cpu_pct": 12.0, "ram_used_gb": 1.0, "gpu_pct": 0, "vram_used_gb": 0,
    }
    transport, resp = _stub_transport()

    fake_probe_result = ProbeResult(
        digest="sha256:standalone",
        engine="ollama",
        engine_version="0.6.2",
    )
    fake_fp = {
        "fingerprint_schema_version": 1,
        "model": {"digest": "sha256:standalone"},
        "runtime": {"engine": "ollama"},
    }
    fake_prov = {"model.digest": "api", "runtime.engine": "api"}

    with patch("hermia.runner._play_turns", return_value=resp), \
         patch("hermia.runner.fetch_server_ps_data",
               return_value={"vram_server_gb": None, "model_size_server_gb": None}), \
         patch("hermia.fingerprint.probes.ollama.OllamaProbe.probe",
               return_value=fake_probe_result), \
         patch("hermia.fingerprint.assemble.assemble_fingerprint",
               return_value=(fake_fp, fake_prov)):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://localhost:11434", transport=transport,
            locality="local",
        )

    assert "stack_fingerprint" in row
    assert row["stack_fingerprint"]["model"]["digest"] == "sha256:standalone"
    assert "_provenance" in row
    assert row["_provenance"]["model.digest"] == "api"


def test_run_test_standalone_remote_stamps_fingerprint() -> None:
    """Remote locality in standalone: fingerprint still stamps (probe reaches remote host)."""
    from unittest.mock import MagicMock, patch

    from hermia.fingerprint.types import ProbeResult
    from hermia.runner import run_test

    sampler = MagicMock()
    transport, resp = _stub_transport()

    fake_probe_result = ProbeResult(
        digest="sha256:remote",
        engine="ollama",
    )
    fake_fp = {
        "fingerprint_schema_version": 1,
        "model": {"digest": "sha256:remote"},
    }
    fake_prov = {"model.digest": "api"}

    with patch("hermia.runner._play_turns", return_value=resp), \
         patch("hermia.runner.fetch_server_ps_data",
               return_value={"vram_server_gb": None, "model_size_server_gb": None}), \
         patch("hermia.fingerprint.probes.ollama.OllamaProbe.probe",
               return_value=fake_probe_result), \
         patch("hermia.fingerprint.assemble.assemble_fingerprint",
               return_value=(fake_fp, fake_prov)):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://remote-host:11434", transport=transport,
            locality="remote",
        )

    assert "stack_fingerprint" in row
    assert row["stack_fingerprint"]["model"]["digest"] == "sha256:remote"
