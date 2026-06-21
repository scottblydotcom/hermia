"""Single host's model picker — uses DrillableList + SearchBar.

Mounts a DrillableList of the host's currently-probed models. Toggling a
row flips host.models[].selected; the parent FleetConfigScreen's run-plan
trial count updates when the user pops back.
"""
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
        # Pre-mark currently-selected models in the widget's selection set.
        for m in self._host.models:
            if m.selected:
                dl._selected.add(m.name)
        dl._refresh()

    # ── Event handlers ────────────────────────────────────────────────────

    def on_drillable_list_toggled(self, event: DrillableList.Toggled) -> None:
        for m in self._host.models:
            if m.name == event.row_id:
                m.selected = not m.selected
                break

    def on_drillable_list_selection_changed(
        self, event: DrillableList.SelectionChanged
    ) -> None:
        # Bulk select_all / select_none in the widget — sync to host.models.
        selected = set(event.selected_ids)
        for m in self._host.models:
            m.selected = m.name in selected

    def on_search_bar_query_changed(self, event: SearchBar.QueryChanged) -> None:
        self.query_one(DrillableList).apply_query(event.query)

    # ── Action wrappers ───────────────────────────────────────────────────

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
        # Sync state to host.models.
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
