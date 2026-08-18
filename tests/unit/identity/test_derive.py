"""Exact identity derivation (hermia-cfqv)."""
import pytest

from hermia.identity.derive import derive_machine_id, select_source
from hermia.identity.salt import SaltInfo
from hermia.identity.types import MachineIdentifiers

SALT = b"\x01" * 32
OTHER = b"\x02" * 32
FULL = MachineIdentifiers(firmware_uuid="UUID-0001-AAAA", hardware_serial="SERIAL-0001")


def test_id_is_16_hex_and_deterministic():
    a, b = derive_machine_id(FULL, SALT), derive_machine_id(FULL, SALT)
    assert a.machine_id == b.machine_id
    assert a.machine_id is not None and len(a.machine_id) == 16
    assert all(c in "0123456789abcdef" for c in a.machine_id)


def test_different_salt_gives_different_id():
    assert derive_machine_id(FULL, SALT).machine_id != derive_machine_id(FULL, OTHER).machine_id


def test_two_machines_same_model_do_not_collide():
    a = MachineIdentifiers(firmware_uuid="UUID-000A-AAAA", hardware_serial="SERIAL-000A")
    b = MachineIdentifiers(firmware_uuid="UUID-000B-BBBB", hardware_serial="SERIAL-000B")
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
    assert select_source(MachineIdentifiers(firmware_uuid="UUID-0001-AAAA"))[0] == "firmware-uuid"
    assert select_source(MachineIdentifiers(hardware_serial="SERIAL-0001"))[0] == "hardware-serial"
    assert select_source(MachineIdentifiers(persisted_token="TOKEN-0001"))[0] == "persisted-token"  # noqa: S106 - field name, not a credential


def test_firmware_root_outranks_the_on_disk_token():
    """A cloned disk image duplicates the token; firmware survives reinstall."""
    ident = MachineIdentifiers(firmware_uuid="UUID-0001-AAAA", persisted_token="TOKEN-0001")  # noqa: S106 - field name, not a credential
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
        MachineIdentifiers(firmware_uuid="UUID-0001-AAAA", hardware_serial="SERIAL-0001"), SALT
    )
    assert before.machine_id == after.machine_id


def test_raw_identifiers_never_appear_in_the_result():
    got = derive_machine_id(FULL, SALT)
    blob = f"{got.machine_id}{got.source}{got.basis}"
    assert "UUID-0001-AAAA" not in blob and "SERIAL-0001" not in blob


def test_source_change_is_visible_rather_than_silent():
    """Losing the firmware root changes the id -- but the source says why."""
    strong = derive_machine_id(FULL, SALT)
    weak = derive_machine_id(MachineIdentifiers(persisted_token="TOKEN-0001"), SALT)  # noqa: S106 - field name, not a credential
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


def test_same_machine_reported_in_different_case_gives_one_id():
    """Punctuation must not fork a physical machine into two identities."""
    lower = MachineIdentifiers(firmware_uuid="4c4c4544-0031-104d-8032-b8c04f4a3633")
    upper = MachineIdentifiers(firmware_uuid="4C4C4544-0031-104D-8032-B8C04F4A3633")
    assert derive_machine_id(lower, SALT).machine_id == derive_machine_id(upper, SALT).machine_id


def test_filler_serial_yields_no_identity_rather_than_a_shared_one():
    ident = MachineIdentifiers(hardware_serial="To Be Filled By O.E.M")
    assert derive_machine_id(ident, SALT).machine_id is None


# --- qwen3.5: a clone-vulnerable identity must say so -------------------


def test_a_cloned_vm_derives_the_same_id_but_is_flagged_transferable():
    """Two VMs from one image share /etc/machine-id, so they share an id. That
    is unavoidable — what is not acceptable is failing to SAY so."""
    a = MachineIdentifiers(persisted_token="deadbeefcafe1234")  # noqa: S106 - field name, not a credential
    b = MachineIdentifiers(persisted_token="deadbeefcafe1234")  # noqa: S106 - field name, not a credential
    ia, ib = derive_machine_id(a, SALT), derive_machine_id(b, SALT)
    assert ia.machine_id == ib.machine_id
    assert ia.is_transferable
    assert "transferable" in ia.basis
    assert "clone" in ia.basis


def test_a_firmware_rooted_identity_is_not_transferable():
    got = derive_machine_id(FULL, SALT)
    assert not got.is_transferable
    assert "transferable" not in got.basis


def test_an_unscoped_id_is_not_comparable():
    """Bare bytes carry no scope, so the id must not be matched against a
    scoped one — same shape, different namespace."""
    bare = derive_machine_id(FULL, SALT)
    scoped = derive_machine_id(FULL, SaltInfo(SALT, "fleet:file"))
    assert bare.salt_scope == "unspecified"
    assert not bare.is_comparable
    assert scoped.is_comparable
    assert bare.machine_id == scoped.machine_id  # identical value...
    assert bare.is_comparable != scoped.is_comparable  # ...but not interchangeable


def test_a_null_identity_is_never_comparable():
    assert not derive_machine_id(MachineIdentifiers(), SaltInfo(SALT, "fleet:env")).is_comparable
