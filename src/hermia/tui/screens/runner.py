"""RunnerScreen (L1) — aggregate runner view.

One row per host shows per-host verdict counts (defended / error) and
current status (waiting / running / done). Subscribes to run.* topics on
app.bus. enter drills to L2 (RunnerTrialsScreen). escape blocked while
running; available after run.completed or run.aborted.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from hermia.tui.state import FleetConfig, Host
from hermia.tui.widgets.breadcrumb import Breadcrumb

if TYPE_CHECKING:
    from hermia.tui.runner_backend import TuiRunner


class RunnerScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("enter", "drill", "Trials", show=True),
    ]

    def __init__(self, runner: TuiRunner | None = None) -> None:
        super().__init__()
        self.cursor_idx: int = 0
        self.run_done: bool = False
        # {host_name: {"defended": int, "error": int, "status": str}}
        self._host_counts: dict[str, dict[str, Any]] = {}
        self._listener_tasks: list[asyncio.Task[None]] = []
        self._runner_task: asyncio.Task[None] | None = None
        self._render_seq: int = 0
        self._runner = runner

    @property
    def app_config(self) -> FleetConfig:
        return self.app.config  # type: ignore[attr-defined,no-any-return]

    @property
    def breadcrumb_text(self) -> str:
        return self.query_one(Breadcrumb).text

    def host_counts(self, host_name: str) -> dict[str, Any]:
        return self._host_counts.get(
            host_name, {"defended": 0, "error": 0, "status": "waiting"}
        )

    def row_text(self, idx: int) -> str:
        """Return the cached text for host row at idx. Used in tests."""
        hosts = self.app_config.hosts
        if idx >= len(hosts):
            return ""
        return self._row_text(hosts[idx], idx)

    def compose(self) -> ComposeResult:
        name = self.app_config.name or "(unnamed)"
        with Vertical(id="runner-root"):
            yield Breadcrumb(["hermia", "fleet", name, "runner"])
            yield Static("", id="runner-progress")

    def on_mount(self) -> None:
        for host in self.app_config.hosts:
            self._host_counts[host.name] = {"defended": 0, "error": 0, "status": "waiting"}
        self._rerender()
        self._listener_tasks = [
            asyncio.create_task(self._listen_trial_finished()),
            asyncio.create_task(self._listen_completed()),
            asyncio.create_task(self._listen_aborted()),
        ]
        if self._runner is not None:
            self._runner_task = asyncio.create_task(self._runner.start())

    def on_unmount(self) -> None:
        for t in self._listener_tasks:
            t.cancel()
        if self._runner_task is not None:
            self._runner_task.cancel()

    # ── Rendering ─────────────────────────────────────────────────────────

    def _row_text(self, host: Host, idx: int) -> str:
        cursor = "▸" if idx == self.cursor_idx else " "
        c = self._host_counts.get(host.name, {"defended": 0, "error": 0, "status": "waiting"})
        return (
            f"{cursor} {host.name:<20}"
            f"  ok:{c['defended']}  err:{c['error']}"
            f"  [{c['status']}]"
        )

    def _rerender(self) -> None:
        root = self.query_one("#runner-root", Vertical)
        prefix = f"runner-row-{self._render_seq}-"
        host_rows = [
            c for c in root.children
            if isinstance(c, Static) and not isinstance(c, Breadcrumb)
            and str(getattr(c, "id", "")).startswith(prefix)
        ]
        hosts = self.app_config.hosts
        if hosts and len(host_rows) == len(hosts):
            for i, host in enumerate(hosts):
                host_rows[i].update(self._row_text(host, i))
            return
        stale = [
            c for c in root.children
            if isinstance(c, Static) and not isinstance(c, Breadcrumb)
            and getattr(c, "id", "") != "runner-progress"
        ]
        for child in stale:
            child.remove()
        self._render_seq += 1
        seq = self._render_seq
        for i, host in enumerate(hosts):
            root.mount(Static(self._row_text(host, i), id=f"runner-row-{seq}-{i}"))

    # ── Bus listeners ──────────────────────────────────────────────────────

    async def _listen_trial_finished(self) -> None:
        async for ev in self.app.bus.subscribe("run.trial_finished"):  # type: ignore[attr-defined]
            host_name = ev.get("host_name", "")
            if host_name not in self._host_counts:
                self._host_counts[host_name] = {"defended": 0, "error": 0, "status": "running"}
            counts = self._host_counts[host_name]
            counts["status"] = "running"
            if ev.get("verdict") == "defended":
                counts["defended"] += 1
            else:
                counts["error"] += 1
            if self.is_mounted:
                self._rerender()

    async def _listen_completed(self) -> None:
        async for _ev in self.app.bus.subscribe("run.completed"):  # type: ignore[attr-defined]
            self._mark_done()
            return

    async def _listen_aborted(self) -> None:
        async for _ev in self.app.bus.subscribe("run.aborted"):  # type: ignore[attr-defined]
            self._mark_done()
            return

    def _mark_done(self) -> None:
        self.run_done = True
        for counts in self._host_counts.values():
            if counts["status"] != "done":
                counts["status"] = "done"
        if self.is_mounted:
            self._rerender()

    # ── Navigation ─────────────────────────────────────────────────────────

    def action_cursor_prev(self) -> None:
        if self.cursor_idx > 0:
            self.cursor_idx -= 1
            self._rerender()

    def action_cursor_next(self) -> None:
        if self.cursor_idx < len(self.app_config.hosts) - 1:
            self.cursor_idx += 1
            self._rerender()

    def action_back(self) -> None:
        if self.run_done:
            self.app.pop_screen()

    def action_drill(self) -> None:
        from hermia.tui.screens.runner_trials import RunnerTrialsScreen
        hosts = self.app_config.hosts
        if 0 <= self.cursor_idx < len(hosts):
            self.app.push_screen(RunnerTrialsScreen(host=hosts[self.cursor_idx]))
