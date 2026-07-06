"""Tests for SearchBar widget API.

Contract under test: open() / close() change visibility; typing into the
Input emits QueryChanged; close() clears the query and emits QueryChanged("").

Key-routing (binding `/` to open, `escape` to close) lives at the screen
level per spec §5 universal contract — tested when screens land in Plan 2.
"""
import asyncio

from textual.app import App, ComposeResult
from textual.widgets import Input

from hermia.tui.widgets.search_bar import SearchBar


class _Host(App):
    def __init__(self) -> None:
        super().__init__()
        self.last_query: str | None = None

    def compose(self) -> ComposeResult:
        yield SearchBar()

    def on_search_bar_query_changed(self, event: SearchBar.QueryChanged) -> None:
        self.last_query = event.query


class TestSearchBar:
    def test_starts_hidden(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                bar = pilot.app.query_one(SearchBar)
                assert bar.display is False

        asyncio.run(_run())

    def test_open_makes_visible(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                bar = pilot.app.query_one(SearchBar)
                bar.open()
                await pilot.pause()
                assert bar.display is True

        asyncio.run(_run())

    def test_close_makes_hidden(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                bar = pilot.app.query_one(SearchBar)
                bar.open()
                await pilot.pause()
                bar.close()
                await pilot.pause()
                assert bar.display is False

        asyncio.run(_run())

    def test_typing_emits_query_changed(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                bar = pilot.app.query_one(SearchBar)
                bar.open()
                await pilot.pause()
                # Simulate typing by setting the Input value directly —
                # this is what would happen during real keyboard input.
                bar.query_one(Input).value = "deep"
                await pilot.pause()
                assert pilot.app.last_query == "deep"

        asyncio.run(_run())

    def test_close_clears_query(self) -> None:
        async def _run() -> None:
            async with _Host().run_test() as pilot:
                bar = pilot.app.query_one(SearchBar)
                bar.open()
                await pilot.pause()
                bar.query_one(Input).value = "deep"
                await pilot.pause()
                bar.close()
                await pilot.pause()
                assert pilot.app.last_query == ""

        asyncio.run(_run())
