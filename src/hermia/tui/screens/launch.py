"""Launch screen — three entries: Load existing fleet / New fleet / Quick local run.

Load existing scans fleets/*.yaml and lists them; enter on a fleet loads it
into app.config and pushes FleetConfigScreen.
New fleet resets app.config to an empty FleetConfig(name="") and pushes
FleetConfigScreen.
Quick local run pre-fills app.config with localhost:11434 (engine=ollama)
and the default test set (all TEST_IDS), then pushes FleetConfigScreen.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from hermia.tui.state import FleetConfig, Host


@dataclass
class LaunchEntry:
    id: str
    label: str


class LaunchScreen(Screen[None]):
    BINDINGS = [
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("enter", "select", "Select", show=True),
        Binding("escape", "back_to_home", "Back", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    HOME_ENTRIES: list[LaunchEntry] = [
        LaunchEntry(id="load", label="Load existing fleet"),
        LaunchEntry(id="new", label="New fleet"),
        LaunchEntry(id="quick", label="Quick local run"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.mode: str = "home"  # "home" or "load"
        self.entries: list[LaunchEntry] = list(self.HOME_ENTRIES)
        self.cursor_index: int = 0
        # Render counter — appended to dynamic IDs so a pending AwaitRemove
        # from the previous render doesn't clash with the new mount.
        self._render_seq: int = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="launch-root"):
            yield Static("Welcome to hermia fleet", id="launch-title")

    def on_mount(self) -> None:
        self._rerender()

    def _row_text(self, entry: LaunchEntry, idx: int) -> str:
        cursor = "▸ " if idx == self.cursor_index else "  "
        return f"  {cursor}{entry.label}"

    def _rerender(self) -> None:
        root = self.query_one("#launch-root", Vertical)
        # Update title in place rather than re-mounting.
        title = root.query_one("#launch-title", Static)
        title.update("Welcome to hermia fleet" if self.mode == "home" else "Load fleet")
        # Remove old dynamic children (everything except the title).
        for child in list(root.children):
            if child.id == "launch-title":
                continue
            child.remove()
        # Mount fresh dynamic children with seq-bumped IDs so any AwaitRemove
        # in flight from the previous _rerender can't collide.
        self._render_seq += 1
        seq = self._render_seq
        if not self.entries:
            root.mount(Static("No saved fleets in fleets/", id="launch-empty-notice"))
            return
        for i, entry in enumerate(self.entries):
            root.mount(Static(self._row_text(entry, i), id=f"launch-row-{seq}-{i}"))

    def _scan_fleets(self) -> list[LaunchEntry]:
        fleets_dir = Path("fleets")
        # `is_dir()` over `exists()` — defensive against a regular file named
        # `fleets` shadowing the expected directory.
        if not fleets_dir.is_dir():
            return []
        return [LaunchEntry(id=f.stem, label=f.stem) for f in sorted(fleets_dir.glob("*.yaml"))]

    # ── Navigation ────────────────────────────────────────────────────────

    def action_cursor_prev(self) -> None:
        if self.cursor_index > 0:
            self.cursor_index -= 1
            self._rerender()

    def action_cursor_next(self) -> None:
        if self.cursor_index < len(self.entries) - 1:
            self.cursor_index += 1
            self._rerender()

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

    def action_back_to_home(self) -> None:
        if self.mode == "load":
            self.mode = "home"
            self.entries = list(self.HOME_ENTRIES)
            self.cursor_index = 0
            self._rerender()

    def action_quit(self) -> None:
        self.app.exit()

    # ── Mode transitions ──────────────────────────────────────────────────

    def _enter_load_mode(self) -> None:
        self.mode = "load"
        self.entries = self._scan_fleets()
        self.cursor_index = 0 if self.entries else -1
        self._rerender()

    def _load_selected_fleet(self) -> None:
        if self.cursor_index < 0:
            return
        from hermia.tui.fleet_io import fleet_path, load_fleet
        from hermia.tui.screens.config import FleetConfigScreen
        entry = self.entries[self.cursor_index]
        path = fleet_path(entry.id)
        # load_fleet can raise FileNotFoundError, yaml.YAMLError, KeyError,
        # TypeError on malformed YAML or missing fields. Notify rather than
        # crash the TUI — user stays on the Launch screen and can pick again.
        try:
            self.app.config = load_fleet(path)  # type: ignore[attr-defined]
        except Exception as exc:
            self.app.notify(f"Failed to load fleet '{entry.id}': {exc}", severity="error")
            return
        self.app.push_screen(FleetConfigScreen())

    def _enter_new_fleet(self) -> None:
        from hermia.tui.screens.config import FleetConfigScreen
        self.app.config = FleetConfig(name="")  # type: ignore[attr-defined]
        self.app.push_screen(FleetConfigScreen())

    def _enter_quick_local(self) -> None:
        from hermia.schemas import TEST_IDS
        from hermia.tui.screens.config import FleetConfigScreen
        self.app.config = FleetConfig(  # type: ignore[attr-defined]
            name="quick-local",
            hosts=[Host(name="local", url="http://localhost:11434", engine="ollama")],
            tests=list(TEST_IDS),
        )
        self.app.push_screen(FleetConfigScreen())
