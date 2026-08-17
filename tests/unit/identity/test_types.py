"""Types for machine identity (hermia-cfqv)."""
import pytest

from hermia.identity.types import HardwareFacts, MachineIdentity


def test_hardware_facts_is_frozen():
    f = HardwareFacts(platform_uuid="U", cpu_brand="C", ram_bytes=1, os_family="darwin")
    with pytest.raises(Exception):
        f.platform_uuid = "other"  # type: ignore[misc]


def test_hardware_facts_defaults_unmeasured_to_none_not_empty_string():
    f = HardwareFacts(
        platform_uuid=None, cpu_brand=None, ram_bytes=None, os_family="linux"
    )
    assert f.platform_uuid is None
    assert f.cpu_brand is None
    assert f.ram_bytes is None
    assert f.unavailable == ()


def test_is_identifiable_requires_platform_uuid():
    """CPU+RAM alone must NOT count: identical laptop models share both."""
    assert HardwareFacts("U", "Apple M1 Pro", 17179869184, "darwin").is_identifiable
    assert not HardwareFacts(None, "Apple M1 Pro", 17179869184, "darwin").is_identifiable


def test_machine_identity_null_id_still_carries_a_basis():
    m = MachineIdentity(
        machine_id=None, basis="unavailable:no-platform-uuid", os_family="linux"
    )
    assert m.machine_id is None
    assert m.basis
