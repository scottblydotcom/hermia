"""Unit tests for MetricsSampler and GPU detection."""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

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

@pytest.fixture
def clean_gpu_globals():
    """Reset the six globals detect_gpu() writes to known-clean defaults, before AND after.

    An earlier version of this fixture SAVED the values at entry and reinstated them on exit.
    That was worse than nothing: if a prior test had left `_NVIDIA_FOUND = True`, the fixture
    captured True as the baseline, the test body proved detect_gpu() had cleared it to False,
    and teardown then put True back -- actively re-polluting state the test had just shown was
    clean. get_gpu_stats() would route to the NVIDIA path on a host with no NVIDIA GPU and
    report a phantom 24 GB from the leaked _NVIDIA_VRAM_TOTAL_GB. Found by outside-family
    review of the first hermia-rk3k fix.

    Resetting to fixed defaults instead makes each of these tests hermetic: the result does not
    depend on what ran before it, which is the property an order-sensitive module global needs.
    """
    defaults = {
        "_AMD_DEV": None,
        "_NVIDIA_FOUND": False,
        "_NVIDIA_VRAM_TOTAL_GB": 0.0,
        "_APPLE_SILICON": False,
        "_APPLE_VRAM_TOTAL_GB": 0.0,
        "_INTEL_IGPU": False,
        "_MAC_DISCRETE": False,
        "_MAC_VRAM_TOTAL_GB": None,
        # The detection latch, added with ensure_gpu_detected(). Omitting it left detection
        # marked done while the six values above were reset, so ensure_gpu_detected() would
        # not re-run and every later test saw a machine with no GPU. Exactly the pollution
        # this fixture exists to prevent, reintroduced by the global that fixed it.
        "_GPU_DETECTED": False,
    }
    for name, value in defaults.items():
        setattr(metrics_mod, name, value)
    yield
    for name, value in defaults.items():
        setattr(metrics_mod, name, value)


def test_detect_gpu_finds_amdgpu_card(clean_gpu_globals):
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
        # detect_gpu() tries NVIDIA -> Apple -> AMD -> Intel, and _detect_apple_silicon() returns
        # immediately unless sys.platform == 'darwin' -- which the mocks below do not touch. On an
        # Apple Silicon dev machine the Apple branch therefore returned before the simulated Linux
        # sysfs was ever read, and this asserted 'amd' against 'apple' (hermia-rk3k). Pinning
        # sys.platform alone is sufficient, and is the target the rest of this file already uses;
        # the platform.machine() gate below it is unreachable once the darwin check has failed.
        patch("hermia.metrics.sys.platform", "linux"),
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    assert info["found"] is True
    assert info["vendor"] == "amd"
    # hermia-gq0g: this used to assert "card2" -- the DRM node name, i.e. it pinned the bug.
    # The card is identified by its device path; with no product_name and no lspci here, its
    # model name is unknown, which is blank, never the node name.
    assert info["card"] == ""
    assert info["dev_path"] == dev
    assert abs(info["vram_total_gb"] - 8.0) < 0.01
    assert metrics_mod._AMD_DEV == dev


def test_detect_gpu_no_amdgpu(clean_gpu_globals):
    """detect_gpu() returns found=False when no GPU is present."""
    uevent_paths = ["/sys/class/drm/card0/device/uevent"]
    with (
        # Pin the host: the Apple branch would otherwise short-circuit before the
        # simulated Linux sysfs is read (hermia-rk3k).
        patch("hermia.metrics.sys.platform", "linux"),
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", mock_open(read_data="DRIVER=virtio\n")),
    ):
        info = detect_gpu()

    assert info["found"] is False
    assert info["vendor"] == "none"
    assert metrics_mod._AMD_DEV is None


def test_detect_gpu_picks_highest_vram_when_multiple_amdgpu(clean_gpu_globals):
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
        # Named explicitly: the default below ("0") would otherwise be read AS the product name.
        "/sys/class/drm/card1/device/product_name": "AMD Radeon RX 6600\n",
        "/sys/class/drm/card2/device/product_name": "AMD Radeon RX 6800 XT\n",
    }

    def fake_open(path, *a, **kw):
        return mock_open(read_data=uevent_data.get(path, "0"))()

    with (
        # Pin the host: the Apple branch would otherwise short-circuit before the
        # simulated Linux sysfs is read (hermia-rk3k).
        patch("hermia.metrics.sys.platform", "linux"),
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    # Selection is by device path, and the name is the SELECTED card's model (hermia-gq0g).
    assert info["dev_path"] == "/sys/class/drm/card2/device"
    assert info["card"] == "AMD Radeon RX 6800 XT"
    assert abs(info["vram_total_gb"] - 16.0) < 0.01


# ---------------------------------------------------------------------------
# NVIDIA detection tests
# ---------------------------------------------------------------------------

def _nvidia_detect_result(
    name: str = "NVIDIA GeForce RTX 5090", vram_mib: int = 32768, compute_cap: float = 8.9
) -> MagicMock:
    r = MagicMock()
    r.returncode = 0
    r.stdout = f"{name}, {vram_mib}, {compute_cap}\n"
    return r


def test_detect_gpu_nvidia_found(clean_gpu_globals):
    """detect_gpu() returns vendor=nvidia when nvidia-smi succeeds."""
    result = _nvidia_detect_result("NVIDIA GeForce RTX 5090", 32768)
    with patch("subprocess.run", return_value=result):
        info = detect_gpu()

    assert info["found"] is True
    assert info["vendor"] == "nvidia"
    assert info["card"] == "NVIDIA GeForce RTX 5090"
    assert abs(info["vram_total_gb"] - 32.0) < 0.1
    assert metrics_mod._NVIDIA_FOUND is True
    assert metrics_mod._AMD_DEV is None


def test_detect_gpu_nvidia_3090(clean_gpu_globals):
    """detect_gpu() correctly parses RTX 3090 (24 GB)."""
    result = _nvidia_detect_result("NVIDIA GeForce RTX 3090", 24576)
    with patch("subprocess.run", return_value=result):
        info = detect_gpu()

    assert info["vendor"] == "nvidia"
    assert abs(info["vram_total_gb"] - 24.0) < 0.1


def test_detect_gpu_nvidia_missing(clean_gpu_globals):
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
        # Pin the host: the Apple branch would otherwise short-circuit before the
        # simulated Linux sysfs is read (hermia-rk3k).
        patch("hermia.metrics.sys.platform", "linux"),
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    assert info["vendor"] == "amd"
    assert metrics_mod._NVIDIA_FOUND is False


def test_detect_gpu_nvidia_error_returncode(clean_gpu_globals):
    """detect_gpu() treats non-zero nvidia-smi exit as no NVIDIA GPU."""
    bad_result = MagicMock()
    bad_result.returncode = 1
    bad_result.stdout = ""

    with (
        # Pin the host: the Apple branch would otherwise short-circuit before the
        # simulated Linux sysfs is read (hermia-rk3k).
        patch("hermia.metrics.sys.platform", "linux"),
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

def _nvidia_stats_result(
    util_pct: float = 82.0, used_mib: float = 12288.0, total_mib: float = 32768.0
) -> MagicMock:
    r = MagicMock()
    r.returncode = 0
    r.stdout = f"{util_pct}, {used_mib}, {total_mib}\n"
    return r


def test_get_gpu_stats_uses_nvidia_when_found():
    """get_gpu_stats() routes to nvidia-smi when _NVIDIA_FOUND is True."""
    with (
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", True),
        patch.object(metrics_mod, "_NVIDIA_VRAM_TOTAL_GB", 32.0),
        patch("subprocess.run", return_value=_nvidia_stats_result(82.0, 12288.0, 32768.0)),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 82.0
    assert abs(vram_used - 12.0) < 0.01
    assert abs(vram_total - 32.0) < 0.01


def test_get_gpu_stats_nvidia_subprocess_error_reports_unmeasured():
    """nvidia-smi crashing means UNMEASURED, not idle; the cached total stays known."""
    with (
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", True),
        patch.object(metrics_mod, "_NVIDIA_VRAM_TOTAL_GB", 24.0),
        patch("subprocess.run", side_effect=OSError),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct is None
    assert vram_used is None
    assert vram_total == 24.0


def test_get_gpu_stats_nvidia_nonzero_returncode_reports_unmeasured():
    """A non-zero nvidia-smi exit means UNMEASURED, not 0% utilisation."""
    bad = MagicMock()
    bad.returncode = 1
    bad.stdout = ""
    with (
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", True),
        patch.object(metrics_mod, "_NVIDIA_VRAM_TOTAL_GB", 24.0),
        patch("subprocess.run", return_value=bad),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct is None
    assert vram_total == 24.0


# ---------------------------------------------------------------------------
# _detect_nvidia compute_cap tests
# ---------------------------------------------------------------------------

def test_detect_nvidia_returns_compute_cap():
    """_detect_nvidia() parses compute_cap as the third CSV field."""
    r = MagicMock()
    r.returncode = 0
    r.stdout = "GTX 980, 4096, 5.2\n"
    with patch("subprocess.run", return_value=r):
        found, name, vram, compute_cap = metrics_mod._detect_nvidia()
    assert found is True
    assert name == "GTX 980"
    assert compute_cap == 5.2


def test_detect_nvidia_compute_cap_missing():
    """_detect_nvidia() returns 0.0 for compute_cap when the field is absent."""
    r = MagicMock()
    r.returncode = 0
    r.stdout = "GTX 980, 4096\n"
    with patch("subprocess.run", return_value=r):
        found, name, vram, compute_cap = metrics_mod._detect_nvidia()
    assert found is True
    assert compute_cap == 0.0


def test_detect_gpu_nvidia_includes_compute_cap(clean_gpu_globals):
    """detect_gpu() includes compute_cap in the returned dict for NVIDIA."""
    result = _nvidia_detect_result("NVIDIA GeForce GTX 980", 4096, compute_cap=5.2)
    with patch("subprocess.run", return_value=result):
        info = detect_gpu()
    assert info["vendor"] == "nvidia"
    assert info["compute_cap"] == 5.2


def test_detect_gpu_non_nvidia_compute_cap_zero(clean_gpu_globals):
    """detect_gpu() returns compute_cap=0.0 for non-NVIDIA (AMD fallback) paths."""
    uevent_paths = ["/sys/class/drm/card1/device/uevent"]
    dev = "/sys/class/drm/card1/device"
    uevent_data = {
        "/sys/class/drm/card1/device/uevent": "DRIVER=amdgpu\n",
        f"{dev}/mem_info_vram_total": str(8 * 1024**3),
    }

    def fake_open(path, *a, **kw):
        return mock_open(read_data=uevent_data.get(path, ""))()

    with (
        # Pin the host: the Apple branch would otherwise short-circuit before the
        # simulated Linux sysfs is read (hermia-rk3k).
        patch("hermia.metrics.sys.platform", "linux"),
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    assert info["vendor"] == "amd"
    assert info["compute_cap"] == 0.0


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
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch.object(metrics_mod, "_APPLE_SILICON", False),
        patch.object(metrics_mod, "_INTEL_IGPU", False),
        patch.object(metrics_mod, "_MAC_DISCRETE", False),
        patch.object(metrics_mod, "_AMD_DEV", dev),
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
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch.object(metrics_mod, "_APPLE_SILICON", False),
        patch.object(metrics_mod, "_INTEL_IGPU", False),
        patch.object(metrics_mod, "_MAC_DISCRETE", False),
        patch.object(metrics_mod, "_AMD_DEV", dev),
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.glob.glob", return_value=[f"{dev}/uevent"]),
        patch("builtins.open", side_effect=fake_open),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 50.0
    assert abs(vram_used - 2.0) < 0.01


# ---------------------------------------------------------------------------
# Apple Silicon detection and stats tests
# ---------------------------------------------------------------------------

def _make_sysctl_run(key: str, value: str) -> MagicMock:
    """Return a mock subprocess.run result for a sysctl query."""
    r = MagicMock()
    r.returncode = 0
    r.stdout = value + "\n"
    return r


def _ioreg_output(gpu_pct: int = 35, mem_used_bytes: int = 2 * 1024**3) -> str:
    return (
        f'"PerformanceStatistics" = {{"In use system memory (driver)"=0,'
        f'"Device Utilization %"={gpu_pct},'
        f'"In use system memory"={mem_used_bytes}}}\n'
    )


def test_detect_apple_silicon_arm64_native(clean_gpu_globals):
    """detect_gpu() returns apple vendor when platform.machine() == 'arm64'."""
    sp_json = json.dumps({"SPDisplaysDataType": [{"sppci_model": "Apple M3 Pro"}]})

    def fake_run(cmd, **kw):
        r = MagicMock()
        r.returncode = 0
        if "hw.memsize" in cmd:
            r.stdout = str(18 * 1024**3) + "\n"
        elif "SPDisplaysDataType" in cmd:
            r.stdout = sp_json
        else:
            r.returncode = 1
            r.stdout = ""
        return r

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("hermia.metrics.platform.machine", return_value="arm64"),
        patch("hermia.metrics.sys.platform", "darwin"),
        patch("hermia.metrics.glob.glob", return_value=[]),
    ):
        info = detect_gpu()

    assert info["found"] is True
    assert info["vendor"] == "apple"
    assert info["card"] == "Apple M3 Pro"
    assert abs(info["vram_total_gb"] - 18.0) < 0.1
    assert metrics_mod._APPLE_SILICON is True


def test_detect_apple_silicon_rosetta(clean_gpu_globals):
    """detect_gpu() detects Apple Silicon even when Python runs under Rosetta (x86_64)."""
    sp_json = json.dumps({"SPDisplaysDataType": [{"sppci_model": "Apple M1 Pro"}]})

    def fake_run(cmd, **kw):
        r = MagicMock()
        r.returncode = 0
        if "hw.optional.arm64" in cmd:
            r.stdout = "1\n"
        elif "hw.memsize" in cmd:
            r.stdout = str(16 * 1024**3) + "\n"
        elif "SPDisplaysDataType" in cmd:
            r.stdout = sp_json
        else:
            r.returncode = 1
            r.stdout = ""
        return r

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("hermia.metrics.platform.machine", return_value="x86_64"),
        patch("hermia.metrics.sys.platform", "darwin"),
        patch("hermia.metrics.glob.glob", return_value=[]),
    ):
        info = detect_gpu()

    assert info["found"] is True
    assert info["vendor"] == "apple"
    assert info["card"] == "Apple M1 Pro"
    assert abs(info["vram_total_gb"] - 16.0) < 0.1


def test_detect_apple_silicon_not_darwin(clean_gpu_globals):
    """detect_gpu() does not report Apple Silicon on Linux."""
    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.sys.platform", "linux"),
        patch("hermia.metrics.glob.glob", return_value=[]),
    ):
        info = detect_gpu()

    assert info["vendor"] != "apple"


def test_get_gpu_stats_apple_silicon_ioreg():
    """get_gpu_stats() returns ioreg data when _APPLE_SILICON is True."""
    mem_bytes = int(1.5 * 1024**3)

    with (
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_APPLE_SILICON", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch.object(metrics_mod, "_APPLE_VRAM_TOTAL_GB", 18.0),
        patch("subprocess.run", return_value=MagicMock(
            returncode=0, stdout=_ioreg_output(gpu_pct=42, mem_used_bytes=mem_bytes)
        )),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 42.0
    assert abs(vram_used - 1.5) < 0.01
    assert vram_total == 18.0


def test_get_gpu_stats_apple_silicon_ioreg_error_reports_unmeasured():
    """ioreg failing means UNMEASURED; the total detection already found stays known."""
    with (
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_APPLE_SILICON", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch.object(metrics_mod, "_APPLE_VRAM_TOTAL_GB", 16.0),
        patch("subprocess.run", side_effect=OSError),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct is None
    assert vram_used is None
    assert vram_total == 16.0


# ---------------------------------------------------------------------------
# hermia-qqz: Intel iGPU detection and CPU-only fallback
# ---------------------------------------------------------------------------

def test_detect_intel_igpu_linux(clean_gpu_globals):
    """detect_gpu() returns vendor=intel when DRIVER=i915 is the only GPU on Linux."""
    uevent_paths = ["/sys/class/drm/card0/device/uevent"]
    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.sys.platform", "linux"),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", mock_open(read_data="DRIVER=i915\n")),
    ):
        info = detect_gpu()

    assert info["found"] is True
    assert info["vendor"] == "intel"
    assert "Intel" in info["card"] or info["card"] == "Intel iGPU"
    assert metrics_mod._INTEL_IGPU is True
    assert metrics_mod._AMD_DEV is None


def test_detect_intel_igpu_xe_driver_linux(clean_gpu_globals):
    """detect_gpu() detects Intel Xe GPU (DRIVER=xe) on Linux."""
    uevent_paths = ["/sys/class/drm/card0/device/uevent"]
    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.sys.platform", "linux"),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", mock_open(read_data="DRIVER=xe\n")),
    ):
        info = detect_gpu()

    assert info["found"] is True
    assert info["vendor"] == "intel"


def test_detect_intel_igpu_macos(clean_gpu_globals):
    """detect_gpu() returns vendor=intel when system_profiler reports an Intel GPU."""
    sp_json = json.dumps({"SPDisplaysDataType": [{"sppci_model": "Intel Iris Pro 580"}]})

    def fake_run(cmd, **kw):
        r = MagicMock()
        r.returncode = 0
        if "SPDisplaysDataType" in cmd:
            r.stdout = sp_json
        else:
            r.returncode = 1
            r.stdout = ""
        return r

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("hermia.metrics.sys.platform", "darwin"),
        patch("hermia.metrics.platform.machine", return_value="x86_64"),
        patch("hermia.metrics.glob.glob", return_value=[]),
    ):
        info = detect_gpu()

    assert info["found"] is True
    assert info["vendor"] == "intel"
    assert info["card"] == "Intel Iris Pro 580"
    assert metrics_mod._INTEL_IGPU is True


def test_detect_intel_igpu_not_found_linux(clean_gpu_globals):
    """detect_gpu() returns vendor=none when no GPU at all on Linux."""
    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.sys.platform", "linux"),
        patch("hermia.metrics.glob.glob", return_value=[]),
    ):
        info = detect_gpu()

    assert info["found"] is False
    assert info["vendor"] == "none"
    assert metrics_mod._INTEL_IGPU is False


def test_detect_amd_takes_priority_over_intel(clean_gpu_globals):
    """AMD dGPU wins when both DRIVER=amdgpu and DRIVER=i915 are present."""
    uevent_paths = [
        "/sys/class/drm/card0/device/uevent",
        "/sys/class/drm/card1/device/uevent",
    ]
    uevent_data = {
        "/sys/class/drm/card0/device/uevent": "DRIVER=i915\n",
        "/sys/class/drm/card1/device/uevent": "DRIVER=amdgpu\n",
        "/sys/class/drm/card1/device/mem_info_vram_total": str(8 * 1024**3),
    }

    def fake_open(path, *a, **kw):
        return mock_open(read_data=uevent_data.get(path, ""))()

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("hermia.metrics.sys.platform", "linux"),
        patch("hermia.metrics.glob.glob", return_value=uevent_paths),
        patch("builtins.open", side_effect=fake_open),
    ):
        info = detect_gpu()

    assert info["vendor"] == "amd"
    assert metrics_mod._INTEL_IGPU is False


def test_get_gpu_stats_intel_routes_to_intel_stats():
    """get_gpu_stats() routes to _gpu_stats_intel() when _INTEL_IGPU is True."""
    with (
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_INTEL_IGPU", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch.object(metrics_mod, "_APPLE_SILICON", False),
        patch.object(metrics_mod, "_AMD_DEV", None),
        patch("hermia.metrics._gpu_stats_intel", return_value=(55.0, 0.0, 0.0)),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct == 55.0
    assert vram_used == 0.0
    assert vram_total == 0.0


def test_get_gpu_stats_intel_no_tool_reports_unmeasured():
    """No intel_gpu_top means UNMEASURED, not a GPU sitting at 0%."""
    with (
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_INTEL_IGPU", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch.object(metrics_mod, "_APPLE_SILICON", False),
        patch.object(metrics_mod, "_AMD_DEV", None),
        patch("hermia.metrics.sys.platform", "linux"),
        patch("subprocess.run", side_effect=FileNotFoundError),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct is None
    assert vram_used is None
    assert vram_total is None


def test_get_gpu_stats_intel_timeout_captures_partial_output():
    """_gpu_stats_intel() captures stdout from TimeoutExpired and parses it."""
    import subprocess as sp

    sample_json = '{"engines": {"Render/3D/0": {"busy": 63.5}}}\n'
    exc = sp.TimeoutExpired(cmd=["intel_gpu_top"], timeout=0.4, output=sample_json)

    with (
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_INTEL_IGPU", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch.object(metrics_mod, "_APPLE_SILICON", False),
        patch.object(metrics_mod, "_AMD_DEV", None),
        patch("hermia.metrics.sys.platform", "linux"),
        patch("subprocess.run", side_effect=exc),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert abs(gpu_pct - 63.5) < 0.01
    assert vram_used == 0.0
    assert vram_total == 0.0


def test_get_gpu_stats_cpu_only_reports_unmeasured():
    """No GPU at all means UNMEASURED. hermia-dl2e: 0.0 asserts a measurement we do not have."""
    with (
        # detection has already happened; these tests describe its RESULT
        patch.object(metrics_mod, "_GPU_DETECTED", True),
        patch.object(metrics_mod, "_NVIDIA_FOUND", False),
        patch.object(metrics_mod, "_APPLE_SILICON", False),
        patch.object(metrics_mod, "_INTEL_IGPU", False),
        patch.object(metrics_mod, "_MAC_DISCRETE", False),
        patch.object(metrics_mod, "_AMD_DEV", None),
    ):
        gpu_pct, vram_used, vram_total = get_gpu_stats()

    assert gpu_pct is None
    assert vram_used is None
    assert vram_total is None


def test_cpu_only_host_reports_none_not_zero(clean_gpu_globals):
    """hermia-dl2e: "no GPU" and "GPU idle" are different facts."""
    with patch.object(metrics_mod, "_GPU_DETECTED", True):
        m = metrics_mod.get_system_metrics()
    assert m["gpu_pct"] is None, "a machine with no GPU has not measured 0% utilisation"
    assert m["vram_used_gb"] is None
    assert m["cpu_pct"] is not None, "CPU is always measurable"


def test_peak_omits_a_field_it_never_measured():
    """An omitted key is what lets runner.py write None instead of a fabricated 0.0."""
    s = metrics_mod.MetricsSampler()
    s.samples = [
        {"cpu_pct": 10.0, "ram_used_gb": 4.0, "gpu_pct": None,
         "vram_used_gb": None, "vram_total_gb": None},
        {"cpu_pct": 50.0, "ram_used_gb": 5.0, "gpu_pct": None,
         "vram_used_gb": None, "vram_total_gb": None},
    ]
    peak = s.peak()
    assert peak["cpu_pct"] == 50.0
    assert "gpu_pct" not in peak, "an unmeasured field must be absent, not zero"
    assert "vram_used_gb" not in peak


def test_get_gpu_stats_initialises_detection_itself(clean_gpu_globals):
    """hermia-dl2e: three callers bypassed MetricsSampler.start() entirely.

    runner.py's cold-load VRAM before/after and preflight.py -- the code that tells a user
    whether a model fits in their VRAM -- call get_gpu_stats() directly. With detection
    wired only into the sampler they read globals at their defaults and preflight would
    have answered 0 GB. Initialising at the READ is the placement a new caller cannot bypass.
    """
    with patch.object(metrics_mod, "detect_gpu") as detect:
        metrics_mod.get_gpu_stats()
    assert detect.called, "get_gpu_stats() must ensure detection, not assume it"


def test_no_collector_fabricates_a_zero_when_its_probe_fails(clean_gpu_globals):
    """hermia-dl2e: finishing the class. 0.0 is a measurement; absence is not.

    Every collector used to return 0.0 when its tool was missing or crashed, so a host with
    no intel_gpu_top, no nvidia-smi, or a failing ioreg recorded "GPU at 0%" -- indistinguishable
    from a real idle GPU. Found one layer at a time across three rounds of outside-family review.
    """
    cases = {
        "no GPU": dict(_NVIDIA_FOUND=False, _APPLE_SILICON=False, _INTEL_IGPU=False, _AMD_DEV=None),
        "intel, tool missing": dict(
            _NVIDIA_FOUND=False, _APPLE_SILICON=False, _INTEL_IGPU=True, _AMD_DEV=None
        ),
        "nvidia, smi missing": dict(
            _NVIDIA_FOUND=True, _APPLE_SILICON=False, _INTEL_IGPU=False, _AMD_DEV=None
        ),
    }
    for label, globals_ in cases.items():
        for name, value in globals_.items():
            setattr(metrics_mod, name, value)
        with patch.object(metrics_mod, "_GPU_DETECTED", True), patch(
            "subprocess.run", side_effect=FileNotFoundError
        ):
            gpu_pct, vram_used, _ = metrics_mod.get_gpu_stats()
            recorded = metrics_mod.get_system_metrics()
        assert gpu_pct is None, f"{label}: utilisation was not measured, so it is not 0.0"
        assert vram_used is None, f"{label}: VRAM was not measured, so it is not 0.0"
        assert recorded["gpu_pct"] is None, f"{label}: a recorded row must not claim 0.0"


def test_sampler_primes_the_cpu_counter(clean_gpu_globals):
    """psutil.cpu_percent's first call in a process always returns 0.0 (hermia-dl2e)."""
    calls = []
    real = metrics_mod.MetricsSampler

    with patch("psutil.cpu_percent", side_effect=lambda **kw: calls.append(1) or 5.0):
        s = real()
        s.start()
        s.stop()
    assert calls, "start() must take and discard a priming reading"


# ---------------------------------------------------------------------------
# hermia-j6a8 — an unprobed GPU is UNKNOWN, never zero
# ---------------------------------------------------------------------------

def _no_gpu_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every probe come up empty, as they all do on Windows for a non-NVIDIA card."""
    monkeypatch.setattr(metrics_mod, "_detect_nvidia", lambda: (False, "", 0.0, 0.0))
    monkeypatch.setattr(metrics_mod, "_detect_apple_silicon", lambda: (False, "", 0.0))
    monkeypatch.setattr(metrics_mod, "_find_amdgpu_dev", lambda: None)
    monkeypatch.setattr(metrics_mod, "_detect_intel_igpu", lambda: (False, ""))
    monkeypatch.setattr(metrics_mod, "_detect_mac_discrete", lambda: None)


def test_unprobed_platform_reports_unknown_not_none(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """On Windows, "no GPU" is a claim hermia is not entitled to make.

    Confirmed on real hardware 2026-09-12: a 16 GB RX 7800 XT reported vendor='none'.
    The AMD probe is `glob('/sys/class/drm/card*/device/uevent')` -- Linux sysfs -- and the
    Intel probe is equally POSIX, so on Windows neither can find a card that is physically
    present. nvidia-smi DOES work on Windows, so an NVIDIA card is still detected; it is
    specifically the AMD and Intel paths that have no Windows implementation. An empty
    result there means NOT PROBED, which is a different fact from NO GPU PRESENT.
    """
    _no_gpu_anywhere(monkeypatch)
    monkeypatch.setattr(sys, "platform", "win32")
    info = metrics_mod.detect_gpu()
    assert info["vendor"] == "unknown", (
        "a platform with no AMD/Intel probe must not claim there is no GPU"
    )
    assert info["found"] is False


def test_unprobed_platform_does_not_fabricate_a_vram_measurement(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """0.0 GB is a MEASUREMENT. None is the absence of one. They are not interchangeable."""
    _no_gpu_anywhere(monkeypatch)
    monkeypatch.setattr(sys, "platform", "win32")
    assert metrics_mod.detect_gpu()["vram_total_gb"] is None


def test_genuinely_gpu_less_posix_host_still_reports_none_vendor(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """On Linux every probe is implemented, so an empty result IS evidence of no GPU.

    This is the negative control for the test above: the fix must not turn every
    CPU-only host into "unknown", which would destroy a real signal.
    """
    _no_gpu_anywhere(monkeypatch)
    monkeypatch.setattr(sys, "platform", "linux")
    info = metrics_mod.detect_gpu()
    assert info["vendor"] == "none"
    assert info["vram_total_gb"] is None, "absent VRAM is still not a measurement of zero"


def test_mac_where_every_probe_is_empty_is_unknown_not_none(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """macOS has no /sys/class/drm either, so the AMD probe is as blind there as on Windows.

    Found by the outside-family review gate on the first version of this fix, which keyed on
    `sys.platform != "win32"` and so still published a darwin host reaching this fallback as
    vendor='none' -> 'local:cpu' -> system RAM -- the exact defect this bead exists to remove,
    reproduced one platform over.

    ⚠️ SCOPE, narrowed after a SECOND gate pass called out the original wording. This proves
    only what it mocks: a darwin host where every probe came up empty. It does NOT prove the
    2019 16-inch MacBook Pro case its first docstring claimed, because that machine has an
    Intel UHD 630 alongside its discrete AMD card, `_detect_intel_igpu` matches ANY darwin
    display whose model contains "Intel", and it is checked BEFORE this fallback -- so such a
    machine exits at vendor='intel' and never reaches the code under test. That shadowing is
    a real, separate defect (hermia-mont) and this test must not be read as covering it.
    hermia-mont is now fixed and covered by test_intel_mac_with_discrete_amd_reports_the_amd_card;
    this test was renamed from ..._intel_mac_with_discrete_amd_gpu_is_unknown_not_none, whose
    name claimed the opposite of the current behaviour.
    """
    _no_gpu_anywhere(monkeypatch)
    monkeypatch.setattr(sys, "platform", "darwin")
    info = metrics_mod.detect_gpu()
    assert info["vendor"] == "unknown", (
        "the AMD sysfs probe cannot run on darwin, so 'no GPU' is not a claim we can make"
    )
    assert info["vram_total_gb"] is None


def test_found_amd_card_with_unreadable_vram_reports_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_gpu_globals: None
) -> None:
    """Same fabrication, one layer down: the card IS found, the measurement is not.

    `mem_info_vram_total` can be absent or unreadable (permissions, a kernel that does not
    export it, a driver mid-reload). The except arm used to substitute 0.0, publishing a
    measurement of zero for a card hermia had just successfully identified.
    """
    monkeypatch.setattr(metrics_mod, "_detect_nvidia", lambda: (False, "", 0.0, 0.0))
    monkeypatch.setattr(metrics_mod, "_detect_apple_silicon", lambda: (False, "", 0.0))
    # A real device path whose mem_info_vram_total does not exist -> the except arm.
    dev = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    dev.mkdir(parents=True)
    monkeypatch.setattr(metrics_mod, "_find_amdgpu_dev", lambda: str(dev))

    info = metrics_mod.detect_gpu()

    assert info["found"] is True, "positive control: the card must still be detected"
    assert info["vendor"] == "amd"
    assert info["vram_total_gb"] is None, "an unreadable measurement is not a measurement of 0"


def test_amd_vram_file_that_is_empty_or_garbage_does_not_crash_detection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_gpu_globals: None
) -> None:
    """`int("")` raises ValueError, which an `except OSError` does not catch.

    The file can exist and be readable yet hold nothing useful -- a driver mid-reload, a
    kernel that exports the node before populating it. The original except arm named only
    OSError, so this escaped as an unhandled crash out of detect_gpu() rather than being
    recorded as an unmeasured value. Found by the outside-family gate.
    """
    dev = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    dev.mkdir(parents=True)
    monkeypatch.setattr(metrics_mod, "_detect_nvidia", lambda: (False, "", 0.0, 0.0))
    monkeypatch.setattr(metrics_mod, "_detect_apple_silicon", lambda: (False, "", 0.0))
    monkeypatch.setattr(metrics_mod, "_find_amdgpu_dev", lambda: str(dev))

    for garbage in ("", "   ", "not-a-number", "12.5GB"):
        (dev / "mem_info_vram_total").write_text(garbage, encoding="utf-8")
        info = metrics_mod.detect_gpu()
        assert info["found"] is True, f"card must still be found for {garbage!r}"
        assert info["vram_total_gb"] is None, f"{garbage!r} is not a measurement"


def test_amd_enumeration_survives_a_garbage_vram_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_gpu_globals: None
) -> None:
    """The same flaw sits one level earlier, in _find_amdgpu_dev's ranking read.

    It crashes during card ENUMERATION, before detect_gpu() reaches the VRAM read at all,
    so fixing only the later site would leave the earlier one live.
    """
    drm = tmp_path / "sys" / "class" / "drm"
    dev = drm / "card0" / "device"
    dev.mkdir(parents=True)
    (dev / "uevent").write_text("DRIVER=amdgpu\n", encoding="utf-8")
    (dev / "mem_info_vram_total").write_text("", encoding="utf-8")
    monkeypatch.setattr(metrics_mod.glob, "glob", lambda _p: [str(dev / "uevent")])

    assert metrics_mod._find_amdgpu_dev() == str(dev), (
        "a card with an unreadable VRAM value still exists and must still be enumerated"
    )


# ---------------------------------------------------------------------------
# hermia-gq0g: the AMD card name was the DRM node ("card0"), never the model, so every AMD
# GPU fell through to local:vulkan/amd. hermia-mont: on an Intel Mac with a discrete AMD card
# the iGPU matched first, hiding the card and publishing host RAM as its memory.
# Tests drafted by the local fleet, rewritten in-window. NOT verified on real AMD or Intel-Mac
# hardware (none reachable); the fixtures follow the documented sysfs / lspci -mm /
# system_profiler formats.

import subprocess  # noqa: E402

from hermia.submit import compute_host_class, compute_unified_memory_gb  # noqa: E402


def _run_returning(stdout: str, expect: list[str] | None = None):
    def fake_run(cmd, **kw):
        if expect is not None:
            assert cmd == expect
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    return fake_run


def _spdisplays(*entries: dict) -> str:
    return json.dumps({"SPDisplaysDataType": list(entries)})


def test_amd_card_name_reads_product_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The driver's own product_name wins when it is present."""
    (tmp_path / "product_name").write_text("AMD Radeon RX 7800 XT\n")
    monkeypatch.setattr(sys, "platform", "linux")
    assert metrics_mod._amd_card_name(str(tmp_path)) == "AMD Radeon RX 7800 XT"


def test_amd_card_name_falls_back_to_lspci(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No product_name: the device name comes from lspci -mm for the card's PCI slot."""
    (tmp_path / "uevent").write_text("DRIVER=amdgpu\nPCI_SLOT_NAME=0000:03:00.0\n")
    out = (
        '03:00.0 "VGA compatible controller" "Advanced Micro Devices, Inc. [AMD/ATI]" '
        '"Navi 32 [Radeon RX 7700 XT / 7800 XT]" -rc8 "Sapphire Technology Limited" '
        '"Device 2426"\n'
    )
    monkeypatch.setattr(
        metrics_mod.subprocess, "run",
        _run_returning(out, ["lspci", "-mm", "-s", "0000:03:00.0"]),
    )
    monkeypatch.setattr(sys, "platform", "linux")
    assert metrics_mod._amd_card_name(str(tmp_path)) == "Navi 32 [Radeon RX 7700 XT / 7800 XT]"


def test_amd_card_name_unknown_is_blank_not_drm_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no name source the answer is blank: never the DRM node name the bug published.

    The device path is the REAL sysfs shape, so the old extraction
    (dev.split("/sys/class/drm/")[-1].split("/")[0]) would yield "card0" here. A tmp_path
    could not catch that regression: the old code yields "" for it (review, test-truth).
    """
    dev = "/sys/class/drm/card0/device"
    files = {f"{dev}/uevent": "DRIVER=amdgpu\nPCI_SLOT_NAME=0000:03:00.0\n"}

    def fake_open(path, *a, **kw):
        if path not in files:
            raise FileNotFoundError(path)
        return mock_open(read_data=files[path])()

    def no_lspci(cmd, **kw):
        raise FileNotFoundError("lspci")

    monkeypatch.setattr("builtins.open", fake_open)
    monkeypatch.setattr(metrics_mod.subprocess, "run", no_lspci)
    assert metrics_mod._amd_card_name(dev) == ""


def test_amd_card_name_survives_a_non_utf8_product_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A FRU string with a stray non-UTF-8 byte falls through instead of crashing detection."""
    (tmp_path / "product_name").write_bytes(b"AMD Instinct MI\xff\n")

    def no_lspci(cmd, **kw):
        raise FileNotFoundError("lspci")

    monkeypatch.setattr(metrics_mod.subprocess, "run", no_lspci)
    assert metrics_mod._amd_card_name(str(tmp_path)) == ""


def test_detect_gpu_amd_branch_uses_model_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """detect_gpu() reports the model name, never the DRM node (hermia-gq0g)."""
    _no_gpu_anywhere(monkeypatch)
    (tmp_path / "product_name").write_text("AMD Radeon RX 6800 XT\n")
    (tmp_path / "mem_info_vram_total").write_text("17163091968")
    monkeypatch.setattr(metrics_mod, "_find_amdgpu_dev", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    info = metrics_mod.detect_gpu()
    assert info["vendor"] == "amd"
    assert info["card"] == "AMD Radeon RX 6800 XT"
    assert compute_host_class(info) == "local:vulkan/amd", "generic by decision (hermia-68jm)"


_REAL_MAC_DISCRETE = metrics_mod.__dict__.get("_detect_mac_discrete")
_REAL_INTEL_IGPU = metrics_mod._detect_intel_igpu


def _mac_with(monkeypatch: pytest.MonkeyPatch, *entries: dict) -> None:
    """A darwin host whose system_profiler lists exactly ``entries``; real mac probes kept."""
    _no_gpu_anywhere(monkeypatch)
    monkeypatch.setattr(metrics_mod, "_detect_mac_discrete", _REAL_MAC_DISCRETE)
    monkeypatch.setattr(metrics_mod, "_detect_intel_igpu", _REAL_INTEL_IGPU)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        metrics_mod.subprocess, "run",
        _run_returning(_spdisplays(*entries), ["system_profiler", "SPDisplaysDataType", "-json"]),
    )


def test_intel_mac_with_discrete_amd_reports_the_amd_card(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """hermia-mont: the 2019 16-inch MacBook Pro shape. The discrete card wins over the iGPU."""
    _mac_with(
        monkeypatch,
        {"sppci_model": "Intel UHD Graphics 630", "spdisplays_vram_shared": "1536 MB"},
        {"sppci_model": "AMD Radeon Pro 5500M", "spdisplays_vendor": "sppci_vendor_amd",
         "spdisplays_vram": "8 GB"},
    )
    info = metrics_mod.detect_gpu()
    assert info["vendor"] == "amd"
    assert info["card"] == "AMD Radeon Pro 5500M"
    assert info["vram_total_gb"] == 8.0
    assert compute_host_class(info) == "local:other", "macOS drives AMD through Metal, not Vulkan"
    assert compute_unified_memory_gb(info) == 8.0


def test_mac_amd_with_unreadable_vram_is_not_host_ram(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """A found card whose VRAM is unreadable is NOT MEASURED, never host RAM."""
    _mac_with(
        monkeypatch,
        {"sppci_model": "Intel UHD Graphics 630"},
        {"sppci_model": "AMD Radeon Pro 5300M", "spdisplays_vendor": "sppci_vendor_amd"},
    )
    info = metrics_mod.detect_gpu()
    assert info["vendor"] == "amd"
    assert info["vram_total_gb"] is None
    assert compute_unified_memory_gb(info) is None


def test_mac_pro_with_only_amd_is_amd_not_unknown(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """A Xeon Mac Pro has no iGPU at all; its card used to land at vendor='unknown'."""
    _mac_with(monkeypatch, {"sppci_model": "AMD Radeon Pro W5700X", "spdisplays_vram": "16 GB"})
    info = metrics_mod.detect_gpu()
    assert info["vendor"] == "amd"
    assert info["vram_total_gb"] == 16.0


def test_intel_only_mac_is_still_intel(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """No discrete card: unchanged, the iGPU is reported."""
    _mac_with(monkeypatch, {"sppci_model": "Intel Iris Plus Graphics"})
    assert metrics_mod.detect_gpu()["vendor"] == "intel"


def test_mac_discrete_parses_megabytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """system_profiler reports some cards in MB."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        metrics_mod.subprocess, "run",
        _run_returning(_spdisplays({"sppci_model": "AMD Radeon Pro 555X",
                                    "spdisplays_vram": "4096 MB"})),
    )
    assert metrics_mod._detect_mac_discrete() == ("amd", "AMD Radeon Pro 555X", 4.0)


def test_mac_discrete_is_none_off_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The macOS probe never runs elsewhere."""
    monkeypatch.setattr(sys, "platform", "linux")

    def must_not_run(cmd, **kw):
        raise AssertionError("system_profiler must not run off darwin")

    monkeypatch.setattr(metrics_mod.subprocess, "run", must_not_run)
    assert metrics_mod._detect_mac_discrete() is None



def test_amd_card_name_ignores_a_failed_lspci(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """lspci exiting non-zero is no name, not its stdout."""
    (tmp_path / "uevent").write_text("DRIVER=amdgpu\nPCI_SLOT_NAME=0000:03:00.0\n")

    def failing(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout='a "b" "c" "d"\n', stderr="")

    monkeypatch.setattr(metrics_mod.subprocess, "run", failing)
    assert metrics_mod._amd_card_name(str(tmp_path)) == ""


def test_mac_with_discrete_nvidia_reports_nvidia_and_a_gpu(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """An older Intel Mac's NVIDIA card is found, and gpu_present() agrees there is a GPU."""
    _mac_with(
        monkeypatch,
        {"sppci_model": "Intel Iris Pro"},
        {"sppci_model": "NVIDIA GeForce GT 750M", "spdisplays_vram": "2 GB"},
    )
    info = metrics_mod.detect_gpu()
    assert (info["vendor"], info["vram_total_gb"]) == ("nvidia", 2.0)
    monkeypatch.setattr(metrics_mod, "_GPU_DETECTED", True)
    assert metrics_mod.gpu_present() is True



def test_mac_prefers_the_largest_discrete_card(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """Internal 5500M, a bigger eGPU, a smaller eGPU: the largest stated VRAM wins.

    The largest is in the MIDDLE, so neither "first discrete wins" nor "last wins" passes.
    """
    _mac_with(
        monkeypatch,
        {"sppci_model": "Intel UHD Graphics 630"},
        {"sppci_model": "AMD Radeon Pro 5500M", "spdisplays_vram": "8 GB"},
        {"sppci_model": "AMD Radeon RX 6800 XT", "spdisplays_vram": "16 GB"},
        {"sppci_model": "Radeon RX 580", "spdisplays_vram": "4 GB"},
    )
    info = metrics_mod.detect_gpu()
    assert (info["card"], info["vram_total_gb"]) == ("AMD Radeon RX 6800 XT", 16.0)


@pytest.mark.parametrize(
    "entry",
    [
        {"sppci_model": "Radeon Pro 560X", "spdisplays_vram": "4 GB"},  # name only: 'radeon'
        {"sppci_model": "FirePro", "spdisplays_vendor": "ATI (0x1002)", "spdisplays_vram": "4 GB"},
    ],
)
def test_mac_amd_recognised_by_radeon_or_pci_id(
    entry: dict, monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """Apple names some AMD cards without 'AMD' ('Radeon Pro 560X'); older text gives the PCI ID."""
    _mac_with(monkeypatch, {"sppci_model": "Intel UHD Graphics 630"}, entry)
    assert metrics_mod.detect_gpu()["vendor"] == "amd"


def test_mac_framebuffer_sized_vram_is_not_measured(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """A card with no macOS driver reports only its boot framebuffer: not its memory."""
    _mac_with(
        monkeypatch,
        {"sppci_model": "AMD Radeon RX 7900 XTX", "spdisplays_vram": "7 MB"},
    )
    info = metrics_mod.detect_gpu()
    assert info["vendor"] == "amd"
    assert info["vram_total_gb"] is None
    assert compute_unified_memory_gb(info) is None


def test_mac_nvidia_card_is_not_labelled_cuda(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """macOS cannot run CUDA: a Mac's NVIDIA card is local:other, like its AMD card."""
    _mac_with(monkeypatch, {"sppci_model": "NVIDIA GeForce GTX 1080", "spdisplays_vram": "8 GB"})
    info = metrics_mod.detect_gpu()
    assert info["vendor"] == "nvidia"
    assert compute_host_class(info) == "local:other"


def test_mac_probes_share_one_system_profiler_answer(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """A cold first call that times out must not let a second call bring back iGPU + host RAM."""
    _no_gpu_anywhere(monkeypatch)
    monkeypatch.setattr(metrics_mod, "_detect_mac_discrete", _REAL_MAC_DISCRETE)
    monkeypatch.setattr(metrics_mod, "_detect_intel_igpu", _REAL_INTEL_IGPU)
    monkeypatch.setattr(sys, "platform", "darwin")
    calls = []
    good = _spdisplays(
        {"sppci_model": "Intel UHD Graphics 630"},
        {"sppci_model": "AMD Radeon Pro 5500M", "spdisplays_vram": "8 GB"},
    )

    def first_times_out(cmd, **kw):
        calls.append(cmd)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(cmd, 5)
        return subprocess.CompletedProcess(cmd, 0, stdout=good, stderr="")

    monkeypatch.setattr(metrics_mod.subprocess, "run", first_times_out)
    info = metrics_mod.detect_gpu()
    assert len(calls) == 1, "one system_profiler call per detection pass"
    assert info["vendor"] == "unknown", "an unread profiler is NOT an Intel-only Mac"
    assert compute_unified_memory_gb(info) is None


def test_detection_passes_do_not_overlap(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """CodeRabbit on #219: a second thread's pass must not start inside the first one.

    Pass A blocks inside system_profiler; pass B (another thread) must not reach
    system_profiler until A has finished, so B can never reset A's shared answer mid-pass.
    """
    import threading as _threading

    _no_gpu_anywhere(monkeypatch)
    monkeypatch.setattr(metrics_mod, "_detect_mac_discrete", _REAL_MAC_DISCRETE)
    monkeypatch.setattr(metrics_mod, "_detect_intel_igpu", _REAL_INTEL_IGPU)
    monkeypatch.setattr(sys, "platform", "darwin")
    entered = _threading.Event()
    release = _threading.Event()
    calls: list[str] = []
    good = _spdisplays({"sppci_model": "AMD Radeon Pro 5500M", "spdisplays_vram": "8 GB"})

    def blocking_run(cmd, **kw):
        calls.append(_threading.current_thread().name)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5), "test deadlocked"
        return subprocess.CompletedProcess(cmd, 0, stdout=good, stderr="")

    monkeypatch.setattr(metrics_mod.subprocess, "run", blocking_run)
    results: dict[str, dict] = {}
    a = _threading.Thread(target=lambda: results.update(A=metrics_mod.detect_gpu()), name="A")
    b = _threading.Thread(target=lambda: results.update(B=metrics_mod.detect_gpu()), name="B")
    a.start()
    assert entered.wait(5)
    b.start()
    b.join(0.3)
    assert calls == ["A"], "pass B started while pass A was still inside system_profiler"
    release.set()
    a.join(5)
    b.join(5)
    assert results["A"]["vendor"] == results["B"]["vendor"] == "amd"



def test_mac_discrete_card_reports_its_vram_total_in_live_stats(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """Scott 2026-10-17: a detected Mac card's VRAM is reported, not dropped by the sampler.

    Capacity was measured at detection; utilisation and VRAM in use have no macOS probe and
    stay None (not measured), never 0.0.
    """
    _mac_with(
        monkeypatch,
        {"sppci_model": "Intel UHD Graphics 630"},
        {"sppci_model": "AMD Radeon Pro 5500M", "spdisplays_vram": "8 GB"},
    )
    metrics_mod.ensure_gpu_detected()
    assert metrics_mod.get_gpu_stats() == (None, None, 8.0)
    assert metrics_mod.get_system_metrics()["vram_total_gb"] == 8.0


def test_mac_discrete_card_with_unstated_vram_reports_none(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """No stated VRAM: the live total is not measured either -- never host RAM, never 0.0."""
    _mac_with(monkeypatch, {"sppci_model": "AMD Radeon Pro 5300M"})
    metrics_mod.ensure_gpu_detected()
    assert metrics_mod.get_gpu_stats() == (None, None, None)


def test_reads_after_detection_never_wait_on_the_detection_lock(
    monkeypatch: pytest.MonkeyPatch, clean_gpu_globals: None
) -> None:
    """Review 2026-10-17, finding 2: once detected, reads must not block on the lock.

    Another thread holds the detection lock for the whole test; gpu_present() and
    get_gpu_stats() must still return. This PINS a property that already held before the
    lock existed (the once-only check returns before taking it); on the previous commit the
    test fails only on its VRAM assertion. It guards against a future change making reads
    take the lock. It says nothing about the FIRST detection pass, which every caller still
    waits for (about 0.7 s on an M1 Pro, longer if a probe tool hangs to its timeout).
    """
    import threading as _threading

    _mac_with(monkeypatch, {"sppci_model": "AMD Radeon Pro 5500M", "spdisplays_vram": "8 GB"})
    metrics_mod.ensure_gpu_detected()
    held, release = _threading.Event(), _threading.Event()

    def hold() -> None:
        with metrics_mod._DETECT_LOCK:
            held.set()
            release.wait(5)

    holder = _threading.Thread(target=hold)
    holder.start()
    assert held.wait(5)
    out: dict[str, object] = {}
    reader = _threading.Thread(
        target=lambda: out.update(present=metrics_mod.gpu_present(),
                                  stats=metrics_mod.get_gpu_stats())
    )
    reader.start()
    reader.join(1)
    blocked = reader.is_alive()
    release.set()
    holder.join(5)
    reader.join(5)
    assert not blocked, "a read after detection waited on the detection lock"
    assert out == {"present": True, "stats": (None, None, 8.0)}
