# Fleet TUI Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the unified picker flow — Launch → Fleet Config → drill-into Hosts / Host Models / Tests — entirely against the Plan 1 foundation. Save/load fleets to `fleets/<name>.yaml`. No runner yet.

**Architecture:** Each picker screen is a `Screen` subclass under `src/hermia/tui/screens/`. Key bindings (`/`, `tab`, `enter`, `esc`, `space`, `a`, `n`) live on each screen per spec §5 universal contract and invoke the foundation widgets' API methods (`SearchBar.open()`, `DrillableList.toggle()`, etc.). The single shared `FleetConfig` lives on `HermiaApp` as the in-memory source of truth.

A separate entry point `python -m hermia.tui` lets the new TUI be exercised end-to-end without disturbing the existing `hermia` CLI. Plan 4 rewires the main entry point and deletes `screens.py`.

**Tech Stack:** Python 3.11+, Textual ≥0.80, asyncio, PyYAML. **No new dependencies.** Pilot tests use stdlib `asyncio.run()` per the pattern established in Plan 1.

**Spec reference:** [docs/superpowers/specs/2026-06-18-fleet-tui-design.md](../specs/2026-06-18-fleet-tui-design.md)

**Tracking bead:** `hermia-86g`

**Prerequisite:** Plan 1 (Foundation) merged to `dev`.

---

## File Structure

```
src/hermia/tui/
  app.py                            # HermiaApp Textual App subclass
  __main__.py                       # `python -m hermia.tui` entry
  test_catalog.py                   # TestRecord(id, frameworks) + load_test_catalog()
  transport_adapter.py              # transport_for(host) → _ListModelsTransport
  widgets/
    breadcrumb.py                   # NEW: clickable drill-path header
  screens/
    __init__.py
    launch.py                       # Load existing / New fleet / Quick local run
    config.py                       # Fleet Config — drill home base
    hosts.py                        # Hosts drill
    host_models.py                  # Single host's model picker
    tests.py                        # Fleet-scoped test picker
    modals.py                       # AddHostModal, FleetNameModal, UnsavedChangesModal

tests/unit/tui/
  test_app.py
  test_test_catalog.py
  test_transport_adapter.py
  test_widgets_breadcrumb.py
  screens/
    __init__.py
    test_launch.py
    test_config.py
    test_hosts.py
    test_host_models.py
    test_tests.py
    test_modals.py
  test_picker_e2e.py                # Pilot smoke covering Launch → New → Quick local
```

Files modified:
- `AGENTS.md` — no change (already includes `src/hermia/tui/`)

Files NOT touched (deferred to later plans):
- `src/hermia/screens.py` — Plan 4 deletes
- `src/hermia/app.py` — Plan 4 rewires
- `src/hermia/runner.py`, `fleet.py`, `transport/`, `scoring.py` — never touched by TUI work

---

## Setup

- [ ] **S1: Branch from updated dev (after Plan 1 merges)**

```bash
git checkout dev
git pull origin dev
git checkout -b feature/fleet-tui-picker
```

- [ ] **S2: Scaffold screens package**

Create empty `__init__.py` files:

```bash
mkdir -p src/hermia/tui/screens tests/unit/tui/screens
```

**`src/hermia/tui/screens/__init__.py`:**
```python
"""Picker + runner screens for the Fleet TUI."""
```

**`tests/unit/tui/screens/__init__.py`:** (empty)

Commit:
```bash
git add src/hermia/tui/screens/__init__.py tests/unit/tui/screens/__init__.py
git commit -m "feat(tui): scaffold screens package"
```

---

## Task 1: test_catalog.py — TestRecord + framework tag loading

**Files:**
- Create: `src/hermia/tui/test_catalog.py`
- Test: `tests/unit/tui/test_test_catalog.py`

The Tests drill needs (test_id, frameworks_present) records. `TEST_IDS` lives in `src/hermia/schemas.py`. Framework tags live in `src/hermia/test-datasets/agentic-tasks.json` under `agentic_test_cases[].frameworks.{owasp_llm_top10, mitre_atlas, csa_maestro, nist_ai_rmf}` (lists; non-empty = test belongs to that framework).

- [ ] **Step 1: Write the failing test**

`tests/unit/tui/test_test_catalog.py`:
```python
"""Tests for hermia.tui.test_catalog — TestRecord + load_test_catalog()."""
from hermia.tui.test_catalog import FRAMEWORKS, TestRecord, load_test_catalog


class TestLoadTestCatalog:
    def test_returns_one_record_per_test_id(self) -> None:
        from hermia.schemas import TEST_IDS
        catalog = load_test_catalog()
        assert {r.id for r in catalog} == set(TEST_IDS)

    def test_records_have_frameworks_keys(self) -> None:
        catalog = load_test_catalog()
        for r in catalog:
            assert set(r.frameworks.keys()) == set(FRAMEWORKS)
            for v in r.frameworks.values():
                assert isinstance(v, bool)

    def test_known_test_has_expected_framework_membership(self) -> None:
        catalog = load_test_catalog()
        # security-boundary is in agentic-tasks.json with non-empty csa_maestro.
        rec = next(r for r in catalog if r.id == "security-boundary")
        # At least one framework membership should be True for an annotated test.
        assert any(rec.frameworks.values())


class TestTestRecord:
    def test_is_in_framework_helper(self) -> None:
        rec = TestRecord(id="x", frameworks={"OWASP": True, "ATLAS": False, "MAESTRO": True, "NIST": False})
        assert rec.is_in_framework("OWASP") is True
        assert rec.is_in_framework("ATLAS") is False
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/unit/tui/test_test_catalog.py -v --no-cov
```

Expected: `ImportError: cannot import name 'TestRecord' from 'hermia.tui.test_catalog'`.

- [ ] **Step 3: Implement test_catalog.py**

```python
"""Test catalog — pairs each schemas.TEST_IDS entry with its framework tags.

Source of truth:
    - schemas.TEST_IDS               — canonical ordered list of test IDs
    - test-datasets/agentic-tasks.json[agentic_test_cases][*].frameworks
      → dict with keys: owasp_llm_top10, mitre_atlas, csa_maestro, nist_ai_rmf
      → non-empty list = test belongs to that framework

The Tests drill uses TestRecord.is_in_framework() for the filter axis.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hermia.schemas import TEST_IDS

FRAMEWORKS: list[str] = ["OWASP", "ATLAS", "MAESTRO", "NIST"]

_TASKS_JSON = Path(__file__).resolve().parent.parent / "test-datasets" / "agentic-tasks.json"

_FRAMEWORK_KEY_MAP: dict[str, str] = {
    "OWASP": "owasp_llm_top10",
    "ATLAS": "mitre_atlas",
    "MAESTRO": "csa_maestro",
    "NIST": "nist_ai_rmf",
}


@dataclass
class TestRecord:
    id: str
    frameworks: dict[str, bool]

    def is_in_framework(self, framework: str) -> bool:
        return self.frameworks.get(framework, False)


def load_test_catalog() -> list[TestRecord]:
    """Build a list of TestRecord — one per id in schemas.TEST_IDS.

    Tests missing from agentic-tasks.json get a record with all framework
    memberships False (their ID is still in the catalog so they appear in
    the picker).
    """
    by_id: dict[str, dict[str, bool]] = {
        tid: {f: False for f in FRAMEWORKS} for tid in TEST_IDS
    }
    raw = json.loads(_TASKS_JSON.read_text())
    for case in raw.get("agentic_test_cases", []):
        cid = case.get("id")
        if cid not in by_id:
            continue
        f = case.get("frameworks", {}) or {}
        for label, key in _FRAMEWORK_KEY_MAP.items():
            by_id[cid][label] = bool(f.get(key))
    return [TestRecord(id=tid, frameworks=by_id[tid]) for tid in TEST_IDS]
```

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/unit/tui/test_test_catalog.py -v --no-cov
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/test_catalog.py tests/unit/tui/test_test_catalog.py
git commit -m "feat(tui): test catalog with framework tags from agentic-tasks.json"
```

---

## Task 2: transport_adapter.py — engine-aware probe transport factory

**Files:**
- Create: `src/hermia/tui/transport_adapter.py`
- Test: `tests/unit/tui/test_transport_adapter.py`

The Hosts drill probes each host. `probe_host` needs a transport with `async list_models()`. The right transport depends on `host.engine`. Map:

| engine | transport |
|---|---|
| `ollama` | wraps Ollama `/api/tags` |
| `openai-compat` | wraps `/v1/models` |
| other | falls back to `openai-compat` for v0.2 (vllm / sglang / litellm all speak OpenAI shape) |

Auth header (when present) comes from the env var named by `host.auth_header_env`.

- [ ] **Step 1: Write the failing test**

`tests/unit/tui/test_transport_adapter.py`:
```python
"""Tests for hermia.tui.transport_adapter — engine → transport factory."""
import asyncio

from hermia.tui.state import Host
from hermia.tui.transport_adapter import transport_for


class _FakeHTTPProbe:
    """Stand-in returned by transport_for in test mode — we only need .list_models()."""
    last_url: str | None = None
    last_auth: str | None = None


class TestTransportFor:
    def test_returns_object_with_list_models(self) -> None:
        host = Host(name="h", url="http://h:11434", engine="ollama")
        tr = transport_for(host)
        assert hasattr(tr, "list_models")

    def test_resolves_auth_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_KEY", "secret-value")
        host = Host(
            name="h",
            url="http://h:4000",
            engine="openai-compat",
            auth_header_env="MY_KEY",
        )
        tr = transport_for(host)
        # The adapter stores the resolved bearer header on the transport
        # instance for the probe to use when calling /v1/models.
        assert tr.auth_header == "Bearer secret-value"

    def test_missing_env_var_leaves_auth_none(self) -> None:
        host = Host(
            name="h",
            url="http://h:4000",
            engine="openai-compat",
            auth_header_env="NOT_SET_ANYWHERE",
        )
        tr = transport_for(host)
        assert tr.auth_header is None

    def test_no_auth_header_env_leaves_auth_none(self) -> None:
        host = Host(name="h", url="http://h:11434", engine="ollama")
        tr = transport_for(host)
        assert tr.auth_header is None
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/unit/tui/test_transport_adapter.py -v --no-cov
```

- [ ] **Step 3: Implement transport_adapter.py**

```python
"""Engine-aware transport factory for the Fleet TUI probe layer.

Maps a Host to a transport object with `async list_models() -> list[str]`,
which is what hermia.tui.probe.probe_host needs.

For v0.2 we ship two probe shapes:
    - Ollama         /api/tags     → list of {"name": str, ...}
    - OpenAI-compat  /v1/models    → {"data": [{"id": str, ...}, ...]}

vLLM / SGLang / LiteLLM all speak the OpenAI shape, so any non-"ollama"
engine falls back to the openai-compat path.

Implementation note: uses stdlib `urllib.request` wrapped in
`asyncio.to_thread` rather than `httpx`. `httpx` is NOT in pyproject.toml
and AGENTS.md rule 3 blocks adding deps without approval. urllib is
stdlib; the thread offload keeps probe_host's async contract.

Per spec §6 / probe.py docstring, this adapter MUST normalize transport
exceptions to the stdlib classes probe.py catches:
    - timeout              → TimeoutError  (handled at probe.py's wait_for)
    - HTTP 401/403         → PermissionError
    - URLError / OSError   → propagates as OSError/ConnectionError

Auth header is resolved from the environment variable named by
host.auth_header_env. Per AGENTS.md rule 11, the secret value never appears
in any saved config — only the env var name does.
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from hermia.tui.state import Host


@dataclass
class _BaseProbeTransport:
    url: str
    auth_header: str | None = None

    def _fetch_sync(self, path: str) -> dict:
        req = urllib.request.Request(f"{self.url.rstrip('/')}{path}")
        if self.auth_header:
            req.add_header("Authorization", self.auth_header)
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise PermissionError(f"{exc.code} from {self.url}") from exc
            raise


class OllamaProbeTransport(_BaseProbeTransport):
    async def list_models(self) -> list[str]:
        data = await asyncio.to_thread(self._fetch_sync, "/api/tags")
        return [m["name"] for m in data.get("models", [])]


class OpenAICompatProbeTransport(_BaseProbeTransport):
    async def list_models(self) -> list[str]:
        data = await asyncio.to_thread(self._fetch_sync, "/v1/models")
        return [m["id"] for m in data.get("data", [])]


def transport_for(host: Host) -> _BaseProbeTransport:
    """Return a probe transport for this host's engine + auth setup."""
    auth_header: str | None = None
    if host.auth_header_env:
        token = os.environ.get(host.auth_header_env)
        if token:
            auth_header = f"Bearer {token}"
    cls = OllamaProbeTransport if host.engine == "ollama" else OpenAICompatProbeTransport
    return cls(url=host.url, auth_header=auth_header)
```

**Dependency check:** stdlib-only — `urllib.request`, `urllib.error`, `json`, `asyncio`. **No `httpx` or `requests` needed.** Confirms compliance with AGENTS.md rule 3. (Note: the existing `src/hermia/transport/` uses `requests`; this is a deliberately separate codepath because the runner is sync-oriented and the TUI probe needs `async`. If a future Plan 3+ wants to share with the runner, an `asyncio.to_thread` wrap around the existing `requests`-based transports also works.)

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/unit/tui/test_transport_adapter.py -v --no-cov
```

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/transport_adapter.py tests/unit/tui/test_transport_adapter.py
git commit -m "feat(tui): engine-aware probe transport factory with env-var auth"
```

---

## Task 3: widgets/breadcrumb.py — clickable drill-path header

**Files:**
- Create: `src/hermia/tui/widgets/breadcrumb.py`
- Modify: `src/hermia/tui/widgets/__init__.py` (add Breadcrumb to re-exports)
- Test: `tests/unit/tui/test_widgets_breadcrumb.py`

Reusable widget showing `hermia · fleet · <name> ▸ hosts ▸ marcus` with each segment clickable. Emits `Breadcrumb.Jumped(index)` when a segment is clicked. Each screen sets the breadcrumb from its drill stack.

- [ ] **Step 1: Write the failing test**

`tests/unit/tui/test_widgets_breadcrumb.py`:
```python
"""Tests for Breadcrumb — segmented drill-path header."""
import asyncio

from textual.app import App, ComposeResult

from hermia.tui.widgets.breadcrumb import Breadcrumb


class _Host(App):
    def __init__(self, segments: list[str]) -> None:
        super().__init__()
        self._segments = segments
        self.jumped_to: int | None = None

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self._segments)

    def on_breadcrumb_jumped(self, event: Breadcrumb.Jumped) -> None:
        self.jumped_to = event.index


class TestBreadcrumb:
    def test_renders_segments_with_separator(self) -> None:
        async def _run() -> None:
            async with _Host(["hermia", "fleet", "smoke"]).run_test() as pilot:
                bc = pilot.app.query_one(Breadcrumb)
                assert bc.text == "hermia ▸ fleet ▸ smoke"

        asyncio.run(_run())

    def test_empty_segments_renders_empty(self) -> None:
        async def _run() -> None:
            async with _Host([]).run_test() as pilot:
                bc = pilot.app.query_one(Breadcrumb)
                assert bc.text == ""

        asyncio.run(_run())

    def test_update_changes_rendering(self) -> None:
        async def _run() -> None:
            async with _Host(["a", "b"]).run_test() as pilot:
                bc = pilot.app.query_one(Breadcrumb)
                bc.set_segments(["x", "y", "z"])
                await pilot.pause()
                assert bc.text == "x ▸ y ▸ z"

        asyncio.run(_run())

    def test_jump_emits_message_with_index(self) -> None:
        async def _run() -> None:
            async with _Host(["a", "b", "c"]).run_test() as pilot:
                bc = pilot.app.query_one(Breadcrumb)
                bc.jump_to(1)
                await pilot.pause()
                assert pilot.app.jumped_to == 1

        asyncio.run(_run())
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement breadcrumb.py**

```python
"""Breadcrumb — segmented drill-path header.

`hermia · fleet · kwaainet-baseline ▸ hosts ▸ marcus`

Each segment is clickable (mouse) and the host screen can call jump_to(i)
to handle keyboard jumps. The widget emits Breadcrumb.Jumped(index) which
the screen translates into pop_screen() calls per drill depth.
"""
from __future__ import annotations

from textual.message import Message
from textual.widgets import Static

SEPARATOR = " ▸ "


class Breadcrumb(Static):
    """Inline segmented drill-path header."""

    DEFAULT_CSS = """
    Breadcrumb {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    class Jumped(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, segments: list[str]) -> None:
        self._segments = list(segments)
        self._text = SEPARATOR.join(self._segments)
        super().__init__(self._text)

    @property
    def text(self) -> str:
        return self._text

    def set_segments(self, segments: list[str]) -> None:
        self._segments = list(segments)
        self._text = SEPARATOR.join(self._segments)
        self.update(self._text)

    def jump_to(self, index: int) -> None:
        """Programmatic jump — used by screen-level handlers."""
        if 0 <= index < len(self._segments):
            self.post_message(self.Jumped(index))
```

Add to `src/hermia/tui/widgets/__init__.py`:
```python
from hermia.tui.widgets.breadcrumb import Breadcrumb
```
And to `__all__`.

- [ ] **Step 4: Verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/widgets/breadcrumb.py src/hermia/tui/widgets/__init__.py tests/unit/tui/test_widgets_breadcrumb.py
git commit -m "feat(tui): Breadcrumb widget — segmented drill-path header"
```

---

## Task 4: app.py — HermiaApp skeleton + smart-config attribute

**Files:**
- Create: `src/hermia/tui/app.py`
- Create: `src/hermia/tui/__main__.py`
- Test: `tests/unit/tui/test_app.py`

HermiaApp is the Textual App that mounts the Launch screen and holds the single shared `FleetConfig` as a mutable attribute. Screens read and write to `app.config`. Plan 3 will add `app.bus = SessionBus()` for the runner; Plan 2 only needs `config`.

- [ ] **Step 1: Write the failing test**

`tests/unit/tui/test_app.py`:
```python
"""Tests for HermiaApp — the unified Fleet TUI Textual App."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.state import FleetConfig


class TestHermiaApp:
    def test_starts_with_empty_config(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                app: HermiaApp = pilot.app  # type: ignore[assignment]
                assert isinstance(app.config, FleetConfig)
                assert app.config.name == ""
                assert app.config.hosts == []

        asyncio.run(_run())

    def test_config_is_mutable(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                app: HermiaApp = pilot.app  # type: ignore[assignment]
                app.config.name = "smoke"
                assert app.config.name == "smoke"

        asyncio.run(_run())

    def test_mounts_launch_screen(self) -> None:
        async def _run() -> None:
            from hermia.tui.screens.launch import LaunchScreen
            async with HermiaApp().run_test() as pilot:
                assert isinstance(pilot.app.screen, LaunchScreen)

        asyncio.run(_run())
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement app.py + __main__.py**

`src/hermia/tui/app.py`:
```python
"""HermiaApp — Textual App for the unified Fleet TUI.

Holds the shared FleetConfig as a mutable attribute. Picker screens read
and write directly to `app.config`. Plan 3 adds `app.bus = SessionBus()`
for runner ↔ screen communication.
"""
from __future__ import annotations

from textual.app import App

from hermia.tui.state import FleetConfig


class HermiaApp(App[None]):
    CSS_PATH = None  # widgets define their own DEFAULT_CSS

    def __init__(self) -> None:
        super().__init__()
        self.config: FleetConfig = FleetConfig(name="")

    def on_mount(self) -> None:
        # Import here to avoid circular import — screens.launch imports HermiaApp.
        from hermia.tui.screens.launch import LaunchScreen
        self.push_screen(LaunchScreen())
```

`src/hermia/tui/__main__.py`:
```python
"""`python -m hermia.tui` — launches the unified Fleet TUI.

Separate from the existing `hermia` CLI (src/hermia/app.py:main) during
Plan 2 development. Plan 4 rewires the main entry to point here and deletes
src/hermia/screens.py.
"""
from hermia.tui.app import HermiaApp


def main() -> None:
    HermiaApp().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/unit/tui/test_app.py -v --no-cov
```

Note: this will fail until Task 5 lands `LaunchScreen`. **For this task's commit, mark the `test_mounts_launch_screen` test with `@pytest.mark.xfail(reason="LaunchScreen lands in Task 5")` and remove the marker in Task 5.**

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/app.py src/hermia/tui/__main__.py tests/unit/tui/test_app.py
git commit -m "feat(tui): HermiaApp skeleton + python -m hermia.tui entry point"
```

---

## Task 5: screens/launch.py — three-entry list

**Files:**
- Create: `src/hermia/tui/screens/launch.py`
- Test: `tests/unit/tui/screens/test_launch.py`

The Launch screen shows three entries: `Load existing fleet`, `New fleet`, `Quick local run`. Cursor + enter selects. Subsequent tasks wire up the actions.

- [ ] **Step 1: Write the failing test**

`tests/unit/tui/screens/test_launch.py`:
```python
"""Tests for LaunchScreen — initial entries + cursor."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.launch import LaunchScreen


class TestLaunchEntries:
    def test_three_entries_present(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                assert isinstance(pilot.app.screen, LaunchScreen)
                screen = pilot.app.screen
                labels = [e.label for e in screen.entries]
                assert labels == ["Load existing fleet", "New fleet", "Quick local run"]

        asyncio.run(_run())

    def test_cursor_starts_on_first_entry(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 0

        asyncio.run(_run())

    def test_arrow_down_moves_cursor(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("down")
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 1

        asyncio.run(_run())

    def test_q_quits_app(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("q")
                await pilot.pause()
                # App is exiting; running flag flips off.
                assert pilot.app._exit is True

        asyncio.run(_run())
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement launch.py**

```python
"""Launch screen — three entries: Load / New / Quick local run.

Quick local run pre-fills a single-host config (http://localhost:11434) and
jumps to model selection on that host. New fleet opens an empty Fleet Config.
Load opens an entry-list of fleets/*.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static


@dataclass
class LaunchEntry:
    id: str
    label: str


class LaunchScreen(Screen[None]):
    BINDINGS = [
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("enter", "select", "Select", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[LaunchEntry] = [
            LaunchEntry(id="load", label="Load existing fleet"),
            LaunchEntry(id="new", label="New fleet"),
            LaunchEntry(id="quick", label="Quick local run"),
        ]
        self.cursor_index: int = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Welcome to hermia fleet", id="launch-title")
            for entry in self.entries:
                yield Static(self._row_text(entry), id=f"launch-{entry.id}")

    def _row_text(self, entry: LaunchEntry) -> str:
        cursor = "▸ " if entry == self.entries[self.cursor_index] else "  "
        return f"  {cursor}{entry.label}"

    def _refresh_rows(self) -> None:
        for entry in self.entries:
            self.query_one(f"#launch-{entry.id}", Static).update(self._row_text(entry))

    def action_cursor_prev(self) -> None:
        if self.cursor_index > 0:
            self.cursor_index -= 1
            self._refresh_rows()

    def action_cursor_next(self) -> None:
        if self.cursor_index < len(self.entries) - 1:
            self.cursor_index += 1
            self._refresh_rows()

    def action_select(self) -> None:
        # Subsequent tasks fill in each branch. For Task 5, no-op.
        entry = self.entries[self.cursor_index]
        # Placeholder: each branch will push a screen / call helper.
        _ = entry  # noqa: F841

    def action_quit(self) -> None:
        self.app.exit()
```

Now remove the `@pytest.mark.xfail` from `test_app.py::test_mounts_launch_screen`.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/unit/tui/test_app.py tests/unit/tui/screens/test_launch.py -v --no-cov
```

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/screens/launch.py tests/unit/tui/screens/test_launch.py tests/unit/tui/test_app.py
git commit -m "feat(tui): LaunchScreen with three entries and cursor navigation"
```

---

## Task 6: screens/launch.py — Load existing fleet flow

**Files:**
- Modify: `src/hermia/tui/screens/launch.py`
- Test: `tests/unit/tui/screens/test_launch.py` (add tests)

When the user selects "Load existing fleet", the Launch screen scans `fleets/*.yaml`, replaces its entry list with the discovered fleets, and pressing `enter` on one loads it into `app.config` and pushes the Fleet Config screen.

This task does NOT yet land the Fleet Config screen — that's Task 8. For now, after loading, the screen calls `self.app.exit()` so the e2e tests in this task can confirm the load happened by reading `app.config`. Task 8 replaces the exit with `push_screen(FleetConfigScreen())`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/tui/screens/test_launch.py`:
```python
from pathlib import Path

from hermia.tui.fleet_io import save_fleet
from hermia.tui.state import FleetConfig, Host, ModelChoice


class TestLoadExisting:
    def test_selecting_load_shows_fleet_list(self, tmp_path, monkeypatch) -> None:
        # Pre-populate fleets/ with two saved fleets.
        save_fleet(FleetConfig(name="alpha"), root=tmp_path)
        save_fleet(FleetConfig(name="beta"), root=tmp_path)
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("enter")  # selects Load
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                # After Load, entries list switches to fleet files (sorted).
                labels = [e.label for e in screen.entries]
                assert labels == ["alpha", "beta"]

        asyncio.run(_run())

    def test_selecting_a_loaded_fleet_populates_config(self, tmp_path, monkeypatch) -> None:
        cfg = FleetConfig(
            name="alpha",
            hosts=[Host(name="h1", url="http://h1", engine="ollama",
                        models=[ModelChoice(name="qwen3:32b", selected=True)])],
            tests=["security-boundary"],
        )
        save_fleet(cfg, root=tmp_path)
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("enter")  # Load
                await pilot.pause()
                await pilot.press("enter")  # select alpha
                await pilot.pause()
                app: HermiaApp = pilot.app  # type: ignore[assignment]
                assert app.config.name == "alpha"
                assert app.config.tests == ["security-boundary"]
                assert app.config.hosts[0].name == "h1"

        asyncio.run(_run())

    def test_load_with_no_fleets_shows_empty_message(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("enter")  # Load
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.entries == []
                # An empty-state notice should be visible.
                notice = pilot.app.query_one("#launch-empty-notice", expect_type=type(screen.query_one("#launch-title")))
                assert "No saved fleets" in notice.renderable or "No saved fleets" in str(notice)

        asyncio.run(_run())
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Modify launch.py**

Add a `mode` attribute ("home" or "load") and split rendering by mode. In "load" mode, list `fleets/*.yaml`. Pressing enter on a fleet entry loads it into `app.config` and (for now) exits — Task 8 will replace exit with `push_screen(FleetConfigScreen())`.

```python
# Inside LaunchScreen — add to __init__:
self.mode: str = "home"

# Add a helper:
def _scan_fleets(self) -> list[LaunchEntry]:
    from pathlib import Path
    fleets_dir = Path("fleets")
    if not fleets_dir.exists():
        return []
    files = sorted(fleets_dir.glob("*.yaml"))
    return [LaunchEntry(id=f.stem, label=f.stem) for f in files]

# Replace action_select:
def action_select(self) -> None:
    if self.mode == "home":
        entry = self.entries[self.cursor_index]
        if entry.id == "load":
            self._enter_load_mode()
        elif entry.id == "new":
            self._enter_new_fleet()
        elif entry.id == "quick":
            self._enter_quick_local()
    elif self.mode == "load":
        self._load_selected_fleet()

def _enter_load_mode(self) -> None:
    self.mode = "load"
    self.entries = self._scan_fleets()
    self.cursor_index = 0 if self.entries else -1
    self._rerender()

def _load_selected_fleet(self) -> None:
    if self.cursor_index < 0:
        return
    from hermia.tui.fleet_io import fleet_path, load_fleet
    entry = self.entries[self.cursor_index]
    path = fleet_path(entry.id)
    self.app.config = load_fleet(path)  # type: ignore[attr-defined]
    # Task 8 will replace this with push_screen(FleetConfigScreen()).
    self.app.exit()

def _enter_new_fleet(self) -> None:
    # Task 7 fills in.
    self.app.exit()

def _enter_quick_local(self) -> None:
    # Task 7 fills in.
    self.app.exit()

def _rerender(self) -> None:
    # Detach all children and recompose.
    for child in list(self.children):
        child.remove()
    # Re-emit compose output.
    self.mount(Static("Welcome to hermia fleet" if self.mode == "home" else "Load fleet", id="launch-title"))
    if not self.entries:
        self.mount(Static("No saved fleets in fleets/", id="launch-empty-notice"))
        return
    for entry in self.entries:
        self.mount(Static(self._row_text(entry), id=f"launch-{entry.id}"))
```

- [ ] **Step 4: Verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/screens/launch.py tests/unit/tui/screens/test_launch.py
git commit -m "feat(tui): Launch — Load existing fleet flow + empty-state notice"
```

---

## Task 7: screens/launch.py — New fleet + Quick local run

**Files:**
- Modify: `src/hermia/tui/screens/launch.py`
- Test: `tests/unit/tui/screens/test_launch.py` (add tests)

`New fleet` initializes `app.config = FleetConfig(name="")` and (placeholder until Task 8) exits.

`Quick local run` pre-populates `app.config` with one host (`http://localhost:11434`, `ollama`, name `"local"`) and the default test set (all `TEST_IDS`). Then (placeholder) exits.

- [ ] **Step 1: Write the failing test**

```python
class TestNewFleet:
    def test_new_fleet_resets_config(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                # Mutate config first so we can prove New resets it.
                pilot.app.config.name = "stale"
                await pilot.press("down")  # cursor to New
                await pilot.press("enter")
                await pilot.pause()
                assert pilot.app.config.name == ""
                assert pilot.app.config.hosts == []

        asyncio.run(_run())


class TestQuickLocalRun:
    def test_quick_local_seeds_config(self) -> None:
        from hermia.schemas import TEST_IDS

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("down")
                await pilot.press("down")  # cursor to Quick
                await pilot.press("enter")
                await pilot.pause()
                cfg = pilot.app.config
                assert cfg.name == "quick-local"
                assert len(cfg.hosts) == 1
                h = cfg.hosts[0]
                assert h.url == "http://localhost:11434"
                assert h.engine == "ollama"
                assert h.name == "local"
                assert cfg.tests == TEST_IDS

        asyncio.run(_run())
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

```python
def _enter_new_fleet(self) -> None:
    self.app.config = FleetConfig(name="")  # type: ignore[attr-defined]
    self.app.exit()

def _enter_quick_local(self) -> None:
    from hermia.schemas import TEST_IDS
    self.app.config = FleetConfig(  # type: ignore[attr-defined]
        name="quick-local",
        hosts=[Host(name="local", url="http://localhost:11434", engine="ollama")],
        tests=list(TEST_IDS),
    )
    self.app.exit()
```

(Add `from hermia.tui.state import FleetConfig, Host` to launch.py imports.)

- [ ] **Step 4: Verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/screens/launch.py tests/unit/tui/screens/test_launch.py
git commit -m "feat(tui): Launch — New fleet reset + Quick local run pre-population"
```

---

## Task 8: screens/config.py — Fleet Config home base

**Files:**
- Create: `src/hermia/tui/screens/config.py`
- Modify: `src/hermia/tui/screens/launch.py` (replace `app.exit()` placeholders with `push_screen(FleetConfigScreen())`)
- Test: `tests/unit/tui/screens/test_config.py`

The Fleet Config screen displays:
- Breadcrumb: `hermia · fleet · <name>`
- Two drillable rows: `Hosts (N hosts · M model trials)` and `Tests (T tests)`
- Run plan line: `N × M × T = total trials`
- Footer key hints: `l load · s save · r run · esc back`

`enter` on Hosts → push `HostsScreen` (Task 10). `enter` on Tests → push `TestsScreen` (Task 12). `r` triggers run (Plan 3). For Task 8 the `enter` actions are no-ops; Tasks 10 and 12 wire them.

- [ ] **Step 1: Write the failing test**

`tests/unit/tui/screens/test_config.py`:
```python
"""Tests for FleetConfigScreen — top-level summary + drill rows."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.config import FleetConfigScreen
from hermia.tui.state import FleetConfig, Host, ModelChoice


class TestFleetConfigSummary:
    def test_renders_empty_config(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert "0 hosts" in screen.summary_text
                assert "0 tests" in screen.summary_text
                assert "0 trials" in screen.run_plan_text

    def test_summary_with_hosts_and_tests(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = FleetConfig(
                    name="smoke",
                    hosts=[Host(name="h1", url="http://h1", engine="ollama",
                                models=[ModelChoice(name="m1", selected=True),
                                        ModelChoice(name="m2", selected=True)])],
                    tests=["t1", "t2", "t3"],
                )
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert "1 host" in screen.summary_text
                assert "3 tests" in screen.summary_text
                # 1 host × 2 selected models × 3 tests = 6 trials.
                assert "6 trials" in screen.run_plan_text

        asyncio.run(_run())

    def test_breadcrumb_includes_fleet_name(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert "smoke" in screen.breadcrumb_text

        asyncio.run(_run())

    def test_escape_pops_back_to_launch(self) -> None:
        async def _run() -> None:
            from hermia.tui.screens.launch import LaunchScreen
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, LaunchScreen)

        asyncio.run(_run())
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement config.py**

```python
"""Fleet Config screen — home base of the picker drill.

Shows two drillable rows (Hosts, Tests), a run-plan trial estimate, and
the breadcrumb header. Future tasks wire enter-on-row to push the child
drills.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from hermia.tui.widgets.breadcrumb import Breadcrumb


class FleetConfigScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("enter", "drill", "Drill", show=True),
        Binding("s", "save", "Save", show=True),
        Binding("l", "load", "Load", show=False),
        Binding("r", "run", "Run", show=False),
    ]

    ROWS = [("hosts", "Hosts"), ("tests", "Tests")]

    def __init__(self) -> None:
        super().__init__()
        self.cursor_row: int = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Breadcrumb(self._breadcrumb_segments())
            yield Static("", id="config-summary-hosts")
            yield Static("", id="config-summary-tests")
            yield Static("", id="config-run-plan")

    def on_mount(self) -> None:
        self._refresh()

    @property
    def app_config(self):
        return self.app.config  # type: ignore[attr-defined]

    @property
    def breadcrumb_text(self) -> str:
        return self.query_one(Breadcrumb).text

    @property
    def summary_text(self) -> str:
        h = self.query_one("#config-summary-hosts", Static)
        t = self.query_one("#config-summary-tests", Static)
        return f"{h.renderable} {t.renderable}"

    @property
    def run_plan_text(self) -> str:
        return str(self.query_one("#config-run-plan", Static).renderable)

    def _breadcrumb_segments(self) -> list[str]:
        name = self.app_config.name or "(unnamed)"
        return ["hermia", "fleet", name]

    def _refresh(self) -> None:
        cfg = self.app_config
        n_hosts = len(cfg.hosts)
        n_models = sum(sum(1 for m in h.models if m.selected) for h in cfg.hosts)
        n_tests = len(cfg.tests)
        trials = n_hosts and n_models and n_tests and (n_hosts * (n_models // max(n_hosts, 1)) * n_tests) or (n_models * n_tests)
        self.query_one(Breadcrumb).set_segments(self._breadcrumb_segments())
        h_label = "host" if n_hosts == 1 else "hosts"
        t_label = "test" if n_tests == 1 else "tests"
        # Row 0 (Hosts):
        cursor = "▸" if self.cursor_row == 0 else " "
        self.query_one("#config-summary-hosts", Static).update(
            f"{cursor} Hosts        {n_hosts} {h_label} · {n_models} model trials"
        )
        # Row 1 (Tests):
        cursor = "▸" if self.cursor_row == 1 else " "
        self.query_one("#config-summary-tests", Static).update(
            f"{cursor} Tests        {n_tests} {t_label}"
        )
        self.query_one("#config-run-plan", Static).update(
            f"Run plan: {n_models * n_tests} trials"
        )

    def action_cursor_prev(self) -> None:
        if self.cursor_row > 0:
            self.cursor_row -= 1
            self._refresh()

    def action_cursor_next(self) -> None:
        if self.cursor_row < len(self.ROWS) - 1:
            self.cursor_row += 1
            self._refresh()

    def action_drill(self) -> None:
        # Hosts and Tests screens land in Tasks 10 and 12.
        pass

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_save(self) -> None:
        # Wired in Task 9.
        pass

    def action_load(self) -> None:
        # Pop back to Launch and re-enter Load mode.
        self.app.pop_screen()

    def action_run(self) -> None:
        # Plan 3 wires this to the runner.
        pass
```

Update `launch.py` to push FleetConfigScreen instead of exiting in `_enter_new_fleet`, `_enter_quick_local`, and `_load_selected_fleet`:

```python
def _enter_new_fleet(self) -> None:
    from hermia.tui.screens.config import FleetConfigScreen
    self.app.config = FleetConfig(name="")  # type: ignore[attr-defined]
    self.app.push_screen(FleetConfigScreen())

def _enter_quick_local(self) -> None:
    from hermia.tui.screens.config import FleetConfigScreen
    from hermia.schemas import TEST_IDS
    self.app.config = FleetConfig(  # type: ignore[attr-defined]
        name="quick-local",
        hosts=[Host(name="local", url="http://localhost:11434", engine="ollama")],
        tests=list(TEST_IDS),
    )
    self.app.push_screen(FleetConfigScreen())

def _load_selected_fleet(self) -> None:
    if self.cursor_index < 0:
        return
    from hermia.tui.fleet_io import fleet_path, load_fleet
    from hermia.tui.screens.config import FleetConfigScreen
    entry = self.entries[self.cursor_index]
    path = fleet_path(entry.id)
    self.app.config = load_fleet(path)  # type: ignore[attr-defined]
    self.app.push_screen(FleetConfigScreen())
```

Update Task 7's tests — `await pilot.press("enter")` no longer triggers `app.exit()`. The tests should now assert that `pilot.app.screen` is a `FleetConfigScreen` after entry.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/unit/tui/screens/ -v --no-cov
```

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/screens/config.py src/hermia/tui/screens/launch.py tests/unit/tui/screens/test_config.py tests/unit/tui/screens/test_launch.py
git commit -m "feat(tui): FleetConfigScreen home base with drill rows + Launch pushes it"
```

---

## Task 9: screens/config.py — save (s) + unsaved-changes indicator

**Files:**
- Modify: `src/hermia/tui/screens/config.py`
- Create: `src/hermia/tui/screens/modals.py` (FleetNameModal — name prompt)
- Test: `tests/unit/tui/screens/test_config.py` (add tests)

Pressing `s` prompts the user for a fleet name (if `app.config.name == ""`) via a modal, then calls `save_fleet(app.config)`. If the name is already set, save immediately. The screen tracks a `dirty: bool` that flips True on any edit and back to False on save; the breadcrumb appends `[unsaved changes]` while True.

For Task 9, the dirty flag is set only by `mark_dirty()` calls. Tasks 11 / 12 / 13 call `mark_dirty()` from the drills.

- [ ] **Step 1: Write the failing test**

```python
class TestSave:
    def test_save_writes_fleet_file_when_name_set(self, tmp_path, monkeypatch) -> None:
        from hermia.tui.fleet_io import fleet_path
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                await pilot.press("s")
                await pilot.pause()
                assert fleet_path("smoke").exists()

        asyncio.run(_run())

    def test_dirty_flag_shows_in_breadcrumb(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                screen.mark_dirty()
                await pilot.pause()
                assert "[unsaved" in screen.breadcrumb_text

        asyncio.run(_run())

    def test_save_clears_dirty_flag(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                screen.mark_dirty()
                await pilot.press("s")
                await pilot.pause()
                assert screen.dirty is False
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

Add `self.dirty = False` to `FleetConfigScreen.__init__`. Add `mark_dirty()` method that flips `dirty` and refreshes the breadcrumb. Update `_breadcrumb_segments()` to append `[unsaved changes]` when `dirty`. Wire `action_save()`:

```python
def action_save(self) -> None:
    from hermia.tui.fleet_io import save_fleet
    if not self.app_config.name:
        # Prompt for a name. FleetNameModal lands in this same task.
        self.app.push_screen(FleetNameModal(), self._on_name_chosen)
        return
    save_fleet(self.app_config)
    self.dirty = False
    self._refresh()

def _on_name_chosen(self, name: str | None) -> None:
    if not name:
        return
    self.app_config.name = name
    self.action_save()

def mark_dirty(self) -> None:
    self.dirty = True
    self._refresh()
```

Create `src/hermia/tui/screens/modals.py`:
```python
"""Modal dialogs used by picker screens."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class FleetNameModal(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal"):
            yield Label("Fleet name:")
            yield Input(placeholder="kwaainet-baseline", id="modal-name")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
```

Update breadcrumb logic:
```python
def _breadcrumb_segments(self) -> list[str]:
    name = self.app_config.name or "(unnamed)"
    suffix = " [unsaved changes]" if self.dirty else ""
    return ["hermia", "fleet", f"{name}{suffix}"]
```

- [ ] **Step 4: Verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/screens/config.py src/hermia/tui/screens/modals.py tests/unit/tui/screens/test_config.py
git commit -m "feat(tui): FleetConfig — save (s) + FleetNameModal + dirty indicator"
```

---

## Task 10: screens/hosts.py — list from seed + AddHostModal

**Files:**
- Create: `src/hermia/tui/screens/hosts.py`
- Modify: `src/hermia/tui/screens/modals.py` (add `AddHostModal`)
- Modify: `src/hermia/tui/screens/config.py` (wire Hosts drill)
- Test: `tests/unit/tui/screens/test_hosts.py`
- Test: `tests/unit/tui/screens/test_modals.py`

Hosts drill loads its initial list from the user's `hosts.yaml` seed and shows any hosts already in `app.config.hosts`. Pressing `+` opens `AddHostModal` (name / URL / engine). The Hosts drill uses the foundation `DrillableList` widget under the hood, but at the screen level it maintains its own row state because each row has structured fields (URL, model count, probe status badge).

For simplicity, this task uses a plain Vertical+Static layout (one Static per host row) and calls `app.config.hosts.append(...)` directly. The `+` key opens the modal; the modal's result is added to both `app.config.hosts` and (optionally) `~/.config/hermia/hosts.yaml` via `save_hosts_seed`.

- [ ] **Step 1: Write the failing test**

`tests/unit/tui/screens/test_hosts.py`:
```python
"""Tests for HostsScreen — list + AddHostModal + escape back."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.config import FleetConfigScreen
from hermia.tui.screens.hosts import HostsScreen
from hermia.tui.state import Host


class TestHostsScreen:
    def test_initial_render_shows_existing_hosts(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [
                    Host(name="eric-5090", url="http://e:11434", engine="ollama"),
                    Host(name="m3-pro", url="http://m:4000", engine="openai-compat"),
                ]
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                screen: HostsScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.host_names == ["eric-5090", "m3-pro"]

        asyncio.run(_run())

    def test_escape_pops_back(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetConfigScreen)

        asyncio.run(_run())

    def test_plus_opens_add_modal(self) -> None:
        async def _run() -> None:
            from hermia.tui.screens.modals import AddHostModal
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                await pilot.press("plus")
                await pilot.pause()
                assert isinstance(pilot.app.screen, AddHostModal)

        asyncio.run(_run())
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement HostsScreen + AddHostModal**

`src/hermia/tui/screens/hosts.py`:
```python
"""Hosts drill — list, add, remove, probe state."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from hermia.tui.state import Host
from hermia.tui.widgets.breadcrumb import Breadcrumb


class HostsScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("plus", "add_host", "Add host", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cursor_idx: int = 0

    @property
    def app_config(self):
        return self.app.config  # type: ignore[attr-defined]

    @property
    def host_names(self) -> list[str]:
        return [h.name for h in self.app_config.hosts]

    def compose(self) -> ComposeResult:
        name = self.app_config.name or "(unnamed)"
        with Vertical():
            yield Breadcrumb(["hermia", "fleet", name, "hosts"])
            yield Static("", id="hosts-empty-notice")
            for i, h in enumerate(self.app_config.hosts):
                yield Static(self._row_text(h, i), id=f"host-row-{i}")

    def on_mount(self) -> None:
        self._refresh_empty_notice()

    def _row_text(self, host: Host, idx: int) -> str:
        cursor = "▸" if idx == self.cursor_idx else " "
        return f"{cursor} {host.name}    {host.url}    [{host.engine}]"

    def _refresh_empty_notice(self) -> None:
        notice = self.query_one("#hosts-empty-notice", Static)
        if self.app_config.hosts:
            notice.update("")
        else:
            notice.update("No hosts yet — press '+' to add one.")

    def action_cursor_prev(self) -> None:
        if self.cursor_idx > 0:
            self.cursor_idx -= 1

    def action_cursor_next(self) -> None:
        if self.cursor_idx < len(self.app_config.hosts) - 1:
            self.cursor_idx += 1

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_add_host(self) -> None:
        from hermia.tui.screens.modals import AddHostModal
        self.app.push_screen(AddHostModal(), self._on_host_added)

    def _on_host_added(self, host: Host | None) -> None:
        if host is None:
            return
        self.app_config.hosts.append(host)
        # Re-mount to show the new row.
        for child in list(self.children):
            child.remove()
        for w in self.compose():
            self.mount(w)
        self._refresh_empty_notice()
```

Add to `modals.py`:
```python
class AddHostModal(ModalScreen["Host | None"]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal"):
            yield Label("Add host:")
            yield Input(placeholder="name (eric-5090)", id="addhost-name")
            yield Input(placeholder="url (http://eric:11434)", id="addhost-url")
            yield Input(placeholder="engine (ollama / openai-compat)", id="addhost-engine")

    def on_mount(self) -> None:
        self.query_one("#addhost-name", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Submit on the engine field — last in the form.
        if event.input.id != "addhost-engine":
            return
        from hermia.tui.state import Host
        name = self.query_one("#addhost-name", Input).value.strip()
        url = self.query_one("#addhost-url", Input).value.strip()
        engine = (self.query_one("#addhost-engine", Input).value.strip()
                  or "ollama")
        if not name or not url:
            return
        self.dismiss(Host(name=name, url=url, engine=engine))

    def action_cancel(self) -> None:
        self.dismiss(None)
```

Update `config.py`'s `action_drill`:
```python
def action_drill(self) -> None:
    from hermia.tui.screens.hosts import HostsScreen
    from hermia.tui.screens.tests import TestsScreen
    if self.cursor_row == 0:
        self.app.push_screen(HostsScreen())
    elif self.cursor_row == 1:
        self.app.push_screen(TestsScreen())  # lands in Task 12
```

Task 10 will not import TestsScreen yet — defer that part until Task 12, or guard the import with a try/except. Cleanest: only push HostsScreen now, leave the tests-row enter as a no-op until Task 12:

```python
def action_drill(self) -> None:
    if self.cursor_row == 0:
        from hermia.tui.screens.hosts import HostsScreen
        self.app.push_screen(HostsScreen())
    # Tests drill lands in Task 12.
```

- [ ] **Step 4: Verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/screens/hosts.py src/hermia/tui/screens/modals.py src/hermia/tui/screens/config.py tests/unit/tui/screens/test_hosts.py
git commit -m "feat(tui): HostsScreen + AddHostModal; config wires Hosts drill"
```

---

## Task 11: screens/hosts.py — probe wiring + status badges

**Files:**
- Modify: `src/hermia/tui/screens/hosts.py`
- Test: `tests/unit/tui/screens/test_hosts.py` (add tests)

When the Hosts screen mounts (or after a host is added), kick off async probes via `probe_host()` for each host that hasn't been probed yet. Track per-host probe state ("idle" / "probing" / "ok" / "failed") and reflect it in the row.

For testing without a network: the probe layer takes a transport argument. We override `transport_for` via dependency injection — `HostsScreen` accepts a `transport_factory: Callable[[Host], Transport] | None = None`. In tests, pass a factory that returns FakeTransport instances. Production uses the real `transport_for`.

- [ ] **Step 1: Write the failing test**

```python
class TestHostsProbe:
    def test_probe_populates_models_and_flips_to_ok(self) -> None:
        from tests.fixtures.fake_transport import FakeTransport
        from hermia.tui.state import Host

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [Host(name="h1", url="http://h1", engine="ollama")]
                # Inject a factory that returns FakeTransport with two models.
                screen = HostsScreen(transport_factory=lambda h: FakeTransport(models=["a", "b"]))
                pilot.app.push_screen(screen)
                await pilot.pause()
                # Give the worker a beat to finish.
                for _ in range(20):
                    if screen.probe_state.get("h1") == "ok":
                        break
                    await pilot.pause()
                assert screen.probe_state["h1"] == "ok"
                assert [m.name for m in pilot.app.config.hosts[0].models] == ["a", "b"]

        asyncio.run(_run())

    def test_probe_timeout_flips_to_failed(self) -> None:
        from tests.fixtures.fake_transport import FakeTransport
        from hermia.tui.state import Host

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [Host(name="slow", url="http://slow", engine="ollama")]
                screen = HostsScreen(
                    transport_factory=lambda h: FakeTransport(models=["x"], delay_seconds=2.0),
                    probe_timeout=0.05,
                )
                pilot.app.push_screen(screen)
                await pilot.pause()
                for _ in range(20):
                    if screen.probe_state.get("slow") in ("ok", "failed"):
                        break
                    await pilot.pause()
                assert screen.probe_state["slow"] == "failed"
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

Add `from textual import work` import. Update `HostsScreen.__init__` to accept the factory and timeout. Add `self.probe_state: dict[str, str] = {}`. Add a Textual `@work` worker that runs `probe_host(...)` for each host and subscribes to `app.bus` if present (Plan 3 adds bus; for Plan 2 we can just await directly).

Actually for Plan 2 the simplest: in `on_mount`, call `self.app.call_later(self._probe_all)`. `_probe_all` is an async method that iterates hosts and awaits `probe_host` with a per-host SessionBus subscriber that updates `probe_state`. Even simpler: use a private bus per screen.

```python
import asyncio
from collections.abc import Callable
from textual import work

from hermia.tui.bus import SessionBus
from hermia.tui.probe import DEFAULT_PROBE_TIMEOUT_SECONDS, probe_host
from hermia.tui.transport_adapter import transport_for as default_transport_for

class HostsScreen(Screen[None]):
    def __init__(
        self,
        *,
        transport_factory: Callable[[Host], object] | None = None,
        probe_timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__()
        self.cursor_idx = 0
        self._make_transport = transport_factory or default_transport_for
        self._probe_timeout = probe_timeout
        self.probe_state: dict[str, str] = {}
        self._bus = SessionBus()

    def on_mount(self) -> None:
        self._refresh_empty_notice()
        self._start_probes()

    @work
    async def _start_probes(self) -> None:
        # Subscribe before publishing so events aren't dropped.
        async def listen() -> None:
            async for ev in self._bus.subscribe("probe.started"):
                self.probe_state[ev["host_name"]] = "probing"
            async for ev in self._bus.subscribe("probe.completed"):
                self.probe_state[ev["host_name"]] = "ok"
            async for ev in self._bus.subscribe("probe.failed"):
                self.probe_state[ev["host_name"]] = "failed"

        # Two separate listener tasks per topic.
        async def listen_one(topic: str, final_state: str) -> None:
            async for ev in self._bus.subscribe(topic):
                self.probe_state[ev["host_name"]] = final_state

        asyncio.create_task(listen_one("probe.started", "probing"))
        asyncio.create_task(listen_one("probe.completed", "ok"))
        asyncio.create_task(listen_one("probe.failed", "failed"))
        await asyncio.sleep(0)

        # Probe each host that hasn't been probed.
        for host in self.app_config.hosts:
            if self.probe_state.get(host.name):
                continue
            transport = self._make_transport(host)
            await probe_host(
                host,
                transport=transport,
                bus=self._bus,
                timeout=self._probe_timeout,
            )
```

(Remove the stray nested `listen()` helper that was an early draft above — keep only `listen_one` plus the loop.)

- [ ] **Step 4: Verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/screens/hosts.py tests/unit/tui/screens/test_hosts.py
git commit -m "feat(tui): HostsScreen — async probe wiring + probe_state map"
```

---

## Task 12: screens/host_models.py — single host model picker

**Files:**
- Create: `src/hermia/tui/screens/host_models.py`
- Modify: `src/hermia/tui/screens/hosts.py` (drill from a host row pushes HostModelsScreen)
- Test: `tests/unit/tui/screens/test_host_models.py`

After a host's probe completes, drilling into it shows its model list. Uses the foundation `DrillableList` widget. Selection state lives on `host.models[].selected`. Universal contract bindings: `/` (search), `space` (toggle), `a` / `n` (select all/none in current filter), `esc` (back).

`tab` cycling for the models filter axis (family / size / quant / modality) is deferred to v0.3 — for Plan 2 we ship the screen with `apply_query` from a SearchBar but no filter axis. The model rows include size + quant hints as their label text so `/` search still hits substring matches.

- [ ] **Step 1: Write the failing test**

`tests/unit/tui/screens/test_host_models.py`:
```python
"""Tests for HostModelsScreen — model picker for one host."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.host_models import HostModelsScreen
from hermia.tui.state import Host, ModelChoice


class TestHostModelsScreen:
    def test_renders_host_models(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = Host(name="h1", url="http://h1", engine="ollama",
                            models=[ModelChoice(name="m1"), ModelChoice(name="m2")])
                pilot.app.config.hosts = [host]
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                screen: HostModelsScreen = pilot.app.screen  # type: ignore[assignment]
                assert sorted(screen.visible_model_names) == ["m1", "m2"]

        asyncio.run(_run())

    def test_space_toggles_selection(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = Host(name="h1", url="http://h1", engine="ollama",
                            models=[ModelChoice(name="m1"), ModelChoice(name="m2")])
                pilot.app.config.hosts = [host]
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                await pilot.press("space")
                await pilot.pause()
                # First model is toggled on.
                assert host.models[0].selected is True

        asyncio.run(_run())

    def test_select_all_then_none(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = Host(name="h1", url="http://h1", engine="ollama",
                            models=[ModelChoice(name="m1"), ModelChoice(name="m2")])
                pilot.app.config.hosts = [host]
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                assert all(m.selected for m in host.models)
                await pilot.press("n")
                await pilot.pause()
                assert not any(m.selected for m in host.models)
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

```python
"""Single host's model picker — uses DrillableList + universal contract."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen

from hermia.tui.state import Host
from hermia.tui.widgets.breadcrumb import Breadcrumb
from hermia.tui.widgets.drillable_list import DrillableList, ListRow
from hermia.tui.widgets.search_bar import SearchBar


class HostModelsScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("space", "toggle", "Toggle", show=True),
        Binding("a", "select_all", "All", show=True),
        Binding("n", "select_none", "None", show=True),
        Binding("slash", "search_open", "Search", show=False),
    ]

    def __init__(self, *, host: Host) -> None:
        super().__init__()
        self._host = host

    @property
    def visible_model_names(self) -> list[str]:
        dl = self.query_one(DrillableList)
        return [r.label for r in dl.visible_rows]

    def compose(self) -> ComposeResult:
        name = self.app.config.name or "(unnamed)"  # type: ignore[attr-defined]
        with Vertical():
            yield Breadcrumb(["hermia", "fleet", name, "hosts", self._host.name])
            rows = [ListRow(id_=m.name, label=m.name) for m in self._host.models]
            yield DrillableList(rows)
            yield SearchBar()

    def on_mount(self) -> None:
        dl = self.query_one(DrillableList)
        # Pre-mark selected models.
        for m in self._host.models:
            if m.selected:
                dl._selected.add(m.name)
        dl._refresh()

    def on_drillable_list_toggled(self, event: DrillableList.Toggled) -> None:
        for m in self._host.models:
            if m.name == event.row_id:
                m.selected = not m.selected
                break

    def on_search_bar_query_changed(self, event: SearchBar.QueryChanged) -> None:
        self.query_one(DrillableList).apply_query(event.query)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_cursor_prev(self) -> None:
        self.query_one(DrillableList).cursor_prev()

    def action_cursor_next(self) -> None:
        self.query_one(DrillableList).cursor_next()

    def action_toggle(self) -> None:
        self.query_one(DrillableList).toggle()

    def action_select_all(self) -> None:
        dl = self.query_one(DrillableList)
        dl.select_all()
        for m in self._host.models:
            if m.name in dl._selected:
                m.selected = True

    def action_select_none(self) -> None:
        dl = self.query_one(DrillableList)
        dl.select_none()
        for m in self._host.models:
            m.selected = False

    def action_search_open(self) -> None:
        self.query_one(SearchBar).open()
```

Wire HostsScreen to push HostModelsScreen on enter:
```python
# In HostsScreen, add enter binding + drill action:
Binding("enter", "drill", "Drill", show=True),
...
def action_drill(self) -> None:
    from hermia.tui.screens.host_models import HostModelsScreen
    hosts = self.app_config.hosts
    if 0 <= self.cursor_idx < len(hosts):
        self.app.push_screen(HostModelsScreen(host=hosts[self.cursor_idx]))
```

- [ ] **Step 4: Verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/screens/host_models.py src/hermia/tui/screens/hosts.py tests/unit/tui/screens/test_host_models.py
git commit -m "feat(tui): HostModelsScreen — single-host model picker"
```

---

## Task 13: screens/tests.py — fleet-scoped multi-select with framework axis

**Files:**
- Create: `src/hermia/tui/screens/tests.py`
- Modify: `src/hermia/tui/screens/config.py` (wire Tests drill)
- Test: `tests/unit/tui/screens/test_tests.py`

Uses `DrillableList` + `SearchBar` + `FilterAxis`. The filter axis is "framework" with values ["OWASP", "ATLAS", "MAESTRO", "NIST"]. When the axis filter is set, only tests with that framework membership show; combined with `/` search.

Selection writes to `app.config.tests`.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for TestsScreen — fleet-scoped test multi-select with framework filter."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.tests import TestsScreen


class TestTestsScreen:
    def test_renders_all_tests_initially(self) -> None:
        from hermia.schemas import TEST_IDS

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                screen: TestsScreen = pilot.app.screen  # type: ignore[assignment]
                assert set(screen.visible_test_ids) == set(TEST_IDS)

        asyncio.run(_run())

    def test_select_all_populates_config_tests(self) -> None:
        from hermia.schemas import TEST_IDS

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                assert set(pilot.app.config.tests) == set(TEST_IDS)

        asyncio.run(_run())

    def test_search_filters_visible_tests(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                screen: TestsScreen = pilot.app.screen  # type: ignore[assignment]
                screen.apply_query("multiturn")
                await pilot.pause()
                ids = screen.visible_test_ids
                assert all("multiturn" in t for t in ids)
                assert len(ids) >= 1
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

```python
"""Fleet-scoped test picker with framework filter axis."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen

from hermia.tui.test_catalog import FRAMEWORKS, load_test_catalog
from hermia.tui.widgets.breadcrumb import Breadcrumb
from hermia.tui.widgets.drillable_list import DrillableList, ListRow
from hermia.tui.widgets.filter_axis import FilterAxis
from hermia.tui.widgets.search_bar import SearchBar


class TestsScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("space", "toggle", "Toggle", show=True),
        Binding("a", "select_all", "All", show=True),
        Binding("n", "select_none", "None", show=True),
        Binding("slash", "search_open", "Search", show=False),
        Binding("tab", "next_axis", "Filter axis", show=False),
        Binding("right", "next_value", "Next value", show=False),
        Binding("left", "prev_value", "Prev value", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._catalog = load_test_catalog()
        self._query: str = ""
        self._framework_filter: str = "All"

    @property
    def visible_test_ids(self) -> list[str]:
        dl = self.query_one(DrillableList)
        return [r.id_ for r in dl.visible_rows]

    def compose(self) -> ComposeResult:
        name = self.app.config.name or "(unnamed)"  # type: ignore[attr-defined]
        with Vertical():
            yield Breadcrumb(["hermia", "fleet", name, "tests"])
            yield FilterAxis({"framework": FRAMEWORKS})
            rows = [ListRow(id_=r.id, label=r.id) for r in self._catalog]
            yield DrillableList(rows)
            yield SearchBar()

    def on_mount(self) -> None:
        dl = self.query_one(DrillableList)
        # Mirror app.config.tests as the initial selection.
        for tid in self.app.config.tests:  # type: ignore[attr-defined]
            dl._selected.add(tid)
        dl._refresh()

    # --- helpers -----------------------------------------------------------

    def apply_query(self, q: str) -> None:
        self._query = q.strip().lower()
        self._reapply()

    def _reapply(self) -> None:
        dl = self.query_one(DrillableList)
        # Compute filtered rows by combining substring + framework membership.
        rows: list[ListRow] = []
        for rec in self._catalog:
            if self._query and self._query not in rec.id.lower():
                continue
            if self._framework_filter != "All" and not rec.is_in_framework(self._framework_filter):
                continue
            rows.append(ListRow(id_=rec.id, label=rec.id))
        dl._all_rows = rows
        dl.visible_rows = rows
        dl._cursor_idx = 0 if rows else -1
        dl._refresh()

    # --- event handlers ----------------------------------------------------

    def on_search_bar_query_changed(self, event: SearchBar.QueryChanged) -> None:
        self.apply_query(event.query)

    def on_filter_axis_changed(self, event: FilterAxis.Changed) -> None:
        self._framework_filter = event.value or "All"
        self._reapply()

    def on_drillable_list_toggled(self, event: DrillableList.Toggled) -> None:
        cfg_tests = list(self.app.config.tests)  # type: ignore[attr-defined]
        if event.row_id in cfg_tests:
            cfg_tests.remove(event.row_id)
        else:
            cfg_tests.append(event.row_id)
        self.app.config.tests = cfg_tests  # type: ignore[attr-defined]

    # --- action_* wrappers -------------------------------------------------

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_cursor_prev(self) -> None:
        self.query_one(DrillableList).cursor_prev()

    def action_cursor_next(self) -> None:
        self.query_one(DrillableList).cursor_next()

    def action_toggle(self) -> None:
        self.query_one(DrillableList).toggle()

    def action_select_all(self) -> None:
        dl = self.query_one(DrillableList)
        dl.select_all()
        # Sync app.config.tests.
        self.app.config.tests = sorted({  # type: ignore[attr-defined]
            *self.app.config.tests,  # type: ignore[attr-defined]
            *(r.id_ for r in dl.visible_rows),
        })

    def action_select_none(self) -> None:
        dl = self.query_one(DrillableList)
        visible = {r.id_ for r in dl.visible_rows}
        dl.select_none()
        self.app.config.tests = [t for t in self.app.config.tests  # type: ignore[attr-defined]
                                 if t not in visible]

    def action_search_open(self) -> None:
        self.query_one(SearchBar).open()

    def action_next_axis(self) -> None:
        self.query_one(FilterAxis).next_axis()

    def action_next_value(self) -> None:
        self.query_one(FilterAxis).next_value()

    def action_prev_value(self) -> None:
        self.query_one(FilterAxis).prev_value()
```

Wire `config.py`'s `action_drill` to push TestsScreen for cursor_row == 1:
```python
def action_drill(self) -> None:
    if self.cursor_row == 0:
        from hermia.tui.screens.hosts import HostsScreen
        self.app.push_screen(HostsScreen())
    elif self.cursor_row == 1:
        from hermia.tui.screens.tests import TestsScreen
        self.app.push_screen(TestsScreen())
```

- [ ] **Step 4: Verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add src/hermia/tui/screens/tests.py src/hermia/tui/screens/config.py tests/unit/tui/screens/test_tests.py
git commit -m "feat(tui): TestsScreen — fleet-scoped multi-select with framework filter"
```

---

## Task 14: End-to-end picker Pilot smoke test

**Files:**
- Create: `tests/unit/tui/test_picker_e2e.py`

One Pilot test per major flow, asserting the picker writes the right `app.config` state.

- [ ] **Step 1: Write the test**

```python
"""End-to-end picker smoke — drives the Launch ▸ Config ▸ drills via Pilot."""
import asyncio
from pathlib import Path

from hermia.schemas import TEST_IDS
from hermia.tui.app import HermiaApp
from hermia.tui.fleet_io import fleet_path, save_fleet
from hermia.tui.screens.config import FleetConfigScreen
from hermia.tui.screens.launch import LaunchScreen
from hermia.tui.state import FleetConfig, Host, ModelChoice


class TestPickerE2E:
    def test_quick_local_flow_ends_in_config_screen_with_pre_populated_config(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                # Launch → Quick local run (third entry).
                await pilot.press("down", "down", "enter")
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetConfigScreen)
                cfg = pilot.app.config
                assert cfg.name == "quick-local"
                assert cfg.hosts[0].url == "http://localhost:11434"
                assert cfg.tests == list(TEST_IDS)

        asyncio.run(_run())

    def test_load_existing_flow_into_config(self, tmp_path, monkeypatch) -> None:
        save_fleet(
            FleetConfig(
                name="loaded",
                hosts=[Host(name="h", url="http://h", engine="ollama",
                            models=[ModelChoice(name="m", selected=True)])],
                tests=["security-boundary"],
            ),
            root=tmp_path,
        )
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                # Launch → Load existing (first entry) → enter on the only fleet.
                await pilot.press("enter")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetConfigScreen)
                assert pilot.app.config.name == "loaded"
                assert pilot.app.config.tests == ["security-boundary"]

        asyncio.run(_run())

    def test_save_via_s_writes_yaml(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("down")  # New fleet
                await pilot.press("enter")
                await pilot.pause()
                pilot.app.config.name = "smoke"
                await pilot.press("s")
                await pilot.pause()
                assert fleet_path("smoke").exists()

        asyncio.run(_run())
```

- [ ] **Step 2: Verify GREEN**

```bash
pytest tests/unit/tui/test_picker_e2e.py -v --no-cov
```

If a flow fails, fix the underlying screen — do NOT bypass the test.

- [ ] **Step 3: Final sweep**

```bash
pytest --no-cov
ruff check src/hermia/tui/ tests/unit/tui/ tests/fixtures/
mypy src/hermia/tui/
```

All three must pass. Fix anything.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/tui/test_picker_e2e.py
git commit -m "test(tui): end-to-end picker smoke — Launch → drills → save"
```

---

## Plan Close

- [ ] **C1: Push and open PR to dev**

```bash
git push -u origin feature/fleet-tui-picker
gh pr create --base dev --title "feat(tui): picker screens — Launch / Config / Hosts / Models / Tests" --body "$(cat <<'EOF'
## Summary

Picker flow for the Fleet TUI per [docs/superpowers/specs/2026-06-18-fleet-tui-design.md](../specs/2026-06-18-fleet-tui-design.md). Builds Launch, Fleet Config, Hosts, Host Models, and Tests screens on top of the Plan 1 foundation. Single fleet config in memory, save/load to `fleets/<name>.yaml`, Quick Local Run smart-default for the laptop-user path.

Runs via `python -m hermia.tui` — separate from the existing `hermia` CLI. Plan 3 (runner) wires the run path; Plan 4 cuts over the main entry and deletes `screens.py`.

## Test plan

- [ ] `pytest tests/unit/tui/` — all green
- [ ] `pytest` — full suite green
- [ ] `ruff check src/hermia/tui/ tests/unit/tui/ tests/fixtures/` — clean
- [ ] `mypy src/hermia/tui/` — clean
- [ ] Manual: `python -m hermia.tui` — walk Quick Local Run → save → reload → exit

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **C2: Post `/gemini review`**

```bash
gh pr comment <PR-number> --body "/gemini review"
```

Address HIGH-priority findings per AGENTS.md rule 9.

- [ ] **C3: bd note on hermia-86g**

```bash
bd note hermia-86g "Plan 2 (picker screens) merged to dev. Plan 3 (runner) next."
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Implemented in this plan |
|---|---|
| §1 module layout (`screens/`, app.py) | Tasks 4-13 |
| §2 hosts.yaml seed source | Task 10 |
| §3 test catalog with framework tags | Task 1 |
| §4 transport adapter (engine dispatch) | Task 2 |
| §5 universal navigation contract (per-screen bindings) | Tasks 5-13 |
| §5 Quick Local Run smart-default | Task 7 |
| §5 unsaved-changes indicator | Task 9 |
| §5 breadcrumb header | Tasks 3, 8-13 |
| §6 probe failure surfaces wired to UI badges | Task 11 |

Out of scope (Plans 3-4):
- Runner screens (L1, L2, L3) — Plan 3
- Unsaved-changes confirm modal at app close — Plan 4 ties this into app.py rewire
- screens.py deletion + app.py rewire — Plan 4
- Models drill `tab` filter axis (family/size/quant/modality) — v0.3 follow-up

**2. Placeholder scan:** Every task contains real code. Test-stub branches in Task 5 are explicitly marked with `@pytest.mark.xfail` and the marker is removed in Task 5 Step 5.

**3. Type consistency:** `FleetConfig` / `Host` / `ModelChoice` signatures match Plan 1. `SessionBus` usage in Task 11 matches Plan 1's API. `DrillableList` / `SearchBar` / `FilterAxis` / `Breadcrumb` usages match their defined widget APIs.

**4. Ambiguity:** Task 11's screen-internal SessionBus is intentionally per-screen for Plan 2; Plan 3 introduces a shared `app.bus` for runner ↔ screens. Task 12 acknowledges the missing models filter axis as v0.3 deferred work. Task 13 wires both Hosts and Tests drills from FleetConfigScreen in the same commit since both depend on FleetConfigScreen's `action_drill`.
