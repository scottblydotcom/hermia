"""RunnerTrialsScreen (L2) — trial table for one host.

One row per (selected model × test × repeat) combination.

On mount the screen registers its bus queues, hydrates every row from
`app.run_state`, and only then starts consuming. Hydration is not optional: the
bus allocates a fresh empty queue per subscriber with no replay, so before
hermia-mo4a every trial that finished while the user was on another screen
rendered as "pending" forever. Registering before hydrating matters just as
much — see on_mount. It also tracks the run's terminal phase; a finished run
with no end state read as frozen.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from hermia.tui.run_state import (
    PHASE_ABORTED,
    STATE_ERROR,
    STATE_PENDING,
    STATE_RUNNING,
    STATE_UNREPORTED,
    RunState,
    opt_float,
)
from hermia.tui.state import FleetConfig, Host
from hermia.tui.widgets.breadcrumb import Breadcrumb

# States that mean "no result has arrived". At a terminal phase these stop
# reading as "pending" — see _apply_terminal.
_UNSETTLED = frozenset({STATE_PENDING, STATE_RUNNING})


@dataclass
class _TrialRow:
    model_name: str
    test_id: str
    repeat_idx: int
    host_name: str = ""
    state: str = STATE_PENDING  # pending | running | defended | error | unreported
    elapsed_sec: float | None = None
    failure_reason: str = ""
    output_preview: str = ""
    # Full payload (hermia-2ke3) — the L3 detail screen renders raw_response;
    # output_preview above is the 120-char row summary, not the response.
    raw_response: str = ""
    raw_prompt: str = ""
    raw_system: str = ""
    raw_thinking: str = ""


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
        self.run_done: bool = False
        self._terminal_text: str = ""
        self._terminal_error: str = ""

    @property
    def app_config(self) -> FleetConfig:
        return self.app.config  # type: ignore[attr-defined,no-any-return]

    @property
    def app_run_state(self) -> RunState | None:
        return getattr(self.app, "run_state", None)

    @property
    def breadcrumb_text(self) -> str:
        return self.query_one(Breadcrumb).text

    @property
    def terminal_text(self) -> str:
        """Banner text once the run ends; "" while it is still running."""
        return self._terminal_text

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
            yield Static(
                "  ✓ defended   ✗ error   ↺ running     pending   ! unreported\n"
                "  Enter  View trial detail     Esc  Back to runner",
                id="trials-legend",
            )
            yield Static("", id="trials-terminal")
        yield Footer()

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
                        host_name=self._host.name,
                    ))
        # Register the queues BEFORE hydrating. bus.subscribe() is synchronous
        # and registers immediately, but the coroutine that calls it does not
        # run until the loop next schedules it — so subscribing inside the
        # listener tasks leaves a window after the hydrate snapshot in which a
        # published event is missed by the snapshot AND by the not-yet-created
        # queue. That is the exact defect this screen is being fixed for.
        # Subscribing first can only duplicate an event, and every apply here
        # is idempotent.
        bus = self.app.bus  # type: ignore[attr-defined]
        started = bus.subscribe("run.trial_started")
        finished = bus.subscribe("run.trial_finished")
        completed = bus.subscribe("run.completed")
        aborted = bus.subscribe("run.aborted")
        self._hydrate()
        self._rerender()
        self._listener_tasks = [
            asyncio.create_task(self._listen_started(started)),
            asyncio.create_task(self._listen_finished(finished)),
            asyncio.create_task(self._listen_terminal(completed, "completed")),
            asyncio.create_task(self._listen_terminal(aborted, "aborted")),
        ]

    def on_unmount(self) -> None:
        for t in self._listener_tasks:
            t.cancel()

    # ── Hydration ─────────────────────────────────────────────────────────

    def _hydrate(self) -> None:
        """Seed rows and terminal state from the app's RunState."""
        rs = self.app_run_state
        if rs is None:
            return
        for t in self._trials:
            rec = rs.trial(self._host.name, t.model_name, t.test_id, t.repeat_idx)
            if rec is None:
                continue
            t.state = rec.state
            t.elapsed_sec = rec.elapsed_sec
            t.failure_reason = rec.failure_reason
            t.output_preview = rec.output_preview
            t.raw_response = rec.raw_response
            t.raw_prompt = rec.raw_prompt
            t.raw_system = rec.raw_system
            t.raw_thinking = rec.raw_thinking
        if rs.is_terminal:
            self._apply_terminal(
                "aborted" if rs.phase == PHASE_ABORTED else "completed",
                error=rs.error,
                rerender=False,
            )

    def _apply_terminal(self, phase: str, *, error: str = "", rerender: bool = True) -> None:
        """Record the run's end state and stop claiming trials are pending.

        A row still at pending/running when the run ends never reported. Leaving
        it as "pending" asserts a result is still coming — the screen has no
        basis for that once the run is over, so it says only what it knows.
        """
        self.run_done = True
        # Never replace a known reason with an empty one: the hydrated phase
        # carries RunState.error, while the matching bus event may not.
        if error:
            self._terminal_error = error
        for t in self._trials:
            if t.state in _UNSETTLED:
                t.state = STATE_UNREPORTED
        # Count the unreported rows rather than the ones this call flipped: on a
        # second invocation (hydrated terminal, then a terminal bus event) the
        # flip count is zero and the banner would claim every trial reported.
        n_unreported = sum(1 for t in self._trials if t.state == STATE_UNREPORTED)
        text = f"run {phase} — {len(self._trials) - n_unreported}/{len(self._trials)} reported"
        if n_unreported:
            text += f", {n_unreported} never reported"
        if self._terminal_error:
            text += f"  [{self._terminal_error}]"
        self._terminal_text = text
        if rerender and self.is_mounted:
            self._rerender()

    # ── Rendering ─────────────────────────────────────────────────────────

    def _row_text(self, trial: _TrialRow, idx: int) -> str:
        cursor = "▸" if idx == self.cursor_idx else " "
        _icons = {
            "pending": " ", "running": "↺", "defended": "✓", "error": "✗",
            STATE_UNREPORTED: "!",
        }
        state_icon = _icons.get(trial.state, "?")
        elapsed = f"  {trial.elapsed_sec:.1f}s" if trial.elapsed_sec is not None else ""
        reason = f"  {escape(f'[{trial.failure_reason}]')}" if trial.failure_reason else ""
        return (
            f"{cursor} {state_icon}  {trial.model_name:<20}"
            f"  {trial.test_id:<24}{elapsed}{reason}"
        )

    def _rerender(self) -> None:
        root = self.query_one("#trials-root", Vertical)
        self.query_one("#trials-terminal", Static).update(escape(self._terminal_text))
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
        # Chrome (legend, terminal banner) is not a stale row — removing it here
        # would delete the banner on the next full re-render.
        stale = [
            c for c in root.children
            if not isinstance(c, Breadcrumb)
            and c.id not in ("trials-legend", "trials-terminal")
        ]
        for child in stale:
            child.remove()
        self._render_seq += 1
        seq = self._render_seq
        for i, trial in enumerate(self._trials):
            root.mount(Static(self._row_text(trial, i), id=f"trial-row-{seq}-{i}"))

    # ── Bus listeners ──────────────────────────────────────────────────────

    async def _listen_started(self, events: AsyncIterator[dict[str, Any]]) -> None:
        async for ev in events:
            if ev.get("host_name") != self._host.name:
                continue
            for t in self._trials:
                if (t.model_name == ev.get("model_name") and t.test_id == ev.get("test_id")
                        and t.repeat_idx == ev.get("repeat_idx")):
                    t.state = STATE_RUNNING
            if self.is_mounted:
                self._rerender()

    async def _listen_finished(self, events: AsyncIterator[dict[str, Any]]) -> None:
        async for ev in events:
            if ev.get("host_name") != self._host.name:
                continue
            for t in self._trials:
                if (t.model_name == ev.get("model_name") and t.test_id == ev.get("test_id")
                        and t.repeat_idx == ev.get("repeat_idx")):
                    # Same coercions RunState.apply uses. When these two paths
                    # disagree, the same event renders differently live than it
                    # does after a remount — an empty verdict became the "?"
                    # icon here but "error" there.
                    t.state = str(ev.get("verdict") or STATE_ERROR)
                    t.elapsed_sec = opt_float(ev.get("elapsed_sec"))
                    t.failure_reason = str(ev.get("failure_reason", ""))
                    t.output_preview = str(ev.get("output_preview", ""))
                    t.raw_response = str(ev.get("raw_response", ""))
                    t.raw_prompt = str(ev.get("raw_prompt", ""))
                    t.raw_system = str(ev.get("raw_system", ""))
                    t.raw_thinking = str(ev.get("raw_thinking", ""))
            if self.is_mounted:
                self._rerender()

    async def _listen_terminal(
        self, events: AsyncIterator[dict[str, Any]], phase: str
    ) -> None:
        """Give the screen an end state. Without this a finished run looks frozen."""
        async for ev in events:
            self._apply_terminal(phase, error=str(ev.get("error", "")))
            return

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
