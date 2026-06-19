"""Async host probe — wraps transport/, publishes probe.* events on the bus.

probe_host():
    - publishes probe.started immediately
    - calls transport.list_models()
    - on success: populates host.models (unselected by default),
      publishes probe.completed (with warning='no_models' when empty)
    - on timeout (8s default): publishes probe.failed with reason='timeout'
    - on auth error (PermissionError): publishes probe.failed with reason='auth'
    - on transport error (any other Exception): publishes probe.failed with reason='offline'

The Hosts drill screen subscribes to all three topics and updates row badges.
"""
from __future__ import annotations

import asyncio
from typing import Protocol

from hermia.tui.bus import SessionBus
from hermia.tui.state import Host, ModelChoice

DEFAULT_PROBE_TIMEOUT_SECONDS = 8.0


class _ListModelsTransport(Protocol):
    async def list_models(self) -> list[str]: ...


async def probe_host(
    host: Host,
    *,
    transport: _ListModelsTransport,
    bus: SessionBus,
    timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> None:
    """Probe a host's available models. Updates host.models and publishes events."""
    await bus.publish("probe.started", {"host_name": host.name, "url": host.url})
    try:
        model_names = await asyncio.wait_for(transport.list_models(), timeout=timeout)
    except TimeoutError:
        await bus.publish(
            "probe.failed",
            {"host_name": host.name, "reason": "timeout", "retryable": True},
        )
        return
    except PermissionError as exc:
        await bus.publish(
            "probe.failed",
            {"host_name": host.name, "reason": "auth", "error": str(exc), "retryable": True},
        )
        return
    except Exception as exc:
        await bus.publish(
            "probe.failed",
            {"host_name": host.name, "reason": "offline", "error": str(exc), "retryable": True},
        )
        return

    host.models = [ModelChoice(name=n, selected=False) for n in model_names]
    await bus.publish(
        "probe.completed",
        {
            "host_name": host.name,
            "models": list(model_names),
            "warning": "no_models" if not model_names else None,
        },
    )
