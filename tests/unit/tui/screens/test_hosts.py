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


class TestHostsProbe:
    def test_probe_populates_models_and_flips_to_ok(self) -> None:
        from tests.fixtures.fake_transport import FakeTransport

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [
                    Host(name="h1", url="http://h1", engine="ollama"),
                ]
                screen = HostsScreen(
                    transport_factory=lambda h: FakeTransport(models=["a", "b"]),
                )
                pilot.app.push_screen(screen)
                # Give the worker a beat to finish.
                for _ in range(30):
                    if screen.probe_state.get("h1") == "ok":
                        break
                    await pilot.pause()
                assert screen.probe_state["h1"] == "ok"
                assert [m.name for m in pilot.app.config.hosts[0].models] == ["a", "b"]

        asyncio.run(_run())

    def test_probe_timeout_flips_to_failed(self) -> None:
        from tests.fixtures.fake_transport import FakeTransport

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [
                    Host(name="slow", url="http://slow", engine="ollama"),
                ]
                screen = HostsScreen(
                    transport_factory=lambda h: FakeTransport(models=["x"], delay_seconds=2.0),
                    probe_timeout=0.05,
                )
                pilot.app.push_screen(screen)
                for _ in range(30):
                    if screen.probe_state.get("slow") in ("ok", "failed"):
                        break
                    await pilot.pause()
                assert screen.probe_state["slow"] == "failed"

        asyncio.run(_run())

    def test_probe_unexpected_error_marks_host_failed(self) -> None:
        # If a transport_factory itself raises (not the probe), gather catches
        # via return_exceptions=True; the screen must mark the host failed so
        # it doesn't stay stuck in "probing" forever.
        def boom(host: Host) -> object:
            raise RuntimeError("factory blew up")

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [Host(name="x", url="http://x", engine="ollama")]
                screen = HostsScreen(transport_factory=boom)
                pilot.app.push_screen(screen)
                for _ in range(30):
                    if screen.probe_state.get("x") in ("ok", "failed"):
                        break
                    await pilot.pause()
                assert screen.probe_state["x"] == "failed"

        asyncio.run(_run())

    def test_probe_auth_error_flips_to_failed(self) -> None:
        from tests.fixtures.fake_transport import FakeTransport

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [
                    Host(name="locked", url="http://locked", engine="openai-compat"),
                ]
                screen = HostsScreen(
                    transport_factory=lambda h: FakeTransport(
                        models=[], fail_with=PermissionError("401 unauthorized")
                    ),
                )
                pilot.app.push_screen(screen)
                for _ in range(30):
                    if screen.probe_state.get("locked") in ("ok", "failed"):
                        break
                    await pilot.pause()
                assert screen.probe_state["locked"] == "failed"

        asyncio.run(_run())


class TestHostsScreenBusMigration:
    def test_probe_events_flow_through_app_bus(self) -> None:
        """After migration, probe.completed events appear on app.bus, not a private bus."""
        import asyncio

        from tests.fixtures.fake_transport import FakeTransport
        from hermia.tui.app import HermiaApp
        from hermia.tui.screens.hosts import HostsScreen
        from hermia.tui.state import Host

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [
                    Host(name="eric-5090", url="http://e:11434", engine="ollama")
                ]
                received: list[dict] = []

                async def listen() -> None:
                    async for ev in pilot.app.bus.subscribe("probe.completed"):
                        received.append(ev)
                        return

                task = asyncio.create_task(listen())
                await asyncio.sleep(0)

                fake = FakeTransport(models=["qwen3:32b"])
                pilot.app.push_screen(
                    HostsScreen(transport_factory=lambda _host: fake, probe_timeout=2.0)
                )
                await pilot.pause()
                await asyncio.wait_for(task, timeout=3.0)
                assert received[0]["host_name"] == "eric-5090"

        asyncio.run(_run())
