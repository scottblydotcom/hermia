"""Tests for hermia.tui.probe — async host probe with timeout + retry + bus events."""
import asyncio
from contextlib import asynccontextmanager

from hermia.tui.bus import SessionBus
from hermia.tui.probe import probe_host
from hermia.tui.state import Host
from tests.fixtures.fake_transport import FakeTransport


@asynccontextmanager
async def _probe_readers(bus: SessionBus):
    """Manage the lifecycle of background readers on the probe.* topics.

    Yields the shared events list. Cancels and awaits readers on exit so
    tests don't leak coroutines into asyncio.run()'s teardown (which would
    surface as 'Task was destroyed but it is pending' warnings).
    """
    events: list[tuple[str, dict]] = []
    tasks: list[asyncio.Task[None]] = []

    async def reader(topic: str) -> None:
        try:
            async for ev in bus.subscribe(topic):
                events.append((topic, ev))
        except asyncio.CancelledError:
            return

    for topic in ("probe.started", "probe.completed", "probe.failed"):
        tasks.append(asyncio.create_task(reader(topic)))
    await asyncio.sleep(0)
    try:
        yield events
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class TestProbeHappyPath:
    def test_publishes_started_then_completed(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            async with _probe_readers(bus) as events:
                host = Host(name="h1", url="http://h1:11434", engine="ollama")
                transport = FakeTransport(models=["qwen3:32b", "llama3:8b"])

                await probe_host(host, transport=transport, bus=bus)
                await asyncio.sleep(0.05)

                topics = [t for t, _ in events]
                assert "probe.started" in topics
                assert "probe.completed" in topics
                assert "probe.failed" not in topics

                completed = next(ev for t, ev in events if t == "probe.completed")
                assert completed["host_name"] == "h1"
                assert completed["models"] == ["qwen3:32b", "llama3:8b"]

        asyncio.run(_run())

    def test_populates_host_models(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            host = Host(name="h1", url="http://h1", engine="ollama")
            transport = FakeTransport(models=["qwen3:32b", "llama3:8b"])
            await probe_host(host, transport=transport, bus=bus)
            assert [m.name for m in host.models] == ["qwen3:32b", "llama3:8b"]
            # Newly probed models start unselected.
            assert all(not m.selected for m in host.models)

        asyncio.run(_run())


class TestProbeFailures:
    def test_timeout_publishes_failed_with_reason_timeout(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            async with _probe_readers(bus) as events:
                host = Host(name="slow", url="http://slow", engine="ollama")
                transport = FakeTransport(models=["x"], delay_seconds=2.0)

                await probe_host(host, transport=transport, bus=bus, timeout=0.05)
                await asyncio.sleep(0.05)

                failed = [ev for t, ev in events if t == "probe.failed"]
                assert len(failed) == 1
                assert failed[0]["reason"] == "timeout"
                assert failed[0]["retryable"] is True

        asyncio.run(_run())

    def test_auth_error_publishes_failed_with_reason_auth(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            async with _probe_readers(bus) as events:
                host = Host(name="locked", url="http://locked", engine="openai-compat")
                transport = FakeTransport(models=[], fail_with=PermissionError("401 unauthorized"))

                await probe_host(host, transport=transport, bus=bus)
                await asyncio.sleep(0.05)

                failed = [ev for t, ev in events if t == "probe.failed"]
                assert len(failed) == 1
                assert failed[0]["reason"] == "auth"

        asyncio.run(_run())

    def test_transport_error_publishes_failed_with_reason_offline(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            async with _probe_readers(bus) as events:
                host = Host(name="dead", url="http://dead", engine="ollama")
                transport = FakeTransport(models=[], fail_with=ConnectionRefusedError("nope"))

                await probe_host(host, transport=transport, bus=bus)
                await asyncio.sleep(0.05)

                failed = [ev for t, ev in events if t == "probe.failed"]
                assert len(failed) == 1
                assert failed[0]["reason"] == "offline"

        asyncio.run(_run())

    def test_programmer_error_publishes_failed_with_reason_unexpected(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            async with _probe_readers(bus) as events:
                host = Host(name="buggy", url="http://buggy", engine="ollama")
                # Simulate a programmer error: AttributeError from a future transport
                # bug should not be reported as "host offline".
                transport = FakeTransport(models=[], fail_with=AttributeError("missing field"))

                await probe_host(host, transport=transport, bus=bus)
                await asyncio.sleep(0.05)

                failed = [ev for t, ev in events if t == "probe.failed"]
                assert len(failed) == 1
                assert failed[0]["reason"] == "unexpected"
                assert failed[0]["retryable"] is False
                assert "AttributeError" in failed[0]["error"]

        asyncio.run(_run())

    def test_empty_model_list_publishes_completed_with_warning(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            async with _probe_readers(bus) as events:
                host = Host(name="empty", url="http://empty", engine="ollama")
                transport = FakeTransport(models=[])

                await probe_host(host, transport=transport, bus=bus)
                await asyncio.sleep(0.05)

                completed = [ev for t, ev in events if t == "probe.completed"]
                assert len(completed) == 1
                assert completed[0]["models"] == []
                assert completed[0]["warning"] == "no_models"
                assert host.models == []

        asyncio.run(_run())
