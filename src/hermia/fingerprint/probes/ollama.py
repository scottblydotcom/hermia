"""Ollama engine probe — /api/show + /api/ps → ProbeResult."""

from __future__ import annotations

import hashlib

import requests

from hermia.fingerprint.types import ProbeResult

_QUANT_FILE_TYPE_MAP: dict[int, str] = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1",
    7: "Q8_0", 8: "Q5_0", 9: "Q5_1", 10: "Q2_K",
    11: "Q3_K_S", 12: "Q3_K_M", 13: "Q3_K_L",
    14: "Q4_K_S", 15: "Q4_K_M", 16: "Q5_K_S",
    17: "Q5_K_M", 18: "Q6_K", 19: "IQ2_XXS",
    20: "IQ2_XS", 24: "IQ1_S",
}


class OllamaProbe:
    """Probe an Ollama instance for model identity and offload state."""

    def detect(self, host: str, headers: dict[str, str] | None = None) -> bool:
        try:
            resp = requests.get(
                f"{host}/api/version", timeout=3, headers=headers or {},
            )
            return resp.ok
        except Exception:  # noqa: BLE001
            return False

    def probe(
        self,
        host: str,
        model: str,
        *,
        headers: dict[str, str] | None = None,
        engine_version: str | None = None,
    ) -> ProbeResult:
        hdrs = headers or {}
        if engine_version is None:
            engine_version = self._fetch_version(host, hdrs)
        show = self._fetch_show(host, model, hdrs)
        ps = self._fetch_ps(host, model, hdrs)
        return self._build_result(show, ps, engine_version)

    def _fetch_version(self, host: str, headers: dict[str, str]) -> str | None:
        try:
            resp = requests.get(
                f"{host}/api/version", timeout=3, headers=headers,
            )
            if resp.ok:
                return resp.json().get("version")
        except Exception:  # noqa: BLE001
            pass
        return None

    def _fetch_show(
        self, host: str, model: str, headers: dict[str, str],
    ) -> dict | None:
        try:
            resp = requests.post(
                f"{host}/api/show",
                json={"name": model},
                timeout=5,
                headers=headers,
            )
            if resp.ok:
                return resp.json()
        except Exception:  # noqa: BLE001
            pass
        return None

    def _fetch_ps(
        self, host: str, model: str, headers: dict[str, str],
    ) -> dict | None:
        try:
            resp = requests.get(
                f"{host}/api/ps", timeout=3, headers=headers,
            )
            if not resp.ok:
                return None
            data = resp.json()
            for m in data.get("models", []):
                if isinstance(m, dict) and m.get("name") == model:
                    return m
        except Exception:  # noqa: BLE001
            pass
        return None

    def _build_result(
        self,
        show: dict | None,
        ps_entry: dict | None,
        engine_version: str | None,
    ) -> ProbeResult:
        if show is None:
            return ProbeResult(engine="ollama", engine_version=engine_version)

        info = show.get("model_info") or {}
        details = show.get("details") or {}

        file_type_int = info.get("general.file_type")
        quant_method = _QUANT_FILE_TYPE_MAP.get(file_type_int) if isinstance(file_type_int, int) else None
        quant_level = details.get("quantization_level")

        template = show.get("template")
        template_hash = (
            hashlib.sha256(template.encode()).hexdigest()
            if isinstance(template, str) else None
        )

        residency_ratio: float | None = None
        execution_path: str | None = None
        if ps_entry is not None:
            size = ps_entry.get("size", 0)
            size_vram = ps_entry.get("size_vram", 0)  # missing = 0 (Ollama #4840)
            if size and size > 0:
                residency_ratio = round(size_vram / size, 4)
                if residency_ratio >= 0.95:
                    execution_path = "gpu"
                elif residency_ratio <= 0.05:
                    execution_path = "cpu"
                else:
                    execution_path = "partial"

        return ProbeResult(
            digest=show.get("digest"),
            architecture=info.get("general.architecture"),
            family=info.get("general.family"),
            parameter_count=info.get("general.parameter_count"),
            parameter_size=details.get("parameter_size"),
            quant_method=quant_method or quant_level,
            quant_level=quant_level,
            context_length=info.get("general.context_length"),
            chat_template=template if isinstance(template, str) else None,
            chat_template_hash=template_hash,
            engine="ollama",
            engine_version=engine_version,
            residency_ratio=residency_ratio,
            execution_path=execution_path,
        )
