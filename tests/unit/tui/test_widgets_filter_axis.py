"""Tests for FilterAxis — API contract: current_axis / current_value / next_axis /
next_value / prev_value plus Changed event emission.

Key-routing (tab / ←→) is a screen-level concern per spec §5.
"""
import asyncio

from textual.app import App, ComposeResult

from hermia.tui.widgets.filter_axis import FilterAxis


class _Host(App):
    def __init__(self, axes: dict[str, list[str]]) -> None:
        super().__init__()
        self.axes = axes
        self.last_axis: str | None = None
        self.last_value: str | None = None

    def compose(self) -> ComposeResult:
        yield FilterAxis(self.axes)

    def on_filter_axis_changed(self, event: FilterAxis.Changed) -> None:
        self.last_axis = event.axis
        self.last_value = event.value


class TestFilterAxis:
    def test_initial_state_is_first_axis_all(self) -> None:
        async def _run() -> None:
            axes = {"framework": ["OWASP", "ATLAS"], "size": ["small", "large"]}
            async with _Host(axes).run_test() as pilot:
                fa = pilot.app.query_one(FilterAxis)
                assert fa.current_axis == "framework"
                assert fa.current_value == "All"

        asyncio.run(_run())

    def test_next_value_cycles_within_axis(self) -> None:
        async def _run() -> None:
            axes = {"framework": ["OWASP", "ATLAS"]}
            async with _Host(axes).run_test() as pilot:
                fa = pilot.app.query_one(FilterAxis)
                fa.next_value()
                assert fa.current_value == "OWASP"
                fa.next_value()
                assert fa.current_value == "ATLAS"
                fa.next_value()
                assert fa.current_value == "All"

        asyncio.run(_run())

    def test_prev_value_cycles_backward(self) -> None:
        async def _run() -> None:
            axes = {"framework": ["OWASP", "ATLAS"]}
            async with _Host(axes).run_test() as pilot:
                fa = pilot.app.query_one(FilterAxis)
                fa.prev_value()
                assert fa.current_value == "ATLAS"

        asyncio.run(_run())

    def test_next_axis_cycles_to_next_axis(self) -> None:
        async def _run() -> None:
            axes = {"framework": ["OWASP"], "size": ["small"]}
            async with _Host(axes).run_test() as pilot:
                fa = pilot.app.query_one(FilterAxis)
                fa.next_axis()
                assert fa.current_axis == "size"
                assert fa.current_value == "All"
                fa.next_axis()
                assert fa.current_axis == "framework"

        asyncio.run(_run())

    def test_change_event_fires(self) -> None:
        async def _run() -> None:
            axes = {"framework": ["OWASP", "ATLAS"]}
            async with _Host(axes).run_test() as pilot:
                fa = pilot.app.query_one(FilterAxis)
                fa.next_value()
                await pilot.pause()
                assert pilot.app.last_axis == "framework"
                assert pilot.app.last_value == "OWASP"

        asyncio.run(_run())

    def test_empty_axes_dict_is_noop(self) -> None:
        async def _run() -> None:
            async with _Host({}).run_test() as pilot:
                fa = pilot.app.query_one(FilterAxis)
                fa.next_axis()
                fa.next_value()
                fa.prev_value()
                assert fa.current_axis is None
                assert fa.current_value is None

        asyncio.run(_run())
