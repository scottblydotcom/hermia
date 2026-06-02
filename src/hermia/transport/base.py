from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Response:
    text: str
    tokens: int
    elapsed_sec: float
    orchestration: str
    orchestration_version: str | None
    is_api_mode: bool


@runtime_checkable
class Transport(Protocol):
    is_api_mode: bool

    def generate(self, model: str, messages: list[dict[str, str]], **opts: object) -> Response:
        ...
