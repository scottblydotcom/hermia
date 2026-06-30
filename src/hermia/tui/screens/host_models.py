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
from textual.widgets import Footer, Static

from hermia.tui.screens._dirty import _mark_dirty_in_stack
from hermia.tui.state import Host
from hermia.tui.widgets.breadcrumb import Breadcrumb
from hermia.tui.widgets.drillable_list import DrillableList, ListRow
from hermia.tui.widgets.search_bar import SearchBar


class HostModelsScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("space", "toggle_model", "Toggle", show=True),
        Binding("a", "select_all", "All", show=True),
        Binding("n", "select_none", "None", show=True),
        Binding("slash", "search_open", "Search", show=True),
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
            yield Static(
                "Select which models on this host to include in the run.\n"
                "\n"
                "  Space  Toggle selected     a  Select all     n  Select none\n"
                "  /  Search by name          Esc  Back to hosts",
                id="host-models-instructions",
            )
            if not self._host.models:
                # Bare empty list left first-time users with no map from
                # "no rows" to "pull a model" (hermia-1pj).
                yield Static(
                    f"No models on '{self._host.name}'. "
                    f"Pull one (e.g. `ollama pull llama3.2`) then go back to "
                    f"hosts and re-enter this screen to re-probe.",
                    id="host-models-empty-hint",
                )
            rows = [ListRow(id_=m.name, label=m.name) for m in self._host.models]
            yield DrillableList(rows)
            yield SearchBar()
        yield Footer()

    def on_mount(self) -> None:
        # Mirror host.models[].selected into the widget via its public API.
        selected = [m.name for m in self._host.models if m.selected]
        self.query_one(DrillableList).set_selected_ids(selected)

    # ── Event handlers ────────────────────────────────────────────────────

    def on_drillable_list_toggled(self, event: DrillableList.Toggled) -> None:
        for m in self._host.models:
            if m.name == event.row_id:
                m.selected = not m.selected
                break
        _mark_dirty_in_stack(self.app)

    def on_drillable_list_selection_changed(
        self, event: DrillableList.SelectionChanged
    ) -> None:
        # Bulk select_all / select_none in the widget — sync to host.models.
        selected = set(event.selected_ids)
        for m in self._host.models:
            m.selected = m.name in selected
        _mark_dirty_in_stack(self.app)

    def on_search_bar_query_changed(self, event: SearchBar.QueryChanged) -> None:
        self.query_one(DrillableList).apply_query(event.query)

    # ── Action wrappers ───────────────────────────────────────────────────

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_cursor_prev(self) -> None:
        self.query_one(DrillableList).cursor_prev()

    def action_cursor_next(self) -> None:
        self.query_one(DrillableList).cursor_next()

    def action_toggle_model(self) -> None:
        self.query_one(DrillableList).toggle()

    def action_select_all(self) -> None:
        # dl.select_all() posts SelectionChanged which our handler picks up
        # and syncs to host.models — no manual mutation needed here.
        self.query_one(DrillableList).select_all()

    def action_select_none(self) -> None:
        self.query_one(DrillableList).select_none()

    def action_search_open(self) -> None:
        self.query_one(SearchBar).open()
