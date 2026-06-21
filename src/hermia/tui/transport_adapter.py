"""Engine-aware transport factory for the Fleet TUI probe layer.

Maps a Host to a transport object with `async list_models() -> list[str]`,
which is what hermia.tui.probe.probe_host needs.

For v0.2 we ship two probe shapes:
    - Ollama         /api/tags     → list of {"name": str, ...}
    - OpenAI-compat  /v1/models    → {"data": [{"id": str, ...}, ...]}

vLLM / SGLang / LiteLLM all speak the OpenAI shape, so any non-"ollama"
engine falls back to the openai-compat path.

Implementation: uses stdlib `urllib.request` wrapped in `asyncio.to_thread`
rather than `httpx`. `httpx` is NOT in pyproject.toml and AGENTS.md rule 3
blocks adding deps without approval. urllib is stdlib; the thread offload
keeps probe_host's async contract intact.

Per spec §6 / probe.py docstring, this adapter normalizes transport
exceptions to the stdlib classes probe.py catches:
    - HTTP 401/403            → PermissionError
    - timeout / network error → urllib.error.URLError (an OSError subclass)
                                propagates and is caught by probe.py's
                                (OSError, ConnectionError) handler.
    - asyncio.wait_for timeout → TimeoutError (probe.py handles)

Auth header is resolved from the environment variable named by
host.auth_header_env. Per AGENTS.md rule 11, the secret value never appears
in any saved config — only the env var name does.
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from hermia.tui.state import Host

# Cap urlopen.read() so a misbehaving (or malicious) host cannot stream an
# unbounded body and OOM the TUI. 10 MiB is generous for /v1/models or
# /api/tags (typical responses are <10 KiB).
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024


@dataclass
class _BaseProbeTransport:
    url: str
    auth_header: str | None = None

    def _fetch_sync(self, path: str) -> dict[str, Any]:
        # SSRF guard: urlopen supports `file://`, `ftp://`, etc. If a user
        # accidentally (or maliciously) sets host.url to file:///etc/passwd
        # we'd happily read it. Force http(s) only.
        parsed = urllib.parse.urlparse(self.url)
        if parsed.scheme not in ("http", "https"):
            raise urllib.error.URLError(
                f"Unsupported protocol scheme: {parsed.scheme!r} (only http/https allowed)"
            )
        # The S310/B310 suppressions below are justified: the URL scheme has
        # been validated above as http(s); we are not opening arbitrary
        # schemes like file://.
        url = f"{self.url.rstrip('/')}{path}"
        req = urllib.request.Request(url)  # noqa: S310
        if self.auth_header:
            req.add_header("Authorization", self.auth_header)
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:  # noqa: S310  # nosec B310
                try:
                    # Cap the read to _MAX_RESPONSE_BYTES — a malicious or
                    # misbehaving host cannot OOM the TUI by streaming an
                    # unbounded body.
                    data: dict[str, Any] = json.loads(resp.read(_MAX_RESPONSE_BYTES))
                except json.JSONDecodeError as exc:
                    # Non-JSON body (HTML error page from a misbehaving proxy,
                    # truncated response, etc). Convert to URLError so probe.py's
                    # (OSError, ConnectionError) handler treats it as offline
                    # rather than letting it bubble as `unexpected`.
                    raise urllib.error.URLError(
                        f"Invalid JSON response from {self.url}"
                    ) from exc
                return data
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise PermissionError(f"{exc.code} from {self.url}") from exc
            raise


class OllamaProbeTransport(_BaseProbeTransport):
    async def list_models(self) -> list[str]:
        data = await asyncio.to_thread(self._fetch_sync, "/api/tags")
        return [m["name"] for m in data.get("models", [])]


class OpenAICompatProbeTransport(_BaseProbeTransport):
    async def list_models(self) -> list[str]:
        data = await asyncio.to_thread(self._fetch_sync, "/v1/models")
        return [m["id"] for m in data.get("data", [])]


def transport_for(host: Host) -> _BaseProbeTransport:
    """Return a probe transport for this host's engine + auth setup."""
    auth_header: str | None = None
    if host.auth_header_env:
        token = os.environ.get(host.auth_header_env)
        if token:
            auth_header = f"Bearer {token}"
    cls = OllamaProbeTransport if host.engine == "ollama" else OpenAICompatProbeTransport
    return cls(url=host.url, auth_header=auth_header)
