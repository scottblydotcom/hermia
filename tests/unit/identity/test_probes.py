"""Cross-platform local hardware probe (hermia-cfqv)."""
from unittest.mock import patch

from hermia.identity.probes import LocalProbe

IOREG_OUT = '    "IOPlatformUUID" = "ABC-123"\n'


def _mac_run(cmd, **kwargs):
    joined = " ".join(cmd)
    if "ioreg" in joined:
        return IOREG_OUT
    if "machdep.cpu.brand_string" in joined:
        return "Apple M1 Pro"
    if "hw.memsize" in joined:
        return "17179869184"
    return None


def test_macos_probe_parses_ioreg_and_sysctl():
    with patch("hermia.identity.probes._run", side_effect=_mac_run):
        f = LocalProbe(os_family="darwin").probe()
    assert f.platform_uuid == "ABC-123"
    assert f.cpu_brand == "Apple M1 Pro"
    assert f.ram_bytes == 17179869184
    assert f.is_identifiable
    assert f.unavailable == ()


def test_probe_failure_yields_none_not_a_guess():
    with patch("hermia.identity.probes._run", return_value=None):
        f = LocalProbe(os_family="darwin").probe()
    assert f.platform_uuid is None
    assert not f.is_identifiable
    assert "platform_uuid" in f.unavailable


def test_unsupported_os_reports_unavailable_rather_than_raising():
    f = LocalProbe(os_family="plan9").probe()
    assert f.platform_uuid is None
    assert f.os_family == "plan9"
    assert not f.is_identifiable


def test_ram_bytes_is_never_zero_when_unmeasured():
    """0 would read as a real measurement of a 0-byte machine."""
    with patch("hermia.identity.probes._run", return_value=""):
        f = LocalProbe(os_family="darwin").probe()
    assert f.ram_bytes is None


def test_non_numeric_ram_is_none_not_an_exception():
    def bad(cmd, **kwargs):
        return "not-a-number" if "hw.memsize" in " ".join(cmd) else _mac_run(cmd)

    with patch("hermia.identity.probes._run", side_effect=bad):
        f = LocalProbe(os_family="darwin").probe()
    assert f.ram_bytes is None
    assert "ram_bytes" in f.unavailable


def test_linux_meminfo_kb_is_converted_to_bytes():
    def read(path):
        return {
            "/etc/machine-id": "deadbeef\n",
            "/proc/cpuinfo": "model name\t: AMD Ryzen 9\n",
            "/proc/meminfo": "MemTotal:       32768000 kB\n",
        }.get(str(path))

    with patch("hermia.identity.probes._read_text", side_effect=read):
        f = LocalProbe(os_family="linux").probe()
    assert f.platform_uuid == "deadbeef"
    assert f.cpu_brand == "AMD Ryzen 9"
    assert f.ram_bytes == 32768000 * 1024


def test_linux_falls_back_to_dmi_product_uuid_when_machine_id_absent():
    def read(path):
        return {
            "/sys/class/dmi/id/product_uuid": "DMI-UUID-9\n",
            "/proc/cpuinfo": "model name\t: AMD Ryzen 9\n",
            "/proc/meminfo": "MemTotal:       1024 kB\n",
        }.get(str(path))

    with patch("hermia.identity.probes._read_text", side_effect=read):
        f = LocalProbe(os_family="linux").probe()
    assert f.platform_uuid == "DMI-UUID-9"


def test_no_mac_address_is_ever_collected():
    """A MAC-derived identity would migrate with a dongle or dock."""
    with patch("hermia.identity.probes._run", side_effect=_mac_run):
        f = LocalProbe(os_family="darwin").probe()
    assert not hasattr(f, "mac")
    assert not hasattr(f, "mac_address")


# ---------------------------------------------------------------------------
# Regression tests for OS-family detection.
#
# The first fleet-generated implementation used `os.name` (which returns
# "posix" on macOS AND Linux, "nt" on Windows) and matched the Windows branch
# on "win32". Both are wrong for `platform.system().lower()`, so the default
# constructor silently probed NOTHING on every platform and returned all-nulls.
# The end-to-end determinism test did not catch it, because null == null is
# perfectly stable. These assert the actual family strings.
# ---------------------------------------------------------------------------


def test_default_os_family_is_platform_system_not_os_name():
    import platform as _platform

    assert LocalProbe().os_family == _platform.system().lower()


def test_default_os_family_is_never_a_posix_or_nt_style_value():
    assert LocalProbe().os_family not in {"posix", "nt", "java"}


def test_windows_branch_matches_the_string_platform_system_returns():
    """platform.system().lower() is 'windows' — never 'win32'."""

    def win_run(cmd, **kwargs):
        joined = " ".join(cmd)
        if "MachineGuid" in joined:
            return "    MachineGuid    REG_SZ    GUID-XYZ\n"
        if "wmic" in joined:
            return "TotalPhysicalMemory\n34359738368\n"
        return None

    with patch("hermia.identity.probes._run", side_effect=win_run):
        f = LocalProbe(os_family="windows").probe()
    assert f.platform_uuid == "GUID-XYZ"
    assert f.ram_bytes == 34359738368
    assert f.is_identifiable


def test_darwin_probe_actually_measures_on_this_machine_when_on_darwin():
    """On a real Mac the default probe must produce a usable identity."""
    import platform as _platform

    import pytest

    if _platform.system().lower() != "darwin":
        pytest.skip("darwin-only: asserts the default probe measures real hardware")
    f = LocalProbe().probe()
    assert f.is_identifiable, f"default probe measured nothing: {f.unavailable}"
    assert f.ram_bytes and f.ram_bytes > 0


def test_blank_measurement_counts_as_unmeasured():
    def blank(cmd, **kwargs):
        return '  "IOPlatformUUID" = ""  ' if "ioreg" in " ".join(cmd) else "   "

    with patch("hermia.identity.probes._run", side_effect=blank):
        f = LocalProbe(os_family="darwin").probe()
    assert f.platform_uuid is None
    assert f.cpu_brand is None
    assert set(f.unavailable) == {"platform_uuid", "cpu_brand", "ram_bytes"}


def test_empty_windows_registry_value_is_not_mistaken_for_a_uuid():
    """`reg query` prints '<name> <type> <value>'. An EMPTY value leaves only
    two tokens, and taking the last one returns the literal type name 'REG_SZ'
    — a fabricated identity that every affected box would share."""
    from hermia.identity.probes import _windows_uuid

    assert _windows_uuid("    MachineGuid    REG_SZ    \n") is None
    assert _windows_uuid("    MachineGuid    REG_SZ\n") is None
    assert _windows_uuid("    MachineGuid    REG_SZ    abc-123\n") == "abc-123"


def test_windows_probe_with_empty_guid_is_not_identifiable():
    def win_run(cmd, **kwargs):
        joined = " ".join(cmd)
        if "MachineGuid" in joined:
            return "    MachineGuid    REG_SZ    \n"
        return None

    with patch("hermia.identity.probes._run", side_effect=win_run):
        f = LocalProbe(os_family="windows").probe()
    assert f.platform_uuid is None
    assert not f.is_identifiable
    assert "platform_uuid" in f.unavailable
