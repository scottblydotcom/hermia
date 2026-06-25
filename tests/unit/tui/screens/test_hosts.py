"""Tests for HostsScreen — list + AddHostModal + escape back."""
import asyncio

from textual.widgets import Footer

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

        from hermia.tui.app import HermiaApp
        from hermia.tui.screens.hosts import HostsScreen
        from hermia.tui.state import Host
        from tests.fixtures.fake_transport import FakeTransport

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


class TestSubscriptionRace:
    """hermia-izi: probe subscriptions must be registered before probes fire.

    SessionBus.subscribe() is synchronous — it appends the queue to _subscribers
    immediately. But _listen() calls subscribe() *inside* a task created with
    create_task(). Tasks don't step until the event loop yields (sleep(0)), so
    there's a race window between create_task() and the first sleep(0): if a probe
    publishes an event in that window the event is lost.

    Fix: call bus.subscribe() synchronously before create_task() and pass the
    pre-created generator to the listener task, eliminating the race window.
    """

    def test_subscribe_inside_task_not_registered_until_task_steps(self) -> None:
        """Demonstrates the race: subscribe() called inside a create_task coroutine
        is NOT registered until the event loop steps that task (after sleep(0)).
        This is the window in which a probe.* publish would be lost."""
        import asyncio

        from hermia.tui.bus import SessionBus

        async def _run() -> None:
            bus = SessionBus()

            async def listener() -> None:
                async for _ in bus.subscribe("probe.completed"):
                    break

            task = asyncio.create_task(listener())
            # Race window: task scheduled but not yet stepped — no subscriber yet.
            assert "probe.completed" not in bus._subscribers, (
                "subscription must not exist before the task steps"
            )

            await asyncio.sleep(0)  # step the task
            assert "probe.completed" in bus._subscribers, (
                "subscription must exist after the task steps"
            )

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(_run())

    def test_subscribe_before_create_task_registers_immediately(self) -> None:
        """The fix: call subscribe() synchronously BEFORE create_task so the
        subscription is registered with no race window."""
        import asyncio

        from hermia.tui.bus import SessionBus

        async def _run() -> None:
            bus = SessionBus()

            # Subscribe synchronously — registration is immediate.
            gen = bus.subscribe("probe.completed")
            assert "probe.completed" in bus._subscribers, (
                "subscription must be registered synchronously before create_task"
            )

            async def listener() -> None:
                async for _ in gen:
                    break

            task = asyncio.create_task(listener())
            # Still registered — no race window.
            assert "probe.completed" in bus._subscribers

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(_run())

    def test_all_three_probe_topics_subscribed_before_probes_fire(self) -> None:
        """Integration: when the first probe event hits the bus, all 3 probe
        topics must already have subscribers — no event should be lost."""
        import asyncio

        from hermia.tui.app import HermiaApp
        from hermia.tui.screens.hosts import HostsScreen
        from hermia.tui.state import Host
        from tests.fixtures.fake_transport import FakeTransport

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [
                    Host(name="h1", url="http://h1", engine="ollama"),
                ]
                subscribed_at_first_publish: set[str] = set()

                original_publish = pilot.app.bus.publish

                async def spy_publish(topic: str, event: dict) -> None:
                    if topic.startswith("probe.") and not subscribed_at_first_publish:
                        subscribed_at_first_publish.update(pilot.app.bus._subscribers.keys())
                    await original_publish(topic, event)

                pilot.app.bus.publish = spy_publish  # type: ignore[method-assign]

                screen = HostsScreen(
                    transport_factory=lambda h: FakeTransport(models=[]),
                    probe_timeout=2.0,
                )
                pilot.app.push_screen(screen)

                for _ in range(30):
                    if subscribed_at_first_publish:
                        break
                    await pilot.pause()

                assert subscribed_at_first_publish, "no probe events published"
                assert "probe.started" in subscribed_at_first_publish
                assert "probe.completed" in subscribed_at_first_publish
                assert "probe.failed" in subscribed_at_first_publish

        asyncio.run(_run())


class TestHostsFooter:
    def test_footer_present(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                screen = pilot.app.screen
                assert isinstance(screen, HostsScreen)
                assert len(screen.query(Footer)) == 1
        asyncio.run(_run())
