"""SessionBus — topic-based async pub/sub for runner ↔ screens.

The only shared mutable state between the runner backend and the runner
screens. Screens subscribe to topics they care about; the runner publishes
events. Per-subscriber asyncio.Queue keeps a slow renderer from
backpressuring the runner.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any


class SessionBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    def subscribe(
        self,
        topic: str,
        *,
        maxsize: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to a topic. Returns an async iterator of event payloads.

        maxsize=0 (default) is an unbounded queue — appropriate for sparse
        trial topics. Pass maxsize > 0 for high-throughput streams (e.g.
        run.trial_chunk) that should drop-oldest on overflow.

        The returned generator self-cleans on close/cancel: when the subscriber
        screen pops or the generator is garbage-collected, the queue is removed
        from `self._subscribers` automatically. No manual unsubscribe needed.
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._subscribers[topic].append(q)
        return self._consume(topic, q)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers of the given topic.

        Bounded subscribers drop their oldest queued event on overflow rather
        than block the publisher. Sparse (unbounded) subscribers never overflow.
        """
        # Iterate over a snapshot — _consume's finally clause mutates the list
        # when a subscriber's generator closes mid-publish (would otherwise
        # raise RuntimeError: list changed size during iteration).
        for q in list(self._subscribers.get(topic, [])):
            if q.maxsize and q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            # put_nowait keeps the get_nowait + put pair atomic in
            # single-threaded asyncio — `await q.put` would yield between the
            # two ops, letting another coroutine fill the slot we just freed
            # and re-blocking the publisher on a full bounded queue.
            q.put_nowait(event)

    async def _consume(
        self,
        topic: str,
        q: asyncio.Queue[dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            while True:
                ev = await q.get()
                yield ev
        finally:
            # Remove this queue from the topic's subscriber list when the
            # generator closes (screen pop, cancel, gc). Idempotent — if the
            # queue is somehow already absent, ValueError is swallowed.
            if topic in self._subscribers:
                try:
                    self._subscribers[topic].remove(q)
                except ValueError:
                    pass
                if not self._subscribers[topic]:
                    del self._subscribers[topic]
