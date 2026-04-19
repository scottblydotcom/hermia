"""Ollama model management and test execution."""

import json
import time
from pathlib import Path
from typing import Any

import requests

from hermia.metrics import MetricsSampler, get_gpu_stats
from hermia.schemas import SCHEMA_CHECKS

OLLAMA_URL = "http://localhost:11434/api/generate"
PROJECT_ROOT = Path(__file__).parents[2]


def get_available_models() -> list[dict[str, Any]]:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
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
    try:
        requests.post(
            OLLAMA_URL,
            json={"model": model_name, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=10,
        )
    except Exception:
        pass


def prewarm_timed(model_name: str) -> tuple[float, float, float]:
    """Unload cached model then time a cold load. Returns (load_time_sec, vram_before_gb, vram_after_gb)."""
    _, vram_before, _ = get_gpu_stats()
    t0 = time.time()
    try:
        requests.post(
            OLLAMA_URL,
            json={
                "model": model_name,
                "prompt": "hi",
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 1},
            },
            timeout=120,
        )
    except Exception:
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
    model: str, test: dict[str, Any], sampler: MetricsSampler
) -> dict[str, Any]:
    payload = {
        "model": model,
        "system": test["system"],
        "prompt": test["prompt"],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    sampler.start()
    try:
        t0 = time.time()
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        elapsed = time.time() - t0
        data = resp.json()
        output: str = data.get("response", "")
        tokens: int = data.get("eval_count", 0)
    except Exception as e:
        sampler.stop()
        peak = sampler.peak()
        return {
            "model": model,
            "test_id": test["id"],
            "json_valid": False,
            "schema_compliant": False,
            "tokens_per_sec": 0,
            "elapsed_sec": 0,
            "tokens": 0,
            "output_preview": f"ERROR: {e}",
            **{f"peak_{k}": v for k, v in peak.items()},
        }
    sampler.stop()
    peak = sampler.peak()

    json_valid = False
    schema_ok = False
    try:
        parsed = json.loads(output.strip())
        json_valid = True
        checker = SCHEMA_CHECKS.get(test["id"])
        if checker:
            schema_ok = bool(checker(parsed))
    except Exception:
        pass

    tps = tokens / elapsed if elapsed > 0 and tokens > 0 else 0
    return {
        "model": model,
        "test_id": test["id"],
        "json_valid": json_valid,
        "schema_compliant": schema_ok,
        "tokens": tokens,
        "elapsed_sec": round(elapsed, 2),
        "tokens_per_sec": round(tps, 1),
        "output_preview": output[:120].replace("\n", " "),
        "peak_cpu_pct": round(peak.get("cpu_pct", 0), 1),
        "peak_ram_used_gb": round(peak.get("ram_used_gb", 0), 2),
        "peak_gpu_pct": round(peak.get("gpu_pct", 0), 1),
        "peak_vram_used_gb": round(peak.get("vram_used_gb", 0), 2),
    }
