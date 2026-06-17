"""Tests for fingerprint type definitions."""

from hermia.fingerprint.types import ProbeResult


def test_probe_result_fields_default_none() -> None:
    """An empty ProbeResult has all fields set to None."""
    result = ProbeResult()
    assert result.digest is None
    assert result.architecture is None
    assert result.family is None
    assert result.parameter_count is None
    assert result.parameter_size is None
    assert result.quant_method is None
    assert result.quant_level is None
    assert result.context_length is None
    assert result.chat_template is None
    assert result.chat_template_hash is None
    assert result.engine == "ollama"
    assert result.engine_version is None
    assert result.residency_ratio is None
    assert result.execution_path is None


def test_probe_result_populated() -> None:
    result = ProbeResult(
        digest="sha256:abc123",
        architecture="llama",
        family="llama",
        parameter_count=8_000_000_000,
        parameter_size="8.0B",
        quant_method="Q4_K_M",
        quant_level="q4_K_M",
        context_length=8192,
        chat_template="{{ if .System }}{{ .System }}{{ end }}{{ .Prompt }}",
        chat_template_hash="deadbeef",
        engine="ollama",
        engine_version="0.6.2",
        residency_ratio=1.0,
        execution_path="gpu",
    )
    assert result.digest == "sha256:abc123"
    assert result.architecture == "llama"
    assert result.execution_path == "gpu"


def test_probe_result_is_frozen() -> None:
    result = ProbeResult()
    try:
        result.digest = "changed"  # type: ignore[misc]
        raise AssertionError("ProbeResult should be frozen")
    except AttributeError:
        pass
