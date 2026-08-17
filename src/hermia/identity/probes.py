"""Cross-platform local hardware probe (hermia-cfqv).

Measures the machine hermia is running ON. Remote probes (SSH, agent) implement
the same ``HardwareProbe`` Protocol later and are deliberately absent here.

Every measurement that fails yields ``None`` and records the field name in
``unavailable``. There is no default, no zero, no empty string standing in for a
real value: a ``ram_bytes`` of 0 would read as a genuine measurement of a
0-byte machine, and a guessed identity is worse than an admitted gap.

No MAC address or other network identifier is collected anywhere in this module.
DHCP reservations are commonly bound to detachable USB/Thunderbolt adapters
or a dock, so a MAC-derived identity follows the accessory rather
than the computer — the exact defect this package exists to end.
"""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from hermia.identity.types import HardwareFacts

_TIMEOUT_SEC = 5


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
    """Normalise a measured string: blank or missing means NOT MEASURED."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _to_int(value: str | None) -> int | None:
    """Parse a positive integer; anything else means NOT MEASURED."""
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except (ValueError, AttributeError):
        return None
    return parsed if parsed > 0 else None


def _macos_uuid(ioreg_output: str | None) -> str | None:
    if not ioreg_output:
        return None
    for line in ioreg_output.splitlines():
        if '"IOPlatformUUID"' not in line:
            continue
        _, _, rhs = line.partition("=")
        return _clean(rhs.strip().strip('"'))
    return None


def _linux_cpu_brand(cpuinfo: str | None) -> str | None:
    if not cpuinfo:
        return None
    for line in cpuinfo.splitlines():
        if line.startswith("model name"):
            return _clean(line.split(":", 1)[1] if ":" in line else None)
    return None


def _linux_ram_bytes(meminfo: str | None) -> int | None:
    if not meminfo:
        return None
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            kb = _to_int(parts[1]) if len(parts) > 1 else None
            return kb * 1024 if kb is not None else None
    return None


def _windows_uuid(reg_output: str | None) -> str | None:
    """Extract MachineGuid from `reg query` output.

    The value token must be the FOURTH-onward field: `reg query` prints
    ``<name> <type> <value>``, so an EMPTY value leaves only two tokens and a
    naive ``parts[-1]`` returns the literal type name ``REG_SZ``. That would be
    accepted downstream as a measured hardware id, giving every affected
    Windows box the same uuid component — a fabricated identity, which is far
    worse than admitting the value is missing.
    """
    if not reg_output:
        return None
    for line in reg_output.splitlines():
        if "MachineGuid" not in line:
            continue
        parts = line.split()
        if len(parts) < 3:
            return None
        value = _clean(parts[-1])
        if value is None or value.upper().startswith("REG_"):
            return None
        return value
    return None


def _windows_ram_bytes(wmic_output: str | None) -> int | None:
    if not wmic_output:
        return None
    for line in wmic_output.splitlines():
        candidate = line.strip()
        if candidate.isdigit():
            return _to_int(candidate)
    return None


class LocalProbe:
    """Measures the machine this process is running on."""

    def __init__(self, os_family: str | None = None) -> None:
        # platform.system().lower() -> "darwin" | "linux" | "windows".
        # NOT os.name, which returns "posix" on both macOS and Linux and would
        # therefore match no branch at all, silently probing nothing everywhere.
        self.os_family = os_family or platform.system().lower()

    def probe(self) -> HardwareFacts:
        platform_uuid: str | None = None
        cpu_brand: str | None = None
        ram_bytes: int | None = None

        if self.os_family == "darwin":
            platform_uuid = _macos_uuid(
                _run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
            )
            cpu_brand = _clean(_run(["sysctl", "-n", "machdep.cpu.brand_string"]))
            ram_bytes = _to_int(_run(["sysctl", "-n", "hw.memsize"]))

        elif self.os_family == "linux":
            platform_uuid = _clean(_read_text("/etc/machine-id")) or _clean(
                _read_text("/sys/class/dmi/id/product_uuid")
            )
            cpu_brand = _linux_cpu_brand(_read_text("/proc/cpuinfo"))
            ram_bytes = _linux_ram_bytes(_read_text("/proc/meminfo"))

        elif self.os_family == "windows":
            platform_uuid = _windows_uuid(
                _run(
                    [
                        "reg",
                        "query",
                        r"HKLM\SOFTWARE\Microsoft\Cryptography",  # pragma: allowlist secret
                        "/v",
                        "MachineGuid",
                    ]
                )
            )
            cpu_brand = _clean(os.environ.get("PROCESSOR_IDENTIFIER"))
            ram_bytes = _windows_ram_bytes(
                _run(["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"])
            )

        # Any other os_family: everything stays None. Not an error, just unknown.

        unavailable = tuple(
            name
            for name, value in (
                ("platform_uuid", platform_uuid),
                ("cpu_brand", cpu_brand),
                ("ram_bytes", ram_bytes),
            )
            if value is None
        )
        return HardwareFacts(
            platform_uuid=platform_uuid,
            cpu_brand=cpu_brand,
            ram_bytes=ram_bytes,
            os_family=self.os_family,
            unavailable=unavailable,
        )
