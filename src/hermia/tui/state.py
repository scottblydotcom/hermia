"""
In-memory data structures for the hermia TUI state management.

FleetConfig serves as the central in-memory source of truth for the current
edit session. HostSource and ModelSource are protocol interfaces for
extending data sources in v0.3+ (Kwaainet registry, recommendation engine,
MCP-sourced data).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ModelChoice:
    name: str
    selected: bool = False
    size_bytes: int | None = None
    quant: str | None = None
    family: str | None = None
    modality: str | None = None


@dataclass
class Host:
    name: str
    url: str
    engine: str
    auth_header_env: str | None = None
    hardware: str | None = None
    # Fleet YAML `stack:` block (gpu_arch / runtime_version). Carried so a TUI
    # run can resolve backend_stack the way the CLI does; previously dropped on
    # load, leaving TUI rows with no backend provenance (hermia-0hqm).
    stack: dict[str, Any] | None = None
    models: list[ModelChoice] = field(default_factory=list)


@dataclass
class FleetConfig:
    name: str
    hosts: list[Host] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    repeat: int = 1


@runtime_checkable
class HostSource(Protocol):
    async def list_hosts(self) -> list[Host]:
        ...


@runtime_checkable
class ModelSource(Protocol):
    async def list_models(self, host: Host) -> list[ModelChoice]:
        ...
