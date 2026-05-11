import http.server
import json
import threading
import time
from typing import Any

import pytest

DEFAULT_GENERATE: dict[str, Any] = {
    "model": "fake-model",
    "created_at": "2026-01-01T00:00:00Z",
    "response": '{"action": "search_documentation", "params": {"query": "requests Session"}}',
    "done": True,
    "eval_count": 42,
    "eval_duration": 1000000000,
}

DEFAULT_TAGS: dict[str, Any] = {
    "models": [{"name": "fake-model", "size": 5368709120}]
}


class _FakeOllamaHandler(http.server.BaseHTTPRequestHandler):
    _overrides: dict[str, Any] = {}

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(content_length)

        if self.path == "/api/generate":
            status = self._overrides.get("generate_status", 200)

            delay = self._overrides.get("generate_delay")
            if delay is not None:
                time.sleep(delay)

            raw: bytes | None = self._overrides.get("generate_raw")
            if raw is not None:
                body = raw
            elif status != 200:
                body = json.dumps({"error": "model not found"}).encode()
            else:
                body = json.dumps(self._overrides.get("generate", DEFAULT_GENERATE)).encode()

            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_GET(self) -> None:
        if self.path == "/api/tags":
            body = json.dumps(self._overrides.get("tags", DEFAULT_TAGS)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture(autouse=True)
def clear_overrides() -> Any:
    _FakeOllamaHandler._overrides = {}
    yield
    _FakeOllamaHandler._overrides = {}


@pytest.fixture(scope="session")
def fake_ollama() -> Any:
    server = http.server.HTTPServer(("127.0.0.1", 0), _FakeOllamaHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
