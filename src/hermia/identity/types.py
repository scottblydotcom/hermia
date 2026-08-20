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
from typing import ClassVar, Protocol

# Firmware placeholder values that are NOT unique and must never be accepted as
# an identity. Vendors ship these in volume: all-zero/all-FF SMBIOS UUIDs come
# from buggy firmware, and DIY builds (this fleet has some) leave the serial as
# an unfilled template string.
KNOWN_BAD_IDENTIFIERS: frozenset[str] = frozenset(
    {
        # mass-duplicated vendor UUID, in canonical (alnum-folded) form
        "03000200040005000006000700080009",
        "tobefilledbyoem",
        "systemserialnumber",
        "baseboardserialnumber",
        "chassisserialnumber",
        "defaultstring",
        "notspecified",
        "notapplicable",
        "none",
        "null",
        "unknown",
        "oem",
        "na",
        "invalid",
        "serialnumber",
        "filledbyoem",
    }
)

# Minimum length for a value to be plausibly unique. Vendors ship short filler
# like "0", "123", "NA"; a real UUID or serial is comfortably longer.
_MIN_IDENTIFIER_LEN = 6


def canonical_identifier(value: str | None) -> str | None:
    """Canonical form used for BOTH the placeholder screen and hashing.

    Case and hyphenation are formatting, not identity: Linux reports a firmware
    UUID lowercase while Windows and macOS report it uppercase, and the same
    UUID appears hyphenated in one place and bare in another. Hashing the raw
    string makes one physical motherboard produce different ids depending on
    which OS asked — a split identity created purely by punctuation.
    """
    if value is None:
        return None
    folded = "".join(ch for ch in value.strip().lower() if ch.isalnum())
    return folded or None


def is_usable_identifier(value: str | None) -> bool:
    """True when a value is present and not a known non-unique placeholder.

    Screening happens on the CANONICAL form, so "To Be Filled By O.E.M",
    "to be filled by o.e.m." and "TO_BE_FILLED_BY_OEM" are all caught by one
    entry. Exact-string matching missed every variant a vendor happened to
    punctuate differently, and two DIY boxes sharing a filler serial then
    derived the SAME machine id.
    """
    canon = canonical_identifier(value)
    if canon is None or len(canon) < _MIN_IDENTIFIER_LEN:
        return False
    if canon in KNOWN_BAD_IDENTIFIERS:
        return False
    if len(set(canon)) == 1:  # "000000...", "ffffff...", "xxxxxx..."
        return False
    return not canon.isdigit() or len(set(canon)) > 2


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
        out: dict[str, str] = {}
        for k, v in candidates.items():
            canon = canonical_identifier(v) if is_usable_identifier(v) else None
            if canon is not None:
                out[k] = canon
        return out

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
    gpu_description: str | None = None
    vram_bytes: int | None = None
    is_virtual: bool | None = None
    unavailable: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class MachineIdentity:
    """A derived identity. ``machine_id is None`` is a valid, explicit outcome.

    ``source`` names which identifier produced it, so a weak identity can never
    be silently read as a strong one, and a later change of source is visible
    rather than appearing as a brand-new machine.

    ``salt_scope`` records WHICH salt produced the id. Two ids are comparable
    only when their scopes match — an id derived under a per-install salt says
    nothing about one derived under a fleet salt. Without this field the scope
    that ``salt.load_salt`` computes is discarded at the moment of derivation,
    and incomparable ids look identical in shape.
    """

    machine_id: str | None
    source: str
    basis: str
    salt_scope: str = "unspecified"

    #: Sources that a disk clone duplicates. An id derived from one of these is
    #: NOT unique to a machine, and two cloned VMs derive the same value.
    TRANSFERABLE_SOURCES: ClassVar[frozenset[str]] = frozenset({"persisted-token"})

    @property
    def is_transferable(self) -> bool:
        """True when a disk clone would reproduce this exact id elsewhere.

        The firmware root is bound to the board; the minted token is a file. In a
        VM — where firmware identifiers are routinely absent — identity falls
        back to that file, and cloning the image clones the identity. The id is
        still the best available, but callers must be able to SEE that it is
        clone-vulnerable rather than reading it as machine-unique.
        """
        return self.source in self.TRANSFERABLE_SOURCES

    @property
    def is_comparable(self) -> bool:
        """False when the salt scope is unknown, so this id must not be matched.

        Ids are only comparable within one salt scope. A caller that took bare
        bytes (rather than SaltInfo) has no scope, and an unscoped id looks
        exactly like a scoped one — so comparing them silently mixes namespaces.
        """
        return self.machine_id is not None and self.salt_scope != "unspecified"


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
