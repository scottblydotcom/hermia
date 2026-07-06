# TUI Footer & Header Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Textual's built-in `Footer` widget to all 8 non-modal TUI screens so key bindings are visible at the bottom of every screen.

**Architecture:** Each screen file gets one new import (`Footer` from `textual.widgets`) and one new `yield Footer()` as the last item in `compose()`. No shared base class or custom widget needed. Header treatment is deferred until after footers are visible — the existing `Breadcrumb` widget already serves as the header.

**Tech Stack:** Python, Textual ≥0.80, pytest, asyncio (stdlib, no pytest-asyncio)

---

## Files Modified

| File | Change |
|------|--------|
| `src/hermia/tui/screens/launch.py` | Add `Footer` import + `yield Footer()` |
| `src/hermia/tui/screens/config.py` | Add `Footer` import + `yield Footer()` |
| `src/hermia/tui/screens/hosts.py` | Add `Footer` import + `yield Footer()` |
| `src/hermia/tui/screens/host_models.py` | Add `Footer` import + `yield Footer()` |
| `src/hermia/tui/screens/tests.py` | Add `Footer` import + `yield Footer()` |
| `src/hermia/tui/screens/runner.py` | Add `Footer` import + `yield Footer()` |
| `src/hermia/tui/screens/runner_trials.py` | Add `Footer` import + `yield Footer()` |
| `src/hermia/tui/screens/runner_detail.py` | Add `Footer` import + `yield Footer()` |
| `tests/unit/tui/screens/test_launch.py` | Add `test_footer_present` |
| `tests/unit/tui/screens/test_config.py` | Add `test_footer_present` |
| `tests/unit/tui/screens/test_hosts.py` | Add `test_footer_present` |
| `tests/unit/tui/screens/test_host_models.py` | Add `test_footer_present` |
| `tests/unit/tui/screens/test_tests.py` | Add `test_footer_present` |
| `tests/unit/tui/screens/test_runner.py` | Add `test_footer_present` |
| `tests/unit/tui/screens/test_runner_trials.py` | Add `test_footer_present` |

(No separate runner_detail test file exists — verified manually in Task 3.)

---

## Task 1: LaunchScreen footer

**Files:**
- Modify: `src/hermia/tui/screens/launch.py:19`
- Modify: `tests/unit/tui/screens/test_launch.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/tui/screens/test_launch.py`:

```python
class TestLaunchFooter:
    def test_footer_present(self) -> None:
        from textual.widgets import Footer

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                screen = pilot.app.screen
                assert screen.query_one(Footer) is not None

        asyncio.run(_run())
```

- [ ] **Step 2: Run the failing test**

```bash
pytest tests/unit/tui/screens/test_launch.py::TestLaunchFooter::test_footer_present -v
```

Expected: FAIL — `NoMatches` (no Footer widget in the DOM)

- [ ] **Step 3: Add Footer import to launch.py**

In `src/hermia/tui/screens/launch.py`, change:

```python
from textual.widgets import Static
```

to:

```python
from textual.widgets import Footer, Static
```

- [ ] **Step 4: Add `yield Footer()` to LaunchScreen.compose()**

In `src/hermia/tui/screens/launch.py`, the `compose()` method currently ends inside a `with Vertical(id="launch-root"):` block after `yield Static("Welcome to hermia fleet", id="launch-title")`. Add `yield Footer()` **outside** the `Vertical` block (after it), so it spans the full width:

```python
    def compose(self) -> ComposeResult:
        with Vertical(id="launch-root"):
            yield Static("Welcome to hermia fleet", id="launch-title")
        yield Footer()
```

- [ ] **Step 5: Run the test to confirm it passes**

```bash
pytest tests/unit/tui/screens/test_launch.py::TestLaunchFooter::test_footer_present -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/hermia/tui/screens/launch.py tests/unit/tui/screens/test_launch.py
git commit -m "feat(tui): add Footer to LaunchScreen"
```

---

## Task 2: Picker screens footer (config, hosts, host_models, tests)

**Files:**
- Modify: `src/hermia/tui/screens/config.py:13`
- Modify: `src/hermia/tui/screens/hosts.py:22`
- Modify: `src/hermia/tui/screens/host_models.py` (no `Static` import — add `Footer` standalone)
- Modify: `src/hermia/tui/screens/tests.py` (no `Static` import — add `Footer` standalone)
- Modify: `tests/unit/tui/screens/test_config.py`
- Modify: `tests/unit/tui/screens/test_hosts.py`
- Modify: `tests/unit/tui/screens/test_host_models.py`
- Modify: `tests/unit/tui/screens/test_tests.py`

- [ ] **Step 1: Write the 4 failing tests**

Append to `tests/unit/tui/screens/test_config.py`:

```python
class TestFleetConfigFooter:
    def test_footer_present(self) -> None:
        import asyncio
        from textual.widgets import Footer
        from hermia.tui.app import HermiaApp
        from hermia.tui.screens.config import FleetConfigScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                assert pilot.app.screen.query_one(Footer) is not None

        asyncio.run(_run())
```

Append to `tests/unit/tui/screens/test_hosts.py`:

```python
class TestHostsFooter:
    def test_footer_present(self) -> None:
        import asyncio
        from textual.widgets import Footer
        from hermia.tui.app import HermiaApp
        from hermia.tui.screens.hosts import HostsScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                assert pilot.app.screen.query_one(Footer) is not None

        asyncio.run(_run())
```

Append to `tests/unit/tui/screens/test_host_models.py`:

```python
class TestHostModelsFooter:
    def test_footer_present(self) -> None:
        import asyncio
        from textual.widgets import Footer
        from hermia.tui.app import HermiaApp
        from hermia.tui.screens.host_models import HostModelsScreen
        from hermia.tui.state import Host

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = Host(name="local", url="http://localhost:11434")
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                assert pilot.app.screen.query_one(Footer) is not None

        asyncio.run(_run())
```

Append to `tests/unit/tui/screens/test_tests.py`:

```python
class TestTestsScreenFooter:
    def test_footer_present(self) -> None:
        import asyncio
        from textual.widgets import Footer
        from hermia.tui.app import HermiaApp
        from hermia.tui.screens.tests import TestsScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                assert pilot.app.screen.query_one(Footer) is not None

        asyncio.run(_run())
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/unit/tui/screens/test_config.py::TestFleetConfigFooter \
       tests/unit/tui/screens/test_hosts.py::TestHostsFooter \
       tests/unit/tui/screens/test_host_models.py::TestHostModelsFooter \
       tests/unit/tui/screens/test_tests.py::TestTestsScreenFooter -v
```

Expected: All 4 FAIL — `NoMatches`

- [ ] **Step 3: Add Footer to config.py**

Change `from textual.widgets import Static` to `from textual.widgets import Footer, Static`.

`compose()` currently ends after `yield Static("", id="config-run-plan")` inside a `with Vertical():` block. Add `yield Footer()` after the `Vertical` block:

```python
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Breadcrumb(self._breadcrumb_segments())
            yield Static("", id="config-summary-hosts")
            yield Static("", id="config-summary-tests")
            yield Static("", id="config-run-plan")
        yield Footer()
```

- [ ] **Step 4: Add Footer to hosts.py**

Change `from textual.widgets import Static` to `from textual.widgets import Footer, Static`.

`compose()` is inside `with Vertical(id="hosts-root"):`. Add `yield Footer()` after the block:

```python
    def compose(self) -> ComposeResult:
        name = self.app_config.name or "(unnamed)"
        with Vertical(id="hosts-root"):
            yield Breadcrumb(["hermia", "fleet", name, "hosts"])
        yield Footer()
```

- [ ] **Step 5: Add Footer to host_models.py**

There is no existing `Static` import in `host_models.py`. Add a new import line after the existing `textual.screen` import:

```python
from textual.widgets import Footer
```

`compose()` ends with `yield SearchBar()` inside `with Vertical():`. Add `yield Footer()` after the block:

```python
    def compose(self) -> ComposeResult:
        name = self.app.config.name or "(unnamed)"
        with Vertical():
            yield Breadcrumb(["hermia", "fleet", name, "hosts", self._host.name])
            rows = [ListRow(id_=m.name, label=m.name) for m in self._host.models]
            yield DrillableList(rows)
            yield SearchBar()
        yield Footer()
```

- [ ] **Step 6: Add Footer to tests.py**

There is no existing `Static` import in `tests.py`. Add after the existing `textual.screen` import:

```python
from textual.widgets import Footer
```

`compose()` ends with `yield SearchBar()` inside `with Vertical():`. Add `yield Footer()` after the block:

```python
    def compose(self) -> ComposeResult:
        name = self.app.config.name or "(unnamed)"
        with Vertical():
            yield Breadcrumb(["hermia", "fleet", name, "tests"])
            yield FilterAxis({"framework": FRAMEWORKS})
            rows = [ListRow(id_=r.id, label=r.id) for r in self._catalog]
            yield DrillableList(rows)
            yield SearchBar()
        yield Footer()
```

- [ ] **Step 7: Run the 4 tests to confirm they pass**

```bash
pytest tests/unit/tui/screens/test_config.py::TestFleetConfigFooter \
       tests/unit/tui/screens/test_hosts.py::TestHostsFooter \
       tests/unit/tui/screens/test_host_models.py::TestHostModelsFooter \
       tests/unit/tui/screens/test_tests.py::TestTestsScreenFooter -v
```

Expected: All 4 PASS

- [ ] **Step 8: Commit**

```bash
git add src/hermia/tui/screens/config.py \
        src/hermia/tui/screens/hosts.py \
        src/hermia/tui/screens/host_models.py \
        src/hermia/tui/screens/tests.py \
        tests/unit/tui/screens/test_config.py \
        tests/unit/tui/screens/test_hosts.py \
        tests/unit/tui/screens/test_host_models.py \
        tests/unit/tui/screens/test_tests.py
git commit -m "feat(tui): add Footer to picker screens (config, hosts, host_models, tests)"
```

---

## Task 3: Runner screens footer (runner, runner_trials, runner_detail)

**Files:**
- Modify: `src/hermia/tui/screens/runner.py:17`
- Modify: `src/hermia/tui/screens/runner_trials.py:17`
- Modify: `src/hermia/tui/screens/runner_detail.py:15`
- Modify: `tests/unit/tui/screens/test_runner.py`
- Modify: `tests/unit/tui/screens/test_runner_trials.py`

Note: There is no `test_runner_detail.py` — runner_detail footer is covered by the full suite run in Task 4.

- [ ] **Step 1: Write the 2 failing tests**

Append to `tests/unit/tui/screens/test_runner.py`:

```python
class TestRunnerFooter:
    def test_footer_present(self) -> None:
        import asyncio
        from textual.widgets import Footer
        from hermia.tui.app import HermiaApp
        from hermia.tui.screens.runner import RunnerScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()
                assert pilot.app.screen.query_one(Footer) is not None

        asyncio.run(_run())
```

Append to `tests/unit/tui/screens/test_runner_trials.py`:

```python
class TestRunnerTrialsFooter:
    def test_footer_present(self) -> None:
        import asyncio
        from textual.widgets import Footer
        from hermia.tui.app import HermiaApp
        from hermia.tui.screens.runner_trials import RunnerTrialsScreen
        from hermia.tui.state import Host

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = Host(name="local", url="http://localhost:11434")
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()
                assert pilot.app.screen.query_one(Footer) is not None

        asyncio.run(_run())
```

- [ ] **Step 2: Run the failing tests**

```bash
pytest tests/unit/tui/screens/test_runner.py::TestRunnerFooter \
       tests/unit/tui/screens/test_runner_trials.py::TestRunnerTrialsFooter -v
```

Expected: Both FAIL — `NoMatches`

- [ ] **Step 3: Add Footer to runner.py**

Change `from textual.widgets import Static` to `from textual.widgets import Footer, Static`.

`compose()` is inside `with Vertical(id="runner-root"):`. Add `yield Footer()` after the block:

```python
    def compose(self) -> ComposeResult:
        name = self.app_config.name or "(unnamed)"
        with Vertical(id="runner-root"):
            yield Breadcrumb(["hermia", "fleet", name, "runner"])
            yield Static("", id="runner-progress")
        yield Footer()
```

- [ ] **Step 4: Add Footer to runner_trials.py**

Change `from textual.widgets import Static` to `from textual.widgets import Footer, Static`.

`compose()` is inside `with Vertical(id="trials-root"):`. Add `yield Footer()` after the block:

```python
    def compose(self) -> ComposeResult:
        name = self.app_config.name or "(unnamed)"
        with Vertical(id="trials-root"):
            yield Breadcrumb(["hermia", "fleet", name, "runner", self._host.name])
        yield Footer()
```

- [ ] **Step 5: Add Footer to runner_detail.py**

Change `from textual.widgets import Static` to `from textual.widgets import Footer, Static`.

`compose()` is inside `with Vertical():`. Add `yield Footer()` after the block:

```python
    def compose(self) -> ComposeResult:
        t = self._trial
        with Vertical():
            yield Breadcrumb(["hermia", "runner", t.model_name, t.test_id])
            yield Static("", id="detail-summary")
            yield Static("", id="detail-output")
        yield Footer()
```

- [ ] **Step 6: Run the 2 tests to confirm they pass**

```bash
pytest tests/unit/tui/screens/test_runner.py::TestRunnerFooter \
       tests/unit/tui/screens/test_runner_trials.py::TestRunnerTrialsFooter -v
```

Expected: Both PASS

- [ ] **Step 7: Commit**

```bash
git add src/hermia/tui/screens/runner.py \
        src/hermia/tui/screens/runner_trials.py \
        src/hermia/tui/screens/runner_detail.py \
        tests/unit/tui/screens/test_runner.py \
        tests/unit/tui/screens/test_runner_trials.py
git commit -m "feat(tui): add Footer to runner screens (runner, runner_trials, runner_detail)"
```

---

## Task 4: Full suite regression + manual verification

- [ ] **Step 1: Run the full test suite**

```bash
pytest
```

Expected: All tests pass (previously 1704 passing). Fix any regressions before proceeding.

- [ ] **Step 2: Run the app and verify footers**

```bash
hermia --fleet
```

Walk through all 8 screens and confirm the footer key-hint bar appears at the bottom of each:
- LaunchScreen: `↵ Select`  `Q Quit`
- FleetConfigScreen: `Esc Back`  `↵ Drill`  `S Save`
- HostsScreen: `Esc Back`  `+ Add host`  `↵ Models`
- HostModelsScreen: `Esc Back`  `Space Toggle`  `A All`  `N None`
- TestsScreen: `Esc Back`  `Space Toggle`  `A All`  `N None`
- RunnerScreen: `Esc Back`  `↵ Trials`
- RunnerTrialsScreen: `Esc Back`  `↵ Detail`
- RunnerDetailScreen: `Esc Back`

- [ ] **Step 3: Decide on header treatment**

With footers in place, assess whether Textual's `Header()` widget adds value above the existing `Breadcrumb`. The `Breadcrumb` already provides navigation context. Options:
- If `Header()` adds useful app-level context (app name, mode) without crowding: add it to all screens using the same pattern as `Footer()`.
- If it duplicates or crowds the `Breadcrumb`: skip it and close this feature as footer-only.

Document the decision as a `bd note` on the active bead before closing.
