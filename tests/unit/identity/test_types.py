"""Identifier/capability split (hermia-cfqv)."""
from dataclasses import FrozenInstanceError

import pytest

from hermia.identity.types import (
    MachineCapabilities,
    MachineIdentifiers,
    MachineIdentity,
    is_usable_identifier,
)


def test_identifiers_are_frozen():
    i = MachineIdentifiers(firmware_uuid="UUID-0001-AAAA")
    with pytest.raises(FrozenInstanceError):
        i.firmware_uuid = "other"  # type: ignore[misc]


def test_unmeasured_is_none_not_empty_string():
    i = MachineIdentifiers()
    assert i.firmware_uuid is None and i.hardware_serial is None
    assert i.persisted_token is None and i.unavailable == ()


def test_identifiers_carry_nothing_detachable():
    """A MAC/IP-derived identity follows the dongle, not the machine."""
    fields = set(MachineIdentifiers.__dataclass_fields__)
    assert not fields & {"mac", "nic_mac", "mac_address", "ip", "hostname"}


def test_capabilities_carry_the_mac_instead():
    assert "nic_mac" in MachineCapabilities.__dataclass_fields__


def test_capabilities_are_not_identifiers():
    """RAM/CPU must not be reachable as identity material."""
    fields = set(MachineIdentifiers.__dataclass_fields__)
    assert not fields & {"ram_bytes", "cpu_brand", "logical_cores"}


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "   ",
        "00000000-0000-0000-0000-000000000000",
        "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
        "03000200-0400-0500-0006-000700080009",
        "To Be Filled By O.E.M.",
        "  default string  ",
        "Not Specified",
    ],
)
def test_known_bad_placeholders_are_not_usable(bad):
    assert not is_usable_identifier(bad)


def test_real_values_are_usable():
    assert is_usable_identifier("ABC-123")
    assert is_usable_identifier("C02XY1234567")


def test_only_placeholders_means_not_identifiable():
    i = MachineIdentifiers(
        firmware_uuid="00000000-0000-0000-0000-000000000000",
        hardware_serial="To Be Filled By O.E.M.",
    )
    assert i.usable == {}
    assert not i.is_identifiable


def test_identity_null_id_still_carries_source_and_basis():
    m = MachineIdentity(None, "none", "unavailable:no-usable-identifier")
    assert m.machine_id is None and m.source and m.basis


# --- Antigravity: the placeholder screen was trivially evaded -------------


@pytest.mark.parametrize(
    "filler",
    [
        "To Be Filled By O.E.M",      # no trailing dot — the variant that slipped through
        "To Be Filled By O.E.M.",
        "TO_BE_FILLED_BY_OEM",
        "to be filled by oem",
        "Default String",
        "Default string ",
        "System Serial Number",
        "Base Board Serial Number",
        "Chassis Serial Number",
        "00000000",
        "0000000000000000",
        "FFFFFFFF",
        "xxxxxxxxxxxx",
        "None",
        "N/A",
        "Not Specified",
        "0",
        "123",
    ],
)
def test_vendor_filler_never_counts_as_an_identity(filler):
    """Two DIY boxes sharing a filler serial derived the SAME machine id."""
    assert not is_usable_identifier(filler)


@pytest.mark.parametrize(
    "real", ["4C4C4544-0031-104D-8032-B8C04F4A3633", "C02XY1234567", "deadbeefcafe"]
)
def test_real_identifiers_still_pass(real):
    assert is_usable_identifier(real)


def test_two_boxes_with_the_same_filler_serial_do_not_collide():
    a = MachineIdentifiers(hardware_serial="To Be Filled By O.E.M")
    b = MachineIdentifiers(hardware_serial="To Be Filled By O.E.M")
    assert a.usable == {} and b.usable == {}
    assert not a.is_identifiable


def test_case_and_hyphenation_are_formatting_not_identity():
    """One motherboard reported by Linux (lowercase) and Windows (uppercase)."""
    lower = MachineIdentifiers(firmware_uuid="4c4c4544-0031-104d-8032-b8c04f4a3633")
    upper = MachineIdentifiers(firmware_uuid="4C4C4544-0031-104D-8032-B8C04F4A3633")
    bare = MachineIdentifiers(firmware_uuid="4c4c45440031104d8032b8c04f4a3633")
    assert lower.usable == upper.usable == bare.usable
