"""Tests for hermia.submit — install_id, host_class, anonymization, payload, CLI."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from hermia.submit import (
    _redact_string,
    anonymize_for_submit,
    build_payload,
    compute_host_class,
    compute_unified_memory_gb,
    load_or_create_install_id,
    submit_command,
)

# ---------------------------------------------------------------------------
# install_id management
# ---------------------------------------------------------------------------


def test_load_or_create_install_id_creates_new_config(tmp_path: Path) -> None:
    """When config_path does not exist, creates the file and returns a UUID string."""
    config_path = tmp_path / "config.toml"
    install_id = load_or_create_install_id(config_path)
    assert isinstance(install_id, str)
    assert len(install_id) == 36  # UUID4 string length
    assert config_path.exists()
    content = config_path.read_text()
    assert f'install_id = "{install_id}"' in content


def test_load_or_create_install_id_reuses_existing(tmp_path: Path) -> None:
    """Calling twice returns the same install_id without rewriting."""
    config_path = tmp_path / "config.toml"
    first = load_or_create_install_id(config_path)
    second = load_or_create_install_id(config_path)
    assert first == second


def test_load_or_create_install_id_stable(tmp_path: Path) -> None:
    """install_id is idempotent across repeated calls."""
    config_path = tmp_path / "config.toml"
    ids = [load_or_create_install_id(config_path) for _ in range(3)]
    assert len(set(ids)) == 1


def test_load_or_create_install_id_parses_handedited_toml(tmp_path: Path) -> None:
    """tomllib reads a hand-edited config with comments and extra keys."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '# hermia config\n[hermia]\nother = 1\ninstall_id = "abc-123"\n',
        encoding="utf-8",
    )
    assert load_or_create_install_id(config_path) == "abc-123"


def test_load_or_create_install_id_regenerates_on_malformed(tmp_path: Path) -> None:
    """A malformed config is treated as absent and regenerated (not crashed on)."""
    config_path = tmp_path / "config.toml"
    config_path.write_text("this is not valid toml ===", encoding="utf-8")
    install_id = load_or_create_install_id(config_path)
    assert install_id
    # The regenerated file is now valid TOML and reads back stably.
    assert load_or_create_install_id(config_path) == install_id


def test_load_or_create_install_id_creates_parent_dir(tmp_path: Path) -> None:
    """Parent directory is created if it does not exist."""
    config_path = tmp_path / "subdir" / "config.toml"
    assert not (tmp_path / "subdir").exists()
    install_id = load_or_create_install_id(config_path)
    assert isinstance(install_id, str)
    assert config_path.exists()


# ---------------------------------------------------------------------------
# host_class mapping
# ---------------------------------------------------------------------------


def test_compute_host_class_nvidia_rtx5090() -> None:
    gpu = {"vendor": "nvidia", "card": "NVIDIA GeForce RTX 5090"}
    assert compute_host_class(gpu) == "local:cuda/rtx-5090"


def test_compute_host_class_nvidia_rtx4090() -> None:
    gpu = {"vendor": "nvidia", "card": "NVIDIA GeForce RTX 4090"}
    assert compute_host_class(gpu) == "local:cuda/rtx-4090"


def test_compute_host_class_nvidia_rtx3090() -> None:
    gpu = {"vendor": "nvidia", "card": "NVIDIA GeForce RTX 3090"}
    assert compute_host_class(gpu) == "local:cuda/rtx-3090"


def test_compute_host_class_nvidia_rtx30xx() -> None:
    # 3050/3060/3070/3080 and Ti variants all map to rtx-30xx (3090 is separate).
    for card in (
        "NVIDIA GeForce RTX 3050",
        "NVIDIA GeForce RTX 3060 Ti",
        "NVIDIA GeForce RTX 3070",
        "NVIDIA GeForce RTX 3080 Ti",
    ):
        gpu = {"vendor": "nvidia", "card": card}
        assert compute_host_class(gpu) == "local:cuda/rtx-30xx", card


def test_compute_host_class_nvidia_rtx3090_is_distinct() -> None:
    gpu = {"vendor": "nvidia", "card": "NVIDIA GeForce RTX 3090"}
    assert compute_host_class(gpu) == "local:cuda/rtx-3090"


def test_compute_host_class_nvidia_rtx_a_series() -> None:
    gpu = {"vendor": "nvidia", "card": "NVIDIA RTX A4000"}
    assert compute_host_class(gpu) == "local:cuda/rtx-a-series"


def test_compute_host_class_nvidia_gtx_legacy() -> None:
    gpu = {"vendor": "nvidia", "card": "NVIDIA GeForce GTX 1080"}
    assert compute_host_class(gpu) == "local:cuda/gtx-legacy"


def test_compute_host_class_nvidia_unrecognized_falls_back() -> None:
    gpu = {"vendor": "nvidia", "card": "NVIDIA Quadro T1000"}
    assert compute_host_class(gpu) == "local:other"


def test_compute_host_class_apple_m1() -> None:
    gpu = {"vendor": "apple", "card": "Apple M1 Pro"}
    assert compute_host_class(gpu) == "local:metal/m1"


def test_compute_host_class_apple_m2() -> None:
    gpu = {"vendor": "apple", "card": "Apple M2 Max"}
    assert compute_host_class(gpu) == "local:metal/m2"


def test_compute_host_class_apple_m3() -> None:
    gpu = {"vendor": "apple", "card": "Apple M3"}
    assert compute_host_class(gpu) == "local:metal/m3"


def test_compute_host_class_apple_m4() -> None:
    gpu = {"vendor": "apple", "card": "Apple M4 Pro"}
    assert compute_host_class(gpu) == "local:metal/m4"


def test_compute_host_class_amd_rdna3() -> None:
    gpu = {"vendor": "amd", "card": "AMD Radeon RX 7800 XT"}
    assert compute_host_class(gpu) == "local:rocm/rdna3"


def test_compute_host_class_amd_rdna2() -> None:
    gpu = {"vendor": "amd", "card": "AMD Radeon RX 6800 XT"}
    assert compute_host_class(gpu) == "local:rocm/rdna2"


def test_compute_host_class_amd_mi_instinct() -> None:
    gpu = {"vendor": "amd", "card": "MI250X"}
    assert compute_host_class(gpu) == "local:rocm/instinct"


def test_compute_host_class_amd_vulkan() -> None:
    # RX 5700 doesn't match any RDNA2/RDNA3 or MI pattern — falls back to vulkan
    gpu = {"vendor": "amd", "card": "AMD Radeon RX 5700"}
    assert compute_host_class(gpu) == "local:vulkan/amd"


def test_compute_host_class_intel_igpu() -> None:
    gpu = {"vendor": "intel", "card": "Intel UHD Graphics 630"}
    assert compute_host_class(gpu) == "local:vulkan/intel-igpu"


def test_compute_host_class_cpu_only() -> None:
    gpu = {"vendor": "none", "card": ""}
    assert compute_host_class(gpu) == "local:cpu"


def test_compute_host_class_unknown_vendor_falls_back() -> None:
    gpu = {"vendor": "unknown", "card": "Exotic GPU"}
    assert compute_host_class(gpu) == "local:other"


# ---------------------------------------------------------------------------
# compute_unified_memory_gb
# ---------------------------------------------------------------------------


def test_compute_unified_memory_gb_nvidia() -> None:
    gpu = {"vendor": "nvidia", "card": "RTX 3090", "vram_total_gb": 24.0}
    result = compute_unified_memory_gb(gpu)
    assert result == pytest.approx(24.0)


def test_compute_unified_memory_gb_apple() -> None:
    gpu = {"vendor": "apple", "card": "M3 Pro", "vram_total_gb": 36.0}
    result = compute_unified_memory_gb(gpu)
    assert result == pytest.approx(36.0)


def test_compute_unified_memory_gb_discrete_zero_vram_returns_none() -> None:
    # Discrete GPUs don't share system RAM — vram=0 must yield None, not a
    # misleading system-RAM figure. (No psutil patch: psutil must NOT be called.)
    for vendor in ("nvidia", "amd"):
        gpu = {"vendor": vendor, "card": "RTX 3090", "vram_total_gb": 0.0}
        assert compute_unified_memory_gb(gpu) is None, vendor


def test_compute_unified_memory_gb_apple_zero_vram_uses_psutil() -> None:
    # Apple Silicon unified memory == system RAM, so a 0.0 vram reading still
    # falls back to total RAM.
    gpu = {"vendor": "apple", "card": "M3", "vram_total_gb": 0.0}
    with patch("hermia.submit.psutil") as mock_psutil:
        mock_vm = MagicMock()
        mock_vm.total = 32 * (1024 ** 3)  # 32 GiB
        mock_psutil.virtual_memory.return_value = mock_vm
        result = compute_unified_memory_gb(gpu)
    assert result == pytest.approx(32.0)


def test_compute_unified_memory_gb_cpu_uses_psutil() -> None:
    gpu = {"vendor": "none", "card": "", "vram_total_gb": 0.0}
    with patch("hermia.submit.psutil") as mock_psutil:
        mock_vm = MagicMock()
        mock_vm.total = 16 * (1024 ** 3)
        mock_psutil.virtual_memory.return_value = mock_vm
        result = compute_unified_memory_gb(gpu)
    assert result == pytest.approx(16.0)


# ---------------------------------------------------------------------------
# _redact_string — value-level anonymization
# ---------------------------------------------------------------------------


def test_redact_string_url_replaced() -> None:
    result = _redact_string("connect to https://server.example/api")
    assert "https://" not in result
    assert "[REDACTED]" in result


def test_redact_string_file_path_users() -> None:
    result = _redact_string("path is /Users/scott/data")
    assert "/Users/" not in result
    assert "[REDACTED]" in result
    # The username segment must also be redacted, not just the prefix (privacy leak).
    assert "scott" not in result


def test_redact_string_redacts_username_across_platforms() -> None:
    """Username in the home-dir segment must be redacted on macOS, Linux, and
    Windows — redacting only the prefix would ship the username."""
    for path in ("/Users/scott/x", "/home/scott/x", "C:\\Users\\scott\\x"):
        result = _redact_string(path)
        assert "scott" not in result, path
        assert "[REDACTED]" in result


def test_redact_string_non_user_windows_path_still_redacted() -> None:
    """A non-user C:\\ path keeps its prefix redacted (no regression)."""
    result = _redact_string("C:\\Windows\\System32")
    assert result.startswith("[REDACTED]")


def test_redact_string_file_path_home() -> None:
    result = _redact_string("path is /home/scott/data")
    assert "/home/" not in result
    assert "[REDACTED]" in result


def test_redact_string_hostname_local() -> None:
    result = _redact_string("host is server.local")
    assert "server.local" not in result
    assert "[REDACTED]" in result


def test_redact_string_attribution_url_exempt() -> None:
    """attribution.url field is exempt from URL redaction."""
    value = "https://example.com/profile"
    result = _redact_string(value, "attribution.url")
    assert result == value


def test_redact_string_extras_json_fully_exempt() -> None:
    """extras_json is fully exempt from all redaction."""
    value = "https://secret.internal/path /Users/data server.local"
    result = _redact_string(value, "extras_json")
    assert result == value


def test_redact_string_normal_text_unchanged() -> None:
    result = _redact_string("hello world, model passed")
    assert result == "hello world, model passed"


# ---------------------------------------------------------------------------
# anonymize_for_submit — integration of whitelist + redaction
# ---------------------------------------------------------------------------


def test_anonymize_strips_forbidden_keys() -> None:
    rows: list[dict[str, object]] = [
        {
            "host": "http://localhost:11434",
            "fleet_host_name": "gateway",
            "output_preview": "some output",
            "raw_response": "raw text",
            "model": "qwen2.5:32b",
            "test_id": "guards_001",
            "score": 1.0,
        }
    ]
    result = anonymize_for_submit(rows)
    row = result[0]
    assert "host" not in row
    assert "fleet_host_name" not in row
    assert "output_preview" not in row
    assert "raw_response" not in row
    assert row["model"] == "qwen2.5:32b"
    assert row["test_id"] == "guards_001"


def test_anonymize_redacts_url_in_whitelisted_string_field() -> None:
    """A URL pattern in a string value gets redacted by _redact_string."""
    # hermia_version is stamped by anonymize_row — we test _redact_string directly
    # since whitelisted string fields like 'model' wouldn't normally contain URLs.
    result = _redact_string("check https://internal.server/api")
    assert "https://" not in result
    assert "[REDACTED]" in result


def test_anonymize_redacts_file_path_in_string() -> None:
    result = _redact_string("/Users/scott/data")
    assert "[REDACTED]" in result
    assert "/Users/" not in result


def test_anonymize_redacts_home_path_in_string() -> None:
    result = _redact_string("/home/scott/data")
    assert "[REDACTED]" in result
    assert "/home/" not in result


def test_anonymize_redacts_hostname_in_string() -> None:
    result = _redact_string("connection to server.local failed")
    assert "server.local" not in result
    assert "[REDACTED]" in result


def test_anonymize_for_submit_produces_list() -> None:
    rows: list[dict[str, object]] = [{"model": "m", "test_id": "t", "score": 0.0}]
    result = anonymize_for_submit(rows)
    assert isinstance(result, list)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# build_payload — envelope structure
# ---------------------------------------------------------------------------


def test_build_payload_structure() -> None:
    rows: list[dict[str, object]] = [{"model": "test"}]
    payload = build_payload("uuid-1234", "local:cuda/rtx-4090", 24.0, rows)
    assert payload["install_id"] == "uuid-1234"
    assert payload["host_class"] == "local:cuda/rtx-4090"
    assert payload["unified_memory_gb"] == 24.0
    assert payload["corpus_version"] == "v0.2"
    assert payload["attribution"] is None
    assert payload["extras_json"] is None
    assert payload["rows"] == rows


def test_build_payload_hermia_version_present() -> None:
    payload = build_payload("uuid-1234", "local:cpu", None, [])
    assert isinstance(payload["hermia_version"], str)
    assert len(payload["hermia_version"]) > 0


def test_build_payload_none_unified_memory_allowed() -> None:
    payload = build_payload("uuid-1234", "local:other", None, [])
    assert payload["unified_memory_gb"] is None


# ---------------------------------------------------------------------------
# Helpers for submit_command tests
# ---------------------------------------------------------------------------


def _make_jsonl(tmp_path: Path, rows: list[dict[str, object]] | None = None) -> Path:
    if rows is None:
        rows = [{"model": "test-model", "test_id": "guards_001", "score": 1.0}]
    p = tmp_path / "eval_test.jsonl"
    with p.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return p


_GPU_INFO = {"vendor": "nvidia", "card": "NVIDIA GeForce RTX 4090", "vram_total_gb": 24.0}


# ---------------------------------------------------------------------------
# --dry-run behaviour
# ---------------------------------------------------------------------------


def test_submit_command_dry_run_prints_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """dry_run=True prints the JSON payload to stdout."""
    jf = _make_jsonl(tmp_path)
    with (
        patch("hermia.submit.detect_gpu", return_value=_GPU_INFO),
        patch("hermia.submit.load_or_create_install_id", return_value="test-uuid-dry"),
        patch("requests.post") as mock_post,
    ):
        submit_command(results_path=jf, dry_run=True, yes=True)

    captured = capsys.readouterr()
    assert "install_id" in captured.out
    assert "test-uuid-dry" in captured.out
    mock_post.assert_not_called()


def test_submit_command_dry_run_no_network(tmp_path: Path) -> None:
    """dry_run=True must never call requests.post."""
    jf = _make_jsonl(tmp_path)
    with (
        patch("hermia.submit.detect_gpu", return_value=_GPU_INFO),
        patch("hermia.submit.load_or_create_install_id", return_value="uuid-dry"),
        patch("requests.post") as mock_post,
    ):
        submit_command(results_path=jf, dry_run=True, yes=True)
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# HTTP response handling
# ---------------------------------------------------------------------------


def test_submit_command_success_201(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    jf = _make_jsonl(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "submission_id": "sub-xyz",
        "public_url": "https://hermia.scottbly.com/v1/r/v0.2/sub-xyz",
    }
    with (
        patch("hermia.submit.detect_gpu", return_value=_GPU_INFO),
        patch("hermia.submit.load_or_create_install_id", return_value="uuid-ok"),
        patch("requests.post", return_value=mock_resp),
    ):
        submit_command(results_path=jf, dry_run=False, yes=True)

    captured = capsys.readouterr()
    assert "Submitted. Public URL:" in captured.out
    assert "hermia.scottbly.com" in captured.out


def test_submit_command_503_exits_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    jf = _make_jsonl(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with (
        patch("hermia.submit.detect_gpu", return_value=_GPU_INFO),
        patch("hermia.submit.load_or_create_install_id", return_value="uuid-503"),
        patch("requests.post", return_value=mock_resp),
        pytest.raises(SystemExit) as exc,
    ):
        submit_command(results_path=jf, dry_run=False, yes=True)

    assert exc.value.code == 1
    assert "temporarily disabled" in capsys.readouterr().err


def test_submit_command_429_exits_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    jf = _make_jsonl(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    with (
        patch("hermia.submit.detect_gpu", return_value=_GPU_INFO),
        patch("hermia.submit.load_or_create_install_id", return_value="uuid-429"),
        patch("requests.post", return_value=mock_resp),
        pytest.raises(SystemExit) as exc,
    ):
        submit_command(results_path=jf, dry_run=False, yes=True)

    assert exc.value.code == 1
    assert "rate limited" in capsys.readouterr().err


def test_submit_command_400_exits_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    jf = _make_jsonl(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "bad field: install_id"
    with (
        patch("hermia.submit.detect_gpu", return_value=_GPU_INFO),
        patch("hermia.submit.load_or_create_install_id", return_value="uuid-400"),
        patch("requests.post", return_value=mock_resp),
        pytest.raises(SystemExit) as exc,
    ):
        submit_command(results_path=jf, dry_run=False, yes=True)

    assert exc.value.code == 1
    assert "server rejected submission" in capsys.readouterr().err


def test_submit_command_network_error_exits_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    jf = _make_jsonl(tmp_path)
    with (
        patch("hermia.submit.detect_gpu", return_value=_GPU_INFO),
        patch("hermia.submit.load_or_create_install_id", return_value="uuid-net"),
        patch(
            "requests.post",
            side_effect=requests.exceptions.ConnectionError("refused"),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        submit_command(results_path=jf, dry_run=False, yes=True)

    assert exc.value.code == 1
    assert "network error" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Confirmation prompt
# ---------------------------------------------------------------------------


def test_submit_command_yes_flag_skips_prompt(tmp_path: Path) -> None:
    """yes=True must call requests.post without calling input()."""
    jf = _make_jsonl(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"submission_id": "x", "public_url": "https://example.com"}
    with (
        patch("hermia.submit.detect_gpu", return_value=_GPU_INFO),
        patch("hermia.submit.load_or_create_install_id", return_value="uuid-yes"),
        patch("requests.post", return_value=mock_resp) as mock_post,
        patch("builtins.input") as mock_input,
    ):
        submit_command(results_path=jf, dry_run=False, yes=True)

    mock_post.assert_called_once()
    mock_input.assert_not_called()


def test_submit_command_abort_on_non_y(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Entering 'n' at the confirmation prompt must abort without POSTing."""
    jf = _make_jsonl(tmp_path)
    with (
        patch("hermia.submit.detect_gpu", return_value=_GPU_INFO),
        patch("hermia.submit.load_or_create_install_id", return_value="uuid-abort"),
        patch("requests.post") as mock_post,
        patch("builtins.input", return_value="n"),
        pytest.raises(SystemExit) as exc,
    ):
        submit_command(results_path=jf, dry_run=False, yes=False)

    assert exc.value.code == 0
    mock_post.assert_not_called()
    assert "Aborted" in capsys.readouterr().out


def test_submit_command_no_results_file_exits_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When results/ has no JSONL files and no --results given, exit(1)."""
    # Redirect RESULTS_DIR to an empty tmp_path
    monkeypatch.setattr("hermia.submit.RESULTS_DIR", tmp_path)
    with pytest.raises(SystemExit) as exc:
        submit_command(results_path=None, dry_run=False, yes=True)
    assert exc.value.code == 1
