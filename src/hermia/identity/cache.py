from __future__ import annotations

import threading
from collections.abc import Callable

from hermia.identity.types import MachineObservation


class IdentityCache:
    """Thread-safe cache for remote identity probes.

    Probes each target at most once; subsequent calls return the cached result.
    """

    def __init__(self) -> None:
        self._cache: dict[str, MachineObservation] = {}
        self._lock = threading.Lock()
        self._target_locks: dict[str, threading.Lock] = {}

    def get_or_probe(
        self,
        target: str,
        factory: Callable[[str], MachineObservation],
    ) -> MachineObservation:
        """Return cached observation for target, or probe and cache it.

        A target is probed AT MOST ONCE even under concurrent first access: a
        per-target lock serializes probing of the same host (an ssh round-trip)
        while distinct targets still probe concurrently. Without it, two threads
        racing an uncached target both fire the full ssh sequence.
        """
        with self._lock:
            if target in self._cache:
                return self._cache[target]
            target_lock = self._target_locks.setdefault(target, threading.Lock())

        with target_lock:
            with self._lock:
                if target in self._cache:
                    return self._cache[target]
            obs = factory(target)
            with self._lock:
                return self._cache.setdefault(target, obs)
