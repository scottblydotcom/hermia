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


def test_assemble_malformed_declared_does_not_crash() -> None:
    """Malformed fleet YAML (non-dict stack / nested fields) must degrade to null,
    not raise AttributeError mid-run."""
    # stack itself is a string
    fp, prov = assemble_fingerprint(ProbeResult(), declared="not-a-dict")  # type: ignore[arg-type]
    assert fp["compute_backend"]["type"] is None
    assert prov["compute_backend.type"] is None

    # nested fields are strings
    declared = {"compute_backend": "cuda", "substrate": "tailscale"}
    fp, prov = assemble_fingerprint(ProbeResult(), declared=declared)
    assert fp["compute_backend"]["type"] is None
    assert fp["substrate"]["delivery"] is None
    assert prov["substrate.delivery"] is None


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
