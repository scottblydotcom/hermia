"""Hosts drill — list, add, remove, probe state.

Lists existing hosts in app.config. `+` opens AddHostModal; enter drills
into the host's models (Task 12); escape pops back. Background probes via
SessionBus update probe_state per host (`probing` / `ok` / `failed`) which
renders as inline `[state]` tags on each row.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from hermia.tui.bus import SessionBus
from hermia.tui.probe import DEFAULT_PROBE_TIMEOUT_SECONDS, probe_host
from hermia.tui.state import Host
from hermia.tui.widgets.breadcrumb import Breadcrumb


class HostsScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("plus", "add_host", "Add host", show=True),
        Binding("enter", "drill", "Models", show=True),
    ]

    def __init__(
        self,
        *,
        transport_factory: Callable[[Host], Any] | None = None,
        probe_timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__()
        self.cursor_idx: int = 0
        # probe_state[host.name] = "probing" | "ok" | "failed".
        self.probe_state: dict[str, str] = {}
        # Injected for tests; production uses transport_adapter.transport_for
        # (resolved at probe time so the import stays lazy).
        self._make_transport = transport_factory
        self._probe_timeout = probe_timeout
        self._render_seq: int = 0
        # Per-screen bus so probe events don't bleed into Plan 3's app.bus
        # when the runner lands.
        self._bus: SessionBus = SessionBus()

    @property
    def app_config(self):
        return self.app.config  # type: ignore[attr-defined]

    @property
    def host_names(self) -> list[str]:
        return [h.name for h in self.app_config.hosts]

    def compose(self) -> ComposeResult:
        name = self.app_config.name or "(unnamed)"
        with Vertical(id="hosts-root"):
            yield Breadcrumb(["hermia", "fleet", name, "hosts"])

    def on_mount(self) -> None:
        self._rerender()
        self._start_probes()

    def _row_text(self, host: Host, idx: int) -> str:
        cursor = "▸" if idx == self.cursor_idx else " "
        state = self.probe_state.get(host.name, "")
        state_str = f" [{state}]" if state else ""
        return f"{cursor} {host.name}    {host.url}    [{host.engine}]{state_str}"

    def _rerender(self) -> None:
        root = self.query_one("#hosts-root", Vertical)
        for child in list(root.children):
            if isinstance(child, Breadcrumb):
                continue
            child.remove()
        self._render_seq += 1
        seq = self._render_seq
        if not self.app_config.hosts:
            root.mount(Static("No hosts yet — press '+' to add one.", id="hosts-empty-notice"))
            return
        for i, host in enumerate(self.app_config.hosts):
            root.mount(Static(self._row_text(host, i), id=f"host-row-{seq}-{i}"))

    # ── Navigation ────────────────────────────────────────────────────────

    def action_cursor_prev(self) -> None:
        if self.cursor_idx > 0:
            self.cursor_idx -= 1
            self._rerender()

    def action_cursor_next(self) -> None:
        if self.cursor_idx < len(self.app_config.hosts) - 1:
            self.cursor_idx += 1
            self._rerender()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_add_host(self) -> None:
        from hermia.tui.screens.modals import AddHostModal
        self.app.push_screen(AddHostModal(), self._on_host_added)

    def action_drill(self) -> None:
        from hermia.tui.screens.host_models import HostModelsScreen
        hosts = self.app_config.hosts
        if 0 <= self.cursor_idx < len(hosts):
            self.app.push_screen(HostModelsScreen(host=hosts[self.cursor_idx]))

    def _on_host_added(self, host: Host | None) -> None:
        if host is None:
            return
        self.app_config.hosts.append(host)
        self._rerender()
        # Kick a probe for the new host.
        self._start_probes()

    # ── Probe wiring ──────────────────────────────────────────────────────

    @work
    async def _start_probes(self) -> None:
        """Background worker: subscribe to probe events, then fire probes.

        Started in on_mount and after any host is added. Idempotent — probes
        are skipped for hosts that already have a recorded probe_state.
        """
        # Subscribe first so events fired during probe_host land in our queues.
        asyncio.create_task(self._listen("probe.started", "probing"))
        asyncio.create_task(self._listen("probe.completed", "ok"))
        asyncio.create_task(self._listen("probe.failed", "failed"))
        await asyncio.sleep(0)

        # Resolve transport factory lazily so unit tests don't import urllib
        # paths unless a real probe runs.
        factory = self._make_transport
        if factory is None:
            from hermia.tui.transport_adapter import transport_for
            factory = transport_for

        for host in list(self.app_config.hosts):
            if host.name in self.probe_state:
                continue
            transport = factory(host)
            await probe_host(
                host,
                transport=transport,
                bus=self._bus,
                timeout=self._probe_timeout,
            )

    async def _listen(self, topic: str, final_state: str) -> None:
        async for ev in self._bus.subscribe(topic):
            self.probe_state[ev["host_name"]] = final_state
            # Re-render so the row's [state] tag updates.
            try:
                self._rerender()
            except Exception:
                # Screen may be unmounting — swallow late events.
                return
