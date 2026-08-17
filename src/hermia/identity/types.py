"""Types for machine identity (hermia-cfqv). No I/O, no subprocess — pure data.

A row's machine identity has historically been ``fleet_host_name``: an
operator-typed string in a fleet YAML, verified against nothing. It has lied in
four independent ways in this corpus — one machine under several names, tunnel
ports repointed between machines, DHCP reservations bound to detachable USB
dongles, and a Thunderbolt dock whose MAC follows whichever laptop is docked.

Note what is deliberately absent here: there is no MAC field. A MAC-derived
identity migrates with a dongle or a dock rather than with the computer, which
is the specific failure this module exists to end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class HardwareFacts:
    """Facts measured ON a machine. ``None`` means NOT MEASURED — never guessed."""

    platform_uuid: str | None
    cpu_brand: str | None
    ram_bytes: int | None
    os_family: str
    unavailable: tuple[str, ...] = field(default=())

    @property
    def is_identifiable(self) -> bool:
        """True only when the strong, machine-bound identifier was measured.

        CPU brand and RAM size are entropy, NOT identity: two identical laptops
        share both. Requiring ``platform_uuid`` is what stops two laptops of
        identical model and memory from hashing to the same ``machine_id``.
        """
        return bool(self.platform_uuid)


@dataclass(frozen=True)
class MachineIdentity:
    """A derived identity. ``machine_id is None`` is a valid, explicit outcome."""

    machine_id: str | None
    basis: str
    os_family: str


class HardwareProbe(Protocol):
    """Measures hardware facts for one machine.

    ``LocalProbe`` implements this for the machine hermia runs on. Remote probes
    (SSH, agent) implement the same Protocol later; nothing else in this package
    may assume the facts came from localhost.
    """

    def probe(self) -> HardwareFacts: ...
