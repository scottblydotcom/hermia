"""Tests for TestsScreen — fleet-scoped test multi-select with framework filter."""
import asyncio

from textual.widgets import Footer

from hermia.tui.app import HermiaApp
from hermia.tui.screens.tests import TestsScreen


class TestTestsScreen:
    def test_renders_all_tests_initially(self) -> None:
        from hermia.schemas import TEST_IDS

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                screen: TestsScreen = pilot.app.screen  # type: ignore[assignment]
                assert set(screen.visible_test_ids) == set(TEST_IDS)

        asyncio.run(_run())

    def test_select_all_populates_config_tests(self) -> None:
        from hermia.schemas import TEST_IDS

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                assert set(pilot.app.config.tests) == set(TEST_IDS)

        asyncio.run(_run())

    def test_search_filters_visible_tests(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                screen: TestsScreen = pilot.app.screen  # type: ignore[assignment]
                screen.apply_query("multiturn")
                await pilot.pause()
                ids = screen.visible_test_ids
                assert all("multiturn" in t for t in ids)
                assert len(ids) >= 1

        asyncio.run(_run())

    def test_pre_selected_tests_remain_selected_on_mount(self) -> None:
        from hermia.tui.widgets.drillable_list import DrillableList

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.tests = ["security-boundary", "tool-calling-basic"]
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                dl = pilot.app.screen.query_one(DrillableList)
                assert dl.is_selected("security-boundary")
                assert dl.is_selected("tool-calling-basic")

        asyncio.run(_run())

    def test_config_drill_into_tests_row_pushes_tests_screen(self) -> None:
        from hermia.tui.screens.config import FleetConfigScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                await pilot.press("down")  # cursor → Tests
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(pilot.app.screen, TestsScreen)

        asyncio.run(_run())

    def test_escape_pops_back(self) -> None:
        from hermia.tui.screens.config import FleetConfigScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetConfigScreen)

        asyncio.run(_run())


class TestTestsScreenFooter:
    def test_footer_present(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                screen = pilot.app.screen
                assert isinstance(screen, TestsScreen)
                assert len(screen.query(Footer)) == 1
        asyncio.run(_run())
