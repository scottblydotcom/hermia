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


class TestHermiaAppBus:
    def test_app_has_bus_attribute(self) -> None:
        from hermia.tui.bus import SessionBus

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                assert isinstance(pilot.app.bus, SessionBus)

        asyncio.run(_run())

    def test_bus_can_publish_and_receive(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                events: list[dict] = []

                async def reader() -> None:
                    async for ev in pilot.app.bus.subscribe("run.started"):
                        events.append(ev)
                        return

                task = asyncio.create_task(reader())
                await asyncio.sleep(0)
                await pilot.app.bus.publish("run.started", {"run_id": "r1"})
                await asyncio.wait_for(task, timeout=1.0)
                assert events == [{"run_id": "r1"}]

        asyncio.run(_run())
