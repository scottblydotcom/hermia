"""Unit tests for MetricsSampler."""

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
        {"cpu_pct": 10.0, "ram_used_gb": 4.0, "gpu_pct": 30.0, "vram_used_gb": 2.0, "vram_total_gb": 8.0},
        {"cpu_pct": 90.0, "ram_used_gb": 12.0, "gpu_pct": 95.0, "vram_used_gb": 7.0, "vram_total_gb": 8.0},
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
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    assert info["found"] is True
    assert info["card"] == "card2"
    assert abs(info["vram_total_gb"] - 8.0) < 0.01
    assert metrics_mod._AMD_DEV == dev


def test_detect_gpu_no_amdgpu():
    """detect_gpu() returns found=False when no amdgpu card is present."""
    uevent_paths = ["/sys/class/drm/card0/device/uevent"]
    with (
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", mock_open(read_data="DRIVER=i915\n")),
    ):
        info = detect_gpu()

    assert info["found"] is False
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
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    assert info["card"] == "card2"
    assert abs(info["vram_total_gb"] - 16.0) < 0.01


def test_get_gpu_stats_falls_back_to_sysfs_when_rocm_returns_zeros():
    """rocm-smi returning all zeros should trigger sysfs fallback."""
    rocm_output = '{"card2": {"GPU use (%)": 0, "VRAM Used Memory (B)": 0, "VRAM Total Memory (B)": 1}}'
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
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=[f"{dev}/uevent"]),
        patch("builtins.open", side_effect=fake_open),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 50.0
    assert abs(vram_used - 2.0) < 0.01
