"""DrillableList — virtual-scroll list with the universal navigation contract.

Every drill screen in the Fleet TUI uses this widget. Public API:

    cursor_prev() / cursor_next()  — move cursor up/down
    drill()                        — emit Drill(row_id) for the cursor row
    toggle()                       — flip selection of the cursor row, emit Toggled
    select_all() / select_none()   — toggle/clear all rows in the *current filter*
    apply_query(query: str)        — live-filter on substring (driven by SearchBar)
    is_selected(row_id: str)       — read selection state
    selected_ids() -> list[str]    — read selection state
    visible_rows                   — current filtered view

Bindings are also registered (↑↓ / enter / space / a / n) so the widget works
in real screen contexts; widget tests exercise the API directly to avoid
Textual focus-chain coupling. Screen tests (Plan 2) cover key routing
end-to-end.
"""
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.events import Click
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
        Binding("space", "toggle_row", "Toggle", show=True),
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

    class SelectionChanged(Message):
        """Emitted after bulk selection ops (select_all / select_none) so the
        host screen can sync the new selection set to its domain model.
        Single-row toggles emit Toggled (above) instead — finer-grained.
        """

        def __init__(self, selected_ids: list[str]) -> None:
            self.selected_ids = selected_ids
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

    def set_selected_ids(self, row_ids: list[str]) -> None:
        """Replace the selection set. Use to mirror the host screen's domain
        model into the widget (e.g., re-opening a screen with pre-selected
        models / tests).

        Does NOT emit SelectionChanged — the screen is the source of truth
        for the new state; re-emitting would loop on the screen's handler.
        """
        self._selected = set(row_ids)
        self._refresh()

    def apply_query(self, query: str) -> None:
        self._query = query.strip().lower()
        if not self._query:
            self.visible_rows = list(self._all_rows)
        else:
            self.visible_rows = [
                r for r in self._all_rows if self._query in r.label.lower()
            ]
        if not self.visible_rows:
            self._cursor_idx = -1
        else:
            self._cursor_idx = min(max(self._cursor_idx, 0), len(self.visible_rows) - 1)
        self._refresh()

    def compose(self) -> ComposeResult:
        for i, row in enumerate(self.visible_rows):
            yield self._row_widget(row, i)

    def _row_widget(self, row: ListRow, idx: int) -> Static:
        cursor = " > " if idx == self._cursor_idx else "   "
        check = "[✓] " if row.id_ in self._selected else "[ ] "
        cls = "row"
        if idx == self._cursor_idx:
            cls += " cursor"
        if row.id_ in self._selected:
            cls += " selected"
        return Static(f"{cursor}{check}{row.label}", classes=cls)

    def _refresh(self) -> None:
        # Stable-row optimization: when the number of visible rows hasn't
        # changed (cursor move, toggle, select-all/none), update existing
        # Static widgets in place. Only structural changes (apply_query) need
        # the full teardown + remount. Saves O(N) DOM churn per keystroke.
        if len(self.children) == len(self.visible_rows):
            for i, child in enumerate(self.children):
                if not isinstance(child, Static):
                    continue
                row = self.visible_rows[i]
                cursor = " > " if i == self._cursor_idx else "   "
                check = "[✓] " if row.id_ in self._selected else "[ ] "
                cls = "row"
                if i == self._cursor_idx:
                    cls += " cursor"
                if row.id_ in self._selected:
                    cls += " selected"
                child.update(f"{cursor}{check}{row.label}")
                child.set_classes(cls)
            return
        for child in list(self.children):
            child.remove()
        for i, row in enumerate(self.visible_rows):
            self.mount(self._row_widget(row, i))

    def cursor_prev(self) -> None:
        if self._cursor_idx > 0:
            self._cursor_idx -= 1
            self._refresh()

    def cursor_next(self) -> None:
        if self._cursor_idx < len(self.visible_rows) - 1:
            self._cursor_idx += 1
            self._refresh()

    def drill(self) -> None:
        rid = self.cursor_row_id
        if rid is not None:
            self.post_message(self.Drill(rid))

    def on_click(self, event: Click) -> None:
        """Mouse-parity per spec §5: row-click === enter."""
        for i, child in enumerate(self.children):
            if child is event.widget:
                self._cursor_idx = i
                self._refresh()
                self.drill()
                event.stop()
                return

    def toggle(self) -> None:
        rid = self.cursor_row_id
        if rid is None:
            return
        if rid in self._selected:
            self._selected.discard(rid)
        else:
            self._selected.add(rid)
        self._refresh()
        self.post_message(self.Toggled(rid))

    def select_all(self) -> None:
        for row in self.visible_rows:
            self._selected.add(row.id_)
        self._refresh()
        self.post_message(self.SelectionChanged(self.selected_ids()))

    def select_none(self) -> None:
        for row in self.visible_rows:
            self._selected.discard(row.id_)
        self._refresh()
        self.post_message(self.SelectionChanged(self.selected_ids()))

    # Textual action_* wrappers route bindings to the public API.
    def action_cursor_prev(self) -> None:
        self.cursor_prev()

    def action_cursor_next(self) -> None:
        self.cursor_next()

    def action_drill(self) -> None:
        self.drill()

    def action_toggle_row(self) -> None:
        self.toggle()

    def action_select_all(self) -> None:
        self.select_all()

    def action_select_none(self) -> None:
        self.select_none()
