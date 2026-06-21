"""Tests for LaunchScreen — initial entries + cursor + key bindings."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.launch import LaunchScreen


class TestLaunchEntries:
    def test_three_entries_present(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                assert isinstance(pilot.app.screen, LaunchScreen)
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                labels = [e.label for e in screen.entries]
                assert labels == ["Load existing fleet", "New fleet", "Quick local run"]

        asyncio.run(_run())

    def test_cursor_starts_on_first_entry(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 0

        asyncio.run(_run())

    def test_arrow_down_moves_cursor(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("down")
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 1

        asyncio.run(_run())

    def test_arrow_up_clamps_at_top(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("up")
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 0

        asyncio.run(_run())

    def test_arrow_down_clamps_at_bottom(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                for _ in range(5):
                    await pilot.press("down")
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 2  # 3 entries → max index 2

        asyncio.run(_run())

    def test_q_quits_app(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("q")
                await pilot.pause()
                # App is exiting; _exit flag flips True.
                assert pilot.app._exit is True

        asyncio.run(_run())
