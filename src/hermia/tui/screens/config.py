"""Fleet Config screen — home base of the picker drill.

Shows two drillable rows (Hosts, Tests), a run-plan trial estimate, and
the breadcrumb header. Future tasks (10, 13) wire enter-on-row to push the
child drills; Task 9 wires save / unsaved-changes indicator.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from hermia.tui.state import FleetConfig
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
        self.dirty: bool = False
        # Cached rendered text so test properties don't depend on Textual's
        # internal Static.renderable API (which changed between versions).
        self._hosts_summary_str: str = ""
        self._tests_summary_str: str = ""
        self._run_plan_str: str = ""

    @property
    def app_config(self) -> FleetConfig:
        return self.app.config  # type: ignore[attr-defined,no-any-return]

    @property
    def breadcrumb_text(self) -> str:
        return self.query_one(Breadcrumb).text

    @property
    def summary_text(self) -> str:
        return f"{self._hosts_summary_str} {self._tests_summary_str}"

    @property
    def run_plan_text(self) -> str:
        return self._run_plan_str

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Breadcrumb(self._breadcrumb_segments())
            yield Static("", id="config-summary-hosts")
            yield Static("", id="config-summary-tests")
            yield Static("", id="config-run-plan")

    def on_mount(self) -> None:
        self._refresh()

    def on_screen_resume(self) -> None:
        # Pop-back from a child drill (Hosts / Tests) may have toggled
        # selections; mark_dirty() propagation handles inline updates, but
        # this is the belt-and-braces refresh per spec §5 lifecycle.
        self._refresh()

    def _breadcrumb_segments(self) -> list[str]:
        name = self.app_config.name or "(unnamed)"
        suffix = " [unsaved changes]" if self.dirty else ""
        return ["hermia", "fleet", f"{name}{suffix}"]

    def _refresh(self) -> None:
        cfg = self.app_config
        n_hosts = len(cfg.hosts)
        n_models_total = sum(sum(1 for m in h.models if m.selected) for h in cfg.hosts)
        n_tests = len(cfg.tests)
        trials = n_models_total * n_tests
        self.query_one(Breadcrumb).set_segments(self._breadcrumb_segments())
        h_label = "host" if n_hosts == 1 else "hosts"
        t_label = "test" if n_tests == 1 else "tests"
        cursor = "▸" if self.cursor_row == 0 else " "
        self._hosts_summary_str = (
            f"{cursor} Hosts        {n_hosts} {h_label} · {n_models_total} model trials"
        )
        self.query_one("#config-summary-hosts", Static).update(self._hosts_summary_str)
        cursor = "▸" if self.cursor_row == 1 else " "
        self._tests_summary_str = f"{cursor} Tests        {n_tests} {t_label}"
        self.query_one("#config-summary-tests", Static).update(self._tests_summary_str)
        self._run_plan_str = f"Run plan: {trials} trials"
        self.query_one("#config-run-plan", Static).update(self._run_plan_str)

    def mark_dirty(self) -> None:
        """Called by child screens when they mutate app.config."""
        self.dirty = True
        self._refresh()

    def action_cursor_prev(self) -> None:
        if self.cursor_row > 0:
            self.cursor_row -= 1
            self._refresh()

    def action_cursor_next(self) -> None:
        if self.cursor_row < len(self.ROWS) - 1:
            self.cursor_row += 1
            self._refresh()

    def action_drill(self) -> None:
        if self.cursor_row == 0:
            from hermia.tui.screens.hosts import HostsScreen
            self.app.push_screen(HostsScreen())
        elif self.cursor_row == 1:
            from hermia.tui.screens.tests import TestsScreen
            self.app.push_screen(TestsScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_save(self) -> None:
        from hermia.tui.fleet_io import save_fleet
        from hermia.tui.screens.modals import FleetNameModal
        if not self.app_config.name:
            self.app.push_screen(FleetNameModal(), self._on_name_chosen)
            return
        # save_fleet can raise on permission denied, disk full, etc. Notify
        # rather than crash the TUI — dirty stays set so the user can retry.
        try:
            save_fleet(self.app_config)
        except Exception as exc:
            self.app.notify(f"Failed to save fleet: {exc}", severity="error")
            return
        self.dirty = False
        self._refresh()
        self.app.notify(f"Fleet '{self.app_config.name}' saved.")

    def _on_name_chosen(self, name: str | None) -> None:
        if not name:
            return
        self.app_config.name = name
        # Recurse — name is now set so the save branch runs.
        self.action_save()

    def action_load(self) -> None:
        # Pop back to Launch and re-enter Load mode (Task 9-ish behavior).
        self.app.pop_screen()

    def action_run(self) -> None:
        from pathlib import Path

        from hermia.tui.runner_backend import TuiRunner
        from hermia.tui.screens.runner import RunnerScreen
        results_dir: Path | None = None
        if self.app_config.name:
            # Strip any directory components from the fleet name before using
            # it as a path segment (guards against '../' traversal in YAML).
            safe_name = Path(self.app_config.name).name or "unnamed"
            results_dir = Path("results") / safe_name
            # mkdir is deferred to _write_result so no empty dir is created
            # if the run is aborted before writing any results.
        runner = TuiRunner(
            config=self.app_config,
            bus=self.app.bus,  # type: ignore[attr-defined]
            results_dir=results_dir,
        )
        self.app.push_screen(RunnerScreen(runner=runner))
