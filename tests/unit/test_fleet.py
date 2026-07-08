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

    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None, **kw):  # type: ignore[no-untyped-def]
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


def test_run_host_eval_emits_engine_security_warnings_via_stderr_fn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """hermia-3zp — CVE warning for a stale Ollama server must surface per-host on stderr."""
    import hermia.fleet as fleet
    from hermia.results import open_run

    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None, **kw):  # type: ignore[no-untyped-def]
        return {"model": model, "test_id": test["id"], "failure_reason": "",
                "elapsed_sec": 0.1, "tokens_per_sec": 1.0}
    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)

    # Force check_ollama_security to see a vulnerable version.
    def fake_check(host, engine, fleet_mode=False, headers=None):  # type: ignore[no-untyped-def]
        if engine == "ollama":
            return [f"SEC ⚠ CVE-2026-7482: Ollama 0.16.0 vulnerable (host={host})"]
        return []
    monkeypatch.setattr("hermia.preflight.check_engine_security", fake_check, raising=False)

    stderr_lines: list[str] = []
    jsonl, csv = open_run(tmp_path)
    entry = {"name": "node1", "host": "http://h1:11434"}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=stderr_lines.append, verbosity=-1,
    )
    assert any("CVE-2026-7482" in line for line in stderr_lines), stderr_lines
    assert any("node1:" in line for line in stderr_lines), stderr_lines


# ---------------------------------------------------------------------------
# --fleet flag in main() skips TUI
# ---------------------------------------------------------------------------


def test_fleet_flag_skips_tui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text("fleet:\n  - name: h1\n    host: http://host1:11434\n")

    import sys

    monkeypatch.setattr(sys, "argv", ["hermia", "--fleet", str(cfg)])

    with (
        patch("hermia.fleet.load_fleet_config", return_value=[{"name": "h1", "host": "http://host1:11434"}]),  # noqa: E501
        patch("hermia.fleet.run_fleet") as mock_run_fleet,
        patch("hermia.submit.RESULTS_DIR", tmp_path),
        pytest.raises(SystemExit) as exc_info,
    ):
        from hermia.app import main
        main()

    assert exc_info.value.code == 0
    mock_run_fleet.assert_called_once()


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


def test_run_fleet_openai_compat_explicit_list_still_runs(tmp_path: Path) -> None:
    """An explicit models list on an openai-compat host evaluates each id (no discovery)."""
    from hermia.fleet import run_fleet

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")

    entries = [{
        "name": "litellm",
        "host": "https://gateway:4000",
        "transport": "openai-compat",
        "models": ["coder-lane", "manager-lane"],
    }]

    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch(
            "hermia.transport.openai_compat.OpenAICompatTransport.list_models",
        ) as mock_list,
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path)

    # Explicit list must NOT trigger discovery.
    mock_list.assert_not_called()
    called_models = {call.args[0] for call in mock_run.call_args_list}
    assert called_models == {"coder-lane", "manager-lane"}


def test_run_fleet_openai_compat_omitted_models_warns_and_skips(tmp_path: Path) -> None:
    """Omitting models on an openai-compat host warns and skips (no eval rows)."""
    from hermia.fleet import run_fleet

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
    errors: list[str] = []

    entries = [{
        "name": "litellm",
        "host": "https://gateway:4000",
        "transport": "openai-compat",
    }]

    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path, stderr_fn=errors.append)

    assert mock_run.call_args_list == []
    assert any("litellm" in line and "models" in line for line in errors)


def test_run_fleet_openai_compat_empty_list_skips_with_clear_message(tmp_path: Path) -> None:
    """models: [] on openai-compat skips with the accurate 'no models' message, not the
    'requires an explicit list' one (the user did provide a list — it's just empty)."""
    from hermia.fleet import run_fleet

    entries = [{
        "name": "litellm",
        "host": "https://gateway:4000",
        "transport": "openai-compat",
        "models": [],
    }]

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
    errors: list[str] = []
    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path, stderr_fn=errors.append)

    assert mock_run.call_args_list == []
    assert any("no models to evaluate" in line for line in errors)


def test_run_fleet_auth_failure_skips_host_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing bearer-auth env var skips the host instead of crashing the whole run."""
    from hermia.fleet import run_fleet

    monkeypatch.delenv("HERMIA_MISSING_BEARER", raising=False)
    entries = [
        {
            "name": "secured",
            "host": "http://host1:11434",
            "auth": {"bearer": {"key_env": "HERMIA_MISSING_BEARER"}},
        }
    ]
    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
    errors: list[str] = []
    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.get_available_models", return_value=[{"name": "m1"}]),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path, stderr_fn=errors.append)
    assert not mock_run.called
    assert any("secured" in line for line in errors)


def test_run_fleet_prints_skipped_summary_when_host_skipped(tmp_path: Path) -> None:
    """A skipped host produces an 'Evaluated N, skipped M' summary line."""
    from hermia.fleet import run_fleet

    entries = [{
        "name": "kwaainet",
        "host": "http://localhost:11435",
        "transport": "openai-compat",
        "models": "auto",
    }]

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
    lines: list[str] = []
    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.transport.openai_compat.OpenAICompatTransport.list_models", return_value=[]),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)),
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(
            entries, repeat=1, results_dir=tmp_path,
            print_fn=lines.append, stderr_fn=lambda *_: None,
        )

    assert any("skipped 1" in line for line in lines)


def test_run_fleet_no_summary_when_nothing_skipped(tmp_path: Path) -> None:
    """A clean run (no skips) prints no skipped-summary line."""
    from hermia.fleet import run_fleet

    entries = [{"name": "gateway", "host": "http://host1:11434"}]

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
    lines: list[str] = []
    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.get_available_models", return_value=[{"name": "m1"}]),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)),
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(entries, repeat=1, results_dir=tmp_path, print_fn=lines.append)

    assert not any("skipped" in line for line in lines)


def test_run_fleet_quiet_mode_suppresses_skipped_summary(tmp_path: Path) -> None:
    """verbosity=-1 keeps stdout to just 'Saved:'; the skip still surfaces on stderr."""
    from hermia.fleet import run_fleet

    entries = [{
        "name": "kwaainet",
        "host": "http://localhost:11435",
        "transport": "openai-compat",
        "models": "auto",
    }]

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
    out: list[str] = []
    err: list[str] = []
    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.transport.openai_compat.OpenAICompatTransport.list_models", return_value=[]),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)),
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(
            entries, repeat=1, results_dir=tmp_path,
            print_fn=out.append, stderr_fn=err.append, verbosity=-1,
        )

    # stdout: only "Saved:", no aggregate summary
    assert not any("skipped" in line or "Evaluated" in line for line in out)
    assert any("Saved:" in line for line in out)
    # stderr: the per-host skip is still surfaced even in quiet mode
    assert any("skipping host" in line for line in err)


def test_run_fleet_zero_models_counts_as_skipped(tmp_path: Path) -> None:
    """A host that resolves zero models is counted skipped (not a silent empty pass)."""
    from hermia.fleet import run_fleet

    entries = [{"name": "gateway", "host": "http://host1:11434"}]

    _tests = [{"id": "t1", "system": "s", "prompt": "p"}]
    _run_files = (tmp_path / "out.jsonl", tmp_path / "out.csv")
    lines: list[str] = []
    with (
        patch("hermia.runner.load_tests_all", return_value=_tests),
        patch("hermia.runner.get_available_models", return_value=[]),
        patch("hermia.runner.run_test", return_value=dict(_MINIMAL_RESULT)) as mock_run,
        patch("hermia.results.open_run", return_value=_run_files),
        patch("hermia.results.append_result"),
        patch("hermia.metrics.MetricsSampler", return_value=MagicMock()),
    ):
        run_fleet(
            entries, repeat=1, results_dir=tmp_path,
            print_fn=lines.append, stderr_fn=lambda *_: None,
        )

    assert not mock_run.called
    assert any("skipped 1" in line for line in lines)


# ---------------------------------------------------------------------------
# transport: field in load_fleet_config
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# hermia-7ao: load_fleet_config must accept TUI-saved fleet YAML
# ---------------------------------------------------------------------------


def test_load_fleet_config_accepts_tui_format(tmp_path: Path) -> None:
    """load_fleet_config must accept TUI-saved YAML (hosts:/url:/engine: schema).

    TUI's save_fleet writes a different schema than the headless runner expects:
      - key 'hosts' (not 'fleet')
      - field 'url' (not 'host')
      - field 'engine' (not 'transport')
      - auth as flat 'auth_header_env' (not nested auth.bearer.key_env)

    Users who create fleets in the TUI and try to run them headless get:
      ValueError: Fleet config must contain at least one entry under 'fleet'
    """
    from hermia.tui.fleet_io import save_fleet
    from hermia.tui.state import FleetConfig, Host, ModelChoice

    config = FleetConfig(
        name="kwaainet-baseline",
        hosts=[
            Host(
                name="eric-5090",
                url="https://eric:11434",
                engine="ollama",
                models=[ModelChoice(name="qwen3:32b", selected=True)],
            )
        ],
        tests=["prompt-injection-1"],
        repeat=2,
    )
    yaml_path = save_fleet(config, root=tmp_path)

    entries = load_fleet_config(yaml_path)

    assert len(entries) == 1
    assert entries[0]["name"] == "eric-5090"
    assert entries[0]["host"] == "https://eric:11434"
    assert entries[0].get("transport", "ollama") == "ollama"


def test_load_fleet_config_tui_format_with_auth(tmp_path: Path) -> None:
    """TUI-saved auth_header_env maps to the headless auth.bearer.key_env structure."""
    from hermia.tui.fleet_io import save_fleet
    from hermia.tui.state import FleetConfig, Host

    config = FleetConfig(
        name="secured",
        hosts=[
            Host(
                name="gateway",
                url="https://gw:4000",
                engine="openai-compat",
                auth_header_env="LITELLM_KEY",
            )
        ],
    )
    yaml_path = save_fleet(config, root=tmp_path)

    entries = load_fleet_config(yaml_path)

    assert entries[0]["auth"]["bearer"]["key_env"] == "LITELLM_KEY"
    assert entries[0].get("transport", "ollama") == "openai-compat"


def test_load_fleet_config_tui_format_preserves_model_list(tmp_path: Path) -> None:
    """TUI-saved selected models are preserved as a list when loaded headless."""
    from hermia.tui.fleet_io import save_fleet
    from hermia.tui.state import FleetConfig, Host, ModelChoice

    config = FleetConfig(
        name="models-test",
        hosts=[
            Host(
                name="node",
                url="http://node:11434",
                engine="ollama",
                models=[
                    ModelChoice(name="qwen3:32b", selected=True),
                    ModelChoice(name="llama3:8b", selected=True),
                    ModelChoice(name="unused", selected=False),
                ],
            )
        ],
    )
    yaml_path = save_fleet(config, root=tmp_path)

    entries = load_fleet_config(yaml_path)

    assert entries[0]["models"] == ["qwen3:32b", "llama3:8b"]


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
        "    host: https://fleet.example:4000\n"
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


@pytest.mark.parametrize(
    "bad_key",
    ["engine", "url"],
    ids=["engine-tui-key", "url-typo-for-host"],
)
def test_load_fleet_config_rejects_unrecognized_key(tmp_path: Path, bad_key: str) -> None:
    """A fleet[] entry key outside the allowed set (e.g. 'engine' — a TUI hosts[]
    key — or a typo'd 'url' instead of 'host') must raise ValueError naming it,
    not silently drop it."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: node3\n"
        "    host: http://host1:11434\n"
        f"    {bad_key}: some-value\n"
    )
    with pytest.raises(ValueError, match=bad_key):
        load_fleet_config(cfg)


def test_load_fleet_config_unrelated_typo_omits_engine_hint(tmp_path: Path) -> None:
    """The 'engine is a TUI key' hint should only appear when 'engine' is the
    actual unrecognized key — not tacked onto every unrelated typo."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: node3\n"
        "    host: http://host1:11434\n"
        "    modles: llama3\n"
    )
    with pytest.raises(ValueError) as exc_info:
        load_fleet_config(cfg)
    assert "modles" in str(exc_info.value)
    assert "TUI hosts" not in str(exc_info.value)


def test_load_fleet_config_rejects_multiple_unrecognized_keys(tmp_path: Path) -> None:
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: node3\n"
        "    host: http://host1:11434\n"
        "    engine: openai-compat\n"
        "    port: 8080\n"
    )
    with pytest.raises(ValueError) as exc_info:
        load_fleet_config(cfg)
    assert "engine" in str(exc_info.value)
    assert "port" in str(exc_info.value)


def test_load_fleet_config_all_allowed_keys_no_raise(tmp_path: Path) -> None:
    """An entry using only the documented allowed keys must parse cleanly."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "fleet:\n"
        "  - name: node3\n"
        "    host: http://host1:11434\n"
        "    transport: openai-compat\n"
        "    auth:\n"
        "      bearer:\n"
        "        key_env: MY_KEY\n"
        "    models:\n"
        "      - llama3\n"
        "    stack:\n"
        "      gpu_arch: sm_89\n"
        "    test_timeout: 30\n"
    )
    entries = load_fleet_config(cfg)
    assert entries[0]["transport"] == "openai-compat"


def test_load_fleet_config_tui_hosts_schema_engine_key_unaffected(tmp_path: Path) -> None:
    """The TUI hosts[] schema's 'engine' key is a different, already-valid
    schema and must not be rejected by the fleet[] unrecognized-key check."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "hosts:\n"
        "  - name: node3\n"
        "    url: http://host1:11434\n"
        "    engine: openai-compat\n"
    )
    entries = load_fleet_config(cfg)
    assert entries[0]["transport"] == "openai-compat"


# ---------------------------------------------------------------------------
# repeat loop — run_results accumulation and score_rows stamping
# ---------------------------------------------------------------------------


def _minimal_pass_result(model: str, test_id: str) -> dict:
    return {
        "model": model, "test_id": test_id,
        "schema_compliant": True, "failure_reason": "",
        "elapsed_sec": 0.1, "tokens_per_sec": 1.0,
    }


def _minimal_fail_result(model: str, test_id: str) -> dict:
    return {
        "model": model, "test_id": test_id,
        "schema_compliant": False, "failure_reason": "SCHEMA_FAIL",
        "elapsed_sec": 0.2, "tokens_per_sec": 0.0,
    }


def test_run_host_eval_repeat_stamps_aggregates_on_all_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With repeat=3 all-pass, every written row carries robustness_n=3 and pass_count=3."""
    import hermia.fleet as fleet
    from hermia.results import load_jsonl, open_run

    monkeypatch.setattr(
        "hermia.runner.run_test",
        lambda model, test, sampler, **kw: _minimal_pass_result(model, test["id"]),
        raising=False,
    )
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr(
        "hermia.runner.get_available_models",
        lambda host=None, headers=None: [{"name": "m1"}],
        raising=False,
    )

    jsonl, csv = open_run(tmp_path)
    fleet._run_host_eval(
        {"name": "node1", "host": "http://h1:11434"},
        repeat=3, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )
    rows = load_jsonl(jsonl)

    assert len(rows) == 3  # 1 model × 1 test × 3 repeats
    for row in rows:
        assert row["robustness_n"] == 3, "all 3 repeats must be scored together, not independently"
        assert row["pass_count"] == 3
        assert row["consistency_pct"] == pytest.approx(1.0)


def test_run_host_eval_mixed_pass_fail_aggregates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2 passing + 1 failing repeat: all 3 rows get the same mixed aggregate."""
    import hermia.fleet as fleet
    from hermia.results import load_jsonl, open_run

    call_n = {"n": 0}

    def fake_run(model, test, sampler, **kw):
        call_n["n"] += 1
        if call_n["n"] <= 2:
            return _minimal_pass_result(model, test["id"])
        return _minimal_fail_result(model, test["id"])

    monkeypatch.setattr("hermia.runner.run_test", fake_run, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr(
        "hermia.runner.get_available_models",
        lambda host=None, headers=None: [{"name": "m1"}],
        raising=False,
    )

    jsonl, csv = open_run(tmp_path)
    fleet._run_host_eval(
        {"name": "node1", "host": "http://h1:11434"},
        repeat=3, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )
    rows = load_jsonl(jsonl)

    assert len(rows) == 3
    for row in rows:
        assert row["robustness_n"] == 3
        assert row["pass_count"] == 2
        # majority=pass (2 vs 1) → consistency = 2/3
        assert row["consistency_pct"] == pytest.approx(2 / 3)


def test_run_host_eval_aggregates_are_per_cell_not_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """robustness_n reflects the repeat count per (model, test) cell, not the total row count.

    With 2 tests × repeat=2, each cell gets robustness_n=2 (not 4).
    """
    import hermia.fleet as fleet
    from hermia.results import load_jsonl, open_run

    monkeypatch.setattr(
        "hermia.runner.run_test",
        lambda model, test, sampler, **kw: _minimal_pass_result(model, test["id"]),
        raising=False,
    )
    monkeypatch.setattr(
        "hermia.runner.load_tests_all",
        lambda: [{"id": "t1"}, {"id": "t2"}],
        raising=False,
    )
    monkeypatch.setattr(
        "hermia.runner.get_available_models",
        lambda host=None, headers=None: [{"name": "m1"}],
        raising=False,
    )

    jsonl, csv = open_run(tmp_path)
    fleet._run_host_eval(
        {"name": "node1", "host": "http://h1:11434"},
        repeat=2, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )
    rows = load_jsonl(jsonl)

    assert len(rows) == 4  # 1 model × 2 tests × 2 repeats
    for row in rows:
        assert row["robustness_n"] == 2, "cell accumulation must reset per test, not be global"


def test_run_host_eval_stamps_reproducibility_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every row in a trial group carries an identical reproducibility block;
    3 identical passing trials -> exact_match_rate_raw=1.0, n_valid=3, pass=1.0."""
    import hermia.fleet as fleet
    from hermia.results import load_jsonl, open_run

    def fake_run(model, test, sampler, **kw):
        return {
            "model": model, "test_id": test["id"],
            "schema_compliant": True, "failure_reason": "",
            "raw_response": '{"action":"read"}',
            "elapsed_sec": 0.1, "tokens_per_sec": 1.0,
        }

    monkeypatch.setattr("hermia.runner.run_test", fake_run, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr(
        "hermia.runner.get_available_models",
        lambda host=None, headers=None: [{"name": "m1"}],
        raising=False,
    )

    jsonl, csv = open_run(tmp_path)
    fleet._run_host_eval(
        {"name": "node1", "host": "http://h1:11434"},
        repeat=3, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )
    rows = load_jsonl(jsonl)

    assert len(rows) == 3
    for row in rows:
        repro = row["reproducibility"]
        assert repro["n_repeats"] == 3
        assert repro["n_valid"] == 3
        assert repro["exact_match_rate_raw"] == 1.0
        assert repro["exact_match_rate_canonical"] == 1.0
        assert repro["pass_rate_mean"] == 1.0
        assert repro["pass_rate_stddev"] == 0.0


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


def test_run_host_eval_passes_locality_remote_to_run_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fleet entries always declare locality='remote' — covers tunnel-port topology."""
    import hermia.fleet as fleet
    from hermia.results import open_run

    captured_kwargs: list[dict] = []

    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None, **kw):  # type: ignore[no-untyped-def]
        captured_kwargs.append(dict(kw))
        return {
            "model": model, "test_id": test["id"], "failure_reason": "",
            "elapsed_sec": 0.1, "tokens_per_sec": 1.0,
            "mode": "fleet",
            "peak_cpu_pct": None, "peak_ram_used_gb": None,
            "peak_gpu_pct": None, "peak_vram_used_gb": None,
        }

    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)

    jsonl, csv = open_run(tmp_path)
    # Loopback-port host simulating an SSH tunnel to a remote node.
    entry = {"name": "tunneled-node", "host": "http://localhost:11440"}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )

    assert len(captured_kwargs) == 1, (
        f"expected exactly one run_test call, got {len(captured_kwargs)}"
    )
    assert captured_kwargs[0].get("locality") == "remote", (
        f"_run_host_eval must declare locality='remote'; got {captured_kwargs[0].get('locality')!r}"
    )


def test_run_host_eval_stamps_fingerprint_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stack_fingerprint and _provenance appear on every result row."""
    import hermia.fleet as fleet
    from hermia.results import open_run

    fake_fp = {
        "fingerprint_schema_version": 1,
        "model": {"digest": "sha256:test123"},
        "runtime": {"engine": "ollama"},
        "offload": {"residency_ratio": 1.0},
    }
    fake_prov = {"model.digest": "api", "runtime.engine": "api"}

    captured_rows: list[dict] = []

    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None, **kw):
        return {
            "model": model, "test_id": test["id"], "failure_reason": "",
            "elapsed_sec": 0.1, "tokens_per_sec": 1.0,
            "mode": "fleet",
            "peak_cpu_pct": None, "peak_ram_used_gb": None,
            "peak_gpu_pct": None, "peak_vram_used_gb": None,
        }

    def fake_append(result, jsonl_path, csv_path):
        captured_rows.append(dict(result))

    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)
    monkeypatch.setattr("hermia.results.append_result", fake_append, raising=False)

    # Patch FingerprintCache to return our fake data without HTTP calls, and
    # capture the auth headers so we can assert they're forwarded to the probe.
    from hermia.fingerprint.cache import FingerprintCache
    seen_headers: list[dict | None] = []

    seen_engines: list[str | None] = []

    def fake_get_or_probe(self, host, model, declared,
                          engine_version=None, headers=None, engine=None):
        seen_headers.append(headers)
        seen_engines.append(engine)
        return (fake_fp, fake_prov)

    monkeypatch.setattr(FingerprintCache, "get_or_probe", fake_get_or_probe)

    jsonl, csv = open_run(tmp_path)
    entry = {"name": "fp-test", "host": "http://localhost:11440"}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )

    assert len(captured_rows) == 1
    row = captured_rows[0]
    assert "stack_fingerprint" in row, "row must contain stack_fingerprint"
    assert row["stack_fingerprint"]["fingerprint_schema_version"] == 1
    assert row["stack_fingerprint"]["model"]["digest"] == "sha256:test123"
    assert "_provenance" in row, "row must contain _provenance"
    assert row["_provenance"]["model.digest"] == "api"
    # Auth headers built by the fleet must be forwarded to the probe.
    assert seen_headers and seen_headers[0] is not None
    # Default fleet entry (no transport key) → engine dispatched as "ollama".
    assert seen_engines == ["ollama"]


def test_run_host_eval_shares_one_cache_across_run_test_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fleet must thread its FingerprintCache into run_test so the probe
    isn't re-run per test/repeat (regression: Gemini review)."""
    import hermia.fleet as fleet
    from hermia.fingerprint.cache import FingerprintCache
    from hermia.results import open_run

    seen_caches: list[object] = []

    def fake_run_test(model, test, sampler, host=None, headers=None,
                      transport=None, *, locality=None, fp_cache=None, **kw):
        seen_caches.append(fp_cache)
        return {
            "model": model, "test_id": test["id"], "failure_reason": "",
            "elapsed_sec": 0.1, "tokens_per_sec": 1.0, "mode": "fleet",
            "peak_cpu_pct": None, "peak_ram_used_gb": None,
            "peak_gpu_pct": None, "peak_vram_used_gb": None,
        }

    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all",
                        lambda: [{"id": "t1"}, {"id": "t2"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)
    monkeypatch.setattr("hermia.results.append_result",
                        lambda *a, **k: None, raising=False)
    monkeypatch.setattr(
        FingerprintCache, "get_or_probe",
        lambda self, host, model, declared, engine_version=None, headers=None,
        engine=None: ({}, {}),
    )

    jsonl, csv = open_run(tmp_path)
    entry = {"name": "share", "host": "http://localhost:11441"}
    fleet._run_host_eval(
        entry, repeat=2, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )

    # 2 tests × 2 repeats = 4 calls, every one handed a real cache instance...
    assert len(seen_caches) == 4
    assert all(isinstance(c, FingerprintCache) for c in seen_caches)
    # ...and it's the SAME instance every time (not a fresh per-call probe).
    assert len({id(c) for c in seen_caches}) == 1


def test_run_host_eval_dispatches_openai_compat_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """openai-compat fleet entries must dispatch engine='openai-compat' to the
    fingerprint cache so the Ollama probe is skipped.

    Regression guard: pre-dispatch, openai-compat hosts (vLLM, SGLang,
    LiteLLM, etc.) received 3 doomed /api/show + /api/ps + /api/version
    round-trips per model that 404'd and silently nulled out the fingerprint.
    """
    import hermia.fleet as fleet
    from hermia.fingerprint.cache import FingerprintCache
    from hermia.results import open_run
    from hermia.transport.openai_compat import OpenAICompatTransport

    seen_engines: list[str | None] = []

    def fake_get_or_probe(self, host, model, declared,
                          engine_version=None, headers=None, engine=None):
        seen_engines.append(engine)
        return ({}, {})

    monkeypatch.setattr(FingerprintCache, "get_or_probe", fake_get_or_probe)
    monkeypatch.setattr("hermia.runner.run_test",
                        lambda *a, **kw: {
                            "model": "m1", "test_id": "t1", "failure_reason": "",
                            "elapsed_sec": 0.1, "tokens_per_sec": 1.0, "mode": "fleet",
                            "peak_cpu_pct": None, "peak_ram_used_gb": None,
                            "peak_gpu_pct": None, "peak_vram_used_gb": None,
                        }, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all",
                        lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.results.append_result",
                        lambda *a, **k: None, raising=False)
    # openai-compat hosts call list_models() instead of /api/tags.
    monkeypatch.setattr(OpenAICompatTransport, "list_models",
                        lambda self: ["m1"], raising=False)

    jsonl, csv = open_run(tmp_path)
    entry = {
        "name": "vllm-gateway",
        "host": "http://gateway:4000",
        "transport": "openai-compat",
        "models": "auto",
    }
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
    )

    assert seen_engines == ["openai-compat"], (
        f"openai-compat entry must dispatch engine='openai-compat'; got {seen_engines}"
    )


# ---------------------------------------------------------------------------
# TUI format edge cases
# ---------------------------------------------------------------------------


def test_tui_format_empty_models_list_preserved(tmp_path: Path) -> None:
    """TUI host entry with models: [] must not fall back to Ollama auto-discovery."""
    cfg = tmp_path / "fleet.yaml"
    cfg.write_text(
        "hosts:\n"
        "  - name: node\n"
        "    url: http://node:11434\n"
        "    engine: ollama\n"
        "    models: []\n"
    )
    entries = load_fleet_config(cfg)
    assert "models" in entries[0], "explicit models: [] must be preserved as an empty list"
    assert entries[0]["models"] == []


# ---------------------------------------------------------------------------
# test_timeout — configurable per-request timeout (hermia-rc8)
# ---------------------------------------------------------------------------

def _minimal_run_result(model: str = "m1", test_id: str = "t1") -> dict:
    return {
        "model": model, "test_id": test_id, "failure_reason": "",
        "elapsed_sec": 0.1, "tokens_per_sec": 1.0, "mode": "fleet",
        "peak_cpu_pct": None, "peak_ram_used_gb": None,
        "peak_gpu_pct": None, "peak_vram_used_gb": None,
    }


def test_run_test_uses_custom_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_test forwards test_timeout to _play_turns."""
    from hermia.metrics import MetricsSampler
    from hermia.runner import run_test

    captured: list[int] = []

    class FakeTransport:
        is_api_mode = True

        def generate(self, model, messages, **opts):
            from hermia.transport.base import Response
            captured.append(opts.get("timeout", -1))
            return Response(text='{"ok": true}', tokens=5, elapsed_sec=0.1,
                            orchestration="test", orchestration_version=None,
                            is_api_mode=True)

    monkeypatch.setattr("hermia.runner.FingerprintCache",
                        lambda: MagicMock(get_or_probe=lambda *a, **k: (None, "none")),
                        raising=False)
    monkeypatch.setattr("hermia.runner.SCHEMA_CHECKS", {}, raising=False)
    monkeypatch.setattr("hermia.runner.SIGNAL_EXTRACTORS", {}, raising=False)
    monkeypatch.setattr("hermia.runner.fetch_server_ps_data",
                        lambda *a, **k: {"vram_server_gb": None, "model_size_server_gb": None},
                        raising=False)
    monkeypatch.setattr("hermia.runner.load_framework_versions", lambda: {}, raising=False)

    test = {"id": "t1", "prompt": "hello", "dimension": "tool-calling", "frameworks": {}}
    run_test("m1", test, MetricsSampler(), transport=FakeTransport(), test_timeout=180)

    assert captured == [180], f"expected timeout=180 passed to transport.generate, got {captured}"


def test_run_test_timeout_error_message_uses_custom_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the request times out, the failure_reason includes the custom timeout value."""
    import requests  # noqa: PLC0415

    from hermia.metrics import MetricsSampler
    from hermia.runner import run_test

    class TimingOutTransport:
        is_api_mode = True

        def generate(self, model, messages, **opts):
            raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr("hermia.runner.FingerprintCache",
                        lambda: MagicMock(get_or_probe=lambda *a, **k: (None, "none")),
                        raising=False)
    monkeypatch.setattr("hermia.runner.SCHEMA_CHECKS", {}, raising=False)
    monkeypatch.setattr("hermia.runner.SIGNAL_EXTRACTORS", {}, raising=False)
    monkeypatch.setattr("hermia.runner.fetch_server_ps_data",
                        lambda *a, **k: {"vram_server_gb": None, "model_size_server_gb": None},
                        raising=False)
    monkeypatch.setattr("hermia.runner.load_framework_versions", lambda: {}, raising=False)

    test = {"id": "t1", "prompt": "hello", "dimension": "tool-calling", "frameworks": {}}
    result = run_test(
        "m1", test, MetricsSampler(), transport=TimingOutTransport(), test_timeout=120
    )

    assert "120s" in result["failure_reason"], (
        f"expected '120s' in failure_reason, got {result['failure_reason']!r}"
    )


def test_run_host_eval_cli_timeout_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI-supplied test_timeout reaches run_test when entry has no test_timeout key."""
    import hermia.fleet as fleet
    from hermia.results import open_run

    captured_timeouts: list[int] = []

    def fake_run_test(model, test, sampler, host=None, headers=None,
                      transport=None, *, locality=None, fp_cache=None,
                      test_timeout=90, **kw):  # type: ignore[no-untyped-def]
        captured_timeouts.append(test_timeout)
        return _minimal_run_result(model, test["id"])

    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)

    jsonl, csv = open_run(tmp_path)
    entry = {"name": "node", "host": "http://node:11434"}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
        test_timeout=180,
    )

    assert captured_timeouts == [180], f"expected [180], got {captured_timeouts}"


def test_run_host_eval_yaml_timeout_used_when_no_cli_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-host 'test_timeout' in fleet YAML is used when no CLI flag is given."""
    import hermia.fleet as fleet
    from hermia.results import open_run

    captured_timeouts: list[int] = []

    def fake_run_test(model, test, sampler, host=None, headers=None,
                      transport=None, *, locality=None, fp_cache=None,
                      test_timeout=90, **kw):  # type: ignore[no-untyped-def]
        captured_timeouts.append(test_timeout)
        return _minimal_run_result(model, test["id"])

    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)

    jsonl, csv = open_run(tmp_path)
    entry = {"name": "node", "host": "http://node:11434", "test_timeout": 120}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
        test_timeout=None,  # no CLI flag
    )

    assert captured_timeouts == [120], f"expected [120] from YAML, got {captured_timeouts}"


def test_run_host_eval_cli_timeout_overrides_yaml_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI flag wins over per-host 'test_timeout' in fleet YAML."""
    import hermia.fleet as fleet
    from hermia.results import open_run

    captured_timeouts: list[int] = []

    def fake_run_test(model, test, sampler, host=None, headers=None,
                      transport=None, *, locality=None, fp_cache=None,
                      test_timeout=90, **kw):  # type: ignore[no-untyped-def]
        captured_timeouts.append(test_timeout)
        return _minimal_run_result(model, test["id"])

    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)

    jsonl, csv = open_run(tmp_path)
    entry = {"name": "node", "host": "http://node:11434", "test_timeout": 120}
    fleet._run_host_eval(
        entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
        print_lock=__import__("threading").Lock(),
        print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
        test_timeout=300,  # CLI wins
    )

    assert captured_timeouts == [300], f"expected CLI value [300], got {captured_timeouts}"


def test_run_fleet_passes_timeout_to_host_eval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_fleet forwards test_timeout kwarg into _run_host_eval."""
    import hermia.fleet as fleet

    captured: list[int | None] = []

    def fake_run_host_eval(entry, repeat, run_id, jsonl_path, csv_path,
                           print_lock, print_fn, stderr_fn, verbosity,
                           test_timeout=None):  # type: ignore[no-untyped-def]
        captured.append(test_timeout)
        return True

    monkeypatch.setattr(fleet, "_run_host_eval", fake_run_host_eval)
    monkeypatch.setattr("hermia.results.open_run",
                        lambda p: (tmp_path / "r.jsonl", tmp_path / "r.csv"))

    entry = {"name": "n", "host": "http://node:11434"}
    fleet.run_fleet([entry], repeat=1, results_dir=tmp_path,
                    print_fn=lambda s: None, test_timeout=180)

    assert captured == [180], f"expected [180] forwarded to _run_host_eval, got {captured}"


def test_run_host_eval_rejects_invalid_yaml_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_run_host_eval raises ValueError when test_timeout in YAML is not a positive int."""
    import hermia.fleet as fleet
    from hermia.results import open_run

    monkeypatch.setattr("hermia.runner.run_test", lambda *a, **k: {}, raising=False)
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)

    jsonl, csv = open_run(tmp_path)
    for bad_value in ("fast", 0, -5, None, True, False):
        entry = {"name": "node", "host": "http://node:11434", "test_timeout": bad_value}
        with pytest.raises(ValueError, match="test_timeout"):
            fleet._run_host_eval(
                entry, repeat=1, run_id="rid", jsonl_path=jsonl, csv_path=csv,
                print_lock=__import__("threading").Lock(),
                print_fn=lambda s: None, stderr_fn=lambda s: None, verbosity=-1,
                test_timeout=None,
            )
