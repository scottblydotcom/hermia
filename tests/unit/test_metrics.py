"""Unit tests for MetricsSampler and GPU detection."""

import time
from unittest.mock import MagicMock, mock_open, patch

import hermia.metrics as metrics_mod
from hermia.metrics import MetricsSampler, detect_gpu, get_gpu_stats


def _fake_metrics():
    return {
        "cpu_pct": 42.0,
        "ram_used_gb": 8.0,
        "ram_total_gb": 16.0,
        "gpu_pct": 80.0,
        "vram_used_gb": 5.0,
        "vram_total_gb": 8.0,
    }


def test_sampler_collects_samples():
    with patch("hermia.metrics.get_system_metrics", side_effect=_fake_metrics):
        s = MetricsSampler()
        s.start()
        time.sleep(0.1)
        s.stop()
    assert len(s.samples) >= 1


def test_sampler_peak_returns_max():
    s = MetricsSampler()
    s.samples = [
        {"cpu_pct": 10.0, "ram_used_gb": 4.0, "gpu_pct": 30.0, "vram_used_gb": 2.0, "vram_total_gb": 8.0},  # noqa: E501
        {"cpu_pct": 90.0, "ram_used_gb": 12.0, "gpu_pct": 95.0, "vram_used_gb": 7.0, "vram_total_gb": 8.0},  # noqa: E501
    ]
    peak = s.peak()
    assert peak["cpu_pct"] == 90.0
    assert peak["gpu_pct"] == 95.0
    assert peak["vram_used_gb"] == 7.0


def test_sampler_peak_empty():
    s = MetricsSampler()
    assert s.peak() == {}


def test_sampler_latest_updated():
    with patch("hermia.metrics.get_system_metrics", side_effect=_fake_metrics):
        s = MetricsSampler()
        s.start()
        time.sleep(0.15)
        s.stop()
    assert s.latest.get("cpu_pct") == 42.0


def _make_uevent_open(dev_path: str, driver: str = "amdgpu", vram_bytes: int = 8 * 1024**3):
    """Return a fake open() that serves uevent, vram_total, gpu_busy_percent, vram_used."""
    uevent_content = f"DRIVER={driver}\nPCI_ID=1002:687F\n"
    file_data = {
        f"{dev_path}/uevent": uevent_content,
        f"{dev_path}/mem_info_vram_total": str(vram_bytes),
        f"{dev_path}/gpu_busy_percent": "75",
        f"{dev_path}/mem_info_vram_used": str(4 * 1024**3),
    }

    def fake_open(path, *a, **kw):
        return mock_open(read_data=file_data.get(path, ""))()

    return fake_open


# ---------------------------------------------------------------------------
# AMD detection tests — patch subprocess.run so nvidia-smi detection is skipped
# ---------------------------------------------------------------------------

def test_detect_gpu_finds_amdgpu_card():
    """detect_gpu() picks the amdgpu card and ignores non-amdgpu cards."""
    uevent_paths = [
        "/sys/class/drm/card1/device/uevent",
        "/sys/class/drm/card2/device/uevent",
    ]
    dev = "/sys/class/drm/card2/device"
    uevent_data = {
        "/sys/class/drm/card1/device/uevent": "DRIVER=i915\n",
        "/sys/class/drm/card2/device/uevent": "DRIVER=amdgpu\n",
        f"{dev}/mem_info_vram_total": str(8 * 1024**3),
    }

    def fake_open(path, *a, **kw):
        return mock_open(read_data=uevent_data.get(path, ""))()

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    assert info["found"] is True
    assert info["vendor"] == "amd"
    assert info["card"] == "card2"
    assert abs(info["vram_total_gb"] - 8.0) < 0.01
    assert metrics_mod._AMD_DEV == dev


def test_detect_gpu_no_amdgpu():
    """detect_gpu() returns found=False when no GPU is present."""
    uevent_paths = ["/sys/class/drm/card0/device/uevent"]
    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", mock_open(read_data="DRIVER=i915\n")),
    ):
        info = detect_gpu()

    assert info["found"] is False
    assert info["vendor"] == "none"
    assert metrics_mod._AMD_DEV is None


def test_detect_gpu_picks_highest_vram_when_multiple_amdgpu():
    """When multiple AMD GPUs exist, detect_gpu() picks the one with the most VRAM."""
    uevent_paths = [
        "/sys/class/drm/card1/device/uevent",
        "/sys/class/drm/card2/device/uevent",
    ]
    uevent_data = {
        "/sys/class/drm/card1/device/uevent": "DRIVER=amdgpu\n",
        "/sys/class/drm/card1/device/mem_info_vram_total": str(8 * 1024**3),
        "/sys/class/drm/card2/device/uevent": "DRIVER=amdgpu\n",
        "/sys/class/drm/card2/device/mem_info_vram_total": str(16 * 1024**3),
    }

    def fake_open(path, *a, **kw):
        return mock_open(read_data=uevent_data.get(path, "0"))()

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    assert info["card"] == "card2"
    assert abs(info["vram_total_gb"] - 16.0) < 0.01


# ---------------------------------------------------------------------------
# NVIDIA detection tests
# ---------------------------------------------------------------------------

def _nvidia_detect_result(name: str = "NVIDIA GeForce RTX 5090", vram_mib: int = 32768) -> MagicMock:
    r = MagicMock()
    r.returncode = 0
    r.stdout = f"{name}, {vram_mib}\n"
    return r


def test_detect_gpu_nvidia_found():
    """detect_gpu() returns vendor=nvidia when nvidia-smi succeeds."""
    with patch("subprocess.run", return_value=_nvidia_detect_result("NVIDIA GeForce RTX 5090", 32768)):
        info = detect_gpu()

    assert info["found"] is True
    assert info["vendor"] == "nvidia"
    assert info["card"] == "NVIDIA GeForce RTX 5090"
    assert abs(info["vram_total_gb"] - 32.0) < 0.1
    assert metrics_mod._NVIDIA_FOUND is True
    assert metrics_mod._AMD_DEV is None


def test_detect_gpu_nvidia_3090():
    """detect_gpu() correctly parses RTX 3090 (24 GB)."""
    with patch("subprocess.run", return_value=_nvidia_detect_result("NVIDIA GeForce RTX 3090", 24576)):
        info = detect_gpu()

    assert info["vendor"] == "nvidia"
    assert abs(info["vram_total_gb"] - 24.0) < 0.1


def test_detect_gpu_nvidia_missing():
    """detect_gpu() falls through to AMD when nvidia-smi is not on PATH."""
    uevent_paths = ["/sys/class/drm/card1/device/uevent"]
    dev = "/sys/class/drm/card1/device"
    uevent_data = {
        "/sys/class/drm/card1/device/uevent": "DRIVER=amdgpu\n",
        f"{dev}/mem_info_vram_total": str(8 * 1024**3),
    }

    def fake_open(path, *a, **kw):
        return mock_open(read_data=uevent_data.get(path, ""))()

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    assert info["vendor"] == "amd"
    assert metrics_mod._NVIDIA_FOUND is False


def test_detect_gpu_nvidia_error_returncode():
    """detect_gpu() treats non-zero nvidia-smi exit as no NVIDIA GPU."""
    bad_result = MagicMock()
    bad_result.returncode = 1
    bad_result.stdout = ""

    with (
        patch("subprocess.run", return_value=bad_result),
        patch("hermia.metrics.glob.glob", return_value=[]),
    ):
        info = detect_gpu()

    assert info["found"] is False
    assert info["vendor"] == "none"
    assert metrics_mod._NVIDIA_FOUND is False


# ---------------------------------------------------------------------------
# get_gpu_stats NVIDIA routing tests
# ---------------------------------------------------------------------------

def _nvidia_stats_result(util_pct: float = 82.0, used_mib: float = 12288.0, total_mib: float = 32768.0) -> MagicMock:
    r = MagicMock()
    r.returncode = 0
    r.stdout = f"{util_pct}, {used_mib}, {total_mib}\n"
    return r


def test_get_gpu_stats_uses_nvidia_when_found():
    """get_gpu_stats() routes to nvidia-smi when _NVIDIA_FOUND is True."""
    with (
        patch.object(metrics_mod, "_NVIDIA_FOUND", True),
        patch.object(metrics_mod, "_NVIDIA_VRAM_TOTAL_GB", 32.0),
        patch("subprocess.run", return_value=_nvidia_stats_result(82.0, 12288.0, 32768.0)),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 82.0
    assert abs(vram_used - 12.0) < 0.01
    assert abs(vram_total - 32.0) < 0.01


def test_get_gpu_stats_nvidia_subprocess_error_returns_zeros():
    """nvidia-smi failure during stats returns zeros with cached vram_total."""
    with (
        patch.object(metrics_mod, "_NVIDIA_FOUND", True),
        patch.object(metrics_mod, "_NVIDIA_VRAM_TOTAL_GB", 24.0),
        patch("subprocess.run", side_effect=OSError),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 0.0
    assert vram_used == 0.0
    assert vram_total == 24.0


def test_get_gpu_stats_nvidia_nonzero_returncode_returns_zeros():
    """Non-zero nvidia-smi exit during stats returns zeros with cached vram_total."""
    bad = MagicMock()
    bad.returncode = 1
    bad.stdout = ""
    with (
        patch.object(metrics_mod, "_NVIDIA_FOUND", True),
        patch.object(metrics_mod, "_NVIDIA_VRAM_TOTAL_GB", 24.0),
        patch("subprocess.run", return_value=bad),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 0.0
    assert vram_total == 24.0


# ---------------------------------------------------------------------------
# Existing AMD get_gpu_stats tests
# ---------------------------------------------------------------------------

def test_get_gpu_stats_falls_back_to_sysfs_when_rocm_returns_zeros():
    """rocm-smi returning all zeros should trigger sysfs fallback."""
    rocm_output = (
        '{"card2": {"GPU use (%)": 0, "VRAM Used Memory (B)": 0, "VRAM Total Memory (B)": 1}}'
    )
    mock_result = MagicMock()
    mock_result.stdout = rocm_output

    dev = "/sys/class/drm/card2/device"
    open_values = {
        f"{dev}/uevent": "DRIVER=amdgpu\n",
        f"{dev}/mem_info_vram_total": "8589934592",
        f"{dev}/gpu_busy_percent": "75",
        f"{dev}/mem_info_vram_used": "4294967296",
    }

    def fake_open(path, *a, **kw):
        return mock_open(read_data=open_values.get(path, "0"))()

    with (
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch("subprocess.run", return_value=mock_result),
        patch("hermia.metrics.glob.glob", return_value=[f"{dev}/uevent"]),
        patch("builtins.open", side_effect=fake_open),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 75.0
    assert abs(vram_used - 4.0) < 0.01
    assert abs(vram_total - 8.0) < 0.01


def test_get_gpu_stats_falls_back_to_sysfs_when_rocm_missing():
    """rocm-smi not found should also fall through to sysfs."""
    dev = "/sys/class/drm/card2/device"
    open_values = {
        f"{dev}/uevent": "DRIVER=amdgpu\n",
        f"{dev}/mem_info_vram_total": "8589934592",
        f"{dev}/gpu_busy_percent": "50",
        f"{dev}/mem_info_vram_used": "2147483648",
    }

    def fake_open(path, *a, **kw):
        return mock_open(read_data=open_values.get(path, "0"))()

    with (
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=[f"{dev}/uevent"]),
        patch("builtins.open", side_effect=fake_open),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 50.0
    assert abs(vram_used - 2.0) < 0.01
