"""Fleet-scoped test picker with framework filter axis.

Mounts a DrillableList of all TEST_IDS plus a FilterAxis for OWASP / ATLAS
/ MAESTRO / NIST and a SearchBar. Selections write to app.config.tests so
the FleetConfigScreen's run-plan trial count updates on pop-back.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen

from hermia.tui.screens._dirty import _mark_dirty_in_stack
from hermia.tui.test_catalog import FRAMEWORKS, load_test_catalog
from hermia.tui.widgets.breadcrumb import Breadcrumb
from hermia.tui.widgets.drillable_list import DrillableList, ListRow
from hermia.tui.widgets.filter_axis import FilterAxis
from hermia.tui.widgets.search_bar import SearchBar


class TestsScreen(Screen[None]):
    # Tell pytest not to collect this class — name starts with "Test" but
    # it's a Screen, not a test class.
    __test__ = False

    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("space", "toggle_test", "Toggle", show=True),
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
        # Mirror app.config.tests into the widget via its public API.
        self.query_one(DrillableList).set_selected_ids(
            list(self.app.config.tests),  # type: ignore[attr-defined]
        )

    # ── Filter combiner ────────────────────────────────────────────────────

    def apply_query(self, q: str) -> None:
        """Public hook so tests can drive query without typing keystrokes."""
        self._query = q.strip().lower()
        self._reapply()

    def _reapply(self) -> None:
        dl = self.query_one(DrillableList)
        # Combine substring + framework membership.
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

    # ── Event handlers ────────────────────────────────────────────────────

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
        _mark_dirty_in_stack(self.app)

    def on_drillable_list_selection_changed(
        self, event: DrillableList.SelectionChanged
    ) -> None:
        # Bulk select_all / select_none from the widget — sync to app.config.tests.
        # Preserve any selections for tests not currently visible (filter-respecting).
        dl = self.query_one(DrillableList)
        visible_ids = {r.id_ for r in dl.visible_rows}
        cfg_tests = [t for t in self.app.config.tests  # type: ignore[attr-defined]
                     if t not in visible_ids]
        cfg_tests.extend(event.selected_ids)
        self.app.config.tests = sorted(set(cfg_tests))  # type: ignore[attr-defined]
        _mark_dirty_in_stack(self.app)

    # ── Action wrappers ───────────────────────────────────────────────────

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_cursor_prev(self) -> None:
        self.query_one(DrillableList).cursor_prev()

    def action_cursor_next(self) -> None:
        self.query_one(DrillableList).cursor_next()

    def action_toggle_test(self) -> None:
        self.query_one(DrillableList).toggle()

    def action_select_all(self) -> None:
        self.query_one(DrillableList).select_all()

    def action_select_none(self) -> None:
        self.query_one(DrillableList).select_none()

    def action_search_open(self) -> None:
        self.query_one(SearchBar).open()

    def action_next_axis(self) -> None:
        self.query_one(FilterAxis).next_axis()

    def action_next_value(self) -> None:
        self.query_one(FilterAxis).next_value()

    def action_prev_value(self) -> None:
        self.query_one(FilterAxis).prev_value()
