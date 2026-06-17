"""In-memory fingerprint cache — avoids redundant API probes within a run."""

from __future__ import annotations

from typing import Any

from hermia.fingerprint.assemble import assemble_fingerprint
from hermia.fingerprint.probes.ollama import OllamaProbe
from hermia.fingerprint.types import ProbeResult

_FP_PAIR = tuple[dict[str, Any], dict[str, str | None]]


class FingerprintCache:
    """Cache fingerprint results per (host, model, engine) for the duration of a run."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], _FP_PAIR] = {}
        self._probe = OllamaProbe()

    def get_or_probe(
        self,
        host: str,
        model: str,
        declared: dict[str, Any] | None,
        engine_version: str | None = None,
        headers: dict[str, str] | None = None,
        engine: str | None = None,
    ) -> _FP_PAIR:
        # Cache key is (host, model, engine) — auth headers are a transport
        # detail and not part of fingerprint identity. Engine is included so a
        # single host serving both engines (rare but possible) doesn't collide.
        engine_key = engine or "ollama"
        key = (host, model, engine_key)
        if key in self._store:
            return self._store[key]
        result = self._do_probe(host, model, declared, engine_version, headers, engine)
        self._store[key] = result
        return result

    def _do_probe(
        self,
        host: str,
        model: str,
        declared: dict[str, Any] | None,
        engine_version: str | None,
        headers: dict[str, str] | None,
        engine: str | None = None,
    ) -> _FP_PAIR:
        # Engine dispatch: only "ollama" (or unset → default ollama for the
        # standalone TUI) gets a live probe. Other engines (openai-compat,
        # future vLLM/llama.cpp/SGLang) return an honest all-null ProbeResult
        # with the engine name stamped, avoiding doomed /api/show + /api/ps
        # round-trips to endpoints that don't exist.
        if engine is None or engine == "ollama":
            probe_result = self._probe.probe(
                host, model, headers=headers, engine_version=engine_version,
            )
            return assemble_fingerprint(probe_result, declared)
        # Null-probe path: the engine string came from fleet YAML (transport hint),
        # not an API response. Correct the provenance vocabulary so consumers
        # auditing _provenance don't see 'api' for a value that was declared.
        probe_result = ProbeResult(engine=engine, engine_version=engine_version)
        fingerprint, provenance = assemble_fingerprint(probe_result, declared)
        if provenance.get("runtime.engine") is not None:
            provenance["runtime.engine"] = "declared"
        if provenance.get("runtime.engine_version") is not None:
            provenance["runtime.engine_version"] = "declared"
        return fingerprint, provenance
