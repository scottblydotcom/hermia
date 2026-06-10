"""Backend stack metadata resolution for fleet eval runs.

Merges fleet YAML ``stack:`` block metadata with live transport data
to produce queryable per-result-row fields: ``gpu_arch``,
``runtime_version``, and a composite ``backend_stack`` summary.
"""

from __future__ import annotations

from typing import Any


def resolve_stack(
    entry: dict[str, Any],
    orchestration_version: str | None = None,
) -> dict[str, str | None]:
    """Merge fleet YAML stack metadata with live query data.

    Returns dict with keys: ``gpu_arch``, ``runtime_version``,
    ``backend_stack``.  ``orchestration`` / ``orchestration_version``
    already exist on the result row — this function does NOT duplicate
    them.
    """
    stack = entry.get("stack")
    if not isinstance(stack, dict):
        stack = {}

    raw_arch = stack.get("gpu_arch")
    gpu_arch = raw_arch if isinstance(raw_arch, str) else None

    raw_rt = stack.get("runtime_version")
    runtime_version = raw_rt if isinstance(raw_rt, str) else None

    components = [orchestration_version, gpu_arch, runtime_version]
    non_none = [c for c in components if c is not None]
    backend_stack = " | ".join(non_none) if non_none else None

    return {
        "gpu_arch": gpu_arch,
        "runtime_version": runtime_version,
        "backend_stack": backend_stack,
    }
