"""Machine identity: a salted, locally-unique id bound to a machine (hermia-cfqv).

Identity is derived from identifiers that belong to the COMPUTER — platform
UUID, CPU brand, physical RAM — and never from a MAC address, because DHCP
reservations in this fleet are bound to detachable USB/Thunderbolt dongles and a
Thunderbolt dock. A MAC-derived id would follow the accessory, not the machine.

Nothing here stamps a result row yet. For a fleet run the model executes on a
remote host while hermia runs locally, so stamping the LOCAL machine onto a
remote row would manufacture exactly the misleading attribution this package
exists to prevent. Row wiring lands with the remote-probe transport decision.
"""
from hermia.identity.crosscheck import (
    IdentityWarning,
    check_identity_consistency,
    record_observation,
)
from hermia.identity.derive import derive_machine_id
from hermia.identity.probes import LocalProbe
from hermia.identity.salt import load_or_create_salt
from hermia.identity.types import HardwareFacts, HardwareProbe, MachineIdentity

__all__ = [
    "HardwareFacts",
    "HardwareProbe",
    "IdentityWarning",
    "LocalProbe",
    "MachineIdentity",
    "check_identity_consistency",
    "derive_machine_id",
    "load_or_create_salt",
    "record_observation",
]
