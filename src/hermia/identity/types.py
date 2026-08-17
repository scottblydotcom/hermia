"""Types for machine identity (hermia-cfqv). No I/O, no subprocess — pure data.

The central split, and the reason this module exists in this shape:

    IDENTIFIERS answer "which machine is this?" — non-transferable, bound to the
    silicon. Only these are ever hashed into a machine_id.

    CAPABILITIES answer "what does this machine have?" — CPU, memory, GPU. These
    are RECORDED and never hashed. Memory is a capability, not an identity: a RAM
    upgrade must not make one machine look like two, and on Linux the reported
    total drifts with kernel updates and driver reservations all by itself.

That split is the whole design. An earlier version hashed capabilities into the
identity and then tried to survive the resulting instability with weighted
threshold matching. Two independent outside reviews rejected that: any threshold
loose enough to tolerate a hardware repair will merge two identical laptops, and
any threshold tight enough to keep them apart is just an exact match on the
strongest identifier. Threshold matching was removed rather than tuned.

Note what is absent from MachineIdentifiers: anything detachable. No MAC, no IP,
no hostname. DHCP reservations here are bound to USB/Thunderbolt adapters and a
dock, so a network-derived identity follows the accessory rather than the
computer — the original defect. A MAC is still recorded, but as a capability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# Firmware placeholder values that are NOT unique and must never be accepted as
# an identity. Vendors ship these in volume: all-zero/all-FF SMBIOS UUIDs come
# from buggy firmware, and DIY builds (this fleet has some) leave the serial as
# an unfilled template string.
KNOWN_BAD_IDENTIFIERS: frozenset[str] = frozenset(
    {
        "00000000-0000-0000-0000-000000000000",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "03000200-0400-0500-0006-000700080009",  # mass-duplicated vendor UUID
        "to be filled by o.e.m.",
        "to be filled by oem",
        "system serial number",
        "default string",
        "not specified",
        "none",
        "unknown",
        "0",
    }
)


def is_usable_identifier(value: str | None) -> bool:
    """True when a value is present and not a known non-unique placeholder."""
    if value is None:
        return False
    cleaned = value.strip()
    return bool(cleaned) and cleaned.lower() not in KNOWN_BAD_IDENTIFIERS


@dataclass(frozen=True)
class MachineIdentifiers:
    """Non-transferable identifiers. ``None`` means NOT MEASURED — never guessed.

    ``persisted_token`` is a UUID hermia mints once and stores on the machine. It
    is the fallback for hosts whose firmware exposes nothing usable. It ranks
    BELOW the firmware root because it lives on the filesystem, so a cloned disk
    image duplicates it — the failure mode that makes VM fleets collapse into one
    identity.
    """

    firmware_uuid: str | None = None
    hardware_serial: str | None = None
    persisted_token: str | None = None
    unavailable: tuple[str, ...] = field(default=())

    @property
    def usable(self) -> dict[str, str]:
        """The identifiers that are present AND not known-bad placeholders."""
        candidates = {
            "firmware_uuid": self.firmware_uuid,
            "hardware_serial": self.hardware_serial,
            "persisted_token": self.persisted_token,
        }
        return {
            k: v.strip()
            for k, v in candidates.items()
            if v is not None and is_usable_identifier(v)
        }

    @property
    def is_identifiable(self) -> bool:
        return bool(self.usable)


@dataclass(frozen=True)
class MachineCapabilities:
    """What the machine HAS. Recorded, reported, compared — never hashed.

    A change here is information, not an identity crisis. ``nic_mac`` lives here
    precisely because it is detachable: recording it lets an operator see that a
    dock moved, without ever letting a dock define which machine answered.
    """

    cpu_brand: str | None = None
    logical_cores: int | None = None
    ram_bytes: int | None = None
    model_identifier: str | None = None
    os_family: str | None = None
    os_version: str | None = None
    nic_mac: str | None = None
    is_virtual: bool | None = None
    unavailable: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class MachineIdentity:
    """A derived identity. ``machine_id is None`` is a valid, explicit outcome.

    ``source`` names which identifier produced it, so a weak identity can never
    be silently read as a strong one, and a later change of source is visible
    rather than appearing as a brand-new machine.
    """

    machine_id: str | None
    source: str
    basis: str


@dataclass(frozen=True)
class MachineObservation:
    """One probe result: who it is, plus what it has."""

    identifiers: MachineIdentifiers
    capabilities: MachineCapabilities


class HardwareProbe(Protocol):
    """Measures one machine. ``LocalProbe`` covers the machine hermia runs on.

    Remote probes (SSH, sidecar endpoint) implement this same Protocol later.
    Nothing else in the package may assume the observation came from localhost —
    for a fleet run it must not, or every row gets the client's identity.
    """

    def probe(self) -> MachineObservation: ...
