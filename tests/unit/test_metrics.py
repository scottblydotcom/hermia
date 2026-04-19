"""Unit tests for MetricsSampler."""

import time
from unittest.mock import MagicMock, mock_open, patch

from hermia.metrics import MetricsSampler, get_gpu_stats


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


def test_get_gpu_stats_falls_back_to_sysfs_when_rocm_returns_zeros():
    """rocm-smi returning all zeros should trigger sysfs fallback."""
    rocm_output = '{"card0": {"GPU use (%)": 0, "VRAM Used Memory (B)": 0, "VRAM Total Memory (B)": 1}}'
    mock_result = MagicMock()
    mock_result.stdout = rocm_output

    sysfs_files = ["/sys/class/drm/card0/device/gpu_busy_percent"]
    open_values = {"gpu_busy_percent": "75\n", "mem_info_vram_used": "4294967296\n", "mem_info_vram_total": "8589934592\n"}

    def fake_open(path, *a, **kw):
        key = path.rsplit("/", 1)[-1]
        return mock_open(read_data=open_values[key])()

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("hermia.metrics.glob.glob", return_value=sysfs_files),
        patch("builtins.open", side_effect=fake_open),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 75.0
    assert abs(vram_used - 4.0) < 0.01
    assert abs(vram_total - 8.0) < 0.01


def test_get_gpu_stats_falls_back_to_sysfs_when_rocm_missing():
    """rocm-smi not found should also fall through to sysfs."""
    sysfs_files = ["/sys/class/drm/card0/device/gpu_busy_percent"]
    open_values = {"gpu_busy_percent": "50\n", "mem_info_vram_used": "2147483648\n", "mem_info_vram_total": "8589934592\n"}

    def fake_open(path, *a, **kw):
        key = path.rsplit("/", 1)[-1]
        return mock_open(read_data=open_values[key])()

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=sysfs_files),
        patch("builtins.open", side_effect=fake_open),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 50.0
    assert abs(vram_used - 2.0) < 0.01
