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
    def app_config(self):
        return self.app.config  # type: ignore[attr-defined]

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
        # Hosts and Tests screens land in Tasks 10 and 13.
        pass

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_save(self) -> None:
        # Wired in Task 9.
        pass

    def action_load(self) -> None:
        # Pop back to Launch and re-enter Load mode (Task 9-ish behavior).
        self.app.pop_screen()

    def action_run(self) -> None:
        # Plan 3 wires this to the runner.
        pass
