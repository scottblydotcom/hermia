"""Tests for IdentityCache — probe once per host (hermia-cfqv wiring)."""
from hermia.identity.cache import IdentityCache
from hermia.identity.types import (
    MachineCapabilities,
    MachineIdentifiers,
    MachineObservation,
)


def _obs(serial):
    return MachineObservation(MachineIdentifiers(hardware_serial=serial), MachineCapabilities())


def test_probes_once_per_target():
    calls = []

    def factory(target):
        calls.append(target)
        return _obs(f"sn-{target}")

    cache = IdentityCache()
    a1 = cache.get_or_probe("rampagev", factory)
    a2 = cache.get_or_probe("rampagev", factory)
    b1 = cache.get_or_probe("m1pro", factory)

    assert a1 is a2
    assert a1.identifiers.hardware_serial == "sn-rampagev"
    assert b1.identifiers.hardware_serial == "sn-m1pro"
    assert calls == ["rampagev", "m1pro"]
