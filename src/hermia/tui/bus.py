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
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._subscribers[topic].append(q)
        return self._consume(q)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers of the given topic.

        Bounded subscribers drop their oldest queued event on overflow rather
        than block the publisher. Sparse (unbounded) subscribers never overflow.
        """
        for q in self._subscribers.get(topic, []):
            if q.maxsize and q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await q.put(event)

    @staticmethod
    async def _consume(q: asyncio.Queue[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        while True:
            ev = await q.get()
            yield ev
