"""Type definitions for the fingerprint package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProbeResult:
    """Data returned by an engine probe.

    All fields default to None (probe failed or field not available).
    The engine field defaults to "ollama" for the 0.2.0 probe.
    """
    digest: str | None = None
    architecture: str | None = None
    family: str | None = None
    parameter_count: int | None = None
    parameter_size: str | None = None
    quant_method: str | None = None
    quant_level: str | None = None
    context_length: int | None = None
    chat_template: str | None = None
    chat_template_hash: str | None = None
    engine: str = "ollama"
    engine_version: str | None = None
    residency_ratio: float | None = None
    execution_path: str | None = None
