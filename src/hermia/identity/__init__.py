"""Machine identity: an exact, salted id bound to the silicon (hermia-cfqv).

Identity comes from NON-TRANSFERABLE identifiers — firmware UUID, hardware serial,
or a minted on-host token — matched exactly. Capabilities (CPU, memory, GPU) are
recorded beside it and never hashed, so a RAM upgrade is a visible fact rather
than a new machine.

Never from a MAC or an IP: reservations here are bound to detachable adapters and
a dock, so a network-derived identity follows the accessory, not the computer.

Nothing here stamps a result row yet. For a fleet run the model executes on a
remote host while hermia runs locally, so stamping the LOCAL machine onto a
remote row would manufacture exactly the misattribution this package exists to
prevent. Row wiring lands with the remote-probe transport decision.
"""
from hermia.identity.crosscheck import (
    IdentityWarning,
    check_identity_consistency,
    pending_conflicts,
    record_observation,
    resolve_conflict,
)
from hermia.identity.derive import derive_machine_id, select_source
from hermia.identity.probes import LocalProbe
from hermia.identity.salt import SaltInfo, load_or_create_salt, load_salt
from hermia.identity.types import (
    HardwareProbe,
    MachineCapabilities,
    MachineIdentifiers,
    MachineIdentity,
    MachineObservation,
    is_usable_identifier,
)

__all__ = [
    "HardwareProbe",
    "IdentityWarning",
    "LocalProbe",
    "MachineCapabilities",
    "MachineIdentifiers",
    "MachineIdentity",
    "MachineObservation",
    "SaltInfo",
    "check_identity_consistency",
    "derive_machine_id",
    "is_usable_identifier",
    "load_or_create_salt",
    "load_salt",
    "pending_conflicts",
    "record_observation",
    "resolve_conflict",
    "select_source",
]
