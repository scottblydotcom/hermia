"""Identifiers + salt -> machine_id (hermia-cfqv). Pure function, no I/O.

Exact match on a strict preference order. No weighting, no threshold, no fuzzy
comparison — see types.py for why that approach was removed rather than tuned.

Capabilities are NEVER an input here. That is what makes a RAM upgrade a recorded
fact instead of a new machine.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from hermia.identity.salt import SALT_BYTES, SaltInfo
from hermia.identity.types import MachineIdentifiers, MachineIdentity

ID_HEX_CHARS = 16

# Strongest first. Both firmware values together beat either alone: vendors have
# shipped batches with duplicate SMBIOS UUIDs, and a serial alone is weaker still.
# The minted token ranks last because it lives on disk, so a cloned image carries
# it to another machine.
PREFERENCE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("firmware-uuid+serial", ("firmware_uuid", "hardware_serial")),
    ("firmware-uuid", ("firmware_uuid",)),
    ("hardware-serial", ("hardware_serial",)),
    ("persisted-token", ("persisted_token",)),
)


def select_source(identifiers: MachineIdentifiers) -> tuple[str, tuple[str, ...]] | None:
    """Return the strongest available (source_name, fields), or None."""
    usable = identifiers.usable
    for source, fields in PREFERENCE:
        if all(f in usable for f in fields):
            return source, fields
    return None


def derive_machine_id(
    identifiers: MachineIdentifiers, salt: bytes | SaltInfo
) -> MachineIdentity:
    """Derive an exact, salted machine id from non-transferable identifiers.

    Returns ``machine_id=None`` with an explanatory ``basis`` when no usable
    identifier exists. There is deliberately no partial identity: a value built
    from CPU and memory would collide across identical laptops, and two machines
    sharing an identity is exactly the defect this prevents. Admitting "not
    known" is the safer failure — a null is visible, a wrong id is not.

    Only the derived digest is returned: never the salt, never a raw identifier.

    Raises ``ValueError`` on a salt that is not exactly ``SALT_BYTES`` long. A
    short or empty salt is a caller bug, not a measurement gap: HMAC accepts it
    happily and returns a confident-looking id whose small keyspace makes the
    underlying hardware identifier confirmable by brute force — defeating the
    only thing the salt is there to do. It must fail loudly rather than return
    a null that reads like "this machine could not be identified".
    """
    scope = "unspecified"
    if isinstance(salt, SaltInfo):
        scope, salt = salt.scope, salt.salt
    if not isinstance(salt, bytes) or len(salt) != SALT_BYTES:
        raise ValueError(
            f"salt must be exactly {SALT_BYTES} bytes; got "
            f"{len(salt) if isinstance(salt, bytes) else type(salt).__name__}"
        )

    selected = select_source(identifiers)
    if selected is None:
        return MachineIdentity(
            None, "none", "unavailable:no-usable-identifier", scope
        )

    source, fields = selected
    usable = identifiers.usable
    canonical = json.dumps(
        {"source": source, **{f: usable[f] for f in fields}},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hmac.new(salt, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return MachineIdentity(
        digest[:ID_HEX_CHARS], source, f"measured:{source}", scope
    )
