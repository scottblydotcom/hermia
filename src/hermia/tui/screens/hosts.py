"""Hosts drill — list, add, remove, probe state.

Lists existing hosts in app.config. `+` opens AddHostModal; enter drills
into the host's models; escape pops back. Background probes via app.bus
update probe_state per host (`probing` / `ok` / `failed`) which renders
as inline `[state]` tags on each row.

Probe events use the `probe.*` topic prefix; runner events use `run.*`.
Both share app.bus — screens subscribe only to their own prefix.
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

from hermia.tui.probe import DEFAULT_PROBE_TIMEOUT_SECONDS, probe_host
from hermia.tui.screens._dirty import _mark_dirty_in_stack
from hermia.tui.state import FleetConfig, Host
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
        # Listener tasks — created once on first probe and reused, so
        # re-firing _start_probes (after add-host) doesn't subscribe twice.
        self._listener_tasks: list[asyncio.Task[None]] = []

    @property
    def _bus(self):  # type: ignore[no-untyped-def]
        """Shared app-level bus. probe.* events use the same bus as run.* events;
        screens subscribe only to the topics they care about, so there is no bleeding."""
        return self.app.bus  # type: ignore[attr-defined]

    @property
    def app_config(self) -> FleetConfig:
        return self.app.config  # type: ignore[attr-defined,no-any-return]

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
        existing_rows = [c for c in root.children if not isinstance(c, Breadcrumb)]
        # Stable-row optimization (Plan 1 lesson): when host count is unchanged
        # and we're not transitioning to/from empty state, update Statics in
        # place. Cursor moves and probe-state updates take this path.
        if (
            self.app_config.hosts
            and len(existing_rows) == len(self.app_config.hosts)
            and all(isinstance(c, Static) for c in existing_rows)
        ):
            for i, host in enumerate(self.app_config.hosts):
                existing_rows[i].update(self._row_text(host, i))  # type: ignore[attr-defined]
            return
        # Structural change (add-host, first mount, mode transition) — full
        # remount with seq-bumped IDs so AwaitRemove can't collide with new
        # mount IDs.
        for child in existing_rows:
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
        _mark_dirty_in_stack(self.app)
        # Kick a probe for the new host.
        self._start_probes()

    # ── Probe wiring ──────────────────────────────────────────────────────

    @work
    async def _start_probes(self) -> None:
        """Background worker: subscribe to probe events, then fire probes.

        Started in on_mount and after any host is added. Idempotent on two
        axes: per-host (probes skipped for hosts with recorded probe_state)
        and per-screen (listener tasks created once and reused, so
        re-firing _start_probes after add-host doesn't double-subscribe).
        """
        # Subscribe first so events fired during probe_host land in queues.
        # Listeners are screen-lifetime singletons — multiple _start_probes
        # calls reuse the same subscribers (no duplicate event handling).
        if not self._listener_tasks:
            self._listener_tasks = [
                asyncio.create_task(self._listen("probe.started", "probing")),
                asyncio.create_task(self._listen("probe.completed", "ok")),
                asyncio.create_task(self._listen("probe.failed", "failed")),
            ]
            await asyncio.sleep(0)  # give subscribers a tick to register

        # Resolve transport factory lazily so unit tests don't import urllib
        # paths unless a real probe runs.
        factory = self._make_transport
        if factory is None:
            from hermia.tui.transport_adapter import transport_for
            factory = transport_for

        async def _probe(host: Host) -> None:
            transport = factory(host)
            await probe_host(
                host,
                transport=transport,  # type: ignore[arg-type]
                bus=self._bus,
                timeout=self._probe_timeout,
            )

        # Probe all unprobed hosts concurrently.
        to_probe = [h for h in list(self.app_config.hosts) if h.name not in self.probe_state]
        if to_probe:
            results = await asyncio.gather(
                *[_probe(h) for h in to_probe],
                return_exceptions=True,
            )
            any_failed = False
            for host, result in zip(to_probe, results, strict=True):
                if isinstance(result, BaseException):
                    self.probe_state[host.name] = "failed"
                    any_failed = True
            if any_failed and self.is_mounted:
                self._rerender()

    def on_unmount(self) -> None:
        # Cancel listener tasks so they don't outlive the screen.
        for t in self._listener_tasks:
            t.cancel()
        self.workers.cancel_all()

    async def _listen(self, topic: str, final_state: str) -> None:
        async for ev in self._bus.subscribe(topic):
            self.probe_state[ev["host_name"]] = final_state
            if self.is_mounted:
                self._rerender()
