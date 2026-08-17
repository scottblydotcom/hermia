"""Cross-platform probe: identifiers vs capabilities (hermia-cfqv)."""
import platform as _platform
from unittest.mock import patch

import pytest

from hermia.identity.probes import LocalProbe, _reg_value


def _mac_run(cmd, **kwargs):
    joined = " ".join(cmd)
    if "ioreg" in joined:
        return '  "IOPlatformUUID" = "ABC-123"\n  "IOPlatformSerialNumber" = "C02XY"\n'
    if "machdep.cpu.brand_string" in joined:
        return "Apple M1 Pro"
    if "hw.memsize" in joined:
        return "17179869184"
    if "hw.logicalcpu" in joined:
        return "10"
    if "hw.model" in joined:
        return "MacBookPro18,1"
    return None


def test_macos_splits_identifiers_from_capabilities():
    with patch("hermia.identity.probes._run", side_effect=_mac_run):
        obs = LocalProbe(os_family="darwin").probe()
    assert obs.identifiers.firmware_uuid == "ABC-123"
    assert obs.identifiers.hardware_serial == "C02XY"
    assert obs.capabilities.ram_bytes == 17179869184
    assert obs.capabilities.cpu_brand == "Apple M1 Pro"
    assert obs.capabilities.model_identifier == "MacBookPro18,1"


def test_probe_failure_yields_none_not_a_guess():
    with patch("hermia.identity.probes._run", return_value=None):
        obs = LocalProbe(os_family="darwin").probe()
    assert obs.identifiers.firmware_uuid is None
    assert not obs.identifiers.is_identifiable
    assert "firmware_uuid" in obs.identifiers.unavailable
    assert obs.capabilities.ram_bytes is None


def test_unsupported_os_does_not_raise():
    obs = LocalProbe(os_family="plan9").probe()
    assert not obs.identifiers.is_identifiable
    assert obs.capabilities.os_family == "plan9"


def test_default_os_family_is_platform_system_not_os_name():
    """os.name returns 'posix' on macOS AND Linux, matching no branch at all."""
    assert LocalProbe().os_family == _platform.system().lower()
    assert LocalProbe().os_family not in {"posix", "nt", "java"}


def test_linux_prefers_the_firmware_root_over_the_on_disk_token():
    """Regression: the old code read /etc/machine-id first and never fell
    through to the firmware UUID, silently preferring the weakest identifier."""

    def read(path):
        return {
            "/sys/class/dmi/id/product_uuid": "DMI-UUID-9\n",
            "/sys/class/dmi/id/board_serial": "BOARD-7\n",
            "/etc/machine-id": "deadbeef\n",
            "/proc/cpuinfo": "processor\t: 0\nmodel name\t: AMD Ryzen 9\n",
            "/proc/meminfo": "MemTotal:       32768000 kB\n",
        }.get(str(path))

    with patch("hermia.identity.probes._read_text", side_effect=read):
        obs = LocalProbe(os_family="linux").probe()
    assert obs.identifiers.firmware_uuid == "DMI-UUID-9"
    assert obs.identifiers.hardware_serial == "BOARD-7"
    assert obs.identifiers.persisted_token == "deadbeef"
    assert obs.capabilities.ram_bytes == 32768000 * 1024
    assert obs.capabilities.cpu_brand == "AMD Ryzen 9"


def test_linux_root_gated_dmi_falls_back_to_the_token_but_records_the_gap():
    def read(path):
        return {"/etc/machine-id": "deadbeef\n"}.get(str(path))

    with patch("hermia.identity.probes._read_text", side_effect=read):
        obs = LocalProbe(os_family="linux").probe()
    assert obs.identifiers.firmware_uuid is None
    assert obs.identifiers.persisted_token == "deadbeef"
    assert "firmware_uuid" in obs.identifiers.unavailable


def test_windows_reads_the_firmware_uuid_not_only_machineguid():
    """Regression: the old code read ONLY MachineGuid, an OS-install id."""

    def win_run(cmd, **kwargs):
        joined = " ".join(cmd)
        if "csproduct" in joined and "UUID" in joined:
            return "UUID\n4C4C4544-0031\n"
        if "baseboard" in joined:
            return "SerialNumber\nBOARD-XYZ\n"
        if "MachineGuid" in joined:
            return "    MachineGuid    REG_SZ    guid-abc\n"
        return None

    with patch("hermia.identity.probes._run", side_effect=win_run):
        obs = LocalProbe(os_family="windows").probe()
    assert obs.identifiers.firmware_uuid == "4C4C4544-0031"
    assert obs.identifiers.hardware_serial == "BOARD-XYZ"
    assert obs.identifiers.persisted_token == "guid-abc"


@pytest.mark.parametrize(
    "line,expected",
    [
        ("    MachineGuid    REG_SZ    abc-123\n", "abc-123"),
        ("    MachineGuid    REG_SZ    \n", None),
        ("    MachineGuid    REG_SZ\n", None),
    ],
)
def test_empty_registry_value_is_not_mistaken_for_an_identifier(line, expected):
    assert _reg_value(line, "MachineGuid") == expected


def test_blank_measurement_counts_as_unmeasured():
    def blank(cmd, **kwargs):
        return '  "IOPlatformUUID" = ""  ' if "ioreg" in " ".join(cmd) else "   "

    with patch("hermia.identity.probes._run", side_effect=blank):
        obs = LocalProbe(os_family="darwin").probe()
    assert obs.identifiers.firmware_uuid is None
    assert obs.capabilities.cpu_brand is None


def test_real_probe_measures_something_on_this_machine():
    if _platform.system().lower() != "darwin":
        pytest.skip("darwin-only: asserts the default probe measures real hardware")
    obs = LocalProbe().probe()
    assert obs.identifiers.is_identifiable, f"measured nothing: {obs.identifiers.unavailable}"
    assert obs.capabilities.ram_bytes and obs.capabilities.ram_bytes > 0
    assert obs.capabilities.model_identifier
