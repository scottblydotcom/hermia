"""YAML round-trip for fleets/<name>.yaml and ~/.config/hermia/hosts.yaml.

Fleet YAML schema:
    name: str
    created: ISO-8601 timestamp
    hermia_version: str
    tests: list[str]
    repeat: int
    hosts:
      - name: str
        url: str
        engine: str
        auth_header_env: str (optional — env var NAME, never a secret value)
        hardware: str (optional)
        models: list[str]  # only selected models

Per AGENTS.md rule 11, credentials are never persisted in this file. Only the
env var name (auth_header_env) is stored; the secret is resolved at runtime
from the environment.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from hermia import __version__
from hermia.tui.state import FleetConfig, Host, ModelChoice

FLEETS_SUBDIR = "fleets"
DEFAULT_HOSTS_SEED_PATH = Path.home() / ".config" / "hermia" / "hosts.yaml"


def fleet_path(name: str, *, root: Path = Path(".")) -> Path:
    """Resolve `fleets/<name>.yaml` relative to a project root."""
    return root / FLEETS_SUBDIR / f"{name}.yaml"


def save_fleet(config: FleetConfig, *, root: Path = Path(".")) -> Path:
    """Serialize a FleetConfig to `fleets/<name>.yaml`.

    Auto-creates the `fleets/` directory if missing. Only selected models are
    persisted. Optional fields (auth_header_env, hardware) are omitted when
    None to keep the YAML clean.
    """
    path = fleet_path(config.name, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "name": config.name,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "hermia_version": __version__,
        "tests": list(config.tests),
        "repeat": config.repeat,
        "hosts": [_serialize_host(h) for h in config.hosts],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def load_fleet(path: Path) -> FleetConfig:
    """Parse a fleet YAML file into a FleetConfig.

    Raises:
        FileNotFoundError: if the path does not exist.
        yaml.YAMLError: if the file is not valid YAML.
        KeyError: if a required field (name) is missing.
    """
    if not path.exists():
        raise FileNotFoundError(f"No fleet found at {path}")
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "name" not in raw:
        # `"name" not in raw` would substring-match if raw were a scalar string,
        # then raw["name"] would TypeError instead of giving the documented
        # KeyError. The isinstance check forces the right error class.
        raise KeyError("name")
    return FleetConfig(
        name=raw["name"],
        tests=list(raw.get("tests", [])),
        repeat=int(raw.get("repeat", 1)),
        hosts=[_deserialize_host(h) for h in raw.get("hosts", [])],
    )


def _serialize_host(h: Host) -> dict[str, Any]:
    d: dict[str, Any] = {"name": h.name, "url": h.url, "engine": h.engine}
    if h.auth_header_env:
        d["auth_header_env"] = h.auth_header_env
    if h.hardware:
        d["hardware"] = h.hardware
    d["models"] = [m.name for m in h.models if m.selected]
    return d


def _deserialize_host(d: dict[str, Any]) -> Host:
    return Host(
        name=d["name"],
        url=d["url"],
        engine=d["engine"],
        auth_header_env=d.get("auth_header_env"),
        hardware=d.get("hardware"),
        models=[ModelChoice(name=n, selected=True) for n in d.get("models", [])],
    )


def save_hosts_seed(hosts: list[Host], *, path: Path = DEFAULT_HOSTS_SEED_PATH) -> Path:
    """Persist the user's seed host list (host identity only — no models).

    Models are not stored because they re-probe each session. Per AGENTS.md
    rule 11, only auth_header_env (env var NAME) is stored.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"hosts": [_serialize_seed_host(h) for h in hosts]}
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def load_hosts_seed(*, path: Path = DEFAULT_HOSTS_SEED_PATH) -> list[Host]:
    """Load the user's seed host list. Returns [] if the file does not exist."""
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text())
    # A malformed seed file (scalar, list, None) returns [] instead of crashing
    # later when .get() is called on a non-dict.
    if not isinstance(raw, dict):
        return []
    return [_deserialize_seed_host(h) for h in raw.get("hosts", [])]


def _serialize_seed_host(h: Host) -> dict[str, Any]:
    d: dict[str, Any] = {"name": h.name, "url": h.url, "engine": h.engine}
    if h.auth_header_env:
        d["auth_header_env"] = h.auth_header_env
    if h.hardware:
        d["hardware"] = h.hardware
    return d


def _deserialize_seed_host(d: dict[str, Any]) -> Host:
    return Host(
        name=d["name"],
        url=d["url"],
        engine=d["engine"],
        auth_header_env=d.get("auth_header_env"),
        hardware=d.get("hardware"),
    )
