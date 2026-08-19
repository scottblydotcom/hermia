"""Tests for SSHProbe — remote hardware identity over ssh (hermia-cfqv wiring).

Every test injects a fake ssh executor; nothing shells out. See the plan's
self-review: this proves parsing/dispatch/degrade logic, NOT a real ssh round
trip against live hardware (that is a separate live-verification step).
"""
from hermia.identity.probes import SSHProbe, _ssh_exec  # noqa: F401


class FakeSSH:
    """Maps a leading argv token to canned stdout; records calls."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, target, argv):
        self.calls.append((target, argv))
        return self.responses.get(argv[0])


# --- OS detection --------------------------------------------------------

def test_detect_os_maps_uname_to_family():
    assert SSHProbe("rampagev", exec_fn=FakeSSH({"uname": "Linux"}))._detect_os() == "linux"
    assert SSHProbe("m1pro", exec_fn=FakeSSH({"uname": "Darwin"}))._detect_os() == "darwin"


def test_detect_os_none_when_unreachable():
    assert SSHProbe("dead-host", exec_fn=FakeSSH({"uname": None}))._detect_os() is None


def test_explicit_os_family_skips_detection():
    ssh = FakeSSH({})
    assert SSHProbe("h", os_family="linux", exec_fn=ssh)._detect_os() == "linux"
    assert ssh.calls == []


# --- macOS ---------------------------------------------------------------

IOREG_FIXTURE = (
    '    "IOPlatformUUID" = "4C4C4544-0051-3010-8051-C7C04F503232"\n'
    '    "IOPlatformSerialNumber" = "C02XYZ123ABC"\n'
)
SPDISPLAYS_FIXTURE = (
    "Graphics/Displays:\n    Apple M1 Ultra:\n"
    "      Chipset Model: Apple M1 Ultra\n      Type: GPU\n"
)


def test_ssh_probe_darwin_reads_identity():
    ssh = FakeSSH({"uname": "Darwin", "ioreg": IOREG_FIXTURE, "sysctl": "128",
                   "sw_vers": "14.5", "system_profiler": SPDISPLAYS_FIXTURE})
    obs = SSHProbe("m1pro", exec_fn=ssh).probe()
    assert obs.identifiers.firmware_uuid == "4C4C4544-0051-3010-8051-C7C04F503232"
    assert obs.identifiers.hardware_serial == "C02XYZ123ABC"
    assert obs.capabilities.os_family == "darwin"
    assert obs.capabilities.gpu_description == "Apple M1 Ultra"


# --- Linux ---------------------------------------------------------------

NVIDIA_SMI_FIXTURE = "NVIDIA GeForce RTX 5090, 32607\n"  # name, memory.total MiB


def _linux_ssh(files):
    cmd_table = {"uname": "Linux", "nvidia-smi": NVIDIA_SMI_FIXTURE}

    class _F:
        calls = []

        def __call__(self, target, argv):
            if argv[0] == "cat":
                return files.get(argv[1])
            return cmd_table.get(argv[0])

    return _F()


def test_ssh_probe_linux_reads_identity_and_vram():
    files = {
        "/sys/class/dmi/id/product_uuid": "6a5b9c1d-0000-0000-0000-abcdef012345",
        "/sys/class/dmi/id/board_serial": "MB-SN-778899",
        "/sys/class/dmi/id/product_serial": "None",
        "/etc/machine-id": "0123456789abcdef0123456789abcdef",  # pragma: allowlist secret
        "/proc/cpuinfo": "processor\t: 0\nmodel name\t: AMD Ryzen 9 7950X\nprocessor\t: 1\n",
        "/proc/meminfo": "MemTotal:       65876000 kB\n",
        "/sys/class/dmi/id/product_name": "System Product Name",
        "/sys/class/dmi/id/sys_vendor": "ASUS",
    }
    obs = SSHProbe("rampagev", exec_fn=_linux_ssh(files)).probe()
    assert obs.identifiers.firmware_uuid == "6a5b9c1d-0000-0000-0000-abcdef012345"
    assert obs.identifiers.hardware_serial == "MB-SN-778899"  # placeholder "None" skipped
    assert obs.capabilities.gpu_description == "NVIDIA GeForce RTX 5090"
    assert obs.capabilities.vram_bytes == 32607 * 1024 * 1024
    assert obs.capabilities.os_family == "linux"


# --- null-degrade contract ----------------------------------------------

def test_unreachable_host_yields_explicit_null():
    obs = SSHProbe("dead", exec_fn=FakeSSH({"uname": None})).probe()
    assert obs.identifiers.usable == {}
    assert obs.identifiers.is_identifiable is False
    assert "firmware_uuid" in obs.identifiers.unavailable


def test_windows_family_is_null_not_attempted():
    obs = SSHProbe("winbox", exec_fn=FakeSSH({"uname": "MINGW64_NT-10.0"})).probe()
    assert obs.identifiers.is_identifiable is False


def test_probe_never_raises_even_if_executor_throws():
    def boom(target, argv):
        raise RuntimeError("ssh subprocess exploded")

    assert SSHProbe("h", exec_fn=boom).probe().identifiers.is_identifiable is False
