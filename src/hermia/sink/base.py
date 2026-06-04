from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Sink(Protocol):
    def write(self, rows: list[dict[str, Any]]) -> None: ...
