"""System and GPU metrics sampling (CPU, RAM, AMD GPU via rocm-smi or sysfs)."""

import glob
import json
import subprocess
import threading
import time
from typing import Any


def _gpu_stats_sysfs() -> tuple[float, float, float]:
    """Read AMD GPU stats from amdgpu kernel sysfs — works without ROCm/Vulkan."""
    try:
        busy_files = glob.glob("/sys/class/drm/card*/device/gpu_busy_percent")
        if not busy_files:
            return 0.0, 0.0, 8.0
        dev = busy_files[0].rsplit("/", 1)[0]
        with open(busy_files[0]) as f:
            gpu_pct = float(f.read().strip())
        with open(f"{dev}/mem_info_vram_used") as f:
            vram_used = float(f.read().strip()) / (1024**3)
        with open(f"{dev}/mem_info_vram_total") as f:
            vram_total = float(f.read().strip()) / (1024**3)
        return gpu_pct, vram_used, vram_total
    except Exception:
        return 0.0, 0.0, 8.0


def get_gpu_stats() -> tuple[float, float, float]:
    """Return (gpu_pct, vram_used_gb, vram_total_gb).

    Tries rocm-smi first; falls back to amdgpu sysfs so Vulkan workloads
    (which rocm-smi reports as zero) are still measured correctly.
    """
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
        # rocm-smi silently returns zeros for Vulkan workloads — fall back to sysfs
        if gpu_pct == 0.0 and vram_used == 0.0:
            return _gpu_stats_sysfs()
        return gpu_pct, vram_used, vram_total
    except Exception:
        return _gpu_stats_sysfs()


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
