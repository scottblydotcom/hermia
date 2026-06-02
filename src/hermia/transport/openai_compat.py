"""OpenAI-compatible HTTP transport — calls /v1/chat/completions (LiteLLM, vLLM, cloud APIs)."""
from __future__ import annotations

import time

import requests

from hermia.transport.base import Response


class OpenAICompatTransport:
    is_api_mode: bool = True

    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self._base_url = base_url.rstrip("/").removesuffix("/v1")
        self._headers = headers or {}

    def generate(self, model: str, messages: list[dict[str, str]], **opts: object) -> Response:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": opts.get("temperature", 0.1),
        }
        t0 = time.monotonic()
        resp = requests.post(  # nosec B113 — timeout passed via opts.get("timeout", 90)
            f"{self._base_url}/v1/chat/completions",
            json=payload,
            headers=self._headers,
            timeout=opts.get("timeout", 90),
        )
        resp.raise_for_status()
        elapsed = time.monotonic() - t0
        data = resp.json()
        if not isinstance(data, dict):
            data = {}
        choices: list = data.get("choices") or []
        first = choices[0] if choices and isinstance(choices[0], dict) else {}
        text: str = (first.get("message") or {}).get("content") or ""
        tokens: int = (data.get("usage") or {}).get("completion_tokens", 0)
        return Response(
            text=text,
            tokens=tokens,
            elapsed_sec=elapsed,
            orchestration="openai-compat",
            orchestration_version=None,
            is_api_mode=True,
        )
