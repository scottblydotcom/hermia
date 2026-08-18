"""Exact identity derivation (hermia-cfqv)."""
import pytest

from hermia.identity.derive import derive_machine_id, select_source
from hermia.identity.salt import SaltInfo
from hermia.identity.types import MachineIdentifiers

SALT = b"\x01" * 32
OTHER = b"\x02" * 32
FULL = MachineIdentifiers(firmware_uuid="UUID-1", hardware_serial="SER-1")


def test_id_is_16_hex_and_deterministic():
    a, b = derive_machine_id(FULL, SALT), derive_machine_id(FULL, SALT)
    assert a.machine_id == b.machine_id
    assert a.machine_id is not None and len(a.machine_id) == 16
    assert all(c in "0123456789abcdef" for c in a.machine_id)


def test_different_salt_gives_different_id():
    assert derive_machine_id(FULL, SALT).machine_id != derive_machine_id(FULL, OTHER).machine_id


def test_two_machines_same_model_do_not_collide():
    a = MachineIdentifiers(firmware_uuid="UUID-A", hardware_serial="SER-A")
    b = MachineIdentifiers(firmware_uuid="UUID-B", hardware_serial="SER-B")
    assert derive_machine_id(a, SALT).machine_id != derive_machine_id(b, SALT).machine_id


def test_no_usable_identifier_yields_null_with_reason():
    got = derive_machine_id(MachineIdentifiers(), SALT)
    assert got.machine_id is None
    assert got.basis == "unavailable:no-usable-identifier"
    assert got.source == "none"


def test_placeholder_identifiers_do_not_produce_an_identity():
    """A vendor placeholder must never become a shared identity."""
    ident = MachineIdentifiers(firmware_uuid="00000000-0000-0000-0000-000000000000")
    assert derive_machine_id(ident, SALT).machine_id is None


def test_preference_order_strongest_first():
    assert select_source(FULL)[0] == "firmware-uuid+serial"
    assert select_source(MachineIdentifiers(firmware_uuid="U"))[0] == "firmware-uuid"
    assert select_source(MachineIdentifiers(hardware_serial="S"))[0] == "hardware-serial"
    assert select_source(MachineIdentifiers(persisted_token="T"))[0] == "persisted-token"  # noqa: S106 - field name, not a credential


def test_firmware_root_outranks_the_on_disk_token():
    """A cloned disk image duplicates the token; firmware survives reinstall."""
    ident = MachineIdentifiers(firmware_uuid="U", persisted_token="T")  # noqa: S106 - field name, not a credential
    assert derive_machine_id(ident, SALT).source == "firmware-uuid"


# --- THE POINT OF THE SPLIT ---------------------------------------------


def test_capabilities_cannot_change_the_identity():
    """A RAM upgrade, a kernel update, a new GPU: identity must not move.

    The previous design hashed ram_bytes into the id, so a Linux kernel update
    that shifts MemTotal looked exactly like a hardware swap.
    """
    before = derive_machine_id(FULL, SALT)
    # There is deliberately no way to pass capabilities in at all.
    after = derive_machine_id(
        MachineIdentifiers(firmware_uuid="UUID-1", hardware_serial="SER-1"), SALT
    )
    assert before.machine_id == after.machine_id


def test_raw_identifiers_never_appear_in_the_result():
    got = derive_machine_id(FULL, SALT)
    blob = f"{got.machine_id}{got.source}{got.basis}"
    assert "UUID-1" not in blob and "SER-1" not in blob


def test_source_change_is_visible_rather_than_silent():
    """Losing the firmware root changes the id -- but the source says why."""
    strong = derive_machine_id(FULL, SALT)
    weak = derive_machine_id(MachineIdentifiers(persisted_token="T"), SALT)  # noqa: S106 - field name, not a credential
    assert strong.source != weak.source
    assert strong.machine_id != weak.machine_id


# --- CodeRabbit: a degenerate salt must fail loudly ----------------------


@pytest.mark.parametrize("bad", [b"", b"x", b"\x00" * 31, b"\x00" * 33, "notbytes"])
def test_invalid_salt_is_rejected(bad):
    """An empty/short salt yields a confident id with a tiny keyspace, which
    makes the underlying hardware identifier confirmable by brute force."""
    with pytest.raises(ValueError, match="32 bytes"):
        derive_machine_id(FULL, bad)


def test_salt_scope_is_carried_onto_the_identity():
    """salt.py requires the scope be recorded with any derived id; without this
    an install-scoped id and a fleet-scoped id look identical in shape."""
    info = SaltInfo(SALT, "fleet:env")
    got = derive_machine_id(FULL, info)
    assert got.salt_scope == "fleet:env"
    assert got.machine_id is not None


def test_scope_is_carried_even_when_nothing_is_identifiable():
    got = derive_machine_id(MachineIdentifiers(), SaltInfo(SALT, "install"))
    assert got.machine_id is None
    assert got.salt_scope == "install"


def test_bare_bytes_salt_reports_an_unspecified_scope():
    assert derive_machine_id(FULL, SALT).salt_scope == "unspecified"
