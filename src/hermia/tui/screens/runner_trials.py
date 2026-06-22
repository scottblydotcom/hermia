"""RunnerTrialsScreen (L2) — trial table for one host.

One row per (selected model × test × repeat) combination. Subscribes to
run.trial_started and run.trial_finished on app.bus; filters to this
host only. enter drills to L3 for the focused trial. escape always pops.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from hermia.tui.state import FleetConfig, Host
from hermia.tui.widgets.breadcrumb import Breadcrumb


@dataclass
class _TrialRow:
    model_name: str
    test_id: str
    repeat_idx: int
    state: str = "pending"   # pending | running | defended | error
    elapsed_sec: float | None = None
    failure_reason: str = ""
    output_preview: str = ""


class RunnerTrialsScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("up", "cursor_prev", "Up", show=False),
        Binding("down", "cursor_next", "Down", show=False),
        Binding("enter", "drill", "Detail", show=True),
    ]

    def __init__(self, *, host: Host) -> None:
        super().__init__()
        self._host = host
        self.cursor_idx: int = 0
        self._trials: list[_TrialRow] = []
        self._render_seq: int = 0
        self._listener_tasks: list[asyncio.Task[None]] = []

    @property
    def app_config(self) -> FleetConfig:
        return self.app.config  # type: ignore[attr-defined,no-any-return]

    @property
    def breadcrumb_text(self) -> str:
        return self.query_one(Breadcrumb).text

    @property
    def n_trial_rows(self) -> int:
        return len(self._trials)

    def trial_state(self, model_name: str, test_id: str, repeat_idx: int) -> str:
        for t in self._trials:
            if t.model_name == model_name and t.test_id == test_id and t.repeat_idx == repeat_idx:
                return t.state
        return "not-found"

    def compose(self) -> ComposeResult:
        name = self.app_config.name or "(unnamed)"
        with Vertical(id="trials-root"):
            yield Breadcrumb(["hermia", "fleet", name, "runner", self._host.name])

    def on_mount(self) -> None:
        for model in self._host.models:
            if not model.selected:
                continue
            for test_id in self.app_config.tests:
                for rep in range(1, self.app_config.repeat + 1):
                    self._trials.append(_TrialRow(
                        model_name=model.name,
                        test_id=test_id,
                        repeat_idx=rep,
                    ))
        self._rerender()
        self._listener_tasks = [
            asyncio.create_task(self._listen_started()),
            asyncio.create_task(self._listen_finished()),
        ]

    def on_unmount(self) -> None:
        for t in self._listener_tasks:
            t.cancel()

    # ── Rendering ─────────────────────────────────────────────────────────

    def _row_text(self, trial: _TrialRow, idx: int) -> str:
        cursor = "▸" if idx == self.cursor_idx else " "
        _icons = {"pending": " ", "running": "↺", "defended": "✓", "error": "✗"}
        state_icon = _icons.get(trial.state, "?")
        elapsed = f"  {trial.elapsed_sec:.1f}s" if trial.elapsed_sec is not None else ""
        reason = f"  [{trial.failure_reason}]" if trial.failure_reason else ""
        return (
            f"{cursor} {state_icon}  {trial.model_name:<20}"
            f"  {trial.test_id:<24}{elapsed}{reason}"
        )

    def _rerender(self) -> None:
        root = self.query_one("#trials-root", Vertical)
        prefix = f"trial-row-{self._render_seq}-"
        current = [
            c for c in root.children
            if not isinstance(c, Breadcrumb)
            and str(getattr(c, "id", "")).startswith(prefix)
        ]
        if current and len(current) == len(self._trials):
            for i, trial in enumerate(self._trials):
                cast("Static", current[i]).update(self._row_text(trial, i))
            return
        stale = [c for c in root.children if not isinstance(c, Breadcrumb)]
        for child in stale:
            child.remove()
        self._render_seq += 1
        seq = self._render_seq
        for i, trial in enumerate(self._trials):
            root.mount(Static(self._row_text(trial, i), id=f"trial-row-{seq}-{i}"))

    # ── Bus listeners ──────────────────────────────────────────────────────

    async def _listen_started(self) -> None:
        async for ev in self.app.bus.subscribe("run.trial_started"):  # type: ignore[attr-defined]
            if ev.get("host_name") != self._host.name:
                continue
            for t in self._trials:
                if (t.model_name == ev.get("model_name") and t.test_id == ev.get("test_id")
                        and t.repeat_idx == ev.get("repeat_idx")):
                    t.state = "running"
            if self.is_mounted:
                self._rerender()

    async def _listen_finished(self) -> None:
        async for ev in self.app.bus.subscribe("run.trial_finished"):  # type: ignore[attr-defined]
            if ev.get("host_name") != self._host.name:
                continue
            for t in self._trials:
                if (t.model_name == ev.get("model_name") and t.test_id == ev.get("test_id")
                        and t.repeat_idx == ev.get("repeat_idx")):
                    t.state = ev.get("verdict", "error")
                    t.elapsed_sec = ev.get("elapsed_sec")
                    t.failure_reason = ev.get("failure_reason", "")
                    t.output_preview = ev.get("output_preview", "")
            if self.is_mounted:
                self._rerender()

    # ── Navigation ─────────────────────────────────────────────────────────

    def action_cursor_prev(self) -> None:
        if self.cursor_idx > 0:
            self.cursor_idx -= 1
            self._rerender()

    def action_cursor_next(self) -> None:
        if self.cursor_idx < len(self._trials) - 1:
            self.cursor_idx += 1
            self._rerender()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_drill(self) -> None:
        from hermia.tui.screens.runner_detail import RunnerDetailScreen
        if 0 <= self.cursor_idx < len(self._trials):
            self.app.push_screen(RunnerDetailScreen(trial=self._trials[self.cursor_idx]))
