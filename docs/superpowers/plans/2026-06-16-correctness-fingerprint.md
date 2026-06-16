# Correctness Fingerprint + Sidecar Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Ollama API probe that captures model identity (digest, quant, arch, chat template) and offload state per row, with a `_provenance` sidecar map documenting where every value came from.

**Architecture:** New `fingerprint/` package with per-engine probe modules behind a shared interface. The Ollama probe calls `/api/show` + `/api/ps`, maps results to a `ProbeResult` dataclass, and `assemble.py` merges probe data with fleet YAML declared values into a `stack_fingerprint` dict + `_provenance` dict. An in-memory `FingerprintCache` avoids redundant HTTP calls across repeats/tests for the same (host, model).

**Tech Stack:** Python 3.14, requests, pytest, dataclasses, hashlib (sha256)

**Spec:** `docs/superpowers/specs/2026-06-16-correctness-fingerprint-design.md`

**Commit convention:** `PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "..."`. Test vars must avoid `secret`/`token`/`password` — use `sentinel`/`marker`. Run tests with `-p no:cacheprovider --no-cov`.

---

### Task 1: ProbeResult dataclass and base protocol

**Files:**
- Create: `src/hermia/fingerprint/__init__.py`
- Create: `src/hermia/fingerprint/types.py`
- Create: `src/hermia/fingerprint/probes/__init__.py`
- Create: `src/hermia/fingerprint/probes/base.py`
- Test: `tests/unit/fingerprint/__init__.py`
- Test: `tests/unit/fingerprint/test_types.py`

- [ ] **Step 1: Create test directories and init files**

```bash
mkdir -p src/hermia/fingerprint/probes
mkdir -p tests/unit/fingerprint
touch src/hermia/fingerprint/__init__.py
touch src/hermia/fingerprint/probes/__init__.py
touch tests/unit/fingerprint/__init__.py
```

- [ ] **Step 2: Write failing test for ProbeResult**

Create `tests/unit/fingerprint/test_types.py`:

```python
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
        assert False, "ProbeResult should be frozen"
    except AttributeError:
        pass
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/fingerprint/test_types.py -v -p no:cacheprovider --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'hermia.fingerprint.types'`

- [ ] **Step 4: Implement ProbeResult**

Create `src/hermia/fingerprint/types.py`:

```python
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
```

Create `src/hermia/fingerprint/probes/base.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/fingerprint/test_types.py -v -p no:cacheprovider --no-cov`
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/hermia/fingerprint/__init__.py src/hermia/fingerprint/types.py \
  src/hermia/fingerprint/probes/__init__.py src/hermia/fingerprint/probes/base.py \
  tests/unit/fingerprint/__init__.py tests/unit/fingerprint/test_types.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(fingerprint): ProbeResult dataclass and EngineProbe protocol"
```

---

### Task 2: Ollama probe

**Files:**
- Create: `src/hermia/fingerprint/probes/ollama.py`
- Test: `tests/unit/fingerprint/test_probes_ollama.py`

- [ ] **Step 1: Write failing tests for Ollama probe**

Create `tests/unit/fingerprint/test_probes_ollama.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fingerprint/test_probes_ollama.py -v -p no:cacheprovider --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'hermia.fingerprint.probes.ollama'`

- [ ] **Step 3: Implement OllamaProbe**

Create `src/hermia/fingerprint/probes/ollama.py`:

```python
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
        show = self._fetch_show(host, model, hdrs)
        ps = self._fetch_ps(host, model, hdrs)
        return self._build_result(show, ps, engine_version)

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fingerprint/test_probes_ollama.py -v -p no:cacheprovider --no-cov`
Expected: 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/hermia/fingerprint/probes/ollama.py tests/unit/fingerprint/test_probes_ollama.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(fingerprint): Ollama probe — /api/show + /api/ps"
```

---

### Task 3: Assemble fingerprint + provenance from probe result and declared values

**Files:**
- Create: `src/hermia/fingerprint/assemble.py`
- Test: `tests/unit/fingerprint/test_assemble.py`

- [ ] **Step 1: Write failing tests for assemble**

Create `tests/unit/fingerprint/test_assemble.py`:

```python
"""Tests for fingerprint assembly — layered merge + provenance."""

from hermia.fingerprint.assemble import assemble_fingerprint
from hermia.fingerprint.types import ProbeResult


def _full_probe() -> ProbeResult:
    return ProbeResult(
        digest="sha256:abc",
        architecture="qwen2",
        family="qwen2",
        parameter_count=7_000_000_000,
        parameter_size="7.0B",
        quant_method="Q4_K_M",
        quant_level="Q4_K_M",
        context_length=32768,
        chat_template="{{ .Prompt }}",
        chat_template_hash="deadbeef",
        engine="ollama",
        engine_version="0.6.2",
        residency_ratio=1.0,
        execution_path="gpu",
    )


# ── Probe-only (no declared block) ──────────────────────────────────────────

def test_assemble_probe_only() -> None:
    fp, prov = assemble_fingerprint(_full_probe(), declared=None)
    assert fp["fingerprint_schema_version"] == 1
    assert fp["model"]["digest"] == "sha256:abc"
    assert fp["model"]["architecture"] == "qwen2"
    assert fp["model"]["chat_template_hash"] == "deadbeef"
    assert fp["runtime"]["engine"] == "ollama"
    assert fp["runtime"]["engine_version"] == "0.6.2"
    assert fp["offload"]["residency_ratio"] == 1.0
    assert fp["offload"]["execution_path"] == "gpu"
    assert prov["model.digest"] == "api"
    assert prov["model.chat_template_hash"] == "computed"
    assert prov["offload.execution_path"] == "computed"
    assert prov["runtime.engine"] == "api"


# ── Declared-only (probe failed) ────────────────────────────────────────────

def test_assemble_declared_only_probe_empty() -> None:
    declared = {
        "compute_backend": {"type": "cuda"},
        "substrate": {
            "delivery": "tailscale",
            "compute_topology": "single-node",
        },
    }
    fp, prov = assemble_fingerprint(ProbeResult(), declared=declared)
    assert fp["model"]["digest"] is None
    assert prov["model.digest"] is None
    assert fp["compute_backend"]["type"] == "cuda"
    assert prov["compute_backend.type"] == "declared"
    assert fp["substrate"]["delivery"] == "tailscale"
    assert prov["substrate.delivery"] == "declared"


# ── Probe + declared ────────────────────────────────────────────────────────

def test_assemble_probe_plus_declared() -> None:
    """Probe wins where both supply a value."""
    declared = {
        "compute_backend": {"type": "rocm"},
        "substrate": {"delivery": "lan", "compute_topology": "single-node"},
    }
    fp, prov = assemble_fingerprint(_full_probe(), declared=declared)
    assert fp["model"]["digest"] == "sha256:abc"
    assert prov["model.digest"] == "api"
    assert fp["compute_backend"]["type"] == "rocm"
    assert prov["compute_backend.type"] == "declared"
    assert fp["substrate"]["delivery"] == "lan"
    assert prov["substrate.delivery"] == "declared"


# ── Computed provenance ──────────────────────────────────────────────────────

def test_computed_provenance_for_derived_fields() -> None:
    fp, prov = assemble_fingerprint(_full_probe(), declared=None)
    assert prov["model.chat_template_hash"] == "computed"
    assert prov["offload.execution_path"] == "computed"


# ── Structural invariant ────────────────────────────────────────────────────

def _collect_leaf_paths(d: dict, prefix: str = "") -> set[str]:
    """Recursively collect dotted paths to leaf values (non-dict)."""
    paths: set[str] = set()
    for k, v in d.items():
        if k == "fingerprint_schema_version":
            continue
        full = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, dict):
            paths |= _collect_leaf_paths(v, full)
        else:
            paths.add(full)
    return paths


def test_every_fingerprint_field_has_provenance() -> None:
    """Structural invariant: every leaf field in stack_fingerprint has a _provenance entry."""
    declared = {
        "compute_backend": {"type": "cuda"},
        "substrate": {
            "delivery": "tailscale",
            "compute_topology": "single-node",
            "abstraction_tier": "bare-metal",
        },
    }
    fp, prov = assemble_fingerprint(_full_probe(), declared=declared)
    fp_paths = _collect_leaf_paths(fp)
    prov_paths = set(prov.keys())
    missing = fp_paths - prov_paths
    assert not missing, f"Fields in stack_fingerprint missing from _provenance: {missing}"


def test_provenance_api_error_on_show_failure() -> None:
    """When probe returns empty (API error), model provenance entries are None."""
    fp, prov = assemble_fingerprint(ProbeResult(), declared=None)
    assert fp["model"]["digest"] is None
    assert prov["model.digest"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fingerprint/test_assemble.py -v -p no:cacheprovider --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'hermia.fingerprint.assemble'`

- [ ] **Step 3: Implement assemble_fingerprint**

Create `src/hermia/fingerprint/assemble.py`:

```python
"""Assemble stack_fingerprint + _provenance from probe result and declared values."""

from __future__ import annotations

from typing import Any

from hermia.fingerprint.types import ProbeResult

FINGERPRINT_SCHEMA_VERSION = 1

_COMPUTED_FIELDS = {"model.chat_template_hash", "offload.execution_path"}


def assemble_fingerprint(
    probe: ProbeResult,
    declared: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    """Build stack_fingerprint dict and _provenance sidecar.

    Returns (fingerprint, provenance).
    """
    decl = declared or {}
    decl_backend = decl.get("compute_backend") or {}
    decl_substrate = decl.get("substrate") or {}

    fingerprint: dict[str, Any] = {
        "fingerprint_schema_version": FINGERPRINT_SCHEMA_VERSION,
        "model": {
            "digest": probe.digest,
            "architecture": probe.architecture,
            "family": probe.family,
            "parameter_count": probe.parameter_count,
            "parameter_size": probe.parameter_size,
            "quant_method": probe.quant_method,
            "quant_level": probe.quant_level,
            "context_length": probe.context_length,
            "chat_template": probe.chat_template,
            "chat_template_hash": probe.chat_template_hash,
        },
        "runtime": {
            "engine": probe.engine,
            "engine_version": probe.engine_version,
        },
        "offload": {
            "residency_ratio": probe.residency_ratio,
            "execution_path": probe.execution_path,
        },
        "compute_backend": {
            "type": decl_backend.get("type"),
        },
        "substrate": {
            "delivery": decl_substrate.get("delivery"),
            "compute_topology": decl_substrate.get("compute_topology"),
            "abstraction_tier": decl_substrate.get("abstraction_tier"),
        },
    }

    provenance: dict[str, str | None] = {}
    _set_provenance_group(provenance, "model", fingerprint["model"], probe, "api")
    _set_provenance_group(provenance, "runtime", fingerprint["runtime"], probe, "api")
    _set_provenance_group(provenance, "offload", fingerprint["offload"], probe, "api")
    _set_provenance_declared(provenance, "compute_backend", fingerprint["compute_backend"])
    _set_provenance_declared(provenance, "substrate", fingerprint["substrate"])

    for path in _COMPUTED_FIELDS:
        if provenance.get(path) is not None:
            provenance[path] = "computed"

    return fingerprint, provenance


def _set_provenance_group(
    provenance: dict[str, str | None],
    prefix: str,
    group: dict[str, Any],
    probe: ProbeResult,
    source: str,
) -> None:
    for key, value in group.items():
        path = f"{prefix}.{key}"
        if value is not None:
            provenance[path] = source
        else:
            provenance[path] = None


def _set_provenance_declared(
    provenance: dict[str, str | None],
    prefix: str,
    group: dict[str, Any],
) -> None:
    for key, value in group.items():
        path = f"{prefix}.{key}"
        if value is not None:
            provenance[path] = "declared"
        else:
            provenance[path] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fingerprint/test_assemble.py -v -p no:cacheprovider --no-cov`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/hermia/fingerprint/assemble.py tests/unit/fingerprint/test_assemble.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(fingerprint): assemble fingerprint + provenance from probe and declared"
```

---

### Task 4: FingerprintCache

**Files:**
- Create: `src/hermia/fingerprint/cache.py`
- Test: `tests/unit/fingerprint/test_cache.py`

- [ ] **Step 1: Write failing tests for FingerprintCache**

Create `tests/unit/fingerprint/test_cache.py`:

```python
"""Tests for FingerprintCache — in-memory (host, model) keyed cache."""

from unittest.mock import MagicMock, call, patch

from hermia.fingerprint.cache import FingerprintCache
from hermia.fingerprint.types import ProbeResult


def _dummy_fp() -> dict:
    return {"fingerprint_schema_version": 1, "model": {"digest": "sha256:abc"}}


def _dummy_prov() -> dict:
    return {"model.digest": "api"}


def test_cache_miss_calls_probe() -> None:
    cache = FingerprintCache()
    with patch.object(cache, "_do_probe", return_value=(_dummy_fp(), _dummy_prov())) as mock_probe:
        fp, prov = cache.get_or_probe("http://host:11434", "m1", declared=None,
                                       engine_version="0.6.2")
    mock_probe.assert_called_once_with("http://host:11434", "m1", None, "0.6.2")
    assert fp["model"]["digest"] == "sha256:abc"


def test_cache_hit_skips_probe() -> None:
    cache = FingerprintCache()
    with patch.object(cache, "_do_probe", return_value=(_dummy_fp(), _dummy_prov())) as mock_probe:
        fp1, _ = cache.get_or_probe("http://host:11434", "m1", declared=None,
                                     engine_version="0.6.2")
        fp2, _ = cache.get_or_probe("http://host:11434", "m1", declared=None,
                                     engine_version="0.6.2")
    mock_probe.assert_called_once()
    assert fp1 is fp2


def test_cache_different_model_triggers_new_probe() -> None:
    cache = FingerprintCache()

    fp_m1 = {"fingerprint_schema_version": 1, "model": {"digest": "sha256:m1"}}
    fp_m2 = {"fingerprint_schema_version": 1, "model": {"digest": "sha256:m2"}}

    returns = [(fp_m1, {"model.digest": "api"}), (fp_m2, {"model.digest": "api"})]
    with patch.object(cache, "_do_probe", side_effect=returns) as mock_probe:
        r1, _ = cache.get_or_probe("http://host:11434", "m1", declared=None,
                                    engine_version="0.6.2")
        r2, _ = cache.get_or_probe("http://host:11434", "m2", declared=None,
                                    engine_version="0.6.2")
    assert mock_probe.call_count == 2
    assert r1["model"]["digest"] == "sha256:m1"
    assert r2["model"]["digest"] == "sha256:m2"


def test_cache_different_host_triggers_new_probe() -> None:
    cache = FingerprintCache()
    with patch.object(cache, "_do_probe", return_value=(_dummy_fp(), _dummy_prov())) as mock_probe:
        cache.get_or_probe("http://h1:11434", "m1", declared=None, engine_version="0.6.2")
        cache.get_or_probe("http://h2:11434", "m1", declared=None, engine_version="0.6.2")
    assert mock_probe.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fingerprint/test_cache.py -v -p no:cacheprovider --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'hermia.fingerprint.cache'`

- [ ] **Step 3: Implement FingerprintCache**

Create `src/hermia/fingerprint/cache.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fingerprint/test_cache.py -v -p no:cacheprovider --no-cov`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/hermia/fingerprint/cache.py tests/unit/fingerprint/test_cache.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(fingerprint): in-memory FingerprintCache per (host, model)"
```

---

### Task 5: Wire fingerprint into `__init__.py` public API

**Files:**
- Modify: `src/hermia/fingerprint/__init__.py`

- [ ] **Step 1: Write the public API exports**

Update `src/hermia/fingerprint/__init__.py`:

```python
"""Fingerprint package — model identity, offload, and provenance probing."""

from hermia.fingerprint.assemble import assemble_fingerprint
from hermia.fingerprint.cache import FingerprintCache
from hermia.fingerprint.probes.ollama import OllamaProbe
from hermia.fingerprint.types import ProbeResult

__all__ = [
    "FingerprintCache",
    "OllamaProbe",
    "ProbeResult",
    "assemble_fingerprint",
]
```

- [ ] **Step 2: Verify imports work**

Run: `python -c "from hermia.fingerprint import FingerprintCache, OllamaProbe, ProbeResult, assemble_fingerprint; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Run all fingerprint tests together**

Run: `pytest tests/unit/fingerprint/ -v -p no:cacheprovider --no-cov`
Expected: All tests PASS (types + probe + assemble + cache)

- [ ] **Step 4: Commit**

```bash
git add src/hermia/fingerprint/__init__.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(fingerprint): public API exports"
```

---

### Task 6: Integrate fingerprint into fleet.py

**Files:**
- Modify: `src/hermia/fleet.py:102-257` (`_run_host_eval`)
- Test: `tests/unit/test_fleet.py` (add integration test)

- [ ] **Step 1: Write failing integration test**

Append to `tests/unit/test_fleet.py`:

```python
def test_run_host_eval_stamps_fingerprint_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stack_fingerprint and _provenance appear on every result row."""
    import hermia.fleet as fleet
    from hermia.results import open_run

    fake_fp = {
        "fingerprint_schema_version": 1,
        "model": {"digest": "sha256:test123"},
        "runtime": {"engine": "ollama"},
        "offload": {"residency_ratio": 1.0},
    }
    fake_prov = {"model.digest": "api", "runtime.engine": "api"}

    captured_rows: list[dict] = []

    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None, **kw):
        return {
            "model": model, "test_id": test["id"], "failure_reason": "",
            "elapsed_sec": 0.1, "tokens_per_sec": 1.0,
            "mode": "fleet",
            "peak_cpu_pct": None, "peak_ram_used_gb": None,
            "peak_gpu_pct": None, "peak_vram_used_gb": None,
        }

    def fake_append(result, jsonl_path, csv_path):
        captured_rows.append(dict(result))

    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)
    monkeypatch.setattr("hermia.results.append_result", fake_append, raising=False)

    # Patch FingerprintCache to return our fake data without HTTP calls
    from hermia.fingerprint.cache import FingerprintCache
    monkeypatch.setattr(
        FingerprintCache, "get_or_probe",
        lambda self, host, model, declared, engine_version=None: (fake_fp, fake_prov),
    )

    jsonl, csv = open_run(tmp_path)
    entry = {"name": "fp-test", "host": "http://localhost:11440"}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )

    assert len(captured_rows) == 1
    row = captured_rows[0]
    assert "stack_fingerprint" in row, "row must contain stack_fingerprint"
    assert row["stack_fingerprint"]["fingerprint_schema_version"] == 1
    assert row["stack_fingerprint"]["model"]["digest"] == "sha256:test123"
    assert "_provenance" in row, "row must contain _provenance"
    assert row["_provenance"]["model.digest"] == "api"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fleet.py::test_run_host_eval_stamps_fingerprint_and_provenance -v -p no:cacheprovider --no-cov`
Expected: FAIL (row doesn't contain `stack_fingerprint` yet)

- [ ] **Step 3: Modify fleet.py to integrate fingerprint**

Add import at the top of `_run_host_eval` (inside the function, where other lazy imports live, around line 121-130):

```python
from hermia.fingerprint import FingerprintCache
```

Create the cache before the model loop (after `sampler = MetricsSampler()`, line 210):

```python
    fp_cache = FingerprintCache()
```

Inside the model loop, before the test loop (after `model = model_entry["name"]`, line 212), add the probe call:

```python
        declared = entry.get("stack")
        orch_version = None  # will be populated from first run_test result
        fingerprint, provenance = fp_cache.get_or_probe(
            host_url, model, declared, engine_version=orch_version,
        )
```

After `result.update(resolve_stack(...))` (line 228-230), add:

```python
                result["stack_fingerprint"] = fingerprint
                result["_provenance"] = provenance
```

Note: `orch_version` starts as None because we don't have it until the first `run_test` returns `orchestration_version`. This is acceptable — the engine version for Ollama is already fetched by `OllamaTransport._fetch_version()` and the probe gets it via the `engine_version` parameter. For the fleet path, the version flows through `run_test -> Response.orchestration_version`. To avoid a chicken-and-egg, we let the cache populate `engine_version` from the probe's own `/api/version` call if None is passed. Update `FingerprintCache._do_probe` to handle this:

Actually, looking at the probe more carefully — the `OllamaProbe` already has `detect()` which calls `/api/version`. We should update the probe to self-fetch the version when `engine_version=None`. Let me adjust the approach:

The simplest solution: pass `engine_version=None` and let the `OllamaProbe.probe()` method call `/api/version` itself if `engine_version` is not provided. This is one extra HTTP call per (host, model), but it's cached by the `FingerprintCache` so it only happens once.

Update `src/hermia/fingerprint/probes/ollama.py` method `probe()`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fleet.py::test_run_host_eval_stamps_fingerprint_and_provenance -v -p no:cacheprovider --no-cov`
Expected: PASS

- [ ] **Step 5: Run all fleet tests to confirm no regressions**

Run: `pytest tests/unit/test_fleet.py tests/unit/test_fleet_concurrency.py -v -p no:cacheprovider --no-cov`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/hermia/fleet.py src/hermia/fingerprint/probes/ollama.py tests/unit/test_fleet.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(fleet): wire fingerprint + provenance into fleet result rows"
```

---

### Task 7: Integrate fingerprint into runner.py (standalone TUI path)

**Files:**
- Modify: `src/hermia/runner.py:272-414` (`run_test`)
- Test: `tests/unit/test_runner.py` (add integration test)

- [ ] **Step 1: Write failing integration test**

Append to `tests/unit/test_runner.py`:

```python
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

    fake_fp = {
        "fingerprint_schema_version": 1,
        "model": {"digest": "sha256:remote"},
    }
    fake_prov = {"model.digest": "api"}

    with patch("hermia.runner._play_turns", return_value=resp), \
         patch("hermia.runner.fetch_server_ps_data",
               return_value={"vram_server_gb": None, "model_size_server_gb": None}), \
         patch("hermia.fingerprint.probes.ollama.OllamaProbe.probe",
               return_value=ProbeResult(digest="sha256:remote", engine="ollama")), \
         patch("hermia.fingerprint.assemble.assemble_fingerprint",
               return_value=(fake_fp, fake_prov)):
        row = run_test(
            "m1", _stub_test_dict(), sampler,
            host="http://remote-host:11434", transport=transport,
            locality="remote",
        )

    assert "stack_fingerprint" in row
    assert row["stack_fingerprint"]["model"]["digest"] == "sha256:remote"
```

Add the missing import at the top of the test file if needed:

```python
from hermia.fingerprint.types import ProbeResult
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_runner.py::test_run_test_standalone_local_stamps_fingerprint tests/unit/test_runner.py::test_run_test_standalone_remote_stamps_fingerprint -v -p no:cacheprovider --no-cov`
Expected: FAIL (row doesn't contain `stack_fingerprint`)

- [ ] **Step 3: Modify runner.py to add fingerprint to standalone path**

Add import near the top of `runner.py` (after line 21):

```python
from hermia.fingerprint.assemble import assemble_fingerprint
from hermia.fingerprint.probes.ollama import OllamaProbe
```

At the end of the `run_test` function, before the `return {` statement (line 380), add the probe call:

```python
    _ollama_probe = OllamaProbe()
    _probe_result = _ollama_probe.probe(_host, model, engine_version=orchestration_version)
    _fp, _prov = assemble_fingerprint(_probe_result, declared=None)
```

Then add to the return dict (inside the `return {` block):

```python
        "stack_fingerprint": _fp,
        "_provenance": _prov,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_runner.py::test_run_test_standalone_local_stamps_fingerprint tests/unit/test_runner.py::test_run_test_standalone_remote_stamps_fingerprint -v -p no:cacheprovider --no-cov`
Expected: PASS

- [ ] **Step 5: Run full runner test suite for regressions**

Run: `pytest tests/unit/test_runner.py -v -p no:cacheprovider --no-cov`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/hermia/runner.py tests/unit/test_runner.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(runner): stamp fingerprint + provenance on standalone TUI rows"
```

---

### Task 8: Full test suite + linting

**Files:** None new — verification only.

- [ ] **Step 1: Run the full test suite**

Run: `pytest -p no:cacheprovider --no-cov`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Run ruff**

Run: `ruff check src/hermia/fingerprint/ tests/unit/fingerprint/`
Expected: No errors

- [ ] **Step 3: Run mypy**

Run: `mypy src/hermia/fingerprint/`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 4: Fix any issues found, then re-run and commit fixes**

```bash
# If fixes needed:
git add -A
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "fix: address lint/type issues in fingerprint package"
```

- [ ] **Step 5: Verify test count increase**

Run: `pytest -p no:cacheprovider --no-cov -q | tail -5`
Expected: Test count should be ~30+ higher than the 1491 baseline (from items #1–3)
