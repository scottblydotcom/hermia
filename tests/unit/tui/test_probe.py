"""Tests for hermia.tui.probe — async host probe with timeout + retry + bus events."""
import asyncio

from hermia.tui.bus import SessionBus
from hermia.tui.probe import probe_host
from hermia.tui.state import Host
from tests.fixtures.fake_transport import FakeTransport


async def _start_readers(bus: SessionBus) -> list[tuple[str, dict]]:
    """Start background readers on probe.* topics and return the shared event list."""
    events: list[tuple[str, dict]] = []

    async def reader(topic: str) -> None:
        async for ev in bus.subscribe(topic):
            events.append((topic, ev))

    for topic in ("probe.started", "probe.completed", "probe.failed"):
        asyncio.create_task(reader(topic))
    await asyncio.sleep(0)
    return events


class TestProbeHappyPath:
    def test_publishes_started_then_completed(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            events = await _start_readers(bus)
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
            events = await _start_readers(bus)
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
            events = await _start_readers(bus)
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
            events = await _start_readers(bus)
            host = Host(name="dead", url="http://dead", engine="ollama")
            transport = FakeTransport(models=[], fail_with=ConnectionRefusedError("nope"))

            await probe_host(host, transport=transport, bus=bus)
            await asyncio.sleep(0.05)

            failed = [ev for t, ev in events if t == "probe.failed"]
            assert len(failed) == 1
            assert failed[0]["reason"] == "offline"

        asyncio.run(_run())

    def test_empty_model_list_publishes_completed_with_warning(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            events = await _start_readers(bus)
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
