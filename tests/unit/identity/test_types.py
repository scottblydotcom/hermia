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
    i = MachineIdentifiers(firmware_uuid="U")
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
