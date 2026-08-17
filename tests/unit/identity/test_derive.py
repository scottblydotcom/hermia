"""Salted machine_id derivation (hermia-cfqv)."""
from hermia.identity.derive import derive_machine_id
from hermia.identity.types import HardwareFacts

SALT = b"\x01" * 32
OTHER = b"\x02" * 32
M1 = HardwareFacts("UUID-1", "Apple M1 Pro", 17179869184, "darwin")


def test_id_is_16_hex_chars_and_deterministic():
    a = derive_machine_id(M1, SALT)
    b = derive_machine_id(M1, SALT)
    assert a.machine_id == b.machine_id
    assert a.machine_id is not None
    assert len(a.machine_id) == 16
    assert all(c in "0123456789abcdef" for c in a.machine_id)


def test_different_salt_gives_different_id_for_same_machine():
    assert (
        derive_machine_id(M1, SALT).machine_id
        != derive_machine_id(M1, OTHER).machine_id
    )


def test_two_identical_models_with_different_uuids_do_not_collide():
    """Two laptops of identical model and memory must never share an id."""
    a = HardwareFacts("UUID-A", "Apple M1 Pro", 17179869184, "darwin")
    b = HardwareFacts("UUID-B", "Apple M1 Pro", 17179869184, "darwin")
    assert derive_machine_id(a, SALT).machine_id != derive_machine_id(b, SALT).machine_id


def test_missing_platform_uuid_yields_null_id_with_reason():
    f = HardwareFacts(None, "Apple M1 Pro", 17179869184, "darwin")
    got = derive_machine_id(f, SALT)
    assert got.machine_id is None
    assert got.basis == "unavailable:no-platform-uuid"


def test_id_changes_when_ram_changes():
    """RAM is entropy in the tuple, so a genuine hardware change is visible."""
    more = HardwareFacts("UUID-1", "Apple M1 Pro", 34359738368, "darwin")
    assert derive_machine_id(more, SALT).machine_id != derive_machine_id(M1, SALT).machine_id


def test_raw_identifiers_never_appear_in_the_result():
    got = derive_machine_id(M1, SALT)
    blob = f"{got.machine_id}{got.basis}{got.os_family}"
    assert "UUID-1" not in blob
    assert "Apple M1 Pro" not in blob
    assert "17179869184" not in blob


def test_basis_records_what_was_measured_on_success():
    assert derive_machine_id(M1, SALT).basis == "measured:platform-uuid+cpu+ram"


def test_same_uuid_different_os_family_does_not_collide():
    a = HardwareFacts("UUID-1", "Apple M1 Pro", 17179869184, "darwin")
    b = HardwareFacts("UUID-1", "Apple M1 Pro", 17179869184, "linux")
    assert derive_machine_id(a, SALT).machine_id != derive_machine_id(b, SALT).machine_id
