from __future__ import annotations

from .base import Response


class OpenAICompatTransport:
    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        raise NotImplementedError

    def generate(self, model: str, messages: list[dict[str, str]], **opts: object) -> Response:
        raise NotImplementedError
