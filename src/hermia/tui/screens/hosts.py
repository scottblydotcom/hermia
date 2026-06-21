"""Hosts drill — list, add, remove, probe state.

Lists existing hosts in app.config. `+` opens AddHostModal; enter drills
into the host's models (Task 12); escape pops back. Background probes for
each host's models land in Task 11 and update probe_state per host.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

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
    ) -> None:
        super().__init__()
        self.cursor_idx: int = 0
        # probe_state[host.name] = "probing" | "ok" | "failed". Task 11 fills.
        self.probe_state: dict[str, str] = {}
        # Injected for tests; production uses transport_adapter.transport_for.
        self._make_transport = transport_factory
        self._render_seq: int = 0

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
        # Task 12 wires the host-models screen push.
        pass

    def _on_host_added(self, host: Host | None) -> None:
        if host is None:
            return
        self.app_config.hosts.append(host)
        self._rerender()
