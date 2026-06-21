"""Tests for HostsScreen — list + AddHostModal + escape back."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.config import FleetConfigScreen
from hermia.tui.screens.hosts import HostsScreen
from hermia.tui.state import Host


class TestHostsScreen:
    def test_initial_render_shows_existing_hosts(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [
                    Host(name="eric-5090", url="http://e:11434", engine="ollama"),
                    Host(name="m3-pro", url="http://m:4000", engine="openai-compat"),
                ]
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                screen: HostsScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.host_names == ["eric-5090", "m3-pro"]

        asyncio.run(_run())

    def test_empty_hosts_shows_notice(self) -> None:
        from textual.widgets import Static

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                await pilot.pause()
                screen: HostsScreen = pilot.app.screen  # type: ignore[assignment]
                notice = screen.query_one("#hosts-empty-notice", Static)
                assert notice is not None

        asyncio.run(_run())

    def test_escape_pops_back(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetConfigScreen)

        asyncio.run(_run())

    def test_plus_opens_add_modal(self) -> None:
        from hermia.tui.screens.modals import AddHostModal

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                await pilot.press("plus")
                await pilot.pause()
                assert isinstance(pilot.app.screen, AddHostModal)

        asyncio.run(_run())

    def test_config_drill_into_hosts_row_pushes_hosts_screen(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                # cursor starts on row 0 (Hosts); enter drills.
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(pilot.app.screen, HostsScreen)

        asyncio.run(_run())
