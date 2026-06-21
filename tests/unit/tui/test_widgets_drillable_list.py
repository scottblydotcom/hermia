"""Tests for DrillableList — API contract: cursor / drill / toggle / select-all/none
plus apply_query filter behavior and Drill / Toggled events.

Key-routing (↑↓ / enter / space / a / n) lives at the screen level per
spec §5 universal contract. Bindings exist on the widget so it works in
real screens; widget tests call the API directly.
"""
import asyncio

from textual.app import App, ComposeResult

from hermia.tui.widgets.drillable_list import DrillableList, ListRow


def _rows() -> list[ListRow]:
    return [
        ListRow(id_="a", label="alpha"),
        ListRow(id_="b", label="bravo"),
        ListRow(id_="c", label="charlie"),
        ListRow(id_="d", label="delta"),
    ]


class _Host(App):
    def __init__(self) -> None:
        super().__init__()
        self.drilled_into: str | None = None
        self.toggled: list[str] = []

    def compose(self) -> ComposeResult:
        yield DrillableList(_rows())

    def on_drillable_list_drill(self, event: DrillableList.Drill) -> None:
        self.drilled_into = event.row_id

    def on_drillable_list_toggled(self, event: DrillableList.Toggled) -> None:
        self.toggled.append(event.row_id)


class TestDrillableList:
    def test_initial_state_renders_all_rows(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                dl = pilot.app.query_one(DrillableList)
                assert len(dl.visible_rows) == 4

        asyncio.run(_run())

    def test_drill_emits_drill_for_current_row(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                dl = pilot.app.query_one(DrillableList)
                dl.drill()
                await pilot.pause()
                assert pilot.app.drilled_into == "a"

        asyncio.run(_run())

    def test_toggle_changes_selection_and_emits(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                dl = pilot.app.query_one(DrillableList)
                dl.toggle()
                await pilot.pause()
                assert pilot.app.toggled == ["a"]
                assert dl.is_selected("a")

        asyncio.run(_run())

    def test_cursor_prev_next_move_cursor(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                dl = pilot.app.query_one(DrillableList)
                dl.cursor_next()
                assert dl.cursor_row_id == "b"
                dl.cursor_prev()
                assert dl.cursor_row_id == "a"

        asyncio.run(_run())

    def test_select_all_selects_visible(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                dl = pilot.app.query_one(DrillableList)
                dl.select_all()
                assert dl.is_selected("a")
                assert dl.is_selected("b")
                assert dl.is_selected("c")
                assert dl.is_selected("d")

        asyncio.run(_run())

    def test_select_none_clears_visible(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                dl = pilot.app.query_one(DrillableList)
                dl.select_all()
                dl.select_none()
                assert not dl.is_selected("a")
                assert not dl.is_selected("d")

        asyncio.run(_run())

    def test_apply_query_filters_rows(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                dl = pilot.app.query_one(DrillableList)
                dl.apply_query("a")  # alpha, bravo, charlie, delta all contain 'a'
                assert len(dl.visible_rows) == 4
                dl.apply_query("ravo")
                assert [r.id_ for r in dl.visible_rows] == ["b"]
                dl.apply_query("")
                assert len(dl.visible_rows) == 4

        asyncio.run(_run())

    def test_click_on_row_drills(self) -> None:
        """Mouse parity per spec §5 — clicking a row moves cursor and drills."""
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                dl = pilot.app.query_one(DrillableList)
                # Click the second visible row (id_="b").
                await pilot.click(dl.children[1])
                await pilot.pause()
                assert pilot.app.drilled_into == "b"

        asyncio.run(_run())

    def test_select_all_respects_filter(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                dl = pilot.app.query_one(DrillableList)
                dl.apply_query("ravo")
                dl.select_all()
                assert dl.is_selected("b")
                assert not dl.is_selected("a")
                assert not dl.is_selected("c")

        asyncio.run(_run())
