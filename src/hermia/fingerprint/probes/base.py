"""Base protocol for engine probes."""

from __future__ import annotations

from typing import Protocol

from hermia.fingerprint.types import ProbeResult


class EngineProbe(Protocol):
    """Interface every engine probe must satisfy."""

    def detect(self, host: str, headers: dict[str, str] | None = None) -> bool:
        """Return True if this engine is running at host."""
        ...

    def probe(
        self,
        host: str,
        model: str,
        *,
        headers: dict[str, str] | None = None,
        engine_version: str | None = None,
    ) -> ProbeResult:
        """Query the engine and return model/runtime/offload data."""
        ...
