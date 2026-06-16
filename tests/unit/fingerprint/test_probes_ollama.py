"""Tests for the Ollama engine probe — runs against captured fixture data."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from hermia.fingerprint.probes.ollama import OllamaProbe


# ── Fixtures ─────────────────────────────────────────────────────────────────

SHOW_RESPONSE_FULL = {
    "digest": "sha256:abc123def456",
    "model_info": {
        "general.architecture": "qwen2",
        "general.family": "qwen2",
        "general.parameter_count": 7_615_616_000,
        "general.file_type": 15,
        "general.context_length": 32768,
    },
    "details": {
        "parameter_size": "7.6B",
        "quantization_level": "Q4_K_M",
    },
    "template": '{{ if .System }}<|im_start|>system\n{{ .System }}<|im_end|>\n{{ end }}<|im_start|>user\n{{ .Prompt }}<|im_end|>\n<|im_start|>assistant\n',
}

PS_RESPONSE_GPU = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "size": 5_000_000_000,
            "size_vram": 5_000_000_000,
        }
    ]
}

PS_RESPONSE_PARTIAL = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "size": 10_000_000_000,
            "size_vram": 7_000_000_000,
        }
    ]
}

PS_RESPONSE_CPU_OMITTED = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "size": 5_000_000_000,
            # size_vram intentionally OMITTED — Ollama #4840
        }
    ]
}

PS_RESPONSE_EMPTY = {"models": []}


# ── Tests ────────────────────────────────────────────────────────────────────


def _mock_requests_post(show_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.ok = True
    resp.json.return_value = show_data
    return resp


def _mock_requests_get(ps_data: dict | None = None, version: str = "0.6.2") -> MagicMock:
    """Returns a side_effect function that handles /api/ps and /api/version."""
    def side_effect(url, **kwargs):
        resp = MagicMock()
        resp.ok = True
        if "/api/ps" in url:
            resp.json.return_value = ps_data if ps_data is not None else PS_RESPONSE_EMPTY
        elif "/api/version" in url:
            resp.json.return_value = {"version": version}
        return resp
    return side_effect


def test_probe_full_gpu() -> None:
    """Happy path: all fields present, model fully GPU-resident."""
    probe = OllamaProbe()
    with patch("hermia.fingerprint.probes.ollama.requests.post",
               return_value=_mock_requests_post(SHOW_RESPONSE_FULL)), \
         patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=_mock_requests_get(PS_RESPONSE_GPU)):
        result = probe.probe("http://localhost:11434", "qwen2.5:7b",
                             engine_version="0.6.2")

    assert result.digest == "sha256:abc123def456"
    assert result.architecture == "qwen2"
    assert result.family == "qwen2"
    assert result.parameter_count == 7_615_616_000
    assert result.parameter_size == "7.6B"
    assert result.quant_method == "Q4_K_M"
    assert result.quant_level == "Q4_K_M"
    assert result.context_length == 32768
    assert result.chat_template == SHOW_RESPONSE_FULL["template"]
    expected_hash = hashlib.sha256(SHOW_RESPONSE_FULL["template"].encode()).hexdigest()
    assert result.chat_template_hash == expected_hash
    assert result.engine == "ollama"
    assert result.engine_version == "0.6.2"
    assert result.residency_ratio == 1.0
    assert result.execution_path == "gpu"


def test_probe_partial_offload() -> None:
    probe = OllamaProbe()
    with patch("hermia.fingerprint.probes.ollama.requests.post",
               return_value=_mock_requests_post(SHOW_RESPONSE_FULL)), \
         patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=_mock_requests_get(PS_RESPONSE_PARTIAL)):
        result = probe.probe("http://localhost:11434", "qwen2.5:7b",
                             engine_version="0.6.2")

    assert result.residency_ratio == pytest.approx(0.7)
    assert result.execution_path == "partial"


def test_probe_cpu_only_size_vram_omitted() -> None:
    """Ollama #4840: size_vram missing (not zero) when pure CPU."""
    probe = OllamaProbe()
    with patch("hermia.fingerprint.probes.ollama.requests.post",
               return_value=_mock_requests_post(SHOW_RESPONSE_FULL)), \
         patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=_mock_requests_get(PS_RESPONSE_CPU_OMITTED)):
        result = probe.probe("http://localhost:11434", "qwen2.5:7b",
                             engine_version="0.6.2")

    assert result.residency_ratio == 0.0
    assert result.execution_path == "cpu"


def test_probe_model_not_loaded() -> None:
    """Model not in /api/ps — offload fields null, model fields still present."""
    probe = OllamaProbe()
    with patch("hermia.fingerprint.probes.ollama.requests.post",
               return_value=_mock_requests_post(SHOW_RESPONSE_FULL)), \
         patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=_mock_requests_get(PS_RESPONSE_EMPTY)):
        result = probe.probe("http://localhost:11434", "qwen2.5:7b",
                             engine_version="0.6.2")

    assert result.digest == "sha256:abc123def456"
    assert result.residency_ratio is None
    assert result.execution_path is None


def test_probe_minimal_show_response() -> None:
    """Some model_info fields missing — graceful nulls."""
    minimal_show = {"digest": "sha256:minimal", "model_info": {}, "details": {}}
    probe = OllamaProbe()
    with patch("hermia.fingerprint.probes.ollama.requests.post",
               return_value=_mock_requests_post(minimal_show)), \
         patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=_mock_requests_get(PS_RESPONSE_EMPTY)):
        result = probe.probe("http://localhost:11434", "qwen2.5:7b",
                             engine_version="0.6.2")

    assert result.digest == "sha256:minimal"
    assert result.architecture is None
    assert result.family is None
    assert result.parameter_count is None
    assert result.quant_method is None
    assert result.chat_template is None
    assert result.chat_template_hash is None


def test_probe_show_api_error_returns_empty_probe_result() -> None:
    """If /api/show fails, probe returns all-None (never raises)."""
    probe = OllamaProbe()
    import requests as req_mod
    with patch("hermia.fingerprint.probes.ollama.requests.post",
               side_effect=req_mod.ConnectionError("refused")), \
         patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=_mock_requests_get(PS_RESPONSE_EMPTY)):
        result = probe.probe("http://localhost:11434", "qwen2.5:7b",
                             engine_version="0.6.2")

    assert result.digest is None
    assert result.architecture is None
    assert result.engine == "ollama"
    assert result.engine_version == "0.6.2"


def test_probe_ps_api_error_leaves_offload_null() -> None:
    """If /api/ps fails, offload fields are null but model fields still present."""
    probe = OllamaProbe()
    import requests as req_mod

    def get_side_effect(url, **kwargs):
        if "/api/ps" in url:
            raise req_mod.ConnectionError("refused")
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {"version": "0.6.2"}
        return resp

    with patch("hermia.fingerprint.probes.ollama.requests.post",
               return_value=_mock_requests_post(SHOW_RESPONSE_FULL)), \
         patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=get_side_effect):
        result = probe.probe("http://localhost:11434", "qwen2.5:7b",
                             engine_version="0.6.2")

    assert result.digest == "sha256:abc123def456"
    assert result.residency_ratio is None
    assert result.execution_path is None


def test_chat_template_hash_known_value() -> None:
    """Verify sha256 hash for a known template string."""
    template = "{{ .Prompt }}"
    expected = hashlib.sha256(template.encode()).hexdigest()
    show = {"digest": "sha256:x", "model_info": {}, "details": {}, "template": template}
    probe = OllamaProbe()
    with patch("hermia.fingerprint.probes.ollama.requests.post",
               return_value=_mock_requests_post(show)), \
         patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=_mock_requests_get(PS_RESPONSE_EMPTY)):
        result = probe.probe("http://localhost:11434", "m1",
                             engine_version="0.6.2")

    assert result.chat_template_hash == expected


def test_detect_ollama() -> None:
    """detect() returns True when /api/version responds."""
    probe = OllamaProbe()
    with patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=_mock_requests_get()):
        assert probe.detect("http://localhost:11434") is True


def test_detect_not_ollama() -> None:
    """detect() returns False on connection error."""
    probe = OllamaProbe()
    import requests as req_mod
    with patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=req_mod.ConnectionError("refused")):
        assert probe.detect("http://localhost:11434") is False
