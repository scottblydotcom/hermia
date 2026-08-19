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

    def get_or_probe(
        self,
        target: str,
        factory: Callable[[str], MachineObservation],
    ) -> MachineObservation:
        """Return cached observation for target, or probe and cache it."""
        with self._lock:
            if target in self._cache:
                return self._cache[target]

        obs = factory(target)
        with self._lock:
            # Double-check after acquiring lock (in case another thread probed first)
            if target not in self._cache:
                self._cache[target] = obs
            else:
                obs = self._cache[target]
        return obs
