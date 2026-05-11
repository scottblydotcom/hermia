"""System and GPU metrics sampling (CPU, RAM, GPU via nvidia-smi or AMD sysfs/rocm-smi)."""

import glob
import json
import subprocess
import threading
import time
from typing import Any

_AMD_DEV: str | None = None
_NVIDIA_FOUND: bool = False
_NVIDIA_VRAM_TOTAL_GB: float = 0.0


def _find_amdgpu_dev() -> str | None:
    """Scan DRM devices and return the sysfs device path for the best AMD GPU.

    Validates via uevent DRIVER=amdgpu — ignores Intel/Nvidia cards regardless
    of card number. When multiple AMD GPUs are present, picks the one with the
    most VRAM.
    """
    candidates: list[tuple[int, str]] = []
    for uevent_path in glob.glob("/sys/class/drm/card*/device/uevent"):
        try:
            with open(uevent_path) as f:
                if "DRIVER=amdgpu" not in f.read():
                    continue
            dev = uevent_path.rsplit("/", 1)[0]
            vram_path = f"{dev}/mem_info_vram_total"
            try:
                with open(vram_path) as f:
                    vram = int(f.read().strip())
            except OSError:
                vram = 0
            candidates.append((vram, dev))
        except OSError:
            continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _detect_nvidia() -> tuple[bool, str, float]:
    """Probe nvidia-smi to detect an NVIDIA GPU. Returns (found, name, vram_total_gb)."""
    try:
        result = subprocess.run(  # noqa: S603
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False, "", 0.0
        line = result.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            return False, "", 0.0
        name = parts[0]
        vram_total_gb = float(parts[1]) / 1024  # MiB → GiB
        return True, name, vram_total_gb
    except (subprocess.SubprocessError, ValueError, IndexError, OSError):
        return False, "", 0.0


def detect_gpu() -> dict[str, Any]:
    """Detect GPU hardware at run start. Updates module-level cache.

    Tries NVIDIA first (via nvidia-smi), then AMD (via sysfs). Returns a dict
    with keys: found (bool), vendor (str), card (str), dev_path (str),
    vram_total_gb (float). vendor is one of: nvidia, amd, none.
    """
    global _AMD_DEV, _NVIDIA_FOUND, _NVIDIA_VRAM_TOTAL_GB

    found, name, vram_total_gb = _detect_nvidia()
    if found:
        _NVIDIA_VRAM_TOTAL_GB = vram_total_gb
        _AMD_DEV = None
        _NVIDIA_FOUND = True
        return {
            "found": True,
            "vendor": "nvidia",
            "card": name,
            "dev_path": "",
            "vram_total_gb": vram_total_gb,
        }

    _NVIDIA_FOUND = False
    _AMD_DEV = _find_amdgpu_dev()
    if _AMD_DEV is None:
        return {"found": False, "vendor": "none", "card": "", "dev_path": "", "vram_total_gb": 0.0}

    card = _AMD_DEV.split("/sys/class/drm/")[-1].split("/")[0]
    try:
        with open(f"{_AMD_DEV}/mem_info_vram_total") as f:
            vram_total_gb = int(f.read().strip()) / (1024**3)
    except OSError:
        vram_total_gb = 0.0
    return {
        "found": True,
        "vendor": "amd",
        "card": card,
        "dev_path": _AMD_DEV,
        "vram_total_gb": vram_total_gb,
    }


def _gpu_stats_nvidia() -> tuple[float, float, float]:
    """Read GPU utilization and VRAM via nvidia-smi."""
    try:
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return 0.0, 0.0, _NVIDIA_VRAM_TOTAL_GB
        line = result.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            return 0.0, 0.0, _NVIDIA_VRAM_TOTAL_GB
        try:
            gpu_pct = float(parts[0])
            vram_used = float(parts[1]) / 1024  # MiB → GiB
            vram_total = float(parts[2]) / 1024  # MiB → GiB
        except ValueError:
            return 0.0, 0.0, _NVIDIA_VRAM_TOTAL_GB
        return gpu_pct, vram_used, vram_total
    except (subprocess.SubprocessError, ValueError, IndexError, OSError):
        return 0.0, 0.0, _NVIDIA_VRAM_TOTAL_GB


def _gpu_stats_sysfs() -> tuple[float, float, float]:
    """Read AMD GPU stats from amdgpu kernel sysfs — works without ROCm/Vulkan."""
    dev = _AMD_DEV
    if dev is None:
        dev = _find_amdgpu_dev()
    if dev is None:
        return 0.0, 0.0, 0.0
    try:
        with open(f"{dev}/gpu_busy_percent") as f:
            gpu_pct = float(f.read().strip())
        with open(f"{dev}/mem_info_vram_used") as f:
            vram_used = float(f.read().strip()) / (1024**3)
        with open(f"{dev}/mem_info_vram_total") as f:
            vram_total = float(f.read().strip()) / (1024**3)
        return gpu_pct, vram_used, vram_total
    except Exception:
        return 0.0, 0.0, 0.0


def get_gpu_stats() -> tuple[float, float, float]:
    """Return (gpu_pct, vram_used_gb, vram_total_gb).

    Routes to nvidia-smi when an NVIDIA GPU was detected, otherwise tries
    rocm-smi then falls back to amdgpu sysfs.
    """
    if _NVIDIA_FOUND:
        return _gpu_stats_nvidia()

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
