from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IdentityTransport:
    """Identity transport configuration for a remote host."""

    kind: str  # 'api' | 'ssh' | 'wmi' | 'agent'
    ssh_target: str | None = None


def parse_identity_transport(entry: dict[str, object]) -> IdentityTransport:
    """Parse identity transport config from a dict.

    Returns IdentityTransport with kind and optional ssh_target.
    Raises ValueError for invalid configs, NotImplementedError for unimplemented kinds.
    """
    raw_cfg = entry.get("identity")
    if raw_cfg is None:
        return IdentityTransport("api", None)
    if not isinstance(raw_cfg, dict):
        raise ValueError("fleet entry 'identity' must be a mapping")
    identity_cfg: dict[str, object] = raw_cfg
    transport_kind = identity_cfg.get("transport")

    if transport_kind is None:
        # Absent block defaults to api null
        return IdentityTransport("api", None)

    if transport_kind == "api":
        return IdentityTransport("api", None)

    if transport_kind == "ssh":
        ssh_target = entry.get("ssh") or identity_cfg.get("ssh")
        if not ssh_target:
            raise ValueError(
                f"ssh transport requires a 'ssh' target string; got {entry!r}"
            )
        return IdentityTransport("ssh", str(ssh_target))

    if transport_kind in ("wmi", "agent"):
        raise NotImplementedError(f"{transport_kind} identity transport not implemented")

    raise ValueError(f"unknown identity transport: {transport_kind}")
