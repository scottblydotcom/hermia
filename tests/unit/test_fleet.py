"""Tests for hermia.fleet — fleet config loading and headless eval runner."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hermia.fleet import _build_auth_headers, load_fleet_config

# ---------------------------------------------------------------------------
# load_fleet_config
# ---------------------------------------------------------------------------


def test_load_fleet_config_valid(tmp_path: Path) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: openclaw\n"
        "    host: http://host1:11434\n"
        "  - name: eric-5090\n"
        "    host: https://host2:4000\n"
    )
    entries = load_fleet_config(cfg)
    assert len(entries) == 2
    assert entries[0]["name"] == "openclaw"
    assert entries[0]["host"] == "http://host1:11434"
    assert entries[1]["name"] == "eric-5090"
    assert entries[1]["host"] == "https://host2:4000"


def test_load_fleet_config_missing_name(tmp_path: Path) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text("fleet:\n  - host: http://host1:11434\n")
    with pytest.raises(ValueError, match="missing or invalid 'name'"):
        load_fleet_config(cfg)


def test_load_fleet_config_missing_host(tmp_path: Path) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text("fleet:\n  - name: openclaw\n")
    with pytest.raises(ValueError, match="missing or invalid 'host'"):
        load_fleet_config(cfg)


def test_load_fleet_config_empty_fleet(tmp_path: Path) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text("fleet: []\n")
    with pytest.raises(ValueError, match="at least one entry"):
        load_fleet_config(cfg)


# ---------------------------------------------------------------------------
# _build_auth_headers
# ---------------------------------------------------------------------------


def test_build_auth_headers_no_auth() -> None:
    entry: dict = {"name": "openclaw", "host": "http://host1:11434"}
    assert _build_auth_headers(entry) == {}


def test_build_auth_headers_bearer_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_API_KEY", "tok_secret")
    entry: dict = {
        "name": "eric-5090",
        "host": "https://host2:4000",
        "auth": {"bearer": {"key_env": "MY_API_KEY"}},
    }
    headers = _build_auth_headers(entry)
    assert headers == {"Authorization": "Bearer tok_secret"}


def test_build_auth_headers_bearer_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    entry: dict = {
        "name": "eric-5090",
        "host": "https://host2:4000",
        "auth": {"bearer": {"key_env": "MISSING_KEY"}},
    }
    with pytest.raises(RuntimeError, match="MISSING_KEY"):
        _build_auth_headers(entry)


# ---------------------------------------------------------------------------
# run_fleet
# ---------------------------------------------------------------------------

_MINIMAL_RESULT = {
    "model": "m1",
    "test_id": "t1",
    "dimension": "",
    "frameworks": {},
    "failure_reason": "",
    "json_valid": True,
    "schema_compliant": True,
    "tokens": 10,
    "elapsed_sec": 0.5,
    "tokens_per_sec": 20.0,
    "output_preview": "ok",
    "peak_cpu_pct": None,
    "peak_ram_used_gb": None,
    "peak_gpu_pct": None,
    "peak_vram_used_gb": None,
    "mode": "fleet",
    "host": "http://localhost:11434",
    "vram_server_gb": None,
}

_ENTRIES_TWO_HOSTS = [
    {"name": "h1", "host": "http://host1:11434"},
    {"name": "h2", "host": "http://host2:11434"},
]


def _make_run_fleet_mocks(tmp_path: Path):
    """Return a context manager stack of patches for run_fleet tests.

    Local imports inside run_fleet() must be patched at the source module.
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
        _models = [{"name": "m1"}]
        _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
        with (
            patch("hermia.runner.load_tests_all", return_value=_tests),
            patch("hermia.runner.get_available_models", return_value=_models),
            patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
            patch("hermia.results.open_run", return_value=_run_files),
            patch("hermia.results.append_result"),
            patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
            patch.dict(os.environ, {}, clear=False),
        ):
            yield mock_run

    return _ctx()


def test_run_fleet_iterates_all_hosts(tmp_path: Path) -> None:
    from hermia.fleet import run_fleet

    with _make_run_fleet_mocks(tmp_path) as mock_run:
        run_fleet(_ENTRIES_TWO_HOSTS, repeat=1, results_dir=tmp_path)

    # 2 hosts × 1 model × 1 test × repeat=1 → 2 calls
    assert mock_run.call_count == 2


def test_run_fleet_repeat(tmp_path: Path) -> None:
    from hermia.fleet import run_fleet

    with _make_run_fleet_mocks(tmp_path) as mock_run:
        run_fleet([_ENTRIES_TWO_HOSTS[0]], repeat=3, results_dir=tmp_path)

    # 1 host × 1 model × 1 test × repeat=3 → 3 calls
    assert mock_run.call_count == 3


def test_run_fleet_result_host_field(tmp_path: Path) -> None:
    from hermia.fleet import run_fleet

    captured: list[dict] = []

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.get_available_models", return_value=[{"name": "m1"}]),
        patch(
            "hermia.runner.run_test",
            side_effect=lambda *a, host=None, **kw: {**_MINIMAL_RESULT, "host": host},
        ),
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result", side_effect=lambda r, *_: captured.append(dict(r))),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
        patch.dict(os.environ, {}, clear=False),
    ):
        run_fleet(_ENTRIES_TWO_HOSTS, repeat=1, results_dir=tmp_path)

    assert len(captured) == 2
    hosts_seen = {r["host"] for r in captured}
    assert hosts_seen == {"http://host1:11434", "http://host2:11434"}


# ---------------------------------------------------------------------------
# --fleet flag in main() skips TUI
# ---------------------------------------------------------------------------


def test_fleet_flag_skips_tui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text("fleet:\n  - name: h1\n    host: http://host1:11434\n")

    import sys

    monkeypatch.setattr(sys, "argv", ["hermia", "--fleet", str(cfg)])

    mock_app = MagicMock()
    # lazy imports inside main() must be patched at the source module
    with (
        patch("hermia.app.EvalApp", return_value=mock_app) as mock_eval_app,
        patch("hermia.fleet.load_fleet_config", return_value=[{"name": "h1", "host": "http://host1:11434"}]),  # noqa: E501
        patch("hermia.fleet.run_fleet") as mock_run_fleet,
        patch("hermia.screens.RESULTS_DIR", tmp_path),
        pytest.raises(SystemExit) as exc_info,
    ):
        from hermia.app import main
        main()

    assert exc_info.value.code == 0
    mock_run_fleet.assert_called_once()
    mock_eval_app.assert_not_called()
