"""Pre-run sanity checks: VRAM, system RAM, disk space, and Ollama security posture."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

from hermia.metrics import get_gpu_stats

VRAM_OVERHEAD_GB = 0.75  # headroom reserved for Ollama runtime
RAM_LOAD_MULTIPLIER = 1.5  # approximate RAM needed for CPU-only inference
MIN_DISK_FREE_GB = 0.5
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MIN_SECURE_VERSION = "0.17.1"  # fixes CVE-2026-7482 (CVSS 9.1, "Bleeding Llama")

# Models confirmed incompatible with Ollama's Vulkan backend on gfx900 (Vega 64).
# gemma2:9b falls back to CPU silently, produces garbled output, and fails all tests.
VULKAN_GFX900_BLOCKLIST: dict[str, str] = {
    "gemma2:9b": "Vulkan/gfx900 incompatible — CPU fallback produces garbled output",
}


@dataclass
class ModelCheck:
    name: str
    size_gb: float
    fits_total_vram: bool   # model <= GPU's total VRAM capacity
    fits_current_vram: bool  # model <= VRAM available right now (after overhead)
    fits_ram: bool           # can fall back to CPU inference
    skip: bool               # definitively cannot run — skip entirely
    reason: str = ""


def _normalize_host(host: str) -> str:
    host = host.rstrip("/")
    return host if "://" in host else f"http://{host}"


def _parse_version(v: str) -> tuple[int, ...] | None:
    """Parse 'vX.Y.Z[-pre][+build]' → (X, Y, Z, release_flag). Returns None on failure.

    release_flag is 1 for release versions and 0 for pre-releases, so that
    0.17.1-rc1 < 0.17.1 in tuple comparison (pre-release of the fix is still vulnerable).
    Handles leading 'v' prefix and SemVer build metadata (+build.123).
    """
    try:
        v = v.lstrip("v") if v else ""
        has_prerelease = "-" in v.split("+")[0]
        base = v.split("-")[0].split("+")[0]
        parts = [int(x) for x in base.split(".")[:3]]
        while len(parts) < 3:
            parts.append(0)
        parts.append(0 if has_prerelease else 1)
        return tuple(parts)
    except (ValueError, AttributeError):
        return None


_parsed_min = _parse_version(OLLAMA_MIN_SECURE_VERSION)
_MIN_SECURE_VERSION_TUPLE: tuple[int, ...] = (
    _parsed_min if _parsed_min is not None else (0, 17, 1, 1)
)


def check_ollama_security(
    host: str,
    fleet_mode: bool = False,
    headers: dict[str, str] | None = None,
) -> list[str]:
    """Query /api/version and return SEC warning strings. Never raises.

    ``headers`` forwards the fleet entry's auth (e.g. bearer token) so
    ``/api/version`` reaches auth-gated hosts (LiteLLM proxies, etc)
    instead of getting a silent 401/403 and skipping the CVE probe.
    """
    import requests  # local import — optional network check, avoid startup overhead
    warnings: list[str] = []
    # Normalize even though every current caller already does — defense
    # in depth against a future caller passing a raw `localhost:11434`
    # (requests raises MissingSchema) or a trailing slash (double-slash URL).
    host = _normalize_host(host)
    try:
        resp = requests.get(
            f"{host}/api/version", timeout=3, headers=headers or {}
        )
        if resp.ok:
            payload = resp.json()
            # Defensive: /api/version could return a list, a bare string,
            # or null on an unexpected server. Only a dict has .get.
            ver = payload.get("version", "") if isinstance(payload, dict) else ""
            v_tuple = _parse_version(ver)
            if v_tuple is not None and v_tuple < _MIN_SECURE_VERSION_TUPLE:
                warnings.append(
                    f"SEC ⚠ CVE-2026-7482 (CVSS 9.1): Ollama {ver} is vulnerable "
                    f"to heap memory disclosure — upgrade to {OLLAMA_MIN_SECURE_VERSION}+"
                )
    except (requests.exceptions.RequestException, ValueError):
        # ValueError catches JSONDecodeError on non-JSON bodies.
        pass

    if not fleet_mode:
        warnings.append(
            "SEC ⚠ CVE-2026-5757 (no patch): Ollama model upload endpoint is "
            "unpatched — restrict /api/create to localhost or trusted networks"
        )
    return warnings


def check_engine_security(
    host: str,
    engine: str,
    fleet_mode: bool = False,
    headers: dict[str, str] | None = None,
) -> list[str]:
    """Engine-aware security posture check. Dispatch on transport type.

    Extension point for the pluggable transport layer: each engine's
    check emits SEC ⚠ warning strings for issues that are *engine*-specific
    (a CVE against the inference server itself, an unauthenticated admin
    endpoint, a stale version). Engines with no known open advisories
    return the empty list; adding a new advisory means editing exactly
    one function, no call-site changes.

    ``headers`` are forwarded to the underlying probe so auth-gated fleet
    hosts (bearer tokens etc) don't get 401 and silently skip the check.

    Currently populated:
    * ``ollama`` → :func:`check_ollama_security` (CVE-2026-7482 heap
      disclosure, CVE-2026-5757 unauthenticated /api/create)
    * ``openai-compat`` / ``vllm`` → ``[]`` today; wire an advisory
      here when one lands.
    """
    if engine == "ollama":
        return check_ollama_security(host, fleet_mode=fleet_mode, headers=headers)
    return []


@dataclass
class PreflightReport:
    vram_total_gb: float
    vram_used_gb: float
    vram_available_gb: float
    ram_total_gb: float
    ram_available_gb: float
    disk_free_gb: float
    disk_ok: bool
    models: list[ModelCheck] = field(default_factory=list)
    security_warnings: list[str] = field(default_factory=list)

    @property
    def runnable_models(self) -> list[str]:
        return [m.name for m in self.models if not m.skip]

    @property
    def skipped_models(self) -> list[str]:
        return [m.name for m in self.models if m.skip]

    @property
    def warnings(self) -> list[str]:
        out: list[str] = []
        if not self.disk_ok:
            out.append(
                f"Low disk space: {self.disk_free_gb:.1f} GB free (need {MIN_DISK_FREE_GB} GB)"
            )
        for m in self.models:
            if m.skip:
                out.append(f"SKIP {m.name}: {m.reason}")
            elif not m.fits_current_vram:
                out.append(
                    f"WARN {m.name} ({m.size_gb:.1f} GB): tight fit — "
                    f"{self.vram_available_gb:.1f} GB VRAM free, may stall"
                )
        return out


def run_preflight(
    selected_models: list[str],
    model_list: list[dict[str, Any]],
    results_dir: Path,
    fleet_mode: bool = False,
) -> PreflightReport:
    _, vram_used, vram_total = get_gpu_stats()
    vram_available = max(0.0, vram_total - vram_used - VRAM_OVERHEAD_GB)

    vm = psutil.virtual_memory()
    ram_total_gb = vm.total / (1024**3)
    ram_available_gb = vm.available / (1024**3)

    check_path = results_dir if results_dir.exists() else results_dir.parent
    disk = psutil.disk_usage(str(check_path))
    disk_free_gb = disk.free / (1024**3)

    size_map = {m["name"]: m.get("size", 0) / (1024**3) for m in model_list}

    checks: list[ModelCheck] = []
    for name in selected_models:
        size_gb = size_map.get(name, 0.0)
        fits_total_vram = size_gb <= vram_total
        fits_current_vram = size_gb <= vram_available
        fits_ram = (size_gb * RAM_LOAD_MULTIPLIER) <= ram_available_gb

        if name in VULKAN_GFX900_BLOCKLIST and not fleet_mode:
            checks.append(ModelCheck(
                name=name,
                size_gb=size_gb,
                fits_total_vram=fits_total_vram,
                fits_current_vram=fits_current_vram,
                fits_ram=fits_ram,
                skip=True,
                reason=VULKAN_GFX900_BLOCKLIST[name],
            ))
            continue

        # In fleet mode the remote server already has these models — trust it
        if fleet_mode:
            skip = False
            reason = ""
        else:
            skip = not fits_total_vram and not fits_ram
            reason = ""
            if not fits_total_vram and not fits_ram:
                reason = (
                    f"{size_gb:.1f} GB exceeds total VRAM ({vram_total:.1f} GB) "
                    f"and available RAM ({ram_available_gb:.1f} GB)"
                )
            elif not fits_total_vram:
                reason = (
                    f"{size_gb:.1f} GB exceeds total VRAM ({vram_total:.1f} GB) — "
                    f"CPU fallback possible but will be very slow"
                )

        checks.append(ModelCheck(
            name=name,
            size_gb=size_gb,
            fits_total_vram=fits_total_vram,
            fits_current_vram=fits_current_vram,
            fits_ram=fits_ram,
            skip=skip,
            reason=reason,
        ))

    host = _normalize_host(os.environ.get("HERMIA_HOST", DEFAULT_OLLAMA_HOST))
    sec = check_ollama_security(host, fleet_mode=fleet_mode)

    return PreflightReport(
        vram_total_gb=vram_total,
        vram_used_gb=vram_used,
        vram_available_gb=vram_available,
        ram_total_gb=ram_total_gb,
        ram_available_gb=ram_available_gb,
        disk_free_gb=disk_free_gb,
        disk_ok=disk_free_gb >= MIN_DISK_FREE_GB,
        models=checks,
        security_warnings=sec,
    )
