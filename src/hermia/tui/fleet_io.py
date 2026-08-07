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


def _headless_host(d: Any) -> Host:
    """Convert one headless `fleet[]` entry to a TUI Host.

    The reverse of ``fleet._tui_fleet_to_entries``, and it must stay in step
    with it: headless writes {name, host, transport?, auth.bearer.key_env?,
    models?}, the TUI wants {name, url, engine, auth_header_env?, models[]}.

    ``test_timeout`` and ``stack`` have no Host field and are dropped — a
    headless config carrying them still loads rather than failing.
    """
    if not isinstance(d, dict):
        raise TypeError("Fleet entry must be a dictionary")
    if not d.get("name"):
        raise KeyError("Fleet entry missing required field: 'name'")
    if not d.get("host"):
        raise KeyError("Fleet entry missing required field: 'host'")
    raw_models = d.get("models")
    # `models: auto` is a headless directive meaning "discover on the host".
    # The TUI discovers through its picker, so it selects nothing here — it must
    # not materialise a model literally named "auto".
    models: list[str] = [] if (raw_models is None or raw_models == "auto") else list(raw_models)
    auth = d.get("auth") or {}
    bearer = (auth.get("bearer") or {}) if isinstance(auth, dict) else {}
    return Host(
        name=d["name"],
        url=d["host"],
        engine=d.get("transport") or "ollama",
        auth_header_env=bearer.get("key_env") if isinstance(bearer, dict) else None,
        models=[ModelChoice(name=n, selected=True) for n in models],
    )


def load_fleet(path: Path) -> FleetConfig:
    """Parse a fleet YAML file into a FleetConfig.

    Accepts BOTH layouts, mirroring ``fleet.load_fleet_config`` which already
    reads TUI files: the TUI's own `hosts:` key, and the headless runner's
    `fleet:` key. Before hermia-79z6 only `hosts:` was read and a headless
    config loaded as zero hosts with no error — 23 of 25 committed configs.

    Raises:
        FileNotFoundError: if the path does not exist.
        yaml.YAMLError: if the file is not valid YAML.
        KeyError: if a required field (name), or any host key at all, is missing.
    """
    if not path.exists():
        raise FileNotFoundError(f"No fleet found at {path}")
    raw = yaml.safe_load(path.read_text())
    # The isinstance check forces the right error class — `"name" not in raw`
    # would substring-match if raw were a scalar string.
    if not isinstance(raw, dict):
        raise KeyError("name")
    is_headless = "hosts" not in raw and "fleet" in raw
    if is_headless:
        # Headless configs have no `name:` — the CLI never needed one. Falling
        # back to the filename keeps them openable AND avoids the unnamed-fleet
        # trap: RunnerScreen only sets results_dir when config.name is truthy,
        # so a nameless fleet runs and silently discards every row.
        # TUI-saved files are `fleets/<name>.yaml`, so stem == name round-trips.
        name = str(raw.get("name") or "") or Path(path.stem).name or "unnamed"
    else:
        # TUI format keeps the strict contract: `name:` (explicit-null) and
        # `name: ""` would otherwise construct FleetConfig(name=None) and write
        # `fleets/None.yaml` downstream.
        if not raw.get("name"):
            raise KeyError("name")
        name = raw["name"]
    # `raw.get("key", [])` would return None if the YAML has an empty key
    # (e.g. `tests:` with no children), causing list(None) / iteration to
    # TypeError. `... or []` short-circuits both missing and explicit-null.
    # `repeat: null` (explicit-null) returns None from .get("repeat", 1),
    # bypassing the default. int(None) raises TypeError; guard explicitly.
    repeat_raw = raw.get("repeat")
    # `tests: <single-string>` would silently `list("foo") == ['f','o','o']`
    # — fail loud instead of producing nonsense test IDs.
    # ABSENT and EMPTY are deliberately different. A headless config omits
    # `tests:` because the CLI always runs the whole corpus, so defaulting an
    # absent key to [] would load a fleet with hosts but zero trials — the same
    # silent-empty shape as the missing hosts. An explicit `tests: []` is a TUI
    # user who deselected everything, and must be left alone.
    if "tests" in raw:
        tests_raw = raw.get("tests") or []
        if isinstance(tests_raw, str):
            raise TypeError("tests must be a list of strings, not a single string")
        tests = list(tests_raw)
    else:
        from hermia.runner import load_tests_all
        tests = [t["id"] for t in load_tests_all()]

    # `hosts:` is the TUI's native key and wins when both are present.
    if "hosts" in raw:
        host_entries = raw.get("hosts") or []
        if not isinstance(host_entries, list):
            raise TypeError("'hosts' must be a list")
        hosts = [_deserialize_host(h) for h in host_entries]
    elif "fleet" in raw:
        fleet_entries = raw.get("fleet") or []
        if not isinstance(fleet_entries, list):
            raise TypeError("'fleet' must be a list")
        hosts = [_headless_host(h) for h in fleet_entries]
    else:
        raise KeyError(
            "fleet config has no 'hosts' (TUI) or 'fleet' (headless) key — "
            "refusing to load it as an empty fleet"
        )

    return FleetConfig(
        name=name,
        tests=tests,
        repeat=int(repeat_raw) if repeat_raw is not None else 1,
        hosts=hosts,
    )


def _serialize_host(h: Host) -> dict[str, Any]:
    d: dict[str, Any] = {"name": h.name, "url": h.url, "engine": h.engine}
    if h.auth_header_env:
        d["auth_header_env"] = h.auth_header_env
    if h.hardware:
        d["hardware"] = h.hardware
    d["models"] = [m.name for m in h.models if m.selected]
    return d


def _deserialize_host(d: Any) -> Host:
    if not isinstance(d, dict):
        raise TypeError("Host entry must be a dictionary")
    # Loud on null/empty required fields rather than silently constructing
    # Host(name=None, url=None, engine=None) — same stance as load_fleet's
    # name guard.
    for field in ("name", "url", "engine"):
        if not d.get(field):
            raise KeyError(f"Host entry missing required field: '{field}'")
    return Host(
        name=d["name"],
        url=d["url"],
        engine=d["engine"],
        auth_header_env=d.get("auth_header_env"),
        hardware=d.get("hardware"),
        # `models:` with no children parses as None; `or []` guards iteration.
        models=[ModelChoice(name=n, selected=True) for n in (d.get("models") or [])],
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
    # Defensive: a malformed seed where `hosts:` is a string or dict (not a
    # list) would iterate wrong — short-circuit to empty rather than crash.
    hosts_raw = raw.get("hosts")
    if not isinstance(hosts_raw, list):
        return []
    return [_deserialize_seed_host(h) for h in hosts_raw]


def _serialize_seed_host(h: Host) -> dict[str, Any]:
    d: dict[str, Any] = {"name": h.name, "url": h.url, "engine": h.engine}
    if h.auth_header_env:
        d["auth_header_env"] = h.auth_header_env
    if h.hardware:
        d["hardware"] = h.hardware
    return d


def _deserialize_seed_host(d: Any) -> Host:
    if not isinstance(d, dict):
        raise TypeError("Seed host entry must be a dictionary")
    for field in ("name", "url", "engine"):
        if not d.get(field):
            raise KeyError(f"Seed host entry missing required field: '{field}'")
    return Host(
        name=d["name"],
        url=d["url"],
        engine=d["engine"],
        auth_header_env=d.get("auth_header_env"),
        hardware=d.get("hardware"),
    )
