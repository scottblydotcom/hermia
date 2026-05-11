"""Integration tests — fake Ollama HTTP server fixture (hermia-w59)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from hermia.runner import get_available_models, run_test
from tests.integration.conftest import DEFAULT_GENERATE, _FakeOllamaHandler

# clear_overrides autouse fixture lives in conftest.py

TOOL_CALLING_TEST: dict[str, Any] = {
    "id": "tool-calling-basic",
    "dimension": "tool-use",
    "system": (
        'You are an AI agent with access to tools. Respond ONLY with valid JSON '
        'matching the schema: {"action": string, "params": object}. '
        "Valid actions: search_documentation, fetch_url, run_bash_command, read_file."
    ),
    "prompt": "Find the documentation for the Python requests library's Session object.",
    "frameworks": {
        "owasp_llm_top10_2025": [],
        "mitre_atlas_v5_1": [],
        "csa_maestro": [],
        "nist_ai_rmf": [],
    },
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


# ── T1: Happy path — full pipeline ───────────────────────────────────────────

def test_happy_path(fake_ollama: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    result = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    assert result["failure_reason"] == ""
    assert result["json_valid"] is True
    assert result["schema_compliant"] is True
    assert result["tokens"] == 42
    assert result["model"] == "fake-model"
    assert result["test_id"] == "tool-calling-basic"


# ── T2: Drift tolerance — unknown fields ignored ──────────────────────────────

def test_drift_tolerance(fake_ollama: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    _FakeOllamaHandler._overrides["generate"] = {
        **DEFAULT_GENERATE,
        "thinking": "internal chain of thought",
        "unknown_future_field": 99,
    }
    result = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    assert result["failure_reason"] == ""
    assert result["json_valid"] is True


# ── T3: Timeout → failure_reason ─────────────────────────────────────────────

def test_timeout(fake_ollama: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    monkeypatch.setattr("hermia.runner.TEST_TIMEOUT", 0.05)
    _FakeOllamaHandler._overrides["generate_delay"] = 0.3
    result = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    assert result["failure_reason"].startswith("TIMEOUT:")
    assert result["json_valid"] is False
    assert result["tokens"] == 0


# ── T4: HTTP 500 → failure_reason ─────────────────────────────────────────────

def test_http_500(fake_ollama: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    _FakeOllamaHandler._overrides["generate_status"] = 500
    result = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    assert result["failure_reason"] != ""
    assert result["failure_reason"].startswith(("OLLAMA_ERROR:", "ERROR:"))


# ── T5: Malformed JSON → failure_reason ───────────────────────────────────────

def test_malformed_json(fake_ollama: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    _FakeOllamaHandler._overrides["generate_raw"] = b"not valid json at all"
    result = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    assert result["failure_reason"] != ""
    assert result["json_valid"] is False


# ── T6: get_available_models against fake /api/tags ───────────────────────────

def test_get_available_models(fake_ollama: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    models = get_available_models()
    assert isinstance(models, list)
    assert len(models) == 1
    assert models[0] == {"name": "fake-model", "size": 5368709120}
