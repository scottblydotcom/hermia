"""Ollama model management and test execution."""

import json
import os
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


def get_ollama_host() -> str:
    """Return the configured Ollama host URL from env var or default."""
    return os.environ.get("HERMIA_HOST", "http://localhost:11434")


def detect_mode(host: str) -> str:
    """Return 'local' if host resolves to localhost/loopback, else 'fleet'."""
    hostname = urlparse(host).hostname or ""
    return "local" if hostname in ("localhost", "127.0.0.1") else "fleet"


def fetch_server_vram(host: str, model: str) -> float | None:
    """Query /api/ps on host; return size_vram for model in GiB, or None.

    Returns None if the endpoint is unavailable, the model is not listed,
    or size_vram is absent. Never raises.
    """
    try:
        resp = requests.get(f"{host}/api/ps", timeout=5)
        for m in resp.json().get("models", []):
            if m.get("name") == model:
                size = m.get("size_vram")
                if size is not None:
                    return size / (1024 ** 3)
        return None
    except Exception:  # noqa: BLE001
        return None


def get_available_models() -> list[dict[str, Any]]:
    host = get_ollama_host()
    try:
        resp = requests.get(f"{host}/api/tags", timeout=5)
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


def load_tests(selected_ids: list[str]) -> list[dict[str, Any]]:
    path = PROJECT_ROOT / "test-datasets" / "agentic-tasks.json"
    with open(path) as f:
        all_tests: list[dict[str, Any]] = json.load(f)["agentic_test_cases"]
    return [t for t in all_tests if t["id"] in selected_ids]


def run_test(
    model: str, test: dict[str, Any], sampler: MetricsSampler, host: str | None = None
) -> dict[str, Any]:
    _host = host if host is not None else get_ollama_host()
    mode = detect_mode(_host)
    payload = {
        "model": model,
        "system": test["system"],
        "prompt": test["prompt"],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    if mode == "local":
        sampler.start()
    error_type: str = ""
    try:
        t0 = time.time()
        resp = requests.post(f"{_host}/api/generate", json=payload, timeout=TEST_TIMEOUT)
        elapsed = time.time() - t0
        data = resp.json()
        ollama_error = data.get("error", "")
        output: str = data.get("response", "")
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
    if output and not error_type:
        try:
            parsed = json.loads(output.strip())
            json_valid = True
            checker = SCHEMA_CHECKS.get(test["id"])
            if checker:
                schema_ok = bool(checker(parsed))
        except Exception:
            pass

    tps = tokens / elapsed if elapsed > 0 and tokens > 0 else 0
    preview = error_type if error_type else output[:120].replace("\n", " ")
    return {
        "model": model,
        "test_id": test["id"],
        "dimension": test.get("dimension", ""),
        "frameworks": test.get("frameworks", {}),
        "failure_reason": error_type,
        "json_valid": json_valid,
        "schema_compliant": schema_ok,
        "tokens": tokens,
        "elapsed_sec": round(elapsed, 2),
        "tokens_per_sec": round(tps, 1),
        "output_preview": preview,
        "peak_cpu_pct": round(peak.get("cpu_pct", 0), 1) if mode == "local" else None,
        "peak_ram_used_gb": round(peak.get("ram_used_gb", 0), 2) if mode == "local" else None,
        "peak_gpu_pct": round(peak.get("gpu_pct", 0), 1) if mode == "local" else None,
        "peak_vram_used_gb": round(peak.get("vram_used_gb", 0), 2) if mode == "local" else None,
        "mode": mode,
        "vram_server_gb": fetch_server_vram(_host, model),
    }
