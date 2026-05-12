"""System and GPU metrics sampling — nvidia-smi, Apple Silicon ioreg, AMD sysfs/rocm-smi, Intel i915."""

import glob
import json
import platform
import re
import subprocess
import sys
import threading
import time
from typing import Any

_AMD_DEV: str | None = None
_NVIDIA_FOUND: bool = False
_NVIDIA_VRAM_TOTAL_GB: float = 0.0
_APPLE_SILICON: bool = False
_APPLE_VRAM_TOTAL_GB: float = 0.0
_INTEL_IGPU: bool = False


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


def _detect_apple_silicon() -> tuple[bool, str, float]:
    """Detect Apple Silicon GPU. Returns (found, chip_name, vram_total_gb).

    Uses sysctl hw.optional.arm64 so detection works even when Python runs
    under Rosetta (where platform.machine() returns 'x86_64'). Total unified
    memory is reported as vram_total_gb — on Apple Silicon, GPU and CPU share
    the same physical memory pool.
    """
    if sys.platform != "darwin":
        return False, "", 0.0

    # platform.machine() works for native arm64 Python; sysctl catches Rosetta
    is_arm = platform.machine() == "arm64"
    if not is_arm:
        try:
            r = subprocess.run(  # noqa: S603
                ["sysctl", "-n", "hw.optional.arm64"],  # noqa: S607
                capture_output=True, text=True, timeout=2,
            )
            is_arm = r.stdout.strip() == "1"
        except (subprocess.SubprocessError, OSError):
            pass

    if not is_arm:
        return False, "", 0.0

    # GPU model name from system_profiler (no sudo)
    name = "Apple Silicon"
    try:
        r = subprocess.run(  # noqa: S603
            ["system_profiler", "SPDisplaysDataType", "-json"],  # noqa: S607
            capture_output=True, text=True, timeout=5,
        )
        data: dict[str, Any] = json.loads(r.stdout)
        entries = data.get("SPDisplaysDataType", [])
        if entries:
            name = entries[0].get("sppci_model", name)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError, KeyError):
        pass

    # Total unified memory from sysctl
    vram_total_gb = 0.0
    try:
        r = subprocess.run(  # noqa: S603
            ["sysctl", "-n", "hw.memsize"],  # noqa: S607
            capture_output=True, text=True, timeout=2,
        )
        vram_total_gb = int(r.stdout.strip()) / (1024**3)
    except (subprocess.SubprocessError, ValueError, OSError):
        import psutil
        vram_total_gb = psutil.virtual_memory().total / (1024**3)

    return True, name, vram_total_gb


def _gpu_stats_apple_silicon() -> tuple[float, float, float]:
    """Read Apple Silicon GPU utilization and VRAM via ioreg (no sudo required).

    ioreg IOAccelerator PerformanceStatistics exposes:
      "Device Utilization %" — overall GPU engine utilization
      "In use system memory" — bytes of unified memory currently used by GPU

    powermetrics (sudo required) provides more granular GPU power data but is
    not used here to avoid requiring elevated privileges.
    """
    try:
        r = subprocess.run(  # noqa: S603
            ["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"],  # noqa: S607
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0 or not r.stdout:
            return 0.0, 0.0, _APPLE_VRAM_TOTAL_GB
        text = r.stdout
        gpu_pct = 0.0
        vram_used_gb = 0.0
        m = re.search(r'"Device Utilization %"=(\d+)', text)
        if m:
            gpu_pct = float(m.group(1))
        # "In use system memory" without the "(driver)" suffix
        m = re.search(r'"In use system memory"=(\d+)', text)
        if m:
            vram_used_gb = int(m.group(1)) / (1024**3)
        return gpu_pct, vram_used_gb, _APPLE_VRAM_TOTAL_GB
    except (subprocess.SubprocessError, OSError, ValueError):
        return 0.0, 0.0, _APPLE_VRAM_TOTAL_GB


def _detect_intel_igpu() -> tuple[bool, str]:
    """Detect Intel iGPU. Returns (found, name).

    macOS: parses system_profiler SPDisplaysDataType for an Intel GPU entry.
    Linux: scans DRM sysfs uevent files for DRIVER=i915.
    Returns (False, "") when not found or on other platforms.
    """
    if sys.platform == "darwin":
        try:
            r = subprocess.run(  # noqa: S603
                ["system_profiler", "SPDisplaysDataType", "-json"],  # noqa: S607
                capture_output=True, text=True, timeout=5,
            )
            data: dict[str, Any] = json.loads(r.stdout)
            for entry in data.get("SPDisplaysDataType", []):
                model = entry.get("sppci_model", "")
                if "Intel" in model:
                    return True, model
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError, KeyError):
            pass
        return False, ""

    if sys.platform == "linux":
        for uevent_path in glob.glob("/sys/class/drm/card*/device/uevent"):
            try:
                with open(uevent_path) as f:
                    content = f.read()
                    if "DRIVER=i915" in content or "DRIVER=xe" in content:
                        return True, "Intel iGPU"
            except OSError:
                continue

    return False, ""


def _gpu_stats_intel() -> tuple[float, float, float]:
    """Read Intel iGPU utilization via intel_gpu_top (Linux only).

    intel_gpu_top streams JSON objects continuously; we run it briefly and
    capture output on TimeoutExpired. VRAM is not exposed by i915/xe sysfs
    without kernel perf access, so vram fields are always 0.0.
    Returns (0.0, 0.0, 0.0) on any failure or when not on Linux.
    """
    if sys.platform != "linux":
        return 0.0, 0.0, 0.0
    try:
        try:
            r = subprocess.run(  # noqa: S603
                ["intel_gpu_top", "-J", "-s", "100"],  # noqa: S607
                capture_output=True, text=True, timeout=0.4,
            )
            text = r.stdout
        except subprocess.TimeoutExpired as e:
            raw = e.stdout
            text = raw if isinstance(raw, str) else (raw.decode(errors="ignore") if raw else "")

        if not text:
            return 0.0, 0.0, 0.0
        lines = [ln for ln in text.splitlines() if ln.strip().startswith("{")]
        if not lines:
            return 0.0, 0.0, 0.0
        obj = json.loads(lines[-1])
        engines = obj.get("engines", {})
        render = engines.get("Render/3D/0", engines.get("Render/3D", {}))
        return float(render.get("busy", 0.0)), 0.0, 0.0
    except Exception:
        return 0.0, 0.0, 0.0


def detect_gpu() -> dict[str, Any]:
    """Detect GPU hardware at run start. Updates module-level cache.

    Tries NVIDIA first (via nvidia-smi), then Apple Silicon (via ioreg/sysctl),
    then AMD (via sysfs), then Intel iGPU (via i915/system_profiler).
    Returns a dict with keys: found (bool), vendor (str), card (str),
    dev_path (str), vram_total_gb (float).
    vendor is one of: nvidia, apple, amd, intel, none.
    """
    global _AMD_DEV, _NVIDIA_FOUND, _NVIDIA_VRAM_TOTAL_GB, _APPLE_SILICON, _APPLE_VRAM_TOTAL_GB, _INTEL_IGPU

    found, name, vram_total_gb = _detect_nvidia()
    if found:
        _NVIDIA_VRAM_TOTAL_GB = vram_total_gb
        _APPLE_SILICON = False
        _AMD_DEV = None
        _INTEL_IGPU = False
        _NVIDIA_FOUND = True  # set last — sampler thread must not see True before VRAM is written
        return {
            "found": True,
            "vendor": "nvidia",
            "card": name,
            "dev_path": "",
            "vram_total_gb": vram_total_gb,
        }

    _NVIDIA_FOUND = False

    found_apple, apple_name, apple_vram = _detect_apple_silicon()
    if found_apple:
        _APPLE_VRAM_TOTAL_GB = apple_vram
        _AMD_DEV = None
        _INTEL_IGPU = False
        _APPLE_SILICON = True  # set last
        return {
            "found": True,
            "vendor": "apple",
            "card": apple_name,
            "dev_path": "",
            "vram_total_gb": apple_vram,
        }

    _APPLE_SILICON = False
    _AMD_DEV = _find_amdgpu_dev()
    if _AMD_DEV is not None:
        _INTEL_IGPU = False
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

    found_intel, intel_name = _detect_intel_igpu()
    if found_intel:
        _INTEL_IGPU = True
        return {
            "found": True,
            "vendor": "intel",
            "card": intel_name,
            "dev_path": "",
            "vram_total_gb": 0.0,
        }

    _INTEL_IGPU = False
    return {"found": False, "vendor": "none", "card": "", "dev_path": "", "vram_total_gb": 0.0}


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

    Routes to nvidia-smi, Apple Silicon ioreg, Intel i915, or AMD rocm-smi/sysfs
    based on what detect_gpu() found at startup. Returns (0.0, 0.0, 0.0) on
    CPU-only systems.
    """
    if _NVIDIA_FOUND:
        return _gpu_stats_nvidia()

    if _APPLE_SILICON:
        return _gpu_stats_apple_silicon()

    if _INTEL_IGPU:
        return _gpu_stats_intel()

    if _AMD_DEV is None:
        return 0.0, 0.0, 0.0

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
