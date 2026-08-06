"""RunState — the durable fold of run.* bus events.

`SessionBus.subscribe()` allocates a fresh empty queue with no history: the bus
is a pure delta channel. A screen mounted mid-run therefore cannot reconstruct
what it missed from the bus alone, which is why the L2 trials screen rendered a
finished run as "pending" (hermia-mo4a) — it built its rows at the dataclass
default and *then* subscribed.

RunState is the store screens hydrate from on mount. `TuiRunner` folds each
event in here *before* publishing it (one `_emit` choke point), so the store can
never lag the bus. It also carries the full `raw_response` the L3 detail screen
needs (hermia-2ke3).

One record per (host, model, test_id, repeat_idx), so memory is O(trials) by
construction rather than O(events) — and `run.started` resets, so a second run
in the same session never hydrates screens from the first run's rows.

Pure stdlib by design: no Textual, no asyncio, no hermia imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# (host_name, model_name, test_id, repeat_idx)
TrialKey = tuple[str, str, str, int]

PHASE_IDLE = "idle"
PHASE_RUNNING = "running"
PHASE_COMPLETED = "completed"
PHASE_ABORTED = "aborted"

STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_ERROR = "error"
# Terminal-run state for a trial that never reported. Distinct from "pending",
# which asserts a result is still coming — an assertion the screen has no basis
# for once the run has ended.
STATE_UNREPORTED = "unreported"

_TERMINAL_PHASES = frozenset({PHASE_COMPLETED, PHASE_ABORTED})


@dataclass
class TrialRecord:
    host_name: str
    model_name: str
    test_id: str
    repeat_idx: int
    state: str = STATE_PENDING
    elapsed_sec: float | None = None
    failure_reason: str = ""
    output_preview: str = ""
    raw_response: str = ""
    raw_prompt: str = ""
    raw_system: str = ""
    raw_thinking: str = ""


def _key(event: dict[str, Any]) -> TrialKey:
    return (
        str(event.get("host_name", "")),
        str(event.get("model_name", "")),
        str(event.get("test_id", "")),
        int(event.get("repeat_idx", 0) or 0),
    )


def _opt_float(value: Any) -> float | None:
    """Coerce an event's elapsed_sec to float, preserving a genuine absence.

    Absent and unparseable both become None rather than 0.0 — a zero would
    assert "this took no time", which is the confident-non-answer shape.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class RunState:
    """Current state of the active run, folded from the run.* event stream."""

    def __init__(self) -> None:
        self.phase: str = PHASE_IDLE
        self.error: str = ""
        # Plain dict: insertion-ordered, so trials_for_host preserves the order
        # trials were first seen and rows never reshuffle under the cursor.
        self._trials: dict[TrialKey, TrialRecord] = {}

    # ── Mutation ───────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Drop every trial and return to the idle phase."""
        self._trials.clear()
        self.phase = PHASE_IDLE
        self.error = ""

    def apply(self, topic: str, event: dict[str, Any]) -> None:
        """Fold one bus event. Unknown topics are ignored."""
        if topic == "run.started":
            # Reset first — a second run in the same session must not leave the
            # previous run's rows visible to a screen that hydrates from here.
            self.reset()
            self.phase = PHASE_RUNNING
        elif topic == "run.trial_started":
            self._upsert(_key(event)).state = STATE_RUNNING
        elif topic == "run.trial_finished":
            rec = self._upsert(_key(event))
            # `or STATE_ERROR` (not a dict default): an empty or null verdict is
            # not a verdict, and must not be rendered as one.
            rec.state = str(event.get("verdict") or STATE_ERROR)
            rec.elapsed_sec = _opt_float(event.get("elapsed_sec"))
            rec.failure_reason = str(event.get("failure_reason", ""))
            rec.output_preview = str(event.get("output_preview", ""))
            rec.raw_response = str(event.get("raw_response", ""))
            rec.raw_prompt = str(event.get("raw_prompt", ""))
            rec.raw_system = str(event.get("raw_system", ""))
            rec.raw_thinking = str(event.get("raw_thinking", ""))
        elif topic == "run.completed":
            self.phase = PHASE_COMPLETED
        elif topic == "run.aborted":
            self.phase = PHASE_ABORTED
            self.error = str(event.get("error", ""))

    def _upsert(self, key: TrialKey) -> TrialRecord:
        rec = self._trials.get(key)
        if rec is None:
            host_name, model_name, test_id, repeat_idx = key
            rec = TrialRecord(
                host_name=host_name,
                model_name=model_name,
                test_id=test_id,
                repeat_idx=repeat_idx,
            )
            self._trials[key] = rec
        return rec

    # ── Queries ────────────────────────────────────────────────────────────

    def trial(
        self,
        host_name: str,
        model_name: str,
        test_id: str,
        repeat_idx: int,
    ) -> TrialRecord | None:
        """Exact lookup. None when this trial has never been seen."""
        return self._trials.get((host_name, model_name, test_id, repeat_idx))

    def trials_for_host(self, host_name: str) -> list[TrialRecord]:
        """Every record for one host, in first-seen order."""
        return [r for r in self._trials.values() if r.host_name == host_name]

    @property
    def is_terminal(self) -> bool:
        return self.phase in _TERMINAL_PHASES
