"""Tests for Breadcrumb — segmented drill-path header."""
import asyncio

from textual.app import App, ComposeResult

from hermia.tui.widgets.breadcrumb import Breadcrumb


class _Host(App):
    def __init__(self, segments: list[str]) -> None:
        super().__init__()
        self._segments = segments
        self.jumped_to: int | None = None

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self._segments)

    def on_breadcrumb_jumped(self, event: Breadcrumb.Jumped) -> None:
        self.jumped_to = event.index


class TestBreadcrumb:
    def test_renders_segments_with_separator(self) -> None:
        async def _run() -> None:
            async with _Host(["hermia", "fleet", "smoke"]).run_test() as pilot:
                bc = pilot.app.query_one(Breadcrumb)
                assert bc.text == "hermia ▸ fleet ▸ smoke"

        asyncio.run(_run())

    def test_empty_segments_renders_empty(self) -> None:
        async def _run() -> None:
            async with _Host([]).run_test() as pilot:
                bc = pilot.app.query_one(Breadcrumb)
                assert bc.text == ""

        asyncio.run(_run())

    def test_update_changes_rendering(self) -> None:
        async def _run() -> None:
            async with _Host(["a", "b"]).run_test() as pilot:
                bc = pilot.app.query_one(Breadcrumb)
                bc.set_segments(["x", "y", "z"])
                await pilot.pause()
                assert bc.text == "x ▸ y ▸ z"

        asyncio.run(_run())

    def test_jump_emits_message_with_index(self) -> None:
        async def _run() -> None:
            async with _Host(["a", "b", "c"]).run_test() as pilot:
                bc = pilot.app.query_one(Breadcrumb)
                bc.jump_to(1)
                await pilot.pause()
                assert pilot.app.jumped_to == 1

        asyncio.run(_run())

    def test_jump_out_of_range_is_noop(self) -> None:
        async def _run() -> None:
            async with _Host(["a", "b"]).run_test() as pilot:
                bc = pilot.app.query_one(Breadcrumb)
                bc.jump_to(5)
                bc.jump_to(-1)
                await pilot.pause()
                assert pilot.app.jumped_to is None

        asyncio.run(_run())
