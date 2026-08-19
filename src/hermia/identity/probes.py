"""Cross-platform local hardware probe (hermia-cfqv).

Measures the machine hermia is running ON, returning identifiers and capabilities
as two separate things (see types.py for why that split is the whole design).

Every measurement that fails yields ``None`` and records the field name in
``unavailable``. No default, no zero, no empty string standing in for a value: a
``ram_bytes`` of 0 would read as a genuine measurement of a 0-byte machine.

Identifier ordering is strongest-first on every platform. An earlier version read
Linux ``/etc/machine-id`` first and never fell through to the firmware UUID,
silently preferring the weakest identifier available; and on Windows read only
``MachineGuid``, never touching the firmware UUID at all. Both are fixed here.
``/etc/machine-id`` and ``MachineGuid`` are OS-install ids, so they are reported
as ``persisted_token`` — the weakest tier — because a reinstall resets them and a
cloned disk image duplicates them.
"""
from __future__ import annotations

import os
import platform
import re
import shlex
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hermia.identity.types import (
    MachineCapabilities,
    MachineIdentifiers,
    MachineObservation,
    is_usable_identifier,
)

_TIMEOUT_SEC = 5
_VIRTUAL_HINTS = ("vmware", "virtualbox", "kvm", "qemu", "xen", "hyper-v", "parallels")


def _run(cmd: list[str], **kwargs: Any) -> str | None:
    """Run a read-only command; return stripped stdout, or None on any failure."""
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_TIMEOUT_SEC,
            check=False,
            **kwargs,
        )
    except Exception:  # noqa: BLE001 - probing must never raise
        return None
    if result.returncode != 0:
        return None
    out: str = result.stdout
    return out.strip()


def _read_text(path: str | Path) -> str | None:
    """Read a file; return stripped contents, or None on any failure."""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001 - probing must never raise
        return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _first_usable(*values: str | None) -> str | None:
    """First value that is present AND not a vendor placeholder.

    A plain `a or b` fallback is wrong here: DMI board_serial is frequently the
    non-empty string "None" or "Default string", which is truthy, so it masks a
    perfectly good product_serial. The placeholder is discarded later, leaving
    NO serial at all — and the machine's id silently changes depending on which
    of the two files happened to be readable on a given run.
    """
    for value in values:
        if is_usable_identifier(value):
            return _clean(value)
    return None


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except (ValueError, AttributeError):
        return None
    return parsed if parsed > 0 else None


def _ioreg_field(output: str | None, key: str) -> str | None:
    if not output:
        return None
    for line in output.splitlines():
        if f'"{key}"' in line:
            _, _, rhs = line.partition("=")
            return _clean(rhs.strip().strip('"'))
    return None


def _reg_value(output: str | None, name: str) -> str | None:
    """Last token of a `reg query` line, rejecting the type token.

    `reg query` prints ``<name> <type> <value>``; an EMPTY value leaves only two
    tokens, so a naive last-token read returns the literal ``REG_SZ`` and every
    affected box would share that as an identifier.
    """
    if not output:
        return None
    for line in output.splitlines():
        if name not in line:
            continue
        parts = line.split()
        if len(parts) < 3:
            # A path header can also contain the value name. Keep scanning
            # rather than aborting, or the real line below is never reached.
            continue
        value = _clean(parts[-1])
        if value is None or value.upper().startswith("REG_"):
            return None
        return value
    return None


_CIM_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("uuid", "Win32_ComputerSystemProduct", "UUID"),
    ("name", "Win32_ComputerSystemProduct", "Name"),
    ("serial", "Win32_BaseBoard", "SerialNumber"),
    ("ram", "Win32_ComputerSystem", "TotalPhysicalMemory"),
)
_CIM_TIMEOUT_SEC = 45


def _cim_all() -> dict[str, str | None]:
    """Read every needed CIM property in ONE PowerShell invocation.

    Preferred over `wmic`, which is removed by default from Windows 11 24H2.
    When wmic vanishes the firmware UUID and board serial vanish with it and
    identity silently drops to the cloneable MachineGuid — a downgrade with no
    outward sign.

    One invocation, not four: PowerShell cold-starts in seconds, so four
    sequential calls against the default 5s timeout would intermittently drop
    whichever property happened to be slow. Losing just the UUID silently
    demotes the machine to a weaker identifier and makes its id flap between
    runs, which looks exactly like hardware being swapped.
    """
    script = "; ".join(
        f'"{key}=" + [string](Get-CimInstance -ClassName {cls}).{prop}'
        for key, cls, prop in _CIM_FIELDS
    )
    out = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=_CIM_TIMEOUT_SEC,
    )
    parsed: dict[str, str | None] = {key: None for key, _, _ in _CIM_FIELDS}
    for line in (out or "").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in parsed:
            parsed[key.strip()] = _clean(value)
    return parsed


def _wmic_value(output: str | None) -> str | None:
    """First non-header, non-blank line of `wmic ... get X` output."""
    if not output:
        return None
    for line in output.splitlines()[1:]:
        value = _clean(line)
        if value:
            return value
    return None


def _proc_field(text: str | None, prefix: str) -> str | None:
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith(prefix) and ":" in line:
            return _clean(line.split(":", 1)[1])
    return None


def _meminfo_bytes(meminfo: str | None) -> int | None:
    """MemTotal in bytes.

    NOTE: MemTotal is kernel-visible memory, not installed DIMM capacity — it
    drifts with kernel updates, crashkernel reservations and driver allocations.
    That is tolerable ONLY because this is a capability. It must never feed an
    identity, or a routine kernel update would look like a hardware swap.
    """
    if not meminfo:
        return None
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            kb = _to_int(parts[1]) if len(parts) > 1 else None
            return kb * 1024 if kb is not None else None
    return None


def _primary_mac() -> str | None:
    """A MAC address, recorded as a CAPABILITY only.

    Never an identifier: reservations here are bound to detachable adapters and a
    dock, so this value follows the accessory. Recording it lets an operator see
    that a dock moved; it must never decide which machine answered.
    """
    node = uuid.getnode()
    # Bit 41 set means the value was randomly generated, not read from hardware.
    if (node >> 40) & 0x1:
        return None
    return ":".join(f"{(node >> shift) & 0xFF:02x}" for shift in range(40, -8, -8))


def _looks_virtual(*values: str | None) -> bool | None:
    joined = " ".join(v.lower() for v in values if v)
    if not joined:
        return None
    return any(hint in joined for hint in _VIRTUAL_HINTS)


class LocalProbe:
    """Measures the machine this process is running on."""

    def __init__(self, os_family: str | None = None) -> None:
        # platform.system().lower() -> "darwin" | "linux" | "windows".
        # NOT os.name, which returns "posix" on macOS AND Linux and would match
        # no branch at all, silently probing nothing on every platform.
        self.os_family = os_family or platform.system().lower()

    def probe(self) -> MachineObservation:
        if self.os_family == "darwin":
            ident, caps = self._darwin()
        elif self.os_family == "linux":
            ident, caps = self._linux()
        elif self.os_family == "windows":
            ident, caps = self._windows()
        else:
            ident, caps = MachineIdentifiers(), MachineCapabilities(
                os_family=self.os_family
            )
        return MachineObservation(
            identifiers=_mark_identifiers(ident), capabilities=_mark_caps(caps)
        )

    def _darwin(self) -> tuple[MachineIdentifiers, MachineCapabilities]:
        ioreg = _run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        model = _clean(_run(["sysctl", "-n", "hw.model"]))
        return (
            MachineIdentifiers(
                firmware_uuid=_ioreg_field(ioreg, "IOPlatformUUID"),
                hardware_serial=_ioreg_field(ioreg, "IOPlatformSerialNumber"),
            ),
            MachineCapabilities(
                cpu_brand=_clean(_run(["sysctl", "-n", "machdep.cpu.brand_string"])),
                logical_cores=_to_int(_run(["sysctl", "-n", "hw.logicalcpu"])),
                ram_bytes=_to_int(_run(["sysctl", "-n", "hw.memsize"])),
                model_identifier=model,
                os_family="darwin",
                os_version=_clean(_run(["sw_vers", "-productVersion"])),
                nic_mac=_primary_mac(),
                is_virtual=_looks_virtual(model),
            ),
        )

    def _linux(self) -> tuple[MachineIdentifiers, MachineCapabilities]:
        # Firmware root FIRST. These are often mode 0400 (root only); when they
        # are unreadable the result is None and we fall through to the weak
        # persisted token, which is recorded AS such rather than promoted.
        product_name = _clean(_read_text("/sys/class/dmi/id/product_name"))
        cpuinfo = _read_text("/proc/cpuinfo")
        cores = len(re.findall(r"^processor\s*:", cpuinfo, re.M)) if cpuinfo else 0
        return (
            MachineIdentifiers(
                firmware_uuid=_clean(_read_text("/sys/class/dmi/id/product_uuid")),
                hardware_serial=_first_usable(
                    _read_text("/sys/class/dmi/id/board_serial"),
                    _read_text("/sys/class/dmi/id/product_serial"),
                ),
                persisted_token=_clean(_read_text("/etc/machine-id")),
            ),
            MachineCapabilities(
                cpu_brand=_proc_field(cpuinfo, "model name"),
                logical_cores=cores or None,
                ram_bytes=_meminfo_bytes(_read_text("/proc/meminfo")),
                model_identifier=product_name,
                os_family="linux",
                os_version=_clean(_run(["uname", "-r"])),
                nic_mac=_primary_mac(),
                is_virtual=_looks_virtual(
                    product_name, _clean(_read_text("/sys/class/dmi/id/sys_vendor"))
                ),
            ),
        )

    def _windows(self) -> tuple[MachineIdentifiers, MachineCapabilities]:
        cim = _cim_all()
        model = cim["name"] or _wmic_value(_run(["wmic", "csproduct", "get", "Name"]))
        return (
            MachineIdentifiers(
                firmware_uuid=_first_usable(
                    cim["uuid"],
                    _wmic_value(_run(["wmic", "csproduct", "get", "UUID"])),
                ),
                hardware_serial=_first_usable(
                    cim["serial"],
                    _wmic_value(_run(["wmic", "baseboard", "get", "SerialNumber"])),
                ),
                persisted_token=_reg_value(
                    _run(
                        [
                            "reg",
                            "query",
                            r"HKLM\SOFTWARE\Microsoft\Cryptography",  # pragma: allowlist secret
                            "/v",
                            "MachineGuid",
                        ]
                    ),
                    "MachineGuid",
                ),
            ),
            MachineCapabilities(
                cpu_brand=_clean(os.environ.get("PROCESSOR_IDENTIFIER")),
                logical_cores=_to_int(os.environ.get("NUMBER_OF_PROCESSORS")),
                ram_bytes=_to_int(
                    cim["ram"]
                    or _wmic_value(
                        _run(["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"])
                    )
                ),
                model_identifier=model,
                os_family="windows",
                os_version=_clean(platform.version()),
                nic_mac=_primary_mac(),
                is_virtual=_looks_virtual(model),
            ),
        )


def _mark_identifiers(ident: MachineIdentifiers) -> MachineIdentifiers:
    missing = tuple(
        name
        for name, value in (
            ("firmware_uuid", ident.firmware_uuid),
            ("hardware_serial", ident.hardware_serial),
            ("persisted_token", ident.persisted_token),
        )
        if value is None
    )
    return MachineIdentifiers(
        firmware_uuid=ident.firmware_uuid,
        hardware_serial=ident.hardware_serial,
        persisted_token=ident.persisted_token,
        unavailable=missing,
    )


def _mark_caps(caps: MachineCapabilities) -> MachineCapabilities:
    missing = tuple(
        name
        for name, value in (
            ("cpu_brand", caps.cpu_brand),
            ("logical_cores", caps.logical_cores),
            ("ram_bytes", caps.ram_bytes),
            ("model_identifier", caps.model_identifier),
            ("nic_mac", caps.nic_mac),
            ("gpu_description", caps.gpu_description),
            ("vram_bytes", caps.vram_bytes),
        )
        if value is None
    )
    return MachineCapabilities(
        cpu_brand=caps.cpu_brand,
        logical_cores=caps.logical_cores,
        ram_bytes=caps.ram_bytes,
        model_identifier=caps.model_identifier,
        os_family=caps.os_family,
        os_version=caps.os_version,
        nic_mac=caps.nic_mac,
        gpu_description=caps.gpu_description,
        vram_bytes=caps.vram_bytes,
        is_virtual=caps.is_virtual,
        unavailable=missing,
    )


SSHExec = Callable[[str, list[str]], str | None]


def _ssh_exec(target: str, argv: list[str]) -> str | None:
    """Execute a command over ssh; return stripped stdout or None on any failure."""
    try:
        remote_cmd = shlex.join(argv)
        result = subprocess.run(  # noqa: S603
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                f"ConnectTimeout={_TIMEOUT_SEC}",
                target,
                remote_cmd,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_TIMEOUT_SEC * 2,
            check=False,
        )
    except Exception:  # noqa: BLE001 - probing must never raise
        return None
    if result.returncode != 0:
        return None
    out: str = result.stdout
    return out.strip()


def _spdisplays_chipset(output: str | None) -> str | None:
    """Extract GPU chipset model from system_profiler output."""
    if not output:
        return None
    for line in output.splitlines():
        if "Chipset Model:" in line:
            _, _, value = line.partition("Chipset Model:")
            return _clean(value.strip())
    return None


def _spdisplays_vram_bytes(output: str | None) -> int | None:
    """Extract VRAM in bytes from system_profiler output (Apple M-series)."""
    if not output:
        return None
    for line in output.splitlines():
        if "Total Number of Cores" in line or "Memory" in line:
            # Apple Silicon reports unified memory, not discrete VRAM
            # For now, return None as we cannot reliably extract GPU-specific VRAM
            pass
    return None


def _nvidia_gpu(output: str | None) -> tuple[str | None, int | None]:
    """(name, total VRAM bytes) from ``nvidia-smi --query-gpu=name,memory.total``.

    Invoked with ``--format=csv,noheader,nounits``, so a line is ``NAME, MIB``.
    Only the first GPU is used. ``(None, None)`` when nvidia-smi is absent
    (AMD/CPU host) — the VRAM sanity-bound cross-check then reads 'unchecked'.
    """
    if not output:
        return None, None
    first = output.splitlines()[0]
    if "," not in first:
        return None, None
    name, _, mib = first.partition(",")
    total_mib = _to_int(mib)
    vram = total_mib * 1024 * 1024 if total_mib is not None else None
    return _clean(name), vram


class SSHProbe:
    """Measures a remote machine over ssh."""

    def __init__(
        self,
        target: str,
        os_family: str | None = None,
        exec_fn: SSHExec | None = None,
    ) -> None:
        self.target = target
        self.os_family = os_family
        self._exec_fn = exec_fn or _ssh_exec

    def _ssh(self, argv: list[str]) -> str | None:
        """Execute a command over ssh."""
        return self._exec_fn(self.target, argv)

    def _detect_os(self) -> str | None:
        """Detect OS family via uname -s."""
        if self.os_family:
            return self.os_family
        output = self._ssh(["uname", "-s"])
        if not output:
            return None
        uname = output.strip().lower()
        if "linux" in uname:
            return "linux"
        if "darwin" in uname:
            return "darwin"
        # Windows and others are not supported for remote probing yet
        return None

    def _darwin(self) -> tuple[MachineIdentifiers, MachineCapabilities]:
        ioreg = self._ssh(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        model = _clean(self._ssh(["sysctl", "-n", "hw.model"]))
        sys_profiler = self._ssh(
            ["system_profiler", "SPDisplaysDataType"]
        )

        return (
            MachineIdentifiers(
                firmware_uuid=_ioreg_field(ioreg, "IOPlatformUUID"),
                hardware_serial=_ioreg_field(ioreg, "IOPlatformSerialNumber"),
            ),
            MachineCapabilities(
                cpu_brand=_clean(self._ssh(["sysctl", "-n", "machdep.cpu.brand_string"])),
                logical_cores=_to_int(self._ssh(["sysctl", "-n", "hw.logicalcpu"])),
                ram_bytes=_to_int(self._ssh(["sysctl", "-n", "hw.memsize"])),
                model_identifier=model,
                os_family="darwin",
                os_version=_clean(self._ssh(["sw_vers", "-productVersion"])),
                gpu_description=_spdisplays_chipset(sys_profiler),
                vram_bytes=_spdisplays_vram_bytes(sys_profiler),
            ),
        )

    def _linux(self) -> tuple[MachineIdentifiers, MachineCapabilities]:
        product_name = _clean(
            self._ssh(["cat", "/sys/class/dmi/id/product_name"])
        )
        cpuinfo = self._ssh(["cat", "/proc/cpuinfo"])
        cores = len(re.findall(r"^processor\s*:", cpuinfo or "", re.M)) if cpuinfo else 0

        gpu_desc, vram_bytes = _nvidia_gpu(
            self._ssh(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ]
            )
        )

        return (
            MachineIdentifiers(
                firmware_uuid=_clean(self._ssh(["cat", "/sys/class/dmi/id/product_uuid"])),
                hardware_serial=_first_usable(
                    self._ssh(["cat", "/sys/class/dmi/id/board_serial"]),
                    self._ssh(["cat", "/sys/class/dmi/id/product_serial"]),
                ),
                persisted_token=_clean(self._ssh(["cat", "/etc/machine-id"])),
            ),
            MachineCapabilities(
                cpu_brand=_proc_field(cpuinfo, "model name"),
                logical_cores=cores or None,
                ram_bytes=_meminfo_bytes(self._ssh(["cat", "/proc/meminfo"])),
                model_identifier=product_name,
                os_family="linux",
                os_version=_clean(self._ssh(["uname", "-r"])),
                gpu_description=gpu_desc,
                vram_bytes=vram_bytes,
            ),
        )

    def probe(self) -> MachineObservation:
        try:
            detected_os = self._detect_os()
            if detected_os == "darwin":
                ident, caps = self._darwin()
            elif detected_os == "linux":
                ident, caps = self._linux()
            else:
                # Unknown or unsupported OS (including Windows) -> null identity
                ident, caps = MachineIdentifiers(), MachineCapabilities(
                    os_family=detected_os
                )
        except Exception:  # noqa: BLE001 - probing must never raise
            ident, caps = MachineIdentifiers(), MachineCapabilities()

        return MachineObservation(
            identifiers=_mark_identifiers(ident), capabilities=_mark_caps(caps)
        )
