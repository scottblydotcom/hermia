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
from collections.abc import AsyncIterator, Callable
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

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
        # Tracks "ok" hosts that came back with zero models — the actionable
        # "host reachable but bare" case (Ollama running, nothing pulled).
        # Kept separate from probe_state so the inline [ok] badge stays
        # accurate while the hint surface picks up the empty case.
        self.probe_warnings: dict[str, str] = {}
        # Injected for tests; production uses transport_adapter.transport_for
        # (resolved at probe time so the import stays lazy).
        self._make_transport = transport_factory
        self._probe_timeout = probe_timeout
        self._render_seq: int = 0
        # Listener tasks — created once on first probe and reused, so
        # re-firing _start_probes (after add-host) doesn't subscribe twice.
        self._listener_tasks: list[asyncio.Task[None]] = []

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
            yield Static(
                "Each host is an Ollama endpoint. hermia will probe it and list available models.\n"
                "\n"
                "  +  Add a new host          Enter  Choose models for this host\n"
                "  Esc  Back to fleet config",
                id="hosts-instructions",
            )
        yield Footer()

    def on_mount(self) -> None:
        self._rerender()
        self._start_probes()

    def _row_text(self, host: Host, idx: int) -> str:
        cursor = "▸" if idx == self.cursor_idx else " "
        state = self.probe_state.get(host.name, "")
        state_str = f" [{state}]" if state else ""
        return f"{cursor} {host.name}    {host.url}    [{host.engine}]{state_str}"

    _HINT_IDS = ("hosts-probe-failed-hint", "hosts-no-models-hint")

    def _rerender(self) -> None:
        root = self.query_one("#hosts-root", Vertical)
        existing_rows = [
            c for c in root.children
            if not isinstance(c, Breadcrumb)
            and c.id != "hosts-instructions"
            and c.id not in self._HINT_IDS
        ]
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
            self._sync_probe_hints(root)
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
        self._sync_probe_hints(root)

    def _sync_probe_hints(self, root: Vertical) -> None:
        """Surface actionable nudges when probes fail or come back bare.

        The bare [failed] / [ok] state badges are not actionable on their own —
        a first-time user has no map from "[failed]" to "start Ollama". These
        hints fill the gap (hermia-1pj). Idempotent — safe to call from both
        the stable-row fast path and the structural-change slow path.
        """
        any_failed = any(s == "failed" for s in self.probe_state.values())
        any_no_models = bool(self.probe_warnings)
        # Remove any stale hints first so condition flips are reflected.
        for hid in self._HINT_IDS:
            for w in root.query(f"#{hid}"):
                w.remove()
        if any_failed:
            root.mount(Static(
                "Hint: a host probe failed. Is Ollama running? "
                "Start it with `ollama serve`, then leave and re-enter this "
                "screen to re-probe.",
                id="hosts-probe-failed-hint",
            ))
        if any_no_models:
            root.mount(Static(
                "Hint: a host is reachable but has no models pulled. "
                "Try `ollama pull llama3.2`, then leave and re-enter to "
                "re-probe.",
                id="hosts-no-models-hint",
            ))

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
        # Subscribe synchronously before spawning tasks so queues are registered
        # with no race window. create_task() schedules but doesn't step the
        # coroutine; anything published between create_task and the first sleep(0)
        # would be lost if subscribe() were called inside the task.
        if not self._listener_tasks or any(t.done() for t in self._listener_tasks):
            for t in self._listener_tasks:
                if not t.done():
                    t.cancel()
            self._listener_tasks = [
                asyncio.create_task(
                    self._listen(self.app.bus.subscribe("probe.started"), "probing")  # type: ignore[attr-defined]
                ),
                asyncio.create_task(
                    self._listen(self.app.bus.subscribe("probe.completed"), "ok")  # type: ignore[attr-defined]
                ),
                asyncio.create_task(
                    self._listen(self.app.bus.subscribe("probe.failed"), "failed")  # type: ignore[attr-defined]
                ),
            ]

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
                bus=self.app.bus,  # type: ignore[attr-defined]
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

    async def _listen(self, gen: AsyncIterator[dict[str, Any]], final_state: str) -> None:
        async for ev in gen:
            host_name = ev["host_name"]
            self.probe_state[host_name] = final_state
            # probe.completed carries `warning: "no_models" | None`; capture
            # it so the hint surface can show the actionable "pull a model"
            # nudge when an otherwise-ok host has zero models pulled.
            warning = ev.get("warning") if final_state == "ok" else None
            if warning:
                self.probe_warnings[host_name] = warning
            else:
                self.probe_warnings.pop(host_name, None)
            if self.is_mounted:
                self._rerender()
