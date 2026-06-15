from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

SAMPLING_SCHEMA_KEYS: tuple[str, ...] = (
    "temperature", "seed", "top_p", "top_k", "repeat_penalty", "num_predict", "num_ctx"
)


@dataclass(frozen=True)
class Response:
    text: str
    tokens: int
    elapsed_sec: float
    orchestration: str
    orchestration_version: str | None
    is_api_mode: bool


class TransportError(Exception):
    """Raised when a transport receives an in-body error from the backend.

    ``kind`` identifies the originating transport ("ollama", "openai-compat")
    so the runner can preserve backend-specific failure classification.
    """

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


@runtime_checkable
class Transport(Protocol):
    is_api_mode: bool

    def generate(self, model: str, messages: list[dict[str, str]], **opts: object) -> Response:
        ...
