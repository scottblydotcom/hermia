"""The example fleets shipped in fleets/ must load and run through the hermia CLI.

These files are referenced verbatim by README.md (Docker quickstart) and
docs/getting-started.md, so a docs-following user copy-pasting
``hermia --fleet fleets/local.yaml`` must find a valid, loadable fleet config.

Per AGENTS.md rule 5, the CLI entrypoint path is exercised directly (``main()``),
not just the internal ``load_fleet_config`` function.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hermia.fleet import load_fleet_config

REPO = Path(__file__).resolve().parents[2]
LOCAL = REPO / "fleets" / "local.yaml"
DESKTOP = REPO / "fleets" / "desktop.yaml"


def test_shipped_local_fleet_loads_headless_schema():
    entries = load_fleet_config(LOCAL)
    assert len(entries) == 1
    assert entries[0]["name"] == "local"
    assert entries[0]["host"] == "http://localhost:11434"
    assert entries[0]["transport"] == "ollama"
    assert entries[0]["models"] == ["llama3.2:latest"]


def test_shipped_desktop_fleet_targets_host_docker_internal():
    entries = load_fleet_config(DESKTOP)
    assert len(entries) == 1
    assert entries[0]["name"] == "docker-desktop"
    assert entries[0]["host"] == "http://host.docker.internal:11434"
    assert entries[0]["transport"] == "ollama"
    assert entries[0]["models"] == ["llama3.2:latest"]


@pytest.mark.parametrize(
    ("fleet_file", "expected"),
    [
        (LOCAL, {"name": "local", "host": "http://localhost:11434"}),
        (DESKTOP, {"name": "docker-desktop", "host": "http://host.docker.internal:11434"}),
    ],
)
def test_cli_fleet_flag_loads_shipped_example(fleet_file, expected, tmp_path, monkeypatch):
    """`hermia --fleet fleets/<example>.yaml` loads the shipped file and hands it to run_fleet."""
    monkeypatch.setattr(sys, "argv", ["hermia", "--fleet", str(fleet_file)])

    with (
        patch("hermia.fleet.run_fleet") as mock_run_fleet,
        patch("hermia.submit.RESULTS_DIR", tmp_path),
        pytest.raises(SystemExit) as exc_info,
    ):
        from hermia.app import main

        main()

    assert exc_info.value.code == 0
    mock_run_fleet.assert_called_once()
    entries = mock_run_fleet.call_args.args[0]
    assert len(entries) == 1
    assert entries[0]["name"] == expected["name"]
    assert entries[0]["host"] == expected["host"]
    assert entries[0]["transport"] == "ollama"
    assert entries[0]["models"] == ["llama3.2:latest"]
