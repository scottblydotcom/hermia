# Fleet TUI Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reusable widget library, event bus, state model, fleet YAML I/O, and async probe layer that the Fleet TUI's picker and runner flows will consume in subsequent plans.

**Architecture:** New package `src/hermia/tui/` with five concerns: domain-agnostic Textual widgets (`widgets/`), in-process pub/sub bus (`bus.py`), in-memory data model with extension protocols (`state.py`), fleet YAML round-trip (`fleet_io.py`), and async host probe wrapping the existing `transport/` layer (`probe.py`). No screens or user-facing flow in this plan — every surface is unit-tested in isolation. Plans 2-4 (picker, runner, migration) consume this foundation.

**Tech Stack:** Python 3.11+, Textual ≥0.80 (already in `pyproject.toml`), asyncio (stdlib), PyYAML (already in `pyproject.toml`), pytest, pytest-asyncio, ruff, mypy. **No new dependencies.**

**Spec reference:** [docs/superpowers/specs/2026-06-18-fleet-tui-design.md](../specs/2026-06-18-fleet-tui-design.md)

**Tracking bead:** `hermia-86g`

---

## File Structure

This plan creates these files. Each file has one clear responsibility:

```
src/hermia/tui/
  __init__.py                        # package marker, exports public types
  state.py                           # FleetConfig, Host, ModelChoice dataclasses + HostSource/ModelSource Protocols
  fleet_io.py                        # load_fleet / save_fleet / load_hosts_seed / save_hosts_seed
  bus.py                             # SessionBus pub/sub
  probe.py                           # async probe wrapping transport/, publishes probe.* events
  widgets/
    __init__.py                      # re-exports public widgets
    status_badge.py                  # ✓ ↺ ✗ ! glyph + direction-aware color
    search_bar.py                    # / live-filter input
    filter_axis.py                   # tab-cycling filter tabs
    progress_bar.py                  # mini (per-host) + aggregate variants
    drillable_list.py                # virtual scroll + universal /, tab, a, n, space keys

tests/unit/tui/
  __init__.py
  test_state.py
  test_fleet_io.py
  test_bus.py
  test_probe.py
  test_widgets_status_badge.py
  test_widgets_search_bar.py
  test_widgets_filter_axis.py
  test_widgets_progress_bar.py
  test_widgets_drillable_list.py

tests/fixtures/
  __init__.py                        # if not present
  fake_transport.py                  # FakeTransport for any test driving probe / runner without a host
```

Files modified by this plan:
- `AGENTS.md` — Module Boundary Table row "UI/TUI changes" gains `src/hermia/tui/`

Files NOT touched (out of scope for this plan):
- `src/hermia/screens.py` — Plan 4 deletes it
- `src/hermia/app.py` — Plan 4 rewires it
- `src/hermia/fleet.py`, `runner.py`, `transport/`, `scoring.py` — never touched by TUI work

---

## Setup

- [ ] **S1: Branch from latest dev**

Run:
```bash
git checkout dev
git pull origin dev
git checkout -b feature/fleet-tui-foundation
```

Expected: clean `dev` checkout, new branch created.

- [ ] **S2: Expand AGENTS.md Module Boundary Table**

Modify `AGENTS.md`. Find the row:

```
| UI/TUI changes              | `src/hermia/screens.py`, `src/hermia/app.py`                 | Core eval logic                      |
```

Replace with:

```
| UI/TUI changes              | `src/hermia/tui/`, `src/hermia/screens.py`, `src/hermia/app.py` | Core eval logic                      |
```

Commit:
```bash
git add AGENTS.md
git commit -m "chore(agents): expand UI/TUI scope to include tui/ package"
```

- [ ] **S3: Scaffold empty package**

Create these files with the exact content shown:

**`src/hermia/tui/__init__.py`:**
```python
"""Hermia Fleet TUI — unified interactive picker + live runner."""
```

**`src/hermia/tui/widgets/__init__.py`:**
```python
"""Reusable, domain-agnostic Textual widgets for the Fleet TUI."""
```

**`tests/unit/tui/__init__.py`:** (empty file)

**`tests/fixtures/__init__.py`:** (empty file — if `tests/fixtures/` doesn't already exist, create it)

Verify `tests/fixtures/` doesn't already exist:
```bash
ls tests/fixtures/ 2>/dev/null || mkdir -p tests/fixtures
```

Commit:
```bash
git add src/hermia/tui/ tests/unit/tui/ tests/fixtures/__init__.py
git commit -m "feat(tui): scaffold empty tui package"
```

---

## Task 1: state.py — Data model & protocols

**Files:**
- Create: `src/hermia/tui/state.py`
- Test: `tests/unit/tui/test_state.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_state.py`:

```python
"""Tests for hermia.tui.state — dataclasses + HostSource / ModelSource protocols."""
from typing import get_type_hints

import pytest

from hermia.tui.state import (
    FleetConfig,
    Host,
    HostSource,
    ModelChoice,
    ModelSource,
)


class TestModelChoice:
    def test_defaults(self) -> None:
        m = ModelChoice(name="qwen3:32b")
        assert m.name == "qwen3:32b"
        assert m.selected is False
        assert m.size_bytes is None
        assert m.quant is None
        assert m.family is None
        assert m.modality is None

    def test_selected_can_be_set(self) -> None:
        m = ModelChoice(name="qwen3:32b", selected=True)
        assert m.selected is True


class TestHost:
    def test_required_fields(self) -> None:
        h = Host(name="node-a", url="http://node-a:11434", engine="ollama")
        assert h.name == "node-a"
        assert h.url == "http://node-a:11434"
        assert h.engine == "ollama"
        assert h.auth_header_env is None
        assert h.hardware is None
        assert h.models == []

    def test_optional_fields(self) -> None:
        h = Host(
            name="m3-pro",
            url="http://m3:4000",
            engine="openai-compat",
            auth_header_env="LITELLM_KEY",
            hardware="M3 Pro 36GB",
            models=[ModelChoice(name="coder-bigger-5090", selected=True)],
        )
        assert h.auth_header_env == "LITELLM_KEY"
        assert h.hardware == "M3 Pro 36GB"
        assert len(h.models) == 1
        assert h.models[0].selected is True


class TestFleetConfig:
    def test_defaults(self) -> None:
        c = FleetConfig(name="smoke")
        assert c.name == "smoke"
        assert c.hosts == []
        assert c.tests == []
        assert c.repeat == 1

    def test_full_construction(self) -> None:
        c = FleetConfig(
            name="kwaainet-baseline",
            hosts=[Host(name="h1", url="http://h1:11434", engine="ollama")],
            tests=["prompt-injection-1", "jailbreak-1"],
            repeat=3,
        )
        assert c.name == "kwaainet-baseline"
        assert len(c.hosts) == 1
        assert c.tests == ["prompt-injection-1", "jailbreak-1"]
        assert c.repeat == 3


class TestProtocols:
    """Smoke test that the Protocols exist and have the expected shape."""

    def test_host_source_is_protocol(self) -> None:
        # A protocol cannot be instantiated; verify it has the method we expect.
        assert hasattr(HostSource, "list_hosts")

    def test_model_source_is_protocol(self) -> None:
        assert hasattr(ModelSource, "list_models")

    def test_host_source_can_be_implemented(self) -> None:
        class FakeHostSource:
            async def list_hosts(self) -> list[Host]:
                return [Host(name="h1", url="http://h1", engine="ollama")]

        src: HostSource = FakeHostSource()  # structural check
        assert isinstance(src, object)

    def test_model_source_can_be_implemented(self) -> None:
        class FakeModelSource:
            async def list_models(self, host: Host) -> list[ModelChoice]:
                return [ModelChoice(name="qwen3:32b", selected=False)]

        src: ModelSource = FakeModelSource()
        assert isinstance(src, object)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_state.py -v
```

Expected: FAIL with `ImportError: cannot import name 'FleetConfig' from 'hermia.tui.state'` (module doesn't exist yet).

- [ ] **Step 3: Implement state.py**

Create `src/hermia/tui/state.py`:

```python
"""In-memory data model for the Fleet TUI.

FleetConfig is the single source of truth for the in-flight edit. Picker
screens read and write directly to it — no diff merging, no draft state.

The HostSource / ModelSource protocols define extension seams for v0.3+
(Kwaainet registry, recommendation engine, MCP-sourced benchmark data).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ModelChoice:
    name: str
    selected: bool = False
    # Cached from probe; not persisted to YAML.
    size_bytes: int | None = None
    quant: str | None = None
    family: str | None = None
    modality: str | None = None


@dataclass
class Host:
    name: str
    url: str
    engine: str
    auth_header_env: str | None = None
    hardware: str | None = None
    models: list[ModelChoice] = field(default_factory=list)


@dataclass
class FleetConfig:
    name: str
    hosts: list[Host] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    repeat: int = 1


@runtime_checkable
class HostSource(Protocol):
    async def list_hosts(self) -> list[Host]: ...


@runtime_checkable
class ModelSource(Protocol):
    async def list_models(self, host: Host) -> list[ModelChoice]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_state.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/state.py tests/unit/tui/test_state.py
git commit -m "feat(tui): add FleetConfig data model + HostSource/ModelSource protocols"
```

---

## Task 2: fleet_io.py — YAML round-trip for `fleets/<name>.yaml`

**Files:**
- Create: `src/hermia/tui/fleet_io.py`
- Test: `tests/unit/tui/test_fleet_io.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_fleet_io.py`:

```python
"""Tests for hermia.tui.fleet_io — YAML load/save for fleets and hosts.yaml."""
from pathlib import Path

import pytest
import yaml

from hermia.tui.fleet_io import (
    fleet_path,
    load_fleet,
    save_fleet,
)
from hermia.tui.state import FleetConfig, Host, ModelChoice


class TestFleetPath:
    def test_returns_fleets_subdir(self, tmp_path: Path) -> None:
        # fleet_path is resolved against the caller-supplied root.
        p = fleet_path("kwaainet-baseline", root=tmp_path)
        assert p == tmp_path / "fleets" / "kwaainet-baseline.yaml"


class TestSaveFleet:
    def test_creates_fleets_dir_if_missing(self, tmp_path: Path) -> None:
        config = FleetConfig(name="smoke")
        path = save_fleet(config, root=tmp_path)
        assert path.exists()
        assert path.parent.name == "fleets"

    def test_writes_minimal_yaml(self, tmp_path: Path) -> None:
        config = FleetConfig(name="smoke")
        path = save_fleet(config, root=tmp_path)
        data = yaml.safe_load(path.read_text())
        assert data["name"] == "smoke"
        assert data["tests"] == []
        assert data["hosts"] == []
        assert data["repeat"] == 1
        assert "created" in data
        assert "hermia_version" in data

    def test_writes_full_fleet(self, tmp_path: Path) -> None:
        config = FleetConfig(
            name="kwaainet-baseline",
            hosts=[
                Host(
                    name="node-a",
                    url="https://node-a:11434",
                    engine="ollama",
                    hardware="RTX 5090",
                    auth_header_env="LITELLM_KEY",
                    models=[
                        ModelChoice(name="qwen3:32b", selected=True),
                        ModelChoice(name="qwen3-coder:30b", selected=True),
                        ModelChoice(name="llama3:70b", selected=False),  # excluded
                    ],
                )
            ],
            tests=["prompt-injection-1", "jailbreak-1"],
            repeat=3,
        )
        path = save_fleet(config, root=tmp_path)
        data = yaml.safe_load(path.read_text())
        assert data["repeat"] == 3
        assert data["tests"] == ["prompt-injection-1", "jailbreak-1"]
        assert len(data["hosts"]) == 1
        h = data["hosts"][0]
        assert h["name"] == "node-a"
        assert h["url"] == "https://node-a:11434"
        assert h["engine"] == "ollama"
        assert h["hardware"] == "RTX 5090"
        assert h["auth_header_env"] == "LITELLM_KEY"
        # only selected models persist
        assert h["models"] == ["qwen3:32b", "qwen3-coder:30b"]

    def test_omits_optional_fields_when_none(self, tmp_path: Path) -> None:
        config = FleetConfig(
            name="minimal",
            hosts=[Host(name="h1", url="http://h1:11434", engine="ollama")],
        )
        path = save_fleet(config, root=tmp_path)
        data = yaml.safe_load(path.read_text())
        h = data["hosts"][0]
        assert "auth_header_env" not in h
        assert "hardware" not in h

    def test_never_writes_secret_value(self, tmp_path: Path) -> None:
        # AGENTS.md rule 11: never store credentials in config files.
        config = FleetConfig(
            name="secrets-test",
            hosts=[
                Host(
                    name="h1",
                    url="http://h1:11434",
                    engine="openai-compat",
                    auth_header_env="LITELLM_KEY",
                )
            ],
        )
        path = save_fleet(config, root=tmp_path)
        text = path.read_text()
        # The env var NAME is allowed; an actual secret value is not.
        assert "LITELLM_KEY" in text
        assert "sk-" not in text
        assert "Bearer " not in text


class TestLoadFleet:
    def test_round_trip(self, tmp_path: Path) -> None:
        original = FleetConfig(
            name="rt",
            hosts=[
                Host(
                    name="h1",
                    url="http://h1:11434",
                    engine="ollama",
                    hardware="RTX 5090",
                    models=[ModelChoice(name="qwen3:32b", selected=True)],
                )
            ],
            tests=["prompt-injection-1"],
            repeat=2,
        )
        path = save_fleet(original, root=tmp_path)
        loaded = load_fleet(path)
        assert loaded.name == "rt"
        assert loaded.repeat == 2
        assert loaded.tests == ["prompt-injection-1"]
        assert len(loaded.hosts) == 1
        h = loaded.hosts[0]
        assert h.name == "h1"
        assert h.engine == "ollama"
        assert h.hardware == "RTX 5090"
        assert len(h.models) == 1
        assert h.models[0].name == "qwen3:32b"
        assert h.models[0].selected is True

    def test_load_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_fleet(tmp_path / "fleets" / "nope.yaml")

    def test_load_malformed_yaml_raises_yaml_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("name: smoke\n  this is: not valid yaml\n: : :")
        with pytest.raises(yaml.YAMLError):
            load_fleet(bad)

    def test_load_missing_required_name_raises_key_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "noname.yaml"
        bad.write_text("tests: []\nhosts: []\n")
        with pytest.raises(KeyError):
            load_fleet(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_fleet_io.py -v
```

Expected: FAIL with `ImportError: cannot import name 'save_fleet' from 'hermia.tui.fleet_io'`.

- [ ] **Step 3: Implement fleet_io.py**

Create `src/hermia/tui/fleet_io.py`:

```python
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

Per AGENTS.md rule 11, credentials are never persisted in this file. Only
the env var name (auth_header_env) is stored; the secret is resolved at
runtime from the environment.
"""
from __future__ import annotations

from datetime import datetime, timezone
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

    Auto-creates the `fleets/` directory if missing. Only selected models
    are persisted. Optional fields (auth_header_env, hardware) are omitted
    when None to keep the YAML clean.
    """
    path = fleet_path(config.name, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "name": config.name,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
    if raw is None or "name" not in raw:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_fleet_io.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/fleet_io.py tests/unit/tui/test_fleet_io.py
git commit -m "feat(tui): fleet YAML round-trip with credential-safe schema"
```

---

## Task 3: fleet_io.py — hosts.yaml seed list

**Files:**
- Modify: `src/hermia/tui/fleet_io.py`
- Test: `tests/unit/tui/test_fleet_io.py` (add to existing file)

- [ ] **Step 1: Add failing tests to test_fleet_io.py**

Append to `tests/unit/tui/test_fleet_io.py`:

```python
from hermia.tui.fleet_io import load_hosts_seed, save_hosts_seed


class TestHostsSeed:
    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        seed_path = tmp_path / "hosts.yaml"
        hosts = [
            Host(
                name="node-a",
                url="https://node-a:11434",
                engine="ollama",
                hardware="RTX 5090",
                auth_header_env="LITELLM_KEY",
            ),
            Host(name="m3-pro", url="https://m3:4000", engine="openai-compat"),
        ]
        save_hosts_seed(hosts, path=seed_path)
        assert seed_path.exists()

        loaded = load_hosts_seed(path=seed_path)
        assert len(loaded) == 2
        assert loaded[0].name == "node-a"
        assert loaded[0].hardware == "RTX 5090"
        assert loaded[0].auth_header_env == "LITELLM_KEY"
        assert loaded[1].name == "m3-pro"
        assert loaded[1].hardware is None

    def test_load_missing_seed_returns_empty_list(self, tmp_path: Path) -> None:
        # A missing seed file is not an error — first-run users have no seed yet.
        loaded = load_hosts_seed(path=tmp_path / "nope.yaml")
        assert loaded == []

    def test_save_creates_parent_dir(self, tmp_path: Path) -> None:
        seed_path = tmp_path / ".config" / "hermia" / "hosts.yaml"
        save_hosts_seed([], path=seed_path)
        assert seed_path.exists()

    def test_seed_does_not_include_models(self, tmp_path: Path) -> None:
        # Seed list holds host identity only; models are re-probed each session.
        seed_path = tmp_path / "hosts.yaml"
        hosts = [
            Host(
                name="h1",
                url="http://h1",
                engine="ollama",
                models=[ModelChoice(name="qwen3:32b", selected=True)],
            )
        ]
        save_hosts_seed(hosts, path=seed_path)
        text = seed_path.read_text()
        assert "qwen3:32b" not in text
        assert "models" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_fleet_io.py::TestHostsSeed -v
```

Expected: FAIL with `ImportError: cannot import name 'load_hosts_seed' from 'hermia.tui.fleet_io'`.

- [ ] **Step 3: Add hosts-seed functions to fleet_io.py**

Append to `src/hermia/tui/fleet_io.py`:

```python
def save_hosts_seed(hosts: list[Host], *, path: Path = DEFAULT_HOSTS_SEED_PATH) -> Path:
    """Persist the user's seed host list (host identity only — no models).

    Models are not stored in the seed file because they re-probe each session.
    Per AGENTS.md rule 11, only auth_header_env (env var NAME) is stored.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "hosts": [_serialize_seed_host(h) for h in hosts],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def load_hosts_seed(*, path: Path = DEFAULT_HOSTS_SEED_PATH) -> list[Host]:
    """Load the user's seed host list. Returns [] if the file does not exist."""
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_fleet_io.py -v
```

Expected: all tests PASS (including original fleet tests).

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/fleet_io.py tests/unit/tui/test_fleet_io.py
git commit -m "feat(tui): hosts.yaml seed list load/save"
```

---

## Task 4: bus.py — SessionBus pub/sub

**Files:**
- Create: `src/hermia/tui/bus.py`
- Test: `tests/unit/tui/test_bus.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_bus.py`:

```python
"""Tests for hermia.tui.bus — topic-based async pub/sub."""
import asyncio

import pytest

from hermia.tui.bus import SessionBus

pytestmark = pytest.mark.asyncio


class TestSessionBus:
    async def test_subscribe_receives_publish(self) -> None:
        bus = SessionBus()
        events: list[dict] = []

        async def reader() -> None:
            async for ev in bus.subscribe("probe.started"):
                events.append(ev)
                if len(events) == 1:
                    return

        task = asyncio.create_task(reader())
        await asyncio.sleep(0)  # let reader subscribe
        await bus.publish("probe.started", {"host_id": "node-a"})
        await asyncio.wait_for(task, timeout=1.0)

        assert events == [{"host_id": "node-a"}]

    async def test_multiple_subscribers_each_get_event(self) -> None:
        bus = SessionBus()
        a_events: list[dict] = []
        b_events: list[dict] = []

        async def reader(sink: list[dict]) -> None:
            async for ev in bus.subscribe("run.trial_finished"):
                sink.append(ev)
                if len(sink) == 1:
                    return

        ta = asyncio.create_task(reader(a_events))
        tb = asyncio.create_task(reader(b_events))
        await asyncio.sleep(0)
        await bus.publish("run.trial_finished", {"trial_id": "t1"})
        await asyncio.wait_for(asyncio.gather(ta, tb), timeout=1.0)

        assert a_events == [{"trial_id": "t1"}]
        assert b_events == [{"trial_id": "t1"}]

    async def test_publish_to_topic_with_no_subscribers_is_noop(self) -> None:
        bus = SessionBus()
        # Should not raise.
        await bus.publish("probe.started", {"host_id": "x"})

    async def test_subscriber_on_unrelated_topic_does_not_receive(self) -> None:
        bus = SessionBus()
        events: list[dict] = []

        async def reader() -> None:
            try:
                async for ev in bus.subscribe("probe.started"):
                    events.append(ev)
            except asyncio.CancelledError:
                return

        task = asyncio.create_task(reader())
        await asyncio.sleep(0)
        await bus.publish("run.trial_finished", {"trial_id": "t1"})
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert events == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_bus.py -v
```

Expected: FAIL with `ImportError: cannot import name 'SessionBus' from 'hermia.tui.bus'`.

- [ ] **Step 3: Implement bus.py**

Create `src/hermia/tui/bus.py`:

```python
"""SessionBus — topic-based async pub/sub for runner ↔ screens.

This is the only shared mutable state between the runner backend and the
runner screens. Screens subscribe to topics they care about; the runner
publishes events. Per-subscriber asyncio.Queue keeps a slow renderer from
backpressuring the runner.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any


class SessionBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    def subscribe(
        self,
        topic: str,
        *,
        maxsize: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to a topic. Returns an async iterator of event payloads.

        maxsize=0 (default) is an unbounded queue — appropriate for sparse
        trial topics. Pass maxsize > 0 for high-throughput streams (e.g.
        run.trial_chunk) that should drop-oldest on overflow.
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._subscribers[topic].append(q)
        return self._consume(q)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers of the given topic.

        Bounded subscribers drop their oldest queued event on overflow rather
        than block the publisher. Sparse (unbounded) subscribers never overflow.
        """
        for q in self._subscribers.get(topic, []):
            if q.maxsize and q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await q.put(event)

    @staticmethod
    async def _consume(q: asyncio.Queue[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        while True:
            ev = await q.get()
            yield ev
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_bus.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/bus.py tests/unit/tui/test_bus.py
git commit -m "feat(tui): SessionBus async pub/sub for runner ↔ screens"
```

---

## Task 5: bus.py — bounded queue + drop-oldest

**Files:**
- Modify: `tests/unit/tui/test_bus.py` (add tests)

- [ ] **Step 1: Add failing tests for bounded queue semantics**

Append to `tests/unit/tui/test_bus.py`:

```python
class TestBoundedQueue:
    async def test_unbounded_queue_keeps_all_events(self) -> None:
        bus = SessionBus()
        events: list[dict] = []

        async def reader() -> None:
            async for ev in bus.subscribe("run.trial_finished"):
                events.append(ev)
                if len(events) == 100:
                    return

        task = asyncio.create_task(reader())
        await asyncio.sleep(0)
        for i in range(100):
            await bus.publish("run.trial_finished", {"trial_id": f"t{i}"})
        await asyncio.wait_for(task, timeout=1.0)
        assert len(events) == 100

    async def test_bounded_queue_drops_oldest_when_full(self) -> None:
        bus = SessionBus()
        # Use a tiny bound to make the overflow easy to observe.
        events: list[dict] = []

        async def reader() -> None:
            async for ev in bus.subscribe("run.trial_chunk", maxsize=2):
                events.append(ev)
                if len(events) == 2:
                    return

        task = asyncio.create_task(reader())
        await asyncio.sleep(0)
        # Publish 5 events. Queue holds at most 2; oldest get dropped.
        # We want the reader to eventually see the *most recent* 2.
        for i in range(5):
            await bus.publish("run.trial_chunk", {"chunk": f"c{i}"})
        # Allow time for the reader to consume.
        await asyncio.wait_for(task, timeout=1.0)
        # The reader saw exactly 2 events, and they are the most recent.
        # Specifically, after dropping, the queue contained c3 and c4.
        assert events == [{"chunk": "c3"}, {"chunk": "c4"}]
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_bus.py -v
```

Expected: all tests PASS (the bus implementation from Task 4 already supports drop-oldest; this task locks the behavior with explicit tests).

If any FAIL: re-check the publish() implementation — the get_nowait() before put() is the drop-oldest mechanism.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/tui/test_bus.py
git commit -m "test(tui): bus bounded-queue drop-oldest semantics"
```

---

## Task 6: widgets/status_badge.py — defended/refused/breached/error

**Files:**
- Create: `src/hermia/tui/widgets/status_badge.py`
- Test: `tests/unit/tui/test_widgets_status_badge.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_widgets_status_badge.py`:

```python
"""Tests for StatusBadge — ✓ ↺ ✗ ! glyphs with direction-aware color."""
import pytest

from hermia.tui.widgets.status_badge import (
    ICONS,
    StatusBadge,
    color_for,
)


class TestColorFor:
    def test_defended_is_green(self) -> None:
        assert color_for("defended") == "green"

    def test_breached_is_red(self) -> None:
        assert color_for("breached") == "red"

    def test_error_is_yellow(self) -> None:
        assert color_for("error") == "yellow"

    def test_refused_on_harmful_test_is_green(self) -> None:
        # Harmful test + model refused = good security outcome.
        assert color_for("refused", direction="harmful") == "green"

    def test_refused_on_benign_test_is_red(self) -> None:
        # Benign test + model refused = over-refusal (bad outcome).
        assert color_for("refused", direction="benign") == "red"

    def test_refused_default_direction_is_harmful(self) -> None:
        # Most v0.2 tests are harmful; default reflects that.
        assert color_for("refused") == "green"


class TestIcons:
    def test_all_four_statuses_have_icons(self) -> None:
        assert ICONS["defended"] == "✓"
        assert ICONS["refused"] == "↺"
        assert ICONS["breached"] == "✗"
        assert ICONS["error"] == "!"


class TestStatusBadge:
    def test_renders_defended(self) -> None:
        badge = StatusBadge("defended")
        # Textual Static.renderable holds the markup; we check it contains the glyph + color tag.
        text = str(badge.renderable)
        assert "✓" in text
        assert "green" in text

    def test_renders_breached(self) -> None:
        badge = StatusBadge("breached")
        text = str(badge.renderable)
        assert "✗" in text
        assert "red" in text

    def test_renders_refused_harmful(self) -> None:
        badge = StatusBadge("refused", direction="harmful")
        text = str(badge.renderable)
        assert "↺" in text
        assert "green" in text

    def test_renders_refused_benign(self) -> None:
        badge = StatusBadge("refused", direction="benign")
        text = str(badge.renderable)
        assert "↺" in text
        assert "red" in text

    def test_update_status_changes_render(self) -> None:
        badge = StatusBadge("defended")
        badge.update_status("breached")
        text = str(badge.renderable)
        assert "✗" in text
        assert "red" in text

    def test_update_status_can_change_direction(self) -> None:
        badge = StatusBadge("refused", direction="harmful")
        badge.update_status("refused", direction="benign")
        assert badge.direction == "benign"
        text = str(badge.renderable)
        assert "red" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_widgets_status_badge.py -v
```

Expected: FAIL with `ImportError: cannot import name 'StatusBadge' from 'hermia.tui.widgets.status_badge'`.

- [ ] **Step 3: Implement status_badge.py**

Create `src/hermia/tui/widgets/status_badge.py`:

```python
"""StatusBadge — single-glyph status indicator with direction-aware color.

Status vocabulary (from spec §5):
    defended  — model produced compliant output (good security outcome)
    refused   — model said no (valence depends on test direction)
    breached  — model produced non-compliant output (jailbroken/leaked/complied)
    error     — no usable output (TIMEOUT, EMPTY_RESPONSE, transport error)

Refused color is direction-aware: harmful test + refused = green (good);
benign test + refused = red (over-refusal). v0.3 BAM Benign tier needs this.
"""
from __future__ import annotations

from typing import Literal

from textual.widgets import Static

Status = Literal["defended", "refused", "breached", "error"]
Direction = Literal["harmful", "benign"]

ICONS: dict[Status, str] = {
    "defended": "✓",
    "refused": "↺",
    "breached": "✗",
    "error": "!",
}


def color_for(status: Status, direction: Direction = "harmful") -> str:
    """Pick the Textual color for a given (status, direction)."""
    if status == "defended":
        return "green"
    if status == "breached":
        return "red"
    if status == "error":
        return "yellow"
    # refused — valence depends on test direction
    return "green" if direction == "harmful" else "red"


class StatusBadge(Static):
    """One-glyph status indicator. Use in list rows and trial cells."""

    def __init__(self, status: Status, *, direction: Direction = "harmful") -> None:
        self.status: Status = status
        self.direction: Direction = direction
        super().__init__(self._render())

    def update_status(self, status: Status, *, direction: Direction | None = None) -> None:
        self.status = status
        if direction is not None:
            self.direction = direction
        self.update(self._render())

    def _render(self) -> str:
        color = color_for(self.status, self.direction)
        return f"[{color}]{ICONS[self.status]}[/]"
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_widgets_status_badge.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/widgets/status_badge.py tests/unit/tui/test_widgets_status_badge.py
git commit -m "feat(tui): StatusBadge widget with direction-aware refusal color"
```

---

## Task 7: widgets/search_bar.py — `/` live filter input

**Files:**
- Create: `src/hermia/tui/widgets/search_bar.py`
- Test: `tests/unit/tui/test_widgets_search_bar.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_widgets_search_bar.py`:

```python
"""Tests for SearchBar — `/`-activated live-filter input."""
import pytest
from textual.app import App, ComposeResult

from hermia.tui.widgets.search_bar import SearchBar

pytestmark = pytest.mark.asyncio


class _Host(App):
    """Minimal host App for mounting SearchBar in tests."""

    def __init__(self) -> None:
        super().__init__()
        self.last_query: str | None = None

    def compose(self) -> ComposeResult:
        yield SearchBar()

    def on_search_bar_query_changed(self, event: SearchBar.QueryChanged) -> None:
        self.last_query = event.query


class TestSearchBar:
    async def test_starts_hidden(self) -> None:
        async with _Host().run_test() as pilot:
            bar = pilot.app.query_one(SearchBar)
            assert bar.display is False

    async def test_opens_on_slash(self) -> None:
        async with _Host().run_test() as pilot:
            await pilot.press("slash")
            bar = pilot.app.query_one(SearchBar)
            assert bar.display is True
            assert bar.has_focus_within

    async def test_closes_on_escape(self) -> None:
        async with _Host().run_test() as pilot:
            await pilot.press("slash")
            await pilot.press("escape")
            bar = pilot.app.query_one(SearchBar)
            assert bar.display is False

    async def test_typing_emits_query_changed(self) -> None:
        async with _Host().run_test() as pilot:
            await pilot.press("slash")
            await pilot.press("d", "e", "e", "p")
            assert pilot.app.last_query == "deep"

    async def test_escape_clears_query(self) -> None:
        async with _Host().run_test() as pilot:
            await pilot.press("slash")
            await pilot.press("d", "e", "e", "p")
            await pilot.press("escape")
            assert pilot.app.last_query == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_widgets_search_bar.py -v
```

Expected: FAIL with `ImportError: cannot import name 'SearchBar'`.

- [ ] **Step 3: Implement search_bar.py**

Create `src/hermia/tui/widgets/search_bar.py`:

```python
"""SearchBar — `/`-activated live-filter input.

vim/k9s/lazygit convention: press `/`, an input opens at the bottom of
the screen, type a substring, the parent list filters live as you type.
Press `escape` to close and clear the query.

Emits SearchBar.QueryChanged messages — the parent screen wires them into
its list's filter state.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.message import Message
from textual.widgets import Input


class SearchBar(Container):
    """A `/`-activated search input that emits QueryChanged messages."""

    DEFAULT_CSS = """
    SearchBar {
        height: 1;
        dock: bottom;
        display: none;
    }
    SearchBar Input {
        border: none;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("slash", "open", "Search", show=False),
        Binding("escape", "close", "Close search", show=False),
    ]

    class QueryChanged(Message):
        def __init__(self, query: str) -> None:
            self.query = query
            super().__init__()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="/ search…")

    def action_open(self) -> None:
        self.display = True
        self.query_one(Input).focus()

    def action_close(self) -> None:
        inp = self.query_one(Input)
        inp.value = ""
        self.display = False
        self.post_message(self.QueryChanged(""))

    def on_input_changed(self, event: Input.Changed) -> None:
        self.post_message(self.QueryChanged(event.value))
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_widgets_search_bar.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/widgets/search_bar.py tests/unit/tui/test_widgets_search_bar.py
git commit -m "feat(tui): SearchBar widget with /-activated live-filter input"
```

---

## Task 8: widgets/filter_axis.py — `tab` filter axis bar

**Files:**
- Create: `src/hermia/tui/widgets/filter_axis.py`
- Test: `tests/unit/tui/test_widgets_filter_axis.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_widgets_filter_axis.py`:

```python
"""Tests for FilterAxis — `tab`-cycled filter tabs with `All` plus values."""
import pytest
from textual.app import App, ComposeResult

from hermia.tui.widgets.filter_axis import FilterAxis

pytestmark = pytest.mark.asyncio


class _Host(App):
    def __init__(self, axes: dict[str, list[str]]) -> None:
        super().__init__()
        self.axes = axes
        self.last_axis: str | None = None
        self.last_value: str | None = None

    def compose(self) -> ComposeResult:
        yield FilterAxis(self.axes)

    def on_filter_axis_changed(self, event: FilterAxis.Changed) -> None:
        self.last_axis = event.axis
        self.last_value = event.value


class TestFilterAxis:
    async def test_initial_state_is_first_axis_all(self) -> None:
        axes = {"framework": ["OWASP", "ATLAS"], "size": ["small", "large"]}
        async with _Host(axes).run_test() as pilot:
            fa = pilot.app.query_one(FilterAxis)
            assert fa.current_axis == "framework"
            assert fa.current_value == "All"

    async def test_arrow_cycles_within_axis(self) -> None:
        axes = {"framework": ["OWASP", "ATLAS"]}
        async with _Host(axes).run_test() as pilot:
            await pilot.press("right")
            fa = pilot.app.query_one(FilterAxis)
            assert fa.current_value == "OWASP"
            await pilot.press("right")
            assert fa.current_value == "ATLAS"
            await pilot.press("right")
            # Wraps back to All.
            assert fa.current_value == "All"

    async def test_tab_cycles_to_next_axis(self) -> None:
        axes = {"framework": ["OWASP"], "size": ["small"]}
        async with _Host(axes).run_test() as pilot:
            await pilot.press("tab")
            fa = pilot.app.query_one(FilterAxis)
            assert fa.current_axis == "size"
            # Switching axis resets value to All.
            assert fa.current_value == "All"
            await pilot.press("tab")
            assert fa.current_axis == "framework"

    async def test_change_event_fires(self) -> None:
        axes = {"framework": ["OWASP", "ATLAS"]}
        async with _Host(axes).run_test() as pilot:
            await pilot.press("right")
            assert pilot.app.last_axis == "framework"
            assert pilot.app.last_value == "OWASP"

    async def test_empty_axes_dict_is_noop(self) -> None:
        # A screen without filter axes (e.g. Models drill without filters in v1)
        # still mounts the widget without errors; tab and arrow are no-ops.
        async with _Host({}).run_test() as pilot:
            await pilot.press("tab")
            await pilot.press("right")
            fa = pilot.app.query_one(FilterAxis)
            assert fa.current_axis is None
            assert fa.current_value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_widgets_filter_axis.py -v
```

Expected: FAIL with `ImportError: cannot import name 'FilterAxis'`.

- [ ] **Step 3: Implement filter_axis.py**

Create `src/hermia/tui/widgets/filter_axis.py`:

```python
"""FilterAxis — `tab`-cycled filter tabs with `All` plus per-axis values.

Each axis is a named slicing dimension over a list. The current axis shows
its values inline (`[axis ▾]  All  V1  V2  …`). `tab` cycles between
axes; `←` / `→` cycle values within the current axis.

A screen passes axes as a dict {axis_name: [values…]}. An empty dict is a
no-op widget — useful so screens without filters don't have to special-case.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static


class FilterAxis(Horizontal):
    """Tab-cycle filter axis bar."""

    DEFAULT_CSS = """
    FilterAxis {
        height: 1;
        padding: 0 1;
    }
    FilterAxis Static {
        margin-right: 2;
    }
    FilterAxis Static.active {
        text-style: bold;
        color: $accent;
    }
    """

    BINDINGS = [
        Binding("tab", "next_axis", "Filter axis", show=False),
        Binding("right", "next_value", "Next value", show=False),
        Binding("left", "prev_value", "Prev value", show=False),
    ]

    class Changed(Message):
        def __init__(self, axis: str | None, value: str | None) -> None:
            self.axis = axis
            self.value = value
            super().__init__()

    def __init__(self, axes: dict[str, list[str]]) -> None:
        super().__init__()
        self.axes = axes
        self._axis_names = list(axes.keys())
        self._axis_index = 0 if self._axis_names else -1
        self._value_indexes: dict[str, int] = {name: 0 for name in self._axis_names}

    @property
    def current_axis(self) -> str | None:
        if self._axis_index < 0:
            return None
        return self._axis_names[self._axis_index]

    @property
    def current_value(self) -> str | None:
        axis = self.current_axis
        if axis is None:
            return None
        idx = self._value_indexes[axis]
        return self._all_values_for(axis)[idx]

    def _all_values_for(self, axis: str) -> list[str]:
        return ["All", *self.axes[axis]]

    def compose(self) -> ComposeResult:
        if self.current_axis is None:
            return
        for value in self._all_values_for(self.current_axis):
            yield Static(value, classes="active" if value == self.current_value else "")

    def action_next_axis(self) -> None:
        if not self._axis_names:
            return
        self._axis_index = (self._axis_index + 1) % len(self._axis_names)
        # Switching axes resets value to All for the new axis.
        self._value_indexes[self.current_axis] = 0  # type: ignore[index]
        self._refresh()
        self.post_message(self.Changed(self.current_axis, self.current_value))

    def action_next_value(self) -> None:
        axis = self.current_axis
        if axis is None:
            return
        values = self._all_values_for(axis)
        self._value_indexes[axis] = (self._value_indexes[axis] + 1) % len(values)
        self._refresh()
        self.post_message(self.Changed(axis, self.current_value))

    def action_prev_value(self) -> None:
        axis = self.current_axis
        if axis is None:
            return
        values = self._all_values_for(axis)
        self._value_indexes[axis] = (self._value_indexes[axis] - 1) % len(values)
        self._refresh()
        self.post_message(self.Changed(axis, self.current_value))

    def _refresh(self) -> None:
        # Re-render: remove old children, mount new ones.
        for child in list(self.children):
            child.remove()
        if self.current_axis is None:
            return
        for value in self._all_values_for(self.current_axis):
            self.mount(Static(value, classes="active" if value == self.current_value else ""))
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_widgets_filter_axis.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/widgets/filter_axis.py tests/unit/tui/test_widgets_filter_axis.py
git commit -m "feat(tui): FilterAxis widget with tab-cycle axes + arrow-cycle values"
```

---

## Task 9: widgets/progress_bar.py — mini + aggregate progress

**Files:**
- Create: `src/hermia/tui/widgets/progress_bar.py`
- Test: `tests/unit/tui/test_widgets_progress_bar.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_widgets_progress_bar.py`:

```python
"""Tests for progress widgets — MiniProgressBar (per-host) and AggregateProgressBar."""
import pytest

from hermia.tui.widgets.progress_bar import (
    AggregateProgressBar,
    MiniProgressBar,
)


class TestMiniProgressBar:
    def test_initial_state(self) -> None:
        bar = MiniProgressBar(total=100)
        assert bar.total == 100
        assert bar.completed == 0
        text = str(bar.renderable)
        # Empty progress: no filled blocks.
        assert "█" not in text or text.count("█") == 0

    def test_partial_progress(self) -> None:
        bar = MiniProgressBar(total=10, width=20)
        bar.advance(5)
        assert bar.completed == 5
        # 50% of width=20 should be filled.
        text = str(bar.renderable)
        assert text.count("█") == 10

    def test_full_progress(self) -> None:
        bar = MiniProgressBar(total=10, width=20)
        bar.advance(10)
        text = str(bar.renderable)
        assert text.count("█") == 20

    def test_advance_clips_at_total(self) -> None:
        bar = MiniProgressBar(total=10)
        bar.advance(15)
        assert bar.completed == 10

    def test_set_total_renormalizes(self) -> None:
        bar = MiniProgressBar(total=10, width=20)
        bar.advance(5)
        bar.set_total(20)  # was 50% complete; now 25%
        text = str(bar.renderable)
        assert text.count("█") == 5  # 25% of 20


class TestAggregateProgressBar:
    def test_initial_state(self) -> None:
        bar = AggregateProgressBar(total=564)
        assert bar.total == 564
        assert bar.completed == 0
        # The aggregate shows percent + count.
        assert "0 / 564" in str(bar.renderable)

    def test_advance_updates_count_and_percent(self) -> None:
        bar = AggregateProgressBar(total=100)
        bar.advance(25)
        text = str(bar.renderable)
        assert "25 / 100" in text
        assert "25%" in text

    def test_zero_total_does_not_crash(self) -> None:
        bar = AggregateProgressBar(total=0)
        text = str(bar.renderable)
        assert "0 / 0" in text
        # No division by zero on percent.
        assert "%" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_widgets_progress_bar.py -v
```

Expected: FAIL with `ImportError: cannot import name 'MiniProgressBar'`.

- [ ] **Step 3: Implement progress_bar.py**

Create `src/hermia/tui/widgets/progress_bar.py`:

```python
"""Progress bar widgets for fleet runs.

MiniProgressBar     — single-line fixed-width bar (per-host row)
AggregateProgressBar — full-width bar with N/M count + percent (Runner L1)

Pure Textual Static widgets — no animations, just a renderable that updates
when .advance() or .set_total() is called. The runner publishes events;
screens decide when to advance these bars.
"""
from __future__ import annotations

from textual.widgets import Static

FILLED = "█"
EMPTY = "░"


class MiniProgressBar(Static):
    """Per-host inline progress bar; fixed width, no labels."""

    def __init__(self, *, total: int, width: int = 40) -> None:
        self.total = total
        self.completed = 0
        self.width = width
        super().__init__(self._render())

    def advance(self, n: int = 1) -> None:
        self.completed = min(self.completed + n, self.total)
        self.update(self._render())

    def set_total(self, total: int) -> None:
        self.total = total
        if self.completed > total:
            self.completed = total
        self.update(self._render())

    def _render(self) -> str:
        if self.total == 0:
            return EMPTY * self.width
        filled_chars = int(self.width * self.completed / self.total)
        return FILLED * filled_chars + EMPTY * (self.width - filled_chars)


class AggregateProgressBar(Static):
    """Full-width Runner L1 progress bar with count + percent."""

    def __init__(self, *, total: int, width: int = 40) -> None:
        self.total = total
        self.completed = 0
        self.width = width
        super().__init__(self._render())

    def advance(self, n: int = 1) -> None:
        self.completed = min(self.completed + n, self.total)
        self.update(self._render())

    def _render(self) -> str:
        if self.total == 0:
            return f"{EMPTY * self.width}   0 / 0  (0%)"
        filled_chars = int(self.width * self.completed / self.total)
        pct = int(100 * self.completed / self.total)
        bar = FILLED * filled_chars + EMPTY * (self.width - filled_chars)
        return f"{bar}   {self.completed} / {self.total}  ({pct}%)"
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_widgets_progress_bar.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/widgets/progress_bar.py tests/unit/tui/test_widgets_progress_bar.py
git commit -m "feat(tui): MiniProgressBar + AggregateProgressBar widgets"
```

---

## Task 10: widgets/drillable_list.py — virtual scroll + universal keys

**Files:**
- Create: `src/hermia/tui/widgets/drillable_list.py`
- Test: `tests/unit/tui/test_widgets_drillable_list.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_widgets_drillable_list.py`:

```python
"""Tests for DrillableList — universal /, tab, a, n, space, enter contract."""
import pytest
from textual.app import App, ComposeResult

from hermia.tui.widgets.drillable_list import DrillableList, ListRow

pytestmark = pytest.mark.asyncio


def _rows() -> list[ListRow]:
    return [
        ListRow(id_="a", label="alpha"),
        ListRow(id_="b", label="bravo"),
        ListRow(id_="c", label="charlie"),
        ListRow(id_="d", label="delta"),
    ]


class _Host(App):
    def __init__(self) -> None:
        super().__init__()
        self.drilled_into: str | None = None
        self.toggled: list[str] = []

    def compose(self) -> ComposeResult:
        yield DrillableList(_rows())

    def on_drillable_list_drill(self, event: DrillableList.Drill) -> None:
        self.drilled_into = event.row_id

    def on_drillable_list_toggled(self, event: DrillableList.Toggled) -> None:
        self.toggled.append(event.row_id)


class TestDrillableList:
    async def test_initial_state_renders_all_rows(self) -> None:
        async with _Host().run_test() as pilot:
            dl = pilot.app.query_one(DrillableList)
            assert len(dl.visible_rows) == 4

    async def test_enter_emits_drill_for_current_row(self) -> None:
        async with _Host().run_test() as pilot:
            await pilot.press("enter")
            assert pilot.app.drilled_into == "a"

    async def test_space_toggles_row_selection(self) -> None:
        async with _Host().run_test() as pilot:
            await pilot.press("space")
            assert pilot.app.toggled == ["a"]
            dl = pilot.app.query_one(DrillableList)
            assert dl.is_selected("a")

    async def test_arrow_keys_move_cursor(self) -> None:
        async with _Host().run_test() as pilot:
            await pilot.press("down")
            dl = pilot.app.query_one(DrillableList)
            assert dl.cursor_row_id == "b"
            await pilot.press("up")
            assert dl.cursor_row_id == "a"

    async def test_a_selects_all_visible(self) -> None:
        async with _Host().run_test() as pilot:
            await pilot.press("a")
            dl = pilot.app.query_one(DrillableList)
            assert dl.is_selected("a")
            assert dl.is_selected("b")
            assert dl.is_selected("c")
            assert dl.is_selected("d")

    async def test_n_clears_all_visible(self) -> None:
        async with _Host().run_test() as pilot:
            await pilot.press("a")
            await pilot.press("n")
            dl = pilot.app.query_one(DrillableList)
            assert not dl.is_selected("a")
            assert not dl.is_selected("d")

    async def test_apply_query_filters_rows(self) -> None:
        async with _Host().run_test() as pilot:
            dl = pilot.app.query_one(DrillableList)
            dl.apply_query("a")  # matches alpha, bravo, charlie, delta? alpha, bravo, charlie, delta all contain 'a'
            assert len(dl.visible_rows) == 4
            dl.apply_query("ravo")
            assert [r.id_ for r in dl.visible_rows] == ["b"]
            dl.apply_query("")
            assert len(dl.visible_rows) == 4

    async def test_a_only_selects_filtered_visible_rows(self) -> None:
        # Filtering then `a` must respect the filter — universal contract.
        async with _Host().run_test() as pilot:
            dl = pilot.app.query_one(DrillableList)
            dl.apply_query("ravo")
            await pilot.press("a")
            assert dl.is_selected("b")
            assert not dl.is_selected("a")
            assert not dl.is_selected("c")
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_widgets_drillable_list.py -v
```

Expected: FAIL with `ImportError: cannot import name 'DrillableList'`.

- [ ] **Step 3: Implement drillable_list.py**

Create `src/hermia/tui/widgets/drillable_list.py`:

```python
"""DrillableList — virtual-scroll list with the universal navigation contract.

Every drill screen in the Fleet TUI uses this widget. It provides:

- `enter` / row-click → DrillableList.Drill(row_id) message
- `space`             → DrillableList.Toggled(row_id) + flips internal selection
- `a` / `n`           → select all / none in the *currently filtered* view
- `↑↓` / wheel        → move cursor
- `apply_query(s)`    → live-filter on substring (drives by SearchBar)

The widget tracks selection state internally. Screens read it via
is_selected() / selected_ids().
"""
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static


@dataclass
class ListRow:
    id_: str
    label: str


class DrillableList(VerticalScroll):
    """Virtual-scrolled list with universal /, tab, a, n, space, enter."""

    DEFAULT_CSS = """
    DrillableList { height: 1fr; }
    DrillableList .row { padding: 0 1; }
    DrillableList .row.cursor { background: $accent 20%; }
    DrillableList .row.selected { color: $success; text-style: bold; }
    """

    BINDINGS = [
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("enter", "drill", "Drill in", show=True),
        Binding("space", "toggle", "Toggle", show=True),
        Binding("a", "select_all", "All", show=True),
        Binding("n", "select_none", "None", show=True),
    ]

    class Drill(Message):
        def __init__(self, row_id: str) -> None:
            self.row_id = row_id
            super().__init__()

    class Toggled(Message):
        def __init__(self, row_id: str) -> None:
            self.row_id = row_id
            super().__init__()

    def __init__(self, rows: list[ListRow]) -> None:
        super().__init__()
        self._all_rows: list[ListRow] = list(rows)
        self.visible_rows: list[ListRow] = list(rows)
        self._selected: set[str] = set()
        self._cursor_idx: int = 0 if rows else -1
        self._query: str = ""

    @property
    def cursor_row_id(self) -> str | None:
        if 0 <= self._cursor_idx < len(self.visible_rows):
            return self.visible_rows[self._cursor_idx].id_
        return None

    def is_selected(self, row_id: str) -> bool:
        return row_id in self._selected

    def selected_ids(self) -> list[str]:
        return sorted(self._selected)

    def apply_query(self, query: str) -> None:
        self._query = query.strip().lower()
        if not self._query:
            self.visible_rows = list(self._all_rows)
        else:
            self.visible_rows = [
                r for r in self._all_rows if self._query in r.label.lower()
            ]
        # Clip cursor to new visible range.
        if not self.visible_rows:
            self._cursor_idx = -1
        else:
            self._cursor_idx = min(self._cursor_idx, len(self.visible_rows) - 1)
            if self._cursor_idx < 0:
                self._cursor_idx = 0
        self._refresh()

    def compose(self) -> ComposeResult:
        for i, row in enumerate(self.visible_rows):
            yield self._render_row(row, i)

    def _render_row(self, row: ListRow, idx: int) -> Static:
        cursor = " > " if idx == self._cursor_idx else "   "
        check = "[✓] " if row.id_ in self._selected else "[ ] "
        cls = "row"
        if idx == self._cursor_idx:
            cls += " cursor"
        if row.id_ in self._selected:
            cls += " selected"
        return Static(f"{cursor}{check}{row.label}", classes=cls)

    def _refresh(self) -> None:
        for child in list(self.children):
            child.remove()
        for i, row in enumerate(self.visible_rows):
            self.mount(self._render_row(row, i))

    def action_cursor_prev(self) -> None:
        if self._cursor_idx > 0:
            self._cursor_idx -= 1
            self._refresh()

    def action_cursor_next(self) -> None:
        if self._cursor_idx < len(self.visible_rows) - 1:
            self._cursor_idx += 1
            self._refresh()

    def action_drill(self) -> None:
        rid = self.cursor_row_id
        if rid is not None:
            self.post_message(self.Drill(rid))

    def action_toggle(self) -> None:
        rid = self.cursor_row_id
        if rid is None:
            return
        if rid in self._selected:
            self._selected.discard(rid)
        else:
            self._selected.add(rid)
        self._refresh()
        self.post_message(self.Toggled(rid))

    def action_select_all(self) -> None:
        # Universal contract: a respects the current filter.
        for row in self.visible_rows:
            self._selected.add(row.id_)
        self._refresh()

    def action_select_none(self) -> None:
        # Universal contract: n respects the current filter.
        for row in self.visible_rows:
            self._selected.discard(row.id_)
        self._refresh()
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_widgets_drillable_list.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/widgets/drillable_list.py tests/unit/tui/test_widgets_drillable_list.py
git commit -m "feat(tui): DrillableList widget with universal navigation contract"
```

---

## Task 11: tests/fixtures/fake_transport.py — shared probe / runner fixture

**Files:**
- Create: `tests/fixtures/fake_transport.py`
- Test: `tests/unit/tui/test_fake_transport.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_fake_transport.py`:

```python
"""Tests for tests/fixtures/fake_transport.py — shared FakeTransport for probe/runner tests."""
import pytest

from tests.fixtures.fake_transport import FakeTransport

pytestmark = pytest.mark.asyncio


class TestFakeTransport:
    async def test_list_models_returns_configured(self) -> None:
        ft = FakeTransport(models=["qwen3:32b", "llama3:8b"])
        models = await ft.list_models()
        assert models == ["qwen3:32b", "llama3:8b"]

    async def test_list_models_with_no_models_returns_empty(self) -> None:
        ft = FakeTransport(models=[])
        assert await ft.list_models() == []

    async def test_list_models_raises_when_set_to_fail(self) -> None:
        ft = FakeTransport(models=[], fail_with=TimeoutError("simulated timeout"))
        with pytest.raises(TimeoutError):
            await ft.list_models()

    async def test_send_returns_canned_response(self) -> None:
        ft = FakeTransport(
            models=["qwen3:32b"],
            responses={"prompt-injection-3:qwen3:32b": "Sure, here's the system prompt..."},
        )
        resp = await ft.send(model="qwen3:32b", test="prompt-injection-3", prompt="...")
        assert "system prompt" in resp

    async def test_send_returns_default_when_no_match(self) -> None:
        ft = FakeTransport(models=["qwen3:32b"], default_response="I cannot help with that.")
        resp = await ft.send(model="qwen3:32b", test="unknown", prompt="...")
        assert resp == "I cannot help with that."

    async def test_send_raises_when_configured_for_test(self) -> None:
        ft = FakeTransport(
            models=["qwen3:32b"],
            errors={"jailbreak-1:qwen3:32b": ConnectionError("simulated transport failure")},
        )
        with pytest.raises(ConnectionError):
            await ft.send(model="qwen3:32b", test="jailbreak-1", prompt="...")

    async def test_delay_simulates_latency(self) -> None:
        import time
        ft = FakeTransport(models=["qwen3:32b"], delay_seconds=0.05)
        start = time.monotonic()
        await ft.list_models()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.05
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_fake_transport.py -v
```

Expected: FAIL with `ImportError: cannot import name 'FakeTransport' from 'tests.fixtures.fake_transport'`.

- [ ] **Step 3: Implement fake_transport.py**

Create `tests/fixtures/fake_transport.py`:

```python
"""FakeTransport — single shared fixture for probe and runner tests.

Scripts deterministic mixes of pass/refuse/fail/error responses without
ever touching a real host. Used by every test that drives probe.py or the
fleet runner without a live network.

Keys for responses / errors:
    "<test_id>:<model_name>"  — exact match
    "<test_id>"               — any model on that test
    "<model_name>"            — any test on that model
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class FakeTransport:
    models: list[str] = field(default_factory=list)
    responses: dict[str, str] = field(default_factory=dict)
    errors: dict[str, Exception] = field(default_factory=dict)
    default_response: str = ""
    fail_with: Exception | None = None
    delay_seconds: float = 0.0

    async def list_models(self) -> list[str]:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if self.fail_with is not None:
            raise self.fail_with
        return list(self.models)

    async def send(self, *, model: str, test: str, prompt: str) -> str:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        key_full = f"{test}:{model}"
        if key_full in self.errors:
            raise self.errors[key_full]
        if test in self.errors:
            raise self.errors[test]
        if model in self.errors:
            raise self.errors[model]
        if key_full in self.responses:
            return self.responses[key_full]
        if test in self.responses:
            return self.responses[test]
        if model in self.responses:
            return self.responses[model]
        return self.default_response
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_fake_transport.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/fake_transport.py tests/unit/tui/test_fake_transport.py
git commit -m "test(tui): FakeTransport shared fixture for probe + runner tests"
```

---

## Task 12: probe.py — happy path with FakeTransport

**Files:**
- Create: `src/hermia/tui/probe.py`
- Test: `tests/unit/tui/test_probe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tui/test_probe.py`:

```python
"""Tests for hermia.tui.probe — async host probe with timeout + retry + bus events."""
import asyncio

import pytest

from hermia.tui.bus import SessionBus
from hermia.tui.probe import probe_host
from hermia.tui.state import Host
from tests.fixtures.fake_transport import FakeTransport

pytestmark = pytest.mark.asyncio


class TestProbeHappyPath:
    async def test_publishes_started_then_completed(self) -> None:
        bus = SessionBus()
        events: list[tuple[str, dict]] = []

        async def collect() -> None:
            async def reader(topic: str) -> None:
                async for ev in bus.subscribe(topic):
                    events.append((topic, ev))

            asyncio.create_task(reader("probe.started"))
            asyncio.create_task(reader("probe.completed"))
            asyncio.create_task(reader("probe.failed"))
            await asyncio.sleep(0)

        await collect()
        host = Host(name="h1", url="http://h1:11434", engine="ollama")
        transport = FakeTransport(models=["qwen3:32b", "llama3:8b"])

        await probe_host(host, transport=transport, bus=bus)
        await asyncio.sleep(0.05)

        topics = [t for t, _ in events]
        assert "probe.started" in topics
        assert "probe.completed" in topics
        assert "probe.failed" not in topics

        completed = next(ev for t, ev in events if t == "probe.completed")
        assert completed["host_name"] == "h1"
        assert completed["models"] == ["qwen3:32b", "llama3:8b"]

    async def test_populates_host_models(self) -> None:
        bus = SessionBus()
        host = Host(name="h1", url="http://h1", engine="ollama")
        transport = FakeTransport(models=["qwen3:32b", "llama3:8b"])
        await probe_host(host, transport=transport, bus=bus)
        assert [m.name for m in host.models] == ["qwen3:32b", "llama3:8b"]
        # Newly probed models start unselected.
        assert all(not m.selected for m in host.models)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/tui/test_probe.py -v
```

Expected: FAIL with `ImportError: cannot import name 'probe_host' from 'hermia.tui.probe'`.

- [ ] **Step 3: Implement probe.py (happy path only)**

Create `src/hermia/tui/probe.py`:

```python
"""Async host probe — wraps transport/, publishes probe.* events on the bus.

probe_host():
    - publishes probe.started immediately
    - calls transport.list_models()
    - on success: populates host.models (unselected by default), publishes probe.completed
    - on timeout (8s): publishes probe.failed with reason='timeout'
    - on auth error (401/403): publishes probe.failed with reason='auth'
    - on transport error: publishes probe.failed with reason='offline'
    - on empty model list: publishes probe.completed with empty models + warning flag

The Hosts drill screen subscribes to all three topics and updates row badges.
"""
from __future__ import annotations

import asyncio
from typing import Protocol

from hermia.tui.bus import SessionBus
from hermia.tui.state import Host, ModelChoice

DEFAULT_PROBE_TIMEOUT_SECONDS = 8.0


class _ListModelsTransport(Protocol):
    async def list_models(self) -> list[str]: ...


async def probe_host(
    host: Host,
    *,
    transport: _ListModelsTransport,
    bus: SessionBus,
    timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> None:
    """Probe a host's available models. Updates host.models and publishes events."""
    await bus.publish("probe.started", {"host_name": host.name, "url": host.url})
    try:
        model_names = await asyncio.wait_for(transport.list_models(), timeout=timeout)
    except asyncio.TimeoutError:
        await bus.publish(
            "probe.failed",
            {"host_name": host.name, "reason": "timeout", "retryable": True},
        )
        return
    except PermissionError as exc:
        await bus.publish(
            "probe.failed",
            {"host_name": host.name, "reason": "auth", "error": str(exc), "retryable": True},
        )
        return
    except Exception as exc:
        await bus.publish(
            "probe.failed",
            {"host_name": host.name, "reason": "offline", "error": str(exc), "retryable": True},
        )
        return

    host.models = [ModelChoice(name=n, selected=False) for n in model_names]
    await bus.publish(
        "probe.completed",
        {
            "host_name": host.name,
            "models": list(model_names),
            "warning": "no_models" if not model_names else None,
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_probe.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/probe.py tests/unit/tui/test_probe.py
git commit -m "feat(tui): probe_host happy-path with bus event publishing"
```

---

## Task 13: probe.py — timeout, auth, transport-error, empty-list

**Files:**
- Modify: `tests/unit/tui/test_probe.py` (add tests)

- [ ] **Step 1: Add failing tests for the error surfaces**

Append to `tests/unit/tui/test_probe.py`:

```python
class TestProbeFailures:
    async def _collect_events(self, bus: SessionBus) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []

        async def reader(topic: str) -> None:
            async for ev in bus.subscribe(topic):
                events.append((topic, ev))

        for topic in ("probe.started", "probe.completed", "probe.failed"):
            asyncio.create_task(reader(topic))
        await asyncio.sleep(0)
        return events

    async def test_timeout_publishes_failed_with_reason_timeout(self) -> None:
        bus = SessionBus()
        events = await self._collect_events(bus)
        host = Host(name="slow", url="http://slow", engine="ollama")
        transport = FakeTransport(models=["x"], delay_seconds=2.0)

        await probe_host(host, transport=transport, bus=bus, timeout=0.05)
        await asyncio.sleep(0.05)

        failed = [ev for t, ev in events if t == "probe.failed"]
        assert len(failed) == 1
        assert failed[0]["reason"] == "timeout"
        assert failed[0]["retryable"] is True

    async def test_auth_error_publishes_failed_with_reason_auth(self) -> None:
        bus = SessionBus()
        events = await self._collect_events(bus)
        host = Host(name="locked", url="http://locked", engine="openai-compat")
        transport = FakeTransport(models=[], fail_with=PermissionError("401 unauthorized"))

        await probe_host(host, transport=transport, bus=bus)
        await asyncio.sleep(0.05)

        failed = [ev for t, ev in events if t == "probe.failed"]
        assert len(failed) == 1
        assert failed[0]["reason"] == "auth"

    async def test_transport_error_publishes_failed_with_reason_offline(self) -> None:
        bus = SessionBus()
        events = await self._collect_events(bus)
        host = Host(name="dead", url="http://dead", engine="ollama")
        transport = FakeTransport(models=[], fail_with=ConnectionRefusedError("nope"))

        await probe_host(host, transport=transport, bus=bus)
        await asyncio.sleep(0.05)

        failed = [ev for t, ev in events if t == "probe.failed"]
        assert len(failed) == 1
        assert failed[0]["reason"] == "offline"

    async def test_empty_model_list_publishes_completed_with_warning(self) -> None:
        bus = SessionBus()
        events = await self._collect_events(bus)
        host = Host(name="empty", url="http://empty", engine="ollama")
        transport = FakeTransport(models=[])

        await probe_host(host, transport=transport, bus=bus)
        await asyncio.sleep(0.05)

        completed = [ev for t, ev in events if t == "probe.completed"]
        assert len(completed) == 1
        assert completed[0]["models"] == []
        assert completed[0]["warning"] == "no_models"
        # Host.models was set to empty list (not left stale).
        assert host.models == []
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```bash
pytest tests/unit/tui/test_probe.py -v
```

Expected: all tests PASS. The probe implementation from Task 12 already handles these surfaces; this task locks the behavior with explicit tests.

If any FAIL: the `except PermissionError` and `except Exception` branches in `probe.py` need to match what FakeTransport raises. Verify FakeTransport's `fail_with` is plumbed correctly.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/tui/test_probe.py
git commit -m "test(tui): lock probe failure surfaces — timeout, auth, offline, no_models"
```

---

## Task 14: Public API re-exports + final sweep

**Files:**
- Modify: `src/hermia/tui/__init__.py`
- Modify: `src/hermia/tui/widgets/__init__.py`

- [ ] **Step 1: Add re-exports to tui/__init__.py**

Replace `src/hermia/tui/__init__.py` with:

```python
"""Hermia Fleet TUI — unified interactive picker + live runner.

Public surface for downstream callers (Plan 2 picker screens, Plan 3 runner
screens, Plan 4 app.py rewire).
"""
from hermia.tui.bus import SessionBus
from hermia.tui.fleet_io import (
    fleet_path,
    load_fleet,
    load_hosts_seed,
    save_fleet,
    save_hosts_seed,
)
from hermia.tui.probe import DEFAULT_PROBE_TIMEOUT_SECONDS, probe_host
from hermia.tui.state import (
    FleetConfig,
    Host,
    HostSource,
    ModelChoice,
    ModelSource,
)

__all__ = [
    "DEFAULT_PROBE_TIMEOUT_SECONDS",
    "FleetConfig",
    "Host",
    "HostSource",
    "ModelChoice",
    "ModelSource",
    "SessionBus",
    "fleet_path",
    "load_fleet",
    "load_hosts_seed",
    "probe_host",
    "save_fleet",
    "save_hosts_seed",
]
```

- [ ] **Step 2: Add re-exports to widgets/__init__.py**

Replace `src/hermia/tui/widgets/__init__.py` with:

```python
"""Reusable, domain-agnostic Textual widgets for the Fleet TUI."""
from hermia.tui.widgets.drillable_list import DrillableList, ListRow
from hermia.tui.widgets.filter_axis import FilterAxis
from hermia.tui.widgets.progress_bar import AggregateProgressBar, MiniProgressBar
from hermia.tui.widgets.search_bar import SearchBar
from hermia.tui.widgets.status_badge import (
    ICONS,
    Direction,
    Status,
    StatusBadge,
    color_for,
)

__all__ = [
    "AggregateProgressBar",
    "Direction",
    "DrillableList",
    "FilterAxis",
    "ICONS",
    "ListRow",
    "MiniProgressBar",
    "SearchBar",
    "Status",
    "StatusBadge",
    "color_for",
]
```

- [ ] **Step 3: Run the full test suite**

Run:
```bash
pytest tests/unit/tui/ -v
```

Expected: all tests in `tests/unit/tui/` PASS.

- [ ] **Step 4: Run ruff**

Run:
```bash
ruff check src/hermia/tui/ tests/unit/tui/ tests/fixtures/
```

Expected: no errors. If any: fix them before proceeding.

- [ ] **Step 5: Run mypy**

Run:
```bash
mypy src/hermia/tui/
```

Expected: no errors. If any: fix them before proceeding (most likely candidates: missing type hints on Protocol implementations or queue parameterization).

- [ ] **Step 6: Run the full project test suite to catch any regression**

Run:
```bash
pytest
```

Expected: all tests pass — the new tui/ package added tests but touched no existing module, so existing tests should be unaffected.

- [ ] **Step 7: Commit**

```bash
git add src/hermia/tui/__init__.py src/hermia/tui/widgets/__init__.py
git commit -m "feat(tui): public re-exports for foundation API"
```

---

## Plan Close

- [ ] **C1: Push branch and open PR to dev**

```bash
git push -u origin feature/fleet-tui-foundation
gh pr create --base dev --title "feat(tui): foundation — widgets, bus, state, fleet I/O, probe" --body "$(cat <<'EOF'
## Summary

Foundation for the Fleet TUI per [docs/superpowers/specs/2026-06-18-fleet-tui-design.md](../specs/2026-06-18-fleet-tui-design.md). Builds the widget library, event bus, state model, fleet YAML I/O, and async host probe. No user-facing flow yet — every surface is unit-tested in isolation.

Subsequent plans:
- Plan 2: Picker screens (Launch, Fleet Config, Hosts, Models, Tests)
- Plan 3: Runner screens (L1 aggregate, L2 trials, L3 streaming detail)
- Plan 4: Migration (delete screens.py, retire old tests, rewire app.py)

## What's in this PR

- `src/hermia/tui/` package: `state.py`, `bus.py`, `fleet_io.py`, `probe.py`
- `src/hermia/tui/widgets/`: `status_badge`, `search_bar`, `filter_axis`, `progress_bar`, `drillable_list`
- `tests/fixtures/fake_transport.py`: shared FakeTransport for any test driving probe/runner
- Full unit-test coverage for every surface
- AGENTS.md Module Boundary Table expanded to include `src/hermia/tui/`

## Test plan

- [ ] `pytest tests/unit/tui/` — all green
- [ ] `pytest` — full suite green, no regression
- [ ] `ruff check src/hermia/tui/ tests/unit/tui/ tests/fixtures/` — clean
- [ ] `mypy src/hermia/tui/` — clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens against `dev`. URL printed to stdout.

- [ ] **C2: Post /gemini review on the PR**

Per AGENTS.md rule 8 — Gemini does not auto-trigger:

```bash
gh pr comment <PR-number> --body "/gemini review"
```

Address any HIGH-priority findings; merge after review cycle completes per project review-gate sequence.

- [ ] **C3: bd note + close on hermia-86g**

When PR merges:

```bash
bd note hermia-86g "Foundation plan (this PR) merged to dev. Plans 2-4 to follow."
```

Do NOT close `hermia-86g` — it tracks the full Fleet TUI, not just the foundation.

---

## Self-Review (run by the plan-writer)

**1. Spec coverage:**

| Spec section | Implemented in this plan |
|---|---|
| §2 Module Layout (`tui/`, widgets, state, bus, fleet_io, probe) | Tasks 1-14 |
| §2 `HostSource` / `ModelSource` protocols | Task 1 |
| §3 Data model (`FleetConfig`, `Host`, `ModelChoice`) | Task 1 |
| §3 Fleet YAML schema (round-trip, `auth_header_env` discipline) | Task 2 |
| §3 hosts.yaml seed list | Task 3 |
| §4 SessionBus pub/sub | Task 4 |
| §4 Queue bounds + drop-oldest | Task 5 |
| §5 Status semantics (`defended/refused/breached/error`) + direction-aware color | Task 6 |
| §5 Universal navigation contract (`/`, `tab`, `space`, `a`, `n`, `enter`) | Tasks 7, 8, 10 |
| §6 Error surfaces (timeout, auth, transport, empty list) | Tasks 12-13 |
| §7 Testing strategy (widget unit tests, bus pytest-asyncio, FakeTransport fixture) | All tasks |

Not covered in this plan (deferred to subsequent plans, as designed):
- Screens (Plan 2 + 3)
- App rewire (Plan 4)
- Deletion of `screens.py` (Plan 4)

**2. Placeholder scan:** No TBD / TODO / "implement later" / "similar to" markers. Every code block contains the actual code an engineer needs.

**3. Type consistency:** `FleetConfig`, `Host`, `ModelChoice` signatures consistent across Tasks 1, 2, 3, 12. `SessionBus.publish` / `subscribe` consistent across Tasks 4, 5, 12. `StatusBadge.update_status` signature consistent across Task 6 tests and impl.

**4. Ambiguity scan:** Task 5 references queue bounds that Task 4's implementation already supports — explicit by note in Task 5 Step 2 ("the implementation already supports drop-oldest; this task locks the behavior with explicit tests"). Task 13 same pattern for probe failure surfaces.
