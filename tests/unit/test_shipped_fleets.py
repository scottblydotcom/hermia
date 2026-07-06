"""The example fleets shipped in fleets/ must load and use the headless schema.

These files are referenced verbatim by README.md (Docker quickstart) and
docs/getting-started.md, so a docs-following user copy-pasting the command must
find a valid, loadable fleet config.
"""

from pathlib import Path

from hermia.fleet import load_fleet_config

REPO = Path(__file__).resolve().parents[2]


def test_shipped_local_fleet_loads_headless_schema():
    entries = load_fleet_config(REPO / "fleets" / "local.yaml")
    assert len(entries) == 1
    assert entries[0]["name"] == "local"
    assert entries[0]["host"] == "http://localhost:11434"
    assert entries[0]["transport"] == "ollama"


def test_shipped_desktop_fleet_targets_host_docker_internal():
    entries = load_fleet_config(REPO / "fleets" / "desktop.yaml")
    assert len(entries) == 1
    assert entries[0]["host"] == "http://host.docker.internal:11434"
    assert entries[0]["transport"] == "ollama"
