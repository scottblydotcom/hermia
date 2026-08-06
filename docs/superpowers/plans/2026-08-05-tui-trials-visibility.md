# Plan — TUI trials visibility (hermia-mo4a + hermia-2ke3)

**Branch:** `feature/hermia-mo4a-2ke3-tui-trials` (off `dev`)
**Scope:** `src/hermia/tui/**` only. No corpus, no CLI writer, no published number.

## Why these two together

Both defects live on the same drill-down path (L1 runner → L2 trials → L3 detail) and both
have the same consequence: **the UI asserts something it does not know.** L2 asserts
"pending" for trials that already finished; L3 asserts a 120-character string is the model's
answer. Fixing one without the other still leaves the audit path unusable.

## Root causes (read from source, not inferred)

### hermia-mo4a — L2 renders a completed run as pending

1. **No replay.** `tui/bus.py:36` — `subscribe()` allocates a *fresh empty queue*. The bus is a
   pure delta channel with no history. `runner_trials.py:81-97` builds every `_TrialRow` at the
   dataclass default `state="pending"` and *then* subscribes, so every event published before
   the user drilled in is gone. Drill in after 13 of 17 trials → the screen shows 4.
2. **No terminal state.** `runner_trials.py` subscribes only to `run.trial_started` /
   `run.trial_finished` — never `run.completed` / `run.aborted`. A finished run therefore has
   no end state and reads as frozen. (L1 `RunnerScreen` *does* subscribe to both and stayed
   accurate.)

Both halves are required. Replay alone still leaves a finished run looking in-progress.

### hermia-2ke3 — L3 shows a 120-char preview, not the response

- `runner.py:455` — `preview = output[:120].replace("\n", " ")`
- `runner_detail.py:73` — renders `t.output_preview`, never `raw_response`.
- `runner_backend.py:147,219` — the TUI backend truncates to 120 *independently*.
- **The `run.trial_finished` event does not carry `raw_response` at all**
  (`runner_backend.py:225-234`). The event contract must be widened; a detail-screen-only
  change cannot work.
- Data is not lost: `runner.py:483` stores `raw_response` / `raw_prompt` / `raw_system` /
  `raw_thinking` (the last since hermia-cv5z).

## Design decision: run-state store, not a bus replay buffer

The handoff offered two directions. **Chosen: an app-level `RunState` that screens hydrate
from on mount; the bus keeps carrying deltas only.**

Rejected — a per-topic replay buffer in `SessionBus`:

- A bounded buffer silently drops the oldest events, so trials whose results aged out render
  as "pending" forever. That is *exactly* the recurring failure shape (a confident non-answer)
  reproduced inside the fix for it.
- An unbounded buffer accumulates every event for the process lifetime, and after this change
  each `trial_finished` carries the full `raw_response` — megabytes on a real fleet run.
- Replay would re-deliver a *previous* run's events to a second run's screens.

`RunState` keys one record per `(host, model, test_id, repeat_idx)`, so memory is O(trials)
by construction, a re-run resets it, and "what is the current state of trial X" is a direct
lookup rather than a fold the caller has to redo.

**Ordering guarantee:** `TuiRunner` folds each event into `RunState` *before* publishing it,
through a single `_emit()` choke point. The store can never lag the bus, and there is one
call site to keep correct instead of six.

## Work items

| # | File | Change |
|---|------|--------|
| 1 | `tui/run_state.py` *(new)* | `TrialRecord` + `RunState.apply(topic, event)` fold; `reset()` on `run.started`; `phase` ∈ idle/running/completed/aborted |
| 2 | `tui/app.py` | `self.run_state = RunState()` alongside `self.bus` |
| 3 | `tui/runner_backend.py` | `run_state=` kwarg; `_emit()` folds-then-publishes; widen `trial_finished` with `raw_response`/`raw_prompt`/`raw_system`/`raw_thinking`; stop truncating error text |
| 4 | `tui/screens/config.py` | pass `run_state=self.app.run_state` into `TuiRunner` |
| 5 | `tui/screens/runner_trials.py` | hydrate grid from `run_state` on mount; subscribe to `run.completed`/`run.aborted`; carry raw fields onto `_TrialRow`; terminal banner; unreported rows stop claiming "pending" |
| 6 | `tui/screens/runner_detail.py` | render full `raw_response` in a scrollable pane (+ prompt/system/thinking); hydrate from `run_state` on mount; escape Rich markup |

## Honesty rule for terminal state

When the run reaches a terminal phase, rows that never reported must **not** keep rendering as
`pending` — "pending" implies a result is still coming. They flip to `unreported`, which
asserts only what is known: no result arrived. The banner states the phase explicitly.

## Test gotchas (cost an hour last session)

- **Use `widget.content`, NOT `widget.renderable`.** On Textual 8.2.8 `renderable` is `None`
  and a probe reading it silently reports "0 rows rendered".
- The **mid-run drill is the necessary condition** for reproducing mo4a. A clean harness that
  pushes L2 and then publishes all events does *not* reproduce it. Tests must publish some
  events *before* the screen mounts.
- Model output routinely contains `[...]` (JSON). Assert it survives Rich rendering, not just
  that it reached the widget.

## Baseline

`.venv/bin/pytest -q` → **1898 passed, 6 failed**. The 6 are `test_detect_gpu_*` in
`tests/unit/test_metrics.py` — pre-existing, macOS-only, tracked as **hermia-2ess**. Scoped
green baseline excludes exactly those.
