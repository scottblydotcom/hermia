"""Tests for HermiaApp — the unified Fleet TUI Textual App.

LaunchScreen mount behavior is verified in tests/unit/tui/screens/test_launch.py
once Task 5 lands the screen.
"""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.state import FleetConfig


class TestHermiaApp:
    def test_starts_with_empty_config(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                app: HermiaApp = pilot.app  # type: ignore[assignment]
                assert isinstance(app.config, FleetConfig)
                assert app.config.name == ""
                assert app.config.hosts == []
                assert app.config.tests == []

        asyncio.run(_run())

    def test_config_is_mutable(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                app: HermiaApp = pilot.app  # type: ignore[assignment]
                app.config.name = "smoke"
                assert app.config.name == "smoke"

        asyncio.run(_run())
