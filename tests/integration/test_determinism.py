"""Determinism / stability harness — hermia-gx8.

Same model + same test + same fake-Ollama response must produce
bytewise-identical scoring fields across repeated runs.
"""

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from hermia.runner import run_test
from tests.integration.conftest import _FakeOllamaHandler

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

STABLE_FIELDS: list[str] = [
    "model", "test_id", "dimension", "frameworks",
    "failure_reason", "json_valid", "schema_compliant",
    "tokens", "output_preview",
    "peak_cpu_pct", "peak_ram_used_gb", "peak_gpu_pct", "peak_vram_used_gb",
]


def _mock_sampler(
    cpu: float = 10.0, ram: float = 8.0, gpu: float = 85.0, vram: float = 20.0
) -> MagicMock:
    s = MagicMock()
    s.peak.return_value = {
        "cpu_pct": cpu, "ram_used_gb": ram, "gpu_pct": gpu, "vram_used_gb": vram,
    }
    return s


# ── T1: Stable fields bytewise identical across two runs ──────────────────────

def test_stable_fields_identical(fake_ollama: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    result1 = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    result2 = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    for field in STABLE_FIELDS:
        assert result1[field] == result2[field], f"field '{field}' not deterministic"


# ── T2: tokens_per_sec is computed (non-zero when tokens > 0) ────────────────
# ±5% stability is only meaningful against a real model; against a fake HTTP
# server the elapsed time is pure OS scheduling noise. We assert the field is
# correctly derived (positive when tokens are returned), not that it's stable.

def test_tokens_per_sec_computed(
    fake_ollama: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    result = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    assert result["tokens"] == 42
    assert result["tokens_per_sec"] > 0


# ── T3: Error-path fields are stable ─────────────────────────────────────────

def test_error_path_stable(fake_ollama: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    _FakeOllamaHandler._overrides["generate_status"] = 500
    result1 = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    result2 = run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    for field in ("failure_reason", "json_valid", "schema_compliant", "tokens"):
        assert result1[field] == result2[field], f"error field '{field}' not deterministic"


# ── T4: Two runs complete in under 2 seconds ──────────────────────────────────

def test_two_runs_under_2s(fake_ollama: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermia.runner.OLLAMA_BASE", fake_ollama)
    t0 = time.monotonic()
    run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    run_test("fake-model", TOOL_CALLING_TEST, _mock_sampler())
    assert time.monotonic() - t0 < 2.0
