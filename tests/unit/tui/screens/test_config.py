"""Tests for FleetConfigScreen — top-level summary + drill rows."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.config import FleetConfigScreen
from hermia.tui.state import FleetConfig, Host, ModelChoice


class TestFleetConfigSummary:
    def test_renders_empty_config(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert "0 hosts" in screen.summary_text
                assert "0 tests" in screen.summary_text
                assert "0 trials" in screen.run_plan_text

        asyncio.run(_run())

    def test_summary_with_hosts_and_tests(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = FleetConfig(
                    name="smoke",
                    hosts=[Host(name="h1", url="http://h1", engine="ollama",
                                models=[ModelChoice(name="m1", selected=True),
                                        ModelChoice(name="m2", selected=True)])],
                    tests=["t1", "t2", "t3"],
                )
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert "1 host" in screen.summary_text
                assert "3 tests" in screen.summary_text
                # 2 selected models × 3 tests = 6 trials.
                assert "6 trials" in screen.run_plan_text

        asyncio.run(_run())

    def test_breadcrumb_includes_fleet_name(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert "smoke" in screen.breadcrumb_text

        asyncio.run(_run())

    def test_breadcrumb_shows_unsaved_when_dirty(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                screen.mark_dirty()
                await pilot.pause()
                assert "[unsaved changes]" in screen.breadcrumb_text

        asyncio.run(_run())

    def test_escape_pops_back_to_launch(self) -> None:
        async def _run() -> None:
            from hermia.tui.screens.launch import LaunchScreen
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, LaunchScreen)

        asyncio.run(_run())
