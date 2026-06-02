"""Ollama HTTP transport — calls /api/chat (message-list semantics)."""
from __future__ import annotations

import threading
import time

import requests

from hermia.transport.base import Response


class OllamaTransport:
    is_api_mode: bool = False

    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = headers or {}
        self._version: str | None = None
        self._version_fetched = False
        self._lock = threading.Lock()

    def _fetch_version(self) -> str | None:
        if not self._version_fetched:
            with self._lock:
                if not self._version_fetched:
                    try:
                        resp = requests.get(
                            f"{self._base_url}/api/version",
                            timeout=3,
                            headers=self._headers,
                        )
                        self._version = resp.json().get("version")
                    except Exception:  # noqa: BLE001
                        self._version = None
                    self._version_fetched = True
        return self._version

    def generate(self, model: str, messages: list[dict[str, str]], **opts: object) -> Response:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": opts.get("temperature", 0.1)},
        }
        t0 = time.monotonic()
        resp = requests.post(
            f"{self._base_url}/api/chat",
            json=payload,
            headers=self._headers,
            timeout=opts.get("timeout", 90),
        )
        resp.raise_for_status()
        elapsed = time.monotonic() - t0
        data = resp.json()
        text: str = (data.get("message") or {}).get("content") or ""
        tokens: int = data.get("eval_count", 0)
        return Response(
            text=text,
            tokens=tokens,
            elapsed_sec=elapsed,
            orchestration="ollama",
            orchestration_version=self._fetch_version(),
            is_api_mode=False,
        )
