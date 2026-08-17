"""Hardware facts + salt -> machine_id (hermia-cfqv). Pure function, no I/O."""
from __future__ import annotations

import hashlib
import hmac
import json

from hermia.identity.types import HardwareFacts, MachineIdentity

ID_HEX_CHARS = 16


def derive_machine_id(facts: HardwareFacts, salt: bytes) -> MachineIdentity:
    """Derive a salted, locally-unique machine id.

    Returns ``machine_id=None`` with an explanatory ``basis`` whenever the
    machine-bound identifier is missing. There is deliberately no partial or
    fallback identity: a hash of CPU + RAM alone would collide across identical
    laptops (identical laptop models are common in a fleet), and two
    machines sharing an identity is precisely the defect this prevents.
    Admitting "not known" is the safer failure.

    Only the derived digest is returned — never the salt, never a raw hardware
    identifier.
    """
    if not facts.is_identifiable:
        return MachineIdentity(None, "unavailable:no-platform-uuid", facts.os_family)

    canonical = json.dumps(
        {
            "platform_uuid": facts.platform_uuid,
            "cpu_brand": facts.cpu_brand,
            "ram_bytes": facts.ram_bytes,
            "os_family": facts.os_family,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hmac.new(salt, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return MachineIdentity(
        digest[:ID_HEX_CHARS], "measured:platform-uuid+cpu+ram", facts.os_family
    )
