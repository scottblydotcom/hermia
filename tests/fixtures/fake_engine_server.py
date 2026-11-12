"""A local HTTP server that answers like Ollama and an OpenAI-compatible engine, and records
every request it receives, including the Authorization header (hermia-bw1q).

It exists so tests can check WHERE a token was sent, not just whether a function was called:
the defects it guards against are requests that should never have been made.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# A reply the tool-calling-basic test grades as a pass, so a test can tell "the trial ran and
# succeeded" from "the trial reached the server and failed".
ANSWER = '{"action": "search_documentation", "params": {}}'

# Shapes follow a real Ollama (0.40.6, checked 2026-11-11): /api/show has NO "digest" key; only
# /api/tags and /api/ps carry one. An earlier version of this fixture put a digest in /api/show,
# so a cache rule keyed on it passed here and never cached a real probe (PR #222 review).
_ROUTES: dict[tuple[str, str], dict[str, Any]] = {
    ("GET", "/api/version"): {"version": "0.40.6"},
    ("GET", "/api/tags"): {"models": [{"name": "m", "digest": "sha256:abc"}]},
    ("POST", "/api/show"): {
        "model_info": {"general.architecture": "llama"},
        "details": {"parameter_size": "8B", "quantization_level": "Q4_K_M"},
    },
    ("GET", "/api/ps"): {
        "models": [{
            "name": "m", "digest": "sha256:abc",
            "size": 4 * 1024**3, "size_vram": 4 * 1024**3,
        }],
    },
    ("POST", "/api/chat"): {
        "message": {"role": "assistant", "content": ANSWER},
        "eval_count": 5,
        "done": True,
    },
    ("POST", "/v1/chat/completions"): {
        "choices": [{"message": {"role": "assistant", "content": ANSWER}}],
        "usage": {"completion_tokens": 3},
    },
}


@dataclass
class FakeEngineServer:
    url: str
    seen: list[tuple[str, str, str | None]] = field(default_factory=list)

    def paths(self) -> list[str]:
        return [path for _, path, _ in self.seen]


@contextmanager
def fake_engine_server(*, fail_show: int = 0) -> Iterator[FakeEngineServer]:
    """Yield a running server; ``seen`` holds (method, path, Authorization or None).

    ``fail_show``: answer the first N POST /api/show with 500, as a host does while it is briefly
    unavailable, so a test can tell a retried probe from a cached failure.
    """
    seen: list[tuple[str, str, str | None]] = []
    show_failures_left = [fail_show]

    class Handler(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            seen.append((self.command, self.path, self.headers.get("Authorization")))
            body = _ROUTES.get((self.command, self.path))
            status = 200 if body is not None else 404
            if (self.command, self.path) == ("POST", "/api/show") and show_failures_left[0] > 0:
                show_failures_left[0] -= 1
                body, status = {"error": "temporarily unavailable"}, 500
            payload = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = _answer  # noqa: N815

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield FakeEngineServer(url=f"http://127.0.0.1:{server.server_address[1]}", seen=seen)
    finally:
        server.shutdown()
        server.server_close()
