"""RunnerDetailScreen (L3) — detail view for one trial.

This is the only surface in the TUI where a model's actual answer can be read,
so it renders the full `raw_response` (hermia-2ke3). It previously rendered
`output_preview` — a 120-character, newline-flattened row summary — which meant
the eval's own output was unreadable from the tool that produced it.

Receives a _TrialRow at init. If that row predates the result, the screen
hydrates from `app.run_state` on mount and, failing that, subscribes to
run.trial_finished. escape always pops.
"""
from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from hermia.tui.run_state import RunState
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
        self._output: str = ""

    @property
    def app_run_state(self) -> RunState | None:
        return getattr(self.app, "run_state", None)

    @property
    def breadcrumb_text(self) -> str:
        return self.query_one(Breadcrumb).text

    @property
    def summary_text(self) -> str:
        return self._summary

    @property
    def output_text(self) -> str:
        """The response text the screen is displaying, verbatim and untruncated."""
        return self._output

    @property
    def is_awaiting_result(self) -> bool:
        return self._trial.state in _AWAITING_STATES

    def compose(self) -> ComposeResult:
        t = self._trial
        with Vertical():
            yield Breadcrumb(["hermia", "runner", t.model_name, t.test_id])
            yield Static("", id="detail-summary")
            # markup=False: model output is routinely JSON and Rich would
            # silently DELETE bracketed spans like "[bold]" from the rendered
            # line. Escaping would work too, but a flag that cannot be forgotten
            # on the next update() call is the safer contract.
            with VerticalScroll(id="detail-output-scroll"):
                yield Static("", id="detail-output", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        # A row handed over before its result arrived is stale by construction.
        # run_state holds the outcome if it landed while L2 was on screen.
        self._hydrate()
        self._refresh()
        if self.is_awaiting_result:
            self._listener_task = asyncio.create_task(self._listen_finished())

    def on_unmount(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()

    def _hydrate(self) -> None:
        rs = self.app_run_state
        t = self._trial
        if rs is None:
            return
        rec = rs.trial(t.host_name, t.model_name, t.test_id, t.repeat_idx)
        if rec is None or rec.state in _AWAITING_STATES:
            return
        t.state = rec.state
        t.elapsed_sec = rec.elapsed_sec
        t.failure_reason = rec.failure_reason
        t.output_preview = rec.output_preview
        t.raw_response = rec.raw_response
        t.raw_prompt = rec.raw_prompt
        t.raw_system = rec.raw_system
        t.raw_thinking = rec.raw_thinking

    def _display_text(self) -> str:
        """Full response, falling back to the preview only when there is none.

        Error and timeout rows carry no raw_response, so the preview is all
        there is — but it is never preferred over a real response.
        """
        t = self._trial
        if t.raw_response:
            return t.raw_response
        return t.output_preview or ""

    def _refresh(self) -> None:
        t = self._trial
        if self.is_awaiting_result:
            summary = f"Trial in progress…  ({t.model_name} / {t.test_id})"
        else:
            elapsed = f"{t.elapsed_sec:.2f}s" if t.elapsed_sec is not None else "—"
            # Escape square brackets so Rich doesn't treat them as markup tags.
            reason = rf"  \[{t.failure_reason}]" if t.failure_reason else ""
            summary = f"verdict: {t.state}  elapsed: {elapsed}{reason}"

        self._summary = summary
        self._output = self._display_text()
        self.query_one("#detail-summary", Static).update(summary)
        self.query_one("#detail-output", Static).update(self._output)

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
                t.raw_response = ev.get("raw_response", "")
                t.raw_prompt = ev.get("raw_prompt", "")
                t.raw_system = ev.get("raw_system", "")
                t.raw_thinking = ev.get("raw_thinking", "")
                if self.is_mounted:
                    self._refresh()
                return

    def action_back(self) -> None:
        self.app.pop_screen()
