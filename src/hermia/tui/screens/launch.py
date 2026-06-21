"""Launch screen — three entries: Load existing fleet / New fleet / Quick local run.

Quick local run pre-fills a single-host config (http://localhost:11434) and
jumps to the Fleet Config screen on that host. New fleet opens an empty
Fleet Config. Load enters a sub-mode listing fleets/*.yaml and loads the
selected one on enter.
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
        _ = entry  # noqa: F841

    def action_quit(self) -> None:
        self.app.exit()
