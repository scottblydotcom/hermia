"""System and GPU metrics sampling (CPU, RAM, AMD GPU via rocm-smi)."""

import json
import subprocess
import threading
import time
from typing import Any


def get_gpu_stats() -> tuple[float, float, float]:
    """Return (gpu_pct, vram_used_gb, vram_total_gb) via rocm-smi."""
    try:
        result = subprocess.run(  # noqa: S603
            ["rocm-smi", "--showuse", "--showmemuse", "--showmeminfo", "vram", "--json"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=3,
        )
        data: dict[str, Any] = json.loads(result.stdout)
        card = next(iter(data.values()))
        gpu_pct = float(card.get("GPU use (%)", 0))
        vram_used = float(card.get("VRAM Used Memory (B)", 0)) / (1024**3)
        vram_total = float(card.get("VRAM Total Memory (B)", 1)) / (1024**3)
        return gpu_pct, vram_used, vram_total
    except Exception:
        return 0.0, 0.0, 8.0


def get_system_metrics() -> dict[str, float]:
    """Return CPU%, RAM, GPU%, VRAM as a flat dict."""
    import psutil

    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    gpu_pct, vram_used, vram_total = get_gpu_stats()
    return {
        "cpu_pct": cpu,
        "ram_used_gb": ram.used / (1024**3),
        "ram_total_gb": ram.total / (1024**3),
        "gpu_pct": gpu_pct,
        "vram_used_gb": vram_used,
        "vram_total_gb": vram_total,
    }


class MetricsSampler:
    """Background thread sampling system metrics every 2 s during a run."""

    def __init__(self) -> None:
        self.samples: list[dict[str, float]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.latest: dict[str, float] = {}

    def start(self) -> None:
        self._stop.clear()
        self.samples = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            m = get_system_metrics()
            m["ts"] = time.time()
            self.samples.append(m)
            self.latest = m
            self._stop.wait(2)

    def peak(self) -> dict[str, float]:
        if not self.samples:
            return {}
        return {
            "cpu_pct": max(s["cpu_pct"] for s in self.samples),
            "ram_used_gb": max(s["ram_used_gb"] for s in self.samples),
            "gpu_pct": max(s["gpu_pct"] for s in self.samples),
            "vram_used_gb": max(s["vram_used_gb"] for s in self.samples),
            "vram_total_gb": self.samples[-1]["vram_total_gb"],
        }
