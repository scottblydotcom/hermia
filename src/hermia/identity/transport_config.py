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

    # A ssh target set without transport: ssh is almost always a forgotten
    # "transport: ssh" line, not an intent to run api. Fail loudly instead of
    # silently nulling the whole run (ultra/Fable review M1).
    _has_ssh = identity_cfg.get("ssh") is not None or entry.get("ssh") is not None
    if transport_kind in (None, "api"):
        if _has_ssh:
            raise ValueError(
                "identity block sets 'ssh' but transport is not 'ssh' "
                f"(add 'transport: ssh'); got transport={transport_kind!r}"
            )
        return IdentityTransport("api", None)

    if transport_kind == "ssh":
        ssh_target = entry.get("ssh") or identity_cfg.get("ssh")
        if not ssh_target:
            raise ValueError(
                f"ssh transport requires a 'ssh' target string; got {entry!r}"
            )
        if not isinstance(ssh_target, str):
            raise ValueError(
                f"ssh target must be a string, got {type(ssh_target).__name__}"
            )
        target = ssh_target
        # A target beginning with "-" is read by the ssh CLI as an option, not a
        # host — the local option/command-injection vector. Reject at config time
        # with a clear error (the probe also passes "--").
        if target.startswith("-"):
            raise ValueError(
                f"ssh target must not start with '-' (arg-injection risk): {target!r}"
            )
        return IdentityTransport("ssh", target)

    if transport_kind in ("wmi", "agent"):
        raise NotImplementedError(f"{transport_kind} identity transport not implemented")

    raise ValueError(f"unknown identity transport: {transport_kind}")
