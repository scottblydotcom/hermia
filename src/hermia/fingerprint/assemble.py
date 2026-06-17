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
    _set_provenance_group(provenance, "model", fingerprint["model"], "api")
    _set_provenance_group(provenance, "runtime", fingerprint["runtime"], "api")
    _set_provenance_group(provenance, "offload", fingerprint["offload"], "api")
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
