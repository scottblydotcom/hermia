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
        "  - name: node3\n"
        "    host: http://host1:11434\n"
        "  - name: eric-5090\n"
        "    host: https://host2:4000\n"
    )
    entries = load_fleet_config(cfg)
    assert len(entries) == 2
    assert entries[0]["name"] == "node3"
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
    cfg.write_text("fleet:\n  - name: node3\n")
    with pytest.raises(ValueError, match="missing or invalid 'host'"):
        load_fleet_config(cfg)


def test_load_fleet_config_empty_fleet(tmp_path: Path) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text("fleet: []\n")
    with pytest.raises(ValueError, match="at least one entry"):
        load_fleet_config(cfg)


def test_load_fleet_config_models_list(tmp_path: Path) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: gateway\n"
        "    host: http://host1:11434\n"
        "    models:\n"
        "      - qwen2.5:3b\n"
        "      - phi3:3.8b\n"
    )
    entries = load_fleet_config(cfg)
    assert entries[0]["models"] == ["qwen2.5:3b", "phi3:3.8b"]


def test_load_fleet_config_models_invalid_type(tmp_path: Path) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: gateway\n"
        "    host: http://host1:11434\n"
        "    models: not-a-list\n"
    )
    with pytest.raises(ValueError, match="list of strings"):
        load_fleet_config(cfg)


# ---------------------------------------------------------------------------
# _build_auth_headers
# ---------------------------------------------------------------------------


def test_build_auth_headers_no_auth() -> None:
    entry: dict = {"name": "node3", "host": "http://host1:11434"}
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


def test_run_host_eval_writes_expected_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hermia.fleet as fleet
    from hermia.results import load_jsonl, open_run

    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None):  # type: ignore[no-untyped-def]
        return {"model": model, "test_id": test["id"], "failure_reason": "",
                "elapsed_sec": 0.1, "tokens_per_sec": 1.0}
    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)

    jsonl, csv = open_run(tmp_path)
    entry = {"name": "node1", "host": "http://h1:11434"}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )
    rows = load_jsonl(jsonl)
    assert [r["model"] for r in rows] == ["m1"]
    assert [r["test_id"] for r in rows] == ["t1"]


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


# hermia-qc: fleet_host_name and fleet_host_start in result rows
# ---------------------------------------------------------------------------


def _make_run_test_result(model: str = "qwen2.5:7b", test_id: str = "tool-calling-basic") -> dict:
    return {
        "model": model,
        "test_id": test_id,
        "dimension": "tool-use",
        "frameworks": {},
        "failure_reason": "",
        "had_markdown_fence": False,
        "json_valid": True,
        "schema_compliant": True,
        "tokens": 10,
        "elapsed_sec": 1.0,
        "tokens_per_sec": 10.0,
        "output_preview": "...",
        "raw_system": "sys",
        "raw_prompt": "prompt",
        "raw_response": "{}",
        "peak_cpu_pct": None,
        "peak_ram_used_gb": None,
        "peak_gpu_pct": None,
        "peak_vram_used_gb": None,
        "mode": "fleet",
        "host": "http://192.168.25.100:11434",
        "vram_server_gb": None,
    }


def test_run_fleet_result_has_fleet_host_name(tmp_path: Path) -> None:
    from hermia.fleet import run_fleet
    entries = [{"name": "node2", "host": "http://192.168.25.100:11434"}]
    fake_result = _make_run_test_result()

    # run_fleet uses lazy imports inside the function body, so patch source modules
    with (
        patch("hermia.runner.get_available_models", return_value=[{"name": "qwen2.5:7b"}]),
        patch("hermia.runner.load_tests_all", return_value=[{
            "id": "tool-calling-basic", "system": "sys", "prompt": "p", "dimension": "tool-use",
        }]),
        patch("hermia.runner.run_test", return_value=fake_result),
        patch("hermia.results.append_result"),
        patch(
            "hermia.results.open_run",
            return_value=(tmp_path / "eval.jsonl", tmp_path / "eval.csv"),
        ),
        patch("hermia.metrics.MetricsSampler"),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path)

    # Verify fleet_host_name was injected (run_test result is mutated in-place)
    assert fake_result["fleet_host_name"] == "node2"


def test_run_fleet_model_filter_applied(tmp_path: Path) -> None:
    """Models listed in fleet YAML are the only ones evaluated; others are skipped."""
    from hermia.fleet import run_fleet

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _all_models = [{"name": "qwen2.5:3b"}, {"name": "phi3:3.8b"}, {"name": "llama3.2:latest"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")

    entries = [{"name": "gateway", "host": "http://host1:11434", "models": ["qwen2.5:3b"]}]

    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.get_available_models", return_value=_all_models),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path)

    called_models = {call.args[0] for call in mock_run.call_args_list}
    assert called_models == {"qwen2.5:3b"}


def test_run_fleet_no_model_filter_runs_all(tmp_path: Path) -> None:
    """Omitting models in fleet YAML runs all models on the endpoint."""
    from hermia.fleet import run_fleet

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _all_models = [{"name": "qwen2.5:3b"}, {"name": "phi3:3.8b"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")

    entries = [{"name": "gateway", "host": "http://host1:11434"}]

    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.get_available_models", return_value=_all_models),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path)

    called_models = {call.args[0] for call in mock_run.call_args_list}
    assert called_models == {"qwen2.5:3b", "phi3:3.8b"}


# ---------------------------------------------------------------------------
# models: auto — openai-compat model auto-discovery
# ---------------------------------------------------------------------------


def test_load_fleet_config_models_auto_openai_compat(tmp_path: Path) -> None:
    """models: auto is accepted for openai-compat transport."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: kwaainet\n"
        "    host: http://localhost:11435\n"
        "    transport: openai-compat\n"
        "    models: auto\n"
    )
    entries = load_fleet_config(cfg)
    assert entries[0]["models"] == "auto"


def test_load_fleet_config_models_auto_rejected_for_ollama(tmp_path: Path) -> None:
    """models: auto on an ollama host raises (ollama auto-discovers via omission)."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: local\n"
        "    host: http://localhost:11434\n"
        "    models: auto\n"
    )
    with pytest.raises(ValueError, match="auto"):
        load_fleet_config(cfg)


def test_run_fleet_models_auto_discovers(tmp_path: Path) -> None:
    """models: auto discovers ids via the transport and evaluates each."""
    from hermia.fleet import run_fleet

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")

    entries = [{
        "name": "kwaainet",
        "host": "http://localhost:11435",
        "transport": "openai-compat",
        "models": "auto",
    }]

    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch(
            "hermia.transport.openai_compat.OpenAICompatTransport.list_models",
            return_value=["disc-a", "disc-b"],
        ),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path)

    called_models = {call.args[0] for call in mock_run.call_args_list}
    assert called_models == {"disc-a", "disc-b"}


def test_run_fleet_models_auto_discovery_failure_skips_host(tmp_path: Path) -> None:
    """If discovery fails, the host is skipped (no eval rows) with a warning."""
    from hermia.fleet import run_fleet
    from hermia.transport.base import TransportError

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
    errors: list[str] = []

    entries = [{
        "name": "kwaainet",
        "host": "http://localhost:11435",
        "transport": "openai-compat",
        "models": "auto",
    }]

    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch(
            "hermia.transport.openai_compat.OpenAICompatTransport.list_models",
            side_effect=TransportError("boom", kind="openai-compat"),
        ),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path, stderr_fn=errors.append)

    assert mock_run.call_args_list == []
    assert any("kwaainet" in line for line in errors)


# ---------------------------------------------------------------------------
# transport: field in load_fleet_config
# ---------------------------------------------------------------------------


def test_load_fleet_config_transport_default(tmp_path: Path) -> None:
    """No transport field → loads without error; default resolves to 'ollama'."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text("fleet:\n  - name: node3\n    host: http://host1:11434\n")
    entries = load_fleet_config(cfg)
    assert len(entries) == 1
    assert entries[0].get("transport", "ollama") == "ollama"


def test_load_fleet_config_transport_openai_compat(tmp_path: Path) -> None:
    """transport: openai-compat is accepted and stored on the entry."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: litellm-gateway\n"
        "    host: https://scottai.tailc7d860.ts.net:4000\n"
        "    transport: openai-compat\n"
    )
    entries = load_fleet_config(cfg)
    assert entries[0]["transport"] == "openai-compat"


def test_load_fleet_config_invalid_transport(tmp_path: Path) -> None:
    """transport: grpc (unknown value) raises ValueError mentioning 'transport'."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: node3\n"
        "    host: http://host1:11434\n"
        "    transport: grpc\n"
    )
    with pytest.raises(ValueError, match="transport"):
        load_fleet_config(cfg)


def test_run_fleet_result_has_fleet_host_start(tmp_path: Path) -> None:
    from hermia.fleet import run_fleet
    entries = [{"name": "node2", "host": "http://192.168.25.100:11434"}]
    fake_result = _make_run_test_result()

    # run_fleet uses lazy imports inside the function body, so patch source modules
    with (
        patch("hermia.runner.get_available_models", return_value=[{"name": "qwen2.5:7b"}]),
        patch("hermia.runner.load_tests_all", return_value=[{
            "id": "tool-calling-basic", "system": "sys", "prompt": "p", "dimension": "tool-use",
        }]),
        patch("hermia.runner.run_test", return_value=fake_result),
        patch("hermia.results.append_result"),
        patch(
            "hermia.results.open_run",
            return_value=(tmp_path / "eval.jsonl", tmp_path / "eval.csv"),
        ),
        patch("hermia.metrics.MetricsSampler"),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path)

    assert "fleet_host_start" in fake_result
    # Should be a valid ISO timestamp string
    from datetime import datetime
    dt = datetime.fromisoformat(fake_result["fleet_host_start"])
    assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# verbosity levels
# ---------------------------------------------------------------------------


def _run_fleet_capture(tmp_path: Path, verbosity: int) -> list[str]:
    """Run run_fleet with given verbosity and return captured print_fn lines."""
    from hermia.fleet import run_fleet

    lines: list[str] = []
    entries = [{"name": "n1", "host": "http://host1:11434"}]
    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")

    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.get_available_models", return_value=[{"name": "m1"}]),
        patch("hermia.runner.run_test", side_effect=lambda *a, **kw: dict(_MINIMAL_RESULT)),
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path,
                  print_fn=lines.append, verbosity=verbosity)
    return lines


def test_run_fleet_normal_prints_host_header(tmp_path: Path) -> None:
    lines = _run_fleet_capture(tmp_path, verbosity=0)
    assert any("n1" in ln and "host1" in ln for ln in lines)


def test_run_fleet_normal_prints_per_test_line(tmp_path: Path) -> None:
    lines = _run_fleet_capture(tmp_path, verbosity=0)
    assert any("m1:t1" in ln for ln in lines)


def test_run_fleet_normal_always_prints_saved_path(tmp_path: Path) -> None:
    lines = _run_fleet_capture(tmp_path, verbosity=0)
    assert any("Saved:" in ln for ln in lines)


def test_run_fleet_quiet_suppresses_host_header(tmp_path: Path) -> None:
    lines = _run_fleet_capture(tmp_path, verbosity=-1)
    assert not any("n1" in ln and "host1" in ln for ln in lines)


def test_run_fleet_quiet_suppresses_per_test_line(tmp_path: Path) -> None:
    lines = _run_fleet_capture(tmp_path, verbosity=-1)
    assert not any("m1:t1" in ln for ln in lines)


def test_run_fleet_quiet_still_prints_saved_path(tmp_path: Path) -> None:
    lines = _run_fleet_capture(tmp_path, verbosity=-1)
    assert any("Saved:" in ln for ln in lines)


def test_run_fleet_verbose_includes_tps(tmp_path: Path) -> None:
    lines = _run_fleet_capture(tmp_path, verbosity=1)
    test_lines = [ln for ln in lines if "m1:t1" in ln]
    assert test_lines, "expected at least one per-test line"
    assert any("t/s" in ln for ln in test_lines)


def test_run_fleet_verbose_includes_failure_reason_when_present(tmp_path: Path) -> None:
    from hermia.fleet import run_fleet

    lines: list[str] = []
    failing_result = {**_MINIMAL_RESULT, "failure_reason": "TIMEOUT: 90s", "tokens_per_sec": 0.0}
    entries = [{"name": "n1", "host": "http://host1:11434"}]
    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")

    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.get_available_models", return_value=[{"name": "m1"}]),
        patch("hermia.runner.run_test", side_effect=lambda *a, **kw: dict(failing_result)),
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path,
                  print_fn=lines.append, verbosity=1)

    test_lines = [ln for ln in lines if "m1:t1" in ln]
    assert any("TIMEOUT" in ln for ln in test_lines)


def test_run_fleet_verbose_omits_failure_reason_on_pass(tmp_path: Path) -> None:
    lines = _run_fleet_capture(tmp_path, verbosity=1)
    test_lines = [ln for ln in lines if "m1:t1" in ln]
    # _MINIMAL_RESULT has failure_reason="" so no bracket annotation expected
    assert not any("[" in ln for ln in test_lines)


def test_run_fleet_verbose_still_prints_saved_path(tmp_path: Path) -> None:
    lines = _run_fleet_capture(tmp_path, verbosity=1)
    assert any("Saved:" in ln for ln in lines)


# ---------------------------------------------------------------------------
# stack: block in fleet YAML
# ---------------------------------------------------------------------------


def test_load_fleet_config_with_stack(tmp_path: Path) -> None:
    """Valid stack block is accepted and preserved on the entry."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: gpu-box\n"
        "    host: http://host1:11434\n"
        "    stack:\n"
        "      gpu_arch: sm_89\n"
        "      runtime_version: CUDA 12.8\n"
    )
    entries = load_fleet_config(cfg)
    assert entries[0]["stack"]["gpu_arch"] == "sm_89"
    assert entries[0]["stack"]["runtime_version"] == "CUDA 12.8"


def test_load_fleet_config_invalid_stack_type(tmp_path: Path) -> None:
    """stack: 'not a dict' must raise ValueError."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: gpu-box\n"
        "    host: http://host1:11434\n"
        "    stack: not-a-dict\n"
    )
    with pytest.raises(ValueError, match="stack"):
        load_fleet_config(cfg)


def test_load_fleet_config_stack_optional(tmp_path: Path) -> None:
    """Missing stack block must not cause an error."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: node3\n"
        "    host: http://host1:11434\n"
    )
    entries = load_fleet_config(cfg)
    assert "stack" not in entries[0]


def test_group_entries_by_host_serializes_same_host() -> None:
    from hermia.fleet import _group_entries_by_host
    entries = [
        {"name": "a", "host": "http://h1:11434"},
        {"name": "b", "host": "http://h2:11434"},
        {"name": "c", "host": "http://h1:11434/"},  # same as a after normalize
    ]
    groups = _group_entries_by_host(entries)
    # two groups (h1, h2); h1 group holds a and c in order
    assert len(groups) == 2
    h1 = [g for g in groups if len(g) == 2][0]
    assert [e["name"] for e in h1] == ["a", "c"]
