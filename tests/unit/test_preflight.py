"""Unit tests for preflight sanity checks."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from hermia.preflight import OLLAMA_MIN_SECURE_VERSION, check_ollama_security, run_preflight

MODEL_LIST = [
    {"name": "llama3:8b", "size": int(4.7 * 1024**3)},
    {"name": "gemma2:9b", "size": int(5.4 * 1024**3)},
    {"name": "mixtral:8x7b", "size": int(26 * 1024**3)},
]


def _mock_gpu(total: float = 8.0, used: float = 0.0):
    return patch("hermia.preflight.get_gpu_stats", return_value=(80.0, used, total))


def _mock_ram(total_gb: float = 16.0, available_gb: float = 12.0):
    class FakeVM:
        total = int(total_gb * 1024**3)
        available = int(available_gb * 1024**3)
    return patch("hermia.preflight.psutil.virtual_memory", return_value=FakeVM())


def _mock_disk(free_gb: float = 50.0):
    class FakeDisk:
        free = int(free_gb * 1024**3)
    return patch("hermia.preflight.psutil.disk_usage", return_value=FakeDisk())


def test_small_model_passes(tmp_path: Path):
    with _mock_gpu(), _mock_ram(), _mock_disk():
        report = run_preflight(["llama3:8b"], MODEL_LIST, tmp_path)
    check = report.models[0]
    assert check.fits_total_vram
    assert not check.skip


def test_oversized_model_skipped(tmp_path: Path):
    with _mock_gpu(total=8.0), _mock_ram(available_gb=8.0), _mock_disk():
        report = run_preflight(["mixtral:8x7b"], MODEL_LIST, tmp_path)
    check = report.models[0]
    assert check.skip
    assert "mixtral:8x7b" in report.skipped_models


def test_oversized_model_cpu_fallback_not_skipped(tmp_path: Path):
    """26GB model can't fit VRAM but has plenty of RAM — warn but don't skip."""
    with _mock_gpu(total=8.0), _mock_ram(available_gb=50.0), _mock_disk():
        report = run_preflight(["mixtral:8x7b"], MODEL_LIST, tmp_path)
    check = report.models[0]
    assert not check.fits_total_vram
    assert not check.skip  # RAM fallback is possible


def test_tight_vram_warns(tmp_path: Path):
    """Use llama3:8b (not blocklisted) to test the tight-VRAM warning path."""
    with _mock_gpu(total=8.0, used=4.0), _mock_ram(), _mock_disk():
        report = run_preflight(["llama3:8b"], MODEL_LIST, tmp_path)
    check = report.models[0]
    assert not check.fits_current_vram
    assert any("WARN" in w for w in report.warnings)


def test_blocklisted_model_skipped(tmp_path: Path):
    """gemma2:9b is on the Vulkan/gfx900 blocklist and must always be skipped."""
    with _mock_gpu(total=8.0, used=0.0), _mock_ram(available_gb=32.0), _mock_disk():
        report = run_preflight(["gemma2:9b"], MODEL_LIST, tmp_path)
    check = report.models[0]
    assert check.skip
    assert "gemma2:9b" in report.skipped_models
    assert any("Vulkan" in w for w in report.warnings)


def test_low_disk_flagged(tmp_path: Path):
    with _mock_gpu(), _mock_ram(), _mock_disk(free_gb=0.1):
        report = run_preflight(["llama3:8b"], MODEL_LIST, tmp_path)
    assert not report.disk_ok
    assert any("Low disk" in w for w in report.warnings)


def test_runnable_models_excludes_skipped(tmp_path: Path):
    with _mock_gpu(total=8.0), _mock_ram(available_gb=8.0), _mock_disk():
        report = run_preflight(
            ["llama3:8b", "mixtral:8x7b"], MODEL_LIST, tmp_path
        )
    assert "llama3:8b" in report.runnable_models
    assert "mixtral:8x7b" not in report.runnable_models


def test_all_models_runnable_no_warnings(tmp_path: Path):
    with _mock_gpu(total=8.0, used=0.0), _mock_ram(available_gb=12.0), _mock_disk():
        report = run_preflight(["llama3:8b", "phi3:3.8b"], MODEL_LIST, tmp_path)
    assert not report.skipped_models


# ---------------------------------------------------------------------------
# Ollama security checks
# ---------------------------------------------------------------------------

def _mock_version(version: str):
    resp = MagicMock()
    resp.ok = True
    resp.json.return_value = {"version": version}
    return patch("requests.get", return_value=resp)


def test_ollama_security_vulnerable_version():
    with _mock_version("0.16.0"):
        warns = check_ollama_security("http://localhost:11434", fleet_mode=False)
    assert any("CVE-2026-7482" in w for w in warns)
    assert any("0.16.0" in w for w in warns)


def test_ollama_security_prerelease_of_fix_is_vulnerable():
    with _mock_version("0.17.1-rc1"):
        warns = check_ollama_security("http://localhost:11434", fleet_mode=False)
    assert any("CVE-2026-7482" in w for w in warns)


def test_ollama_security_v_prefix_handled():
    with _mock_version("v0.22.1"):
        warns = check_ollama_security("http://localhost:11434", fleet_mode=False)
    assert not any("CVE-2026-7482" in w for w in warns)


def test_ollama_security_build_metadata_handled():
    with _mock_version("0.22.1+build.123"):
        warns = check_ollama_security("http://localhost:11434", fleet_mode=False)
    assert not any("CVE-2026-7482" in w for w in warns)


def test_ollama_security_patched_version():
    with _mock_version(OLLAMA_MIN_SECURE_VERSION):
        warns = check_ollama_security("http://localhost:11434", fleet_mode=False)
    assert not any("CVE-2026-7482" in w for w in warns)


def test_ollama_security_newer_version():
    with _mock_version("0.22.1"):
        warns = check_ollama_security("http://localhost:11434", fleet_mode=False)
    assert not any("CVE-2026-7482" in w for w in warns)


def test_ollama_security_version_unreachable():
    with patch("requests.get", side_effect=Exception("connection refused")):
        warns = check_ollama_security("http://localhost:11434", fleet_mode=False)
    assert not any("CVE-2026-7482" in w for w in warns)
    assert any("CVE-2026-5757" in w for w in warns)


def test_ollama_security_fleet_mode_no_5757():
    with _mock_version("0.22.1"):
        warns = check_ollama_security("http://remotehost:11434", fleet_mode=True)
    assert not any("CVE-2026-5757" in w for w in warns)


def test_preflight_report_security_warnings_populated(tmp_path: Path):
    with (
        _mock_gpu(),
        _mock_ram(),
        _mock_disk(),
        _mock_version("0.16.0"),
    ):
        report = run_preflight(["llama3:8b"], MODEL_LIST, tmp_path, fleet_mode=False)
    assert any("CVE-2026-7482" in w for w in report.security_warnings)
    assert any("CVE-2026-5757" in w for w in report.security_warnings)
