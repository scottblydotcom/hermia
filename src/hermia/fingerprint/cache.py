"""In-memory fingerprint cache — avoids redundant API probes within a run."""

from __future__ import annotations

from typing import Any

from hermia.fingerprint.assemble import assemble_fingerprint
from hermia.fingerprint.probes.ollama import OllamaProbe
from hermia.fingerprint.types import ProbeResult

_FP_PAIR = tuple[dict[str, Any], dict[str, str | None]]


class FingerprintCache:
    """Cache fingerprint results per (host, model) for the duration of a run."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], _FP_PAIR] = {}
        self._probe = OllamaProbe()

    def get_or_probe(
        self,
        host: str,
        model: str,
        declared: dict[str, Any] | None,
        engine_version: str | None = None,
    ) -> _FP_PAIR:
        key = (host, model)
        if key in self._store:
            return self._store[key]
        result = self._do_probe(host, model, declared, engine_version)
        self._store[key] = result
        return result

    def _do_probe(
        self,
        host: str,
        model: str,
        declared: dict[str, Any] | None,
        engine_version: str | None,
    ) -> _FP_PAIR:
        probe_result = self._probe.probe(
            host, model, engine_version=engine_version,
        )
        return assemble_fingerprint(probe_result, declared)
