"""Ollama model management and test execution."""

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from hermia.metrics import MetricsSampler, get_gpu_stats
from hermia.schemas import SCHEMA_CHECKS

PROJECT_ROOT = Path(__file__).parents[2]

TEST_TIMEOUT = 90    # seconds per individual test request
LOAD_TIMEOUT = 120   # seconds for cold model load


def _strip_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences from model output."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()


def _normalize_host(host: str) -> str:
    host = host.rstrip("/")
    return host if "://" in host else f"http://{host}"


def get_ollama_host() -> str:
    """Return the configured Ollama host URL from env var or default."""
    return _normalize_host(os.environ.get("HERMIA_HOST", "http://localhost:11434"))


def detect_mode(host: str) -> str:
    """Return 'local' if host resolves to localhost/loopback, else 'fleet'."""
    hostname = urlparse(_normalize_host(host)).hostname or ""
    return "local" if hostname in ("localhost", "127.0.0.1", "::1") else "fleet"


_vram_cache: dict[tuple[Any, ...], float | None] = {}


def fetch_server_vram(
    host: str, model: str, headers: dict[str, str] | None = None
) -> float | None:
    """Query /api/ps on host; return size_vram for model in GiB, or None.

    Caches the result (including None) on a successful response or a 404 —
    both are stable within a session. Network errors and other non-2xx
    responses are not cached so transient failures retry. Never raises.
    """
    host = _normalize_host(host)
    headers_key = tuple(sorted(headers.items())) if headers else ()
    key = (host, model, headers_key)
    if key in _vram_cache:
        return _vram_cache[key]
    try:
        resp = requests.get(f"{host}/api/ps", timeout=2, headers=headers or {})
        if not resp.ok:
            if resp.status_code == 404:
                _vram_cache[key] = None
            return None

        found_vram = None
        data = resp.json()
        if isinstance(data, dict):
            for m in data.get("models") or []:
                if m.get("name") == model:
                    size = m.get("size_vram")
                    if size is not None:
                        found_vram = float(size) / (1024 ** 3)
                    break

        _vram_cache[key] = found_vram
        return found_vram
    except Exception:  # noqa: BLE001
        return None


def get_available_models(
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    _host = _normalize_host(host) if host is not None else get_ollama_host()
    try:
        resp = requests.get(f"{_host}/api/tags", timeout=5, headers=headers or {})
        return resp.json().get("models", [])  # type: ignore[no-any-return]
    except Exception:
        return []


def get_model_size_gb(model_name: str, model_list: list[dict[str, Any]]) -> float:
    for m in model_list:
        if m["name"] == model_name:
            return m.get("size", 0) / (1024**3)  # type: ignore[no-any-return]
    return 0.0


def unload_model(model_name: str) -> None:
    """Evict model from VRAM."""
    host = get_ollama_host()
    try:
        requests.post(
            f"{host}/api/generate",
            json={"model": model_name, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=10,
        )
    except Exception:  # noqa: BLE001
        pass


def prewarm_timed(model_name: str) -> tuple[float, float, float]:
    """Unload cached model, then time a cold load.

    Returns (load_time_sec, vram_before_gb, vram_after_gb).
    """
    host = get_ollama_host()
    _, vram_before, _ = get_gpu_stats()
    t0 = time.time()
    try:
        requests.post(
            f"{host}/api/generate",
            json={
                "model": model_name,
                "prompt": "hi",
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 1},
            },
            timeout=LOAD_TIMEOUT,
        )
    except Exception:  # noqa: BLE001
        pass
    load_time = time.time() - t0
    _, vram_after, _ = get_gpu_stats()
    return load_time, vram_before, vram_after


def load_tests_all() -> list[dict[str, Any]]:
    """Load all test cases from agentic-tasks.json (no ID filter)."""
    path = PROJECT_ROOT / "test-datasets" / "agentic-tasks.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["agentic_test_cases"]  # type: ignore[no-any-return]


def load_tests(selected_ids: list[str]) -> list[dict[str, Any]]:
    return [t for t in load_tests_all() if t["id"] in selected_ids]


def run_test(
    model: str,
    test: dict[str, Any],
    sampler: MetricsSampler,
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    _host = _normalize_host(host) if host is not None else get_ollama_host()
    mode = detect_mode(_host)
    payload = {
        "model": model,
        "system": test["system"],
        "prompt": test["prompt"],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    req_headers = headers or {}
    if mode == "local":
        sampler.start()
    error_type: str = ""
    try:
        t0 = time.time()
        resp = requests.post(
            f"{_host}/api/generate", json=payload, headers=req_headers, timeout=TEST_TIMEOUT
        )
        elapsed = time.time() - t0
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected Ollama response type: {type(data).__name__}")
        ollama_error = data.get("error", "")
        output: str = data.get("response") or ""
        tokens: int = data.get("eval_count", 0)
        if ollama_error:
            error_type = f"OLLAMA_ERROR: {ollama_error}"
    except requests.exceptions.Timeout:
        elapsed = TEST_TIMEOUT
        output = ""
        tokens = 0
        error_type = f"TIMEOUT: no response in {TEST_TIMEOUT}s"
    except Exception as e:
        elapsed = time.time() - t0
        output = ""
        tokens = 0
        error_type = f"ERROR: {e}"
    if mode == "local":
        sampler.stop()
    peak = sampler.peak() if mode == "local" else {}

    json_valid = False
    schema_ok = False
    had_markdown_fence = False
    failure_reason = error_type  # network/Ollama errors; "" on clean path

    if output and not error_type:
        cleaned = _strip_fences(output)
        had_markdown_fence = cleaned != output.strip()
        try:
            parsed = json.loads(cleaned)
            json_valid = True
            checker = SCHEMA_CHECKS.get(test["id"])
            if checker:
                schema_ok = bool(checker(parsed))
            if not schema_ok:
                failure_reason = "SCHEMA_FAIL"
        except json.JSONDecodeError:
            failure_reason = "JSON_PARSE_ERROR"
    elif not error_type:
        failure_reason = "EMPTY_RESPONSE"

    tps = tokens / elapsed if elapsed > 0 and tokens > 0 else 0
    preview = output[:120].replace("\n", " ") if output.strip() else failure_reason
    return {
        "model": model,
        "test_id": test["id"],
        "dimension": test.get("dimension", ""),
        "frameworks": test.get("frameworks", {}),
        "failure_reason": failure_reason,
        "had_markdown_fence": had_markdown_fence,
        "json_valid": json_valid,
        "schema_compliant": schema_ok,
        "tokens": tokens,
        "elapsed_sec": round(elapsed, 2),
        "tokens_per_sec": round(tps, 1),
        "output_preview": preview,
        "raw_system": test["system"] or "",
        "raw_prompt": test["prompt"] or "",
        "raw_response": "" if error_type else output,
        "peak_cpu_pct": round(peak.get("cpu_pct", 0), 1) if mode == "local" else None,
        "peak_ram_used_gb": round(peak.get("ram_used_gb", 0), 2) if mode == "local" else None,
        "peak_gpu_pct": round(peak.get("gpu_pct", 0), 1) if mode == "local" else None,
        "peak_vram_used_gb": round(peak.get("vram_used_gb", 0), 2) if mode == "local" else None,
        "mode": mode,
        "host": _host,
        "vram_server_gb": fetch_server_vram(_host, model, headers=req_headers or None),
    }
