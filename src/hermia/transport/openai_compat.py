"""OpenAI-compatible HTTP transport — calls /v1/chat/completions (LiteLLM, vLLM, cloud APIs)."""
from __future__ import annotations

import time
from typing import Any

import requests

from hermia.transport.base import Response, TransportError


class OpenAICompatTransport:
    is_api_mode: bool = True

    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self._base_url = base_url.rstrip("/").removesuffix("/v1")
        self._headers = headers or {}

    def list_models(self) -> list[str]:
        """Discover model ids via ``GET /v1/models`` (OpenAI-standard listing).

        Lightweight metadata call — uses a short timeout, not generate()'s 90s.
        Tolerates a malformed body (non-dict, missing/``null`` ``data``, non-dict
        or id-less elements) by returning what it can rather than raising. Raises
        ``TransportError`` only on an explicit in-body ``error`` (HTTP errors
        propagate via ``raise_for_status``).
        """
        resp = requests.get(  # nosec B113 — short fixed timeout below
            f"{self._base_url}/v1/models",
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            # Non-JSON 200 (empty body, HTML error page) — honor the tolerate-
            # malformed-body contract rather than raising.
            return []
        if not isinstance(data, dict):
            return []
        if data.get("error"):
            raise TransportError(str(data["error"]), kind="openai-compat")
        items = data.get("data")
        if not isinstance(items, list):
            return []
        return [
            it["id"]
            for it in items
            if isinstance(it, dict) and isinstance(it.get("id"), str)
        ]

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
            timeout=float(opts.get("timeout", 90)),  # type: ignore[arg-type]
        )
        resp.raise_for_status()
        elapsed = time.monotonic() - t0
        data = resp.json()
        if not isinstance(data, dict):
            data = {}
        if data.get("error"):
            # Gateways (LiteLLM, etc.) can return HTTP 200 with an error body.
            raise TransportError(str(data["error"]), kind="openai-compat")
        choices_raw = data.get("choices")
        choices: list[Any] = choices_raw if isinstance(choices_raw, list) else []
        first = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = first.get("message")
        text: str = message.get("content") or "" if isinstance(message, dict) else ""
        # .get(default) does not catch an explicit JSON null; coerce with `or 0`.
        usage = data.get("usage")
        tokens: int = usage.get("completion_tokens") or 0 if isinstance(usage, dict) else 0
        return Response(
            text=text,
            tokens=tokens,
            elapsed_sec=elapsed,
            orchestration="openai-compat",
            orchestration_version=None,
            is_api_mode=True,
        )
