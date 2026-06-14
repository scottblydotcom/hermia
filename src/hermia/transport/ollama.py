"""Ollama HTTP transport — calls /api/chat (message-list semantics)."""
from __future__ import annotations

import threading
import time

import requests

from hermia.transport.base import SAMPLING_SCHEMA_KEYS, Response, TransportError

_OLLAMA_SAMPLING_KEYS = SAMPLING_SCHEMA_KEYS


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
        sampling: dict[str, object] = {
            key: opts[key] for key in _OLLAMA_SAMPLING_KEYS
            if key in opts and opts[key] is not None
        }
        if "temperature" not in sampling:
            sampling["temperature"] = 0.1
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": sampling,
        }
        t0 = time.monotonic()
        resp = requests.post(  # nosec B113 — timeout passed via opts.get("timeout", 90)
            f"{self._base_url}/api/chat",
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
            raise TransportError(str(data["error"]), kind="ollama")
        message = data.get("message")
        text: str = message.get("content") or "" if isinstance(message, dict) else ""
        # .get(default) does not catch an explicit JSON null; coerce with `or 0`.
        tokens: int = data.get("eval_count") or 0
        return Response(
            text=text,
            tokens=tokens,
            elapsed_sec=elapsed,
            orchestration="ollama",
            orchestration_version=self._fetch_version(),
            is_api_mode=False,
        )
