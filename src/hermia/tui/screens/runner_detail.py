"""RunnerDetailScreen (L3) — detail view for one trial.

Receives a _TrialRow at init. If the trial is still pending or running,
subscribes to run.trial_finished to update when the result arrives. escape
always pops.
"""
from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from hermia.tui.screens.runner_trials import _TrialRow
from hermia.tui.widgets.breadcrumb import Breadcrumb

_AWAITING_STATES = frozenset({"pending", "running"})


class RunnerDetailScreen(Screen[None]):
    BINDINGS = [Binding("escape", "back", "Back", show=True)]

    def __init__(self, *, trial: _TrialRow) -> None:
        super().__init__()
        self._trial = trial
        self._listener_task: asyncio.Task[None] | None = None
        self._summary: str = ""

    @property
    def breadcrumb_text(self) -> str:
        return self.query_one(Breadcrumb).text

    @property
    def summary_text(self) -> str:
        return self._summary

    @property
    def is_awaiting_result(self) -> bool:
        return self._trial.state in _AWAITING_STATES

    def compose(self) -> ComposeResult:
        t = self._trial
        with Vertical():
            yield Breadcrumb(["hermia", "runner", t.model_name, t.test_id])
            yield Static("", id="detail-summary")
            yield Static("", id="detail-output")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()
        if self.is_awaiting_result:
            self._listener_task = asyncio.create_task(self._listen_finished())

    def on_unmount(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()

    def _refresh(self) -> None:
        t = self._trial
        if self.is_awaiting_result:
            summary = f"Trial in progress…  ({t.model_name} / {t.test_id})"
        else:
            elapsed = f"{t.elapsed_sec:.2f}s" if t.elapsed_sec is not None else "—"
            # Escape square brackets so Rich doesn't treat them as markup tags.
            reason = f"  \[{t.failure_reason}]" if t.failure_reason else ""
            summary = f"verdict: {t.state}  elapsed: {elapsed}{reason}"

        self._summary = summary
        self.query_one("#detail-summary", Static).update(summary)
        self.query_one("#detail-output", Static).update(t.output_preview or "")

    async def _listen_finished(self) -> None:
        t = self._trial
        async for ev in self.app.bus.subscribe("run.trial_finished"):  # type: ignore[attr-defined]
            if (
                ev.get("model_name") == t.model_name
                and ev.get("test_id") == t.test_id
                and ev.get("repeat_idx") == t.repeat_idx
                and (not t.host_name or ev.get("host_name") == t.host_name)
            ):
                t.state = ev.get("verdict", "error")
                t.elapsed_sec = ev.get("elapsed_sec")
                t.failure_reason = ev.get("failure_reason", "")
                t.output_preview = ev.get("output_preview", "")
                if self.is_mounted:
                    self._refresh()
                return

    def action_back(self) -> None:
        self.app.pop_screen()
