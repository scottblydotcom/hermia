from __future__ import annotations

_VRAM_SLACK_GB = 1.0
_VRAM_SLACK_BYTES = _VRAM_SLACK_GB * 1024**3


def vram_sanity_check(
    total_vram_bytes: int | None, endpoint_size_vram_gb: float | None
) -> str:
    """Check if model VRAM requirement fits in box VRAM.

    Returns 'ok' if model fits (with slack), 'mismatch' if it exceeds capacity,
    or 'unchecked' if either value is missing.
    """
    if total_vram_bytes is None or endpoint_size_vram_gb is None:
        return "unchecked"

    required_bytes = int(endpoint_size_vram_gb * 1024**3)
    available_bytes = total_vram_bytes + _VRAM_SLACK_BYTES

    if required_bytes <= available_bytes:
        return "ok"
    return "mismatch"
