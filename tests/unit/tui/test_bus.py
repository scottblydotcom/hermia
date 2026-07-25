"""Tests for hermia.tui.bus — topic-based async pub/sub."""
import asyncio

from hermia.tui.bus import SessionBus


class TestSessionBus:
    def test_subscribe_receives_publish(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            events: list[dict] = []

            async def reader() -> None:
                async for ev in bus.subscribe("probe.started"):
                    events.append(ev)
                    if len(events) == 1:
                        return

            task = asyncio.create_task(reader())
            await asyncio.sleep(0)
            await bus.publish("probe.started", {"host_id": "node-a"})
            await asyncio.wait_for(task, timeout=1.0)
            assert events == [{"host_id": "node-a"}]

        asyncio.run(_run())

    def test_multiple_subscribers_each_get_event(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            a_events: list[dict] = []
            b_events: list[dict] = []

            async def reader(sink: list[dict]) -> None:
                async for ev in bus.subscribe("run.trial_finished"):
                    sink.append(ev)
                    if len(sink) == 1:
                        return

            ta = asyncio.create_task(reader(a_events))
            tb = asyncio.create_task(reader(b_events))
            await asyncio.sleep(0)
            await bus.publish("run.trial_finished", {"trial_id": "t1"})
            await asyncio.wait_for(asyncio.gather(ta, tb), timeout=1.0)
            assert a_events == [{"trial_id": "t1"}]
            assert b_events == [{"trial_id": "t1"}]

        asyncio.run(_run())

    def test_publish_to_topic_with_no_subscribers_is_noop(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            await bus.publish("probe.started", {"host_id": "x"})

        asyncio.run(_run())

    def test_subscriber_on_unrelated_topic_does_not_receive(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            events: list[dict] = []

            async def reader() -> None:
                try:
                    async for ev in bus.subscribe("probe.started"):
                        events.append(ev)
                except asyncio.CancelledError:
                    return

            task = asyncio.create_task(reader())
            await asyncio.sleep(0)
            await bus.publish("run.trial_finished", {"trial_id": "t1"})
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert events == []

        asyncio.run(_run())


class TestBoundedQueue:
    def test_unbounded_queue_keeps_all_events(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            events: list[dict] = []

            async def reader() -> None:
                async for ev in bus.subscribe("run.trial_finished"):
                    events.append(ev)
                    if len(events) == 100:
                        return

            task = asyncio.create_task(reader())
            await asyncio.sleep(0)
            for i in range(100):
                await bus.publish("run.trial_finished", {"trial_id": f"t{i}"})
            await asyncio.wait_for(task, timeout=1.0)
            assert len(events) == 100

        asyncio.run(_run())

    def test_subscriber_self_cleans_on_reader_task_cancel(self) -> None:
        """Cancelling the reader task fires the generator's finally clause,
        which removes its queue from `_subscribers` — screens that pop don't
        leak queues for their lifetime.
        """
        async def _run() -> None:
            bus = SessionBus()
            events: list[dict] = []

            async def reader() -> None:
                async for ev in bus.subscribe("probe.started"):
                    events.append(ev)

            task = asyncio.create_task(reader())
            await asyncio.sleep(0)
            assert len(bus._subscribers["probe.started"]) == 1

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            # Give the generator a chance to run its finally clause.
            await asyncio.sleep(0)

            assert "probe.started" not in bus._subscribers

        asyncio.run(_run())

    def test_bounded_queue_drops_oldest_when_full(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            events: list[dict] = []

            async def reader() -> None:
                async for ev in bus.subscribe("run.trial_chunk", maxsize=2):
                    events.append(ev)
                    if len(events) == 2:
                        return

            task = asyncio.create_task(reader())
            await asyncio.sleep(0)
            for i in range(5):
                await bus.publish("run.trial_chunk", {"chunk": f"c{i}"})
            await asyncio.wait_for(task, timeout=1.0)
            assert events == [{"chunk": "c3"}, {"chunk": "c4"}]

        asyncio.run(_run())


class TestSessionBusClose:
    def test_close_clears_subscriber_registry(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            events: list[dict] = []

            async def reader() -> None:
                try:
                    async for ev in bus.subscribe("probe.started"):
                        events.append(ev)
                except asyncio.CancelledError:
                    return

            task = asyncio.create_task(reader())
            await asyncio.sleep(0)
            assert "probe.started" in bus._subscribers

            bus.close()
            # After close, the registry is empty.
            assert bus._subscribers == {}
            # Cancel the reader (it's blocked on q.get — close doesn't unblock it).
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(_run())

    def test_publish_after_close_is_noop(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            bus.close()
            # Should not raise.
            await bus.publish("run.started", {"run_id": "r1"})

        asyncio.run(_run())

    def test_close_is_idempotent(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            bus.close()
            bus.close()  # should not raise

        asyncio.run(_run())
