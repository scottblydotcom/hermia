"""Tests for RunState — the durable fold of run.* bus events.

NOTE ON TEST NAMES: keep them under ~35 characters after the `test_` prefix.
TruffleHog's Lob detector matches a long lowercase identifier following
`test_` and reports it as a verified API key, which fails the Security
workflow. Two names in this file did exactly that (hermia-v0h6).

The SessionBus carries deltas only: `subscribe()` allocates a fresh empty
queue, so a screen mounted mid-run can never reconstruct what it missed from
the bus. RunState is the store screens hydrate from instead (hermia-mo4a), and
the carrier for the full model response the L3 detail screen needs
(hermia-2ke3).
"""
from hermia.tui.run_state import RunState, TrialRecord

_KEY = ("host1", "model1", "test1", 1)


def _started(host: str = "host1", model: str = "model1",
             test: str = "test1", rep: int = 1) -> dict:
    return {
        "host_name": host, "model_name": model,
        "test_id": test, "repeat_idx": rep,
    }


def _finished(verdict: str = "defended", **over: object) -> dict:
    ev: dict = {**_started(), "verdict": verdict}
    ev.update(over)
    return ev


class TestInitialState:
    def test_fresh_run_state_is_idle_and_empty(self) -> None:
        rs = RunState()
        assert rs.phase == "idle"
        assert rs.is_terminal is False
        assert rs.error == ""
        assert rs.trial(*_KEY) is None
        assert rs.trials_for_host("host1") == []

    def test_trials_for_unknown_host_is_empty(self) -> None:
        rs = RunState()
        rs.apply("run.trial_started", _started())
        assert rs.trials_for_host("nobody") == []


class TestTrialFold:
    def test_trial_started_creates_running_record(self) -> None:
        rs = RunState()
        rs.apply("run.trial_started", _started())
        rec = rs.trial(*_KEY)
        assert isinstance(rec, TrialRecord)
        assert rec.state == "running"

    def test_trial_finished_sets_state_from_verdict(self) -> None:
        rs = RunState()
        rs.apply("run.trial_started", _started())
        rs.apply("run.trial_finished", _finished("defended"))
        rec = rs.trial(*_KEY)
        assert rec is not None
        assert rec.state == "defended"

    def test_trial_finished_without_verdict_defaults_to_error(self) -> None:
        rs = RunState()
        ev = _started()
        rs.apply("run.trial_finished", ev)
        rec = rs.trial(*_KEY)
        assert rec is not None
        assert rec.state == "error"

    def test_trial_finished_without_a_prior_start_still_records(self) -> None:
        # The host-error path in TuiRunner publishes trial_finished with no
        # matching trial_started; so does any trial whose start was missed.
        rs = RunState()
        rs.apply("run.trial_finished", _finished("error"))
        rec = rs.trial(*_KEY)
        assert rec is not None
        assert rec.state == "error"

    def test_started_then_finished_updates_one_record(self) -> None:
        rs = RunState()
        rs.apply("run.trial_started", _started())
        rs.apply("run.trial_finished", _finished("defended"))
        assert len(rs.trials_for_host("host1")) == 1
        rec = rs.trial(*_KEY)
        assert rec is not None
        assert rec.state == "defended"

    def test_repeat_idx_distinguishes_records(self) -> None:
        rs = RunState()
        rs.apply("run.trial_started", _started(rep=1))
        rs.apply("run.trial_started", _started(rep=2))
        assert len(rs.trials_for_host("host1")) == 2

    def test_host_name_distinguishes_and_filters_records(self) -> None:
        rs = RunState()
        rs.apply("run.trial_started", _started(host="host1"))
        rs.apply("run.trial_started", _started(host="host2"))
        assert len(rs.trials_for_host("host1")) == 1
        assert len(rs.trials_for_host("host2")) == 1
        assert rs.trials_for_host("host1")[0].host_name == "host1"

    def test_trials_for_host_preserves_first_seen_order(self) -> None:
        rs = RunState()
        for tid in ("test1", "test2", "test3"):
            rs.apply("run.trial_started", _started(test=tid))
        assert [t.test_id for t in rs.trials_for_host("host1")] == [
            "test1", "test2", "test3",
        ]

    def test_reordered_events_keep_first_seen_order(self) -> None:
        # A later finish on an earlier-started trial must not reshuffle rows
        # under the user's cursor.
        rs = RunState()
        rs.apply("run.trial_started", _started(test="test1"))
        rs.apply("run.trial_started", _started(test="test2"))
        rs.apply("run.trial_finished", {**_started(test="test1"), "verdict": "defended"})
        assert [t.test_id for t in rs.trials_for_host("host1")] == ["test1", "test2"]


class TestPayloadPassthrough:
    def test_full_raw_response_is_not_truncated(self) -> None:
        # The entire point of hermia-2ke3: nothing in the fold may truncate.
        raw = "x" * 5000
        rs = RunState()
        rs.apply("run.trial_finished", _finished(raw_response=raw))
        rec = rs.trial(*_KEY)
        assert rec is not None
        assert len(rec.raw_response) == 5000
        assert rec.raw_response == raw

    def test_all_payload_fields_round_trip(self) -> None:
        rs = RunState()
        rs.apply("run.trial_finished", _finished(
            "error",
            elapsed_sec=1.25,
            failure_reason="JSON_PARSE_ERROR",
            output_preview="trunc",
            raw_response="full response",
            raw_prompt="the prompt",
            raw_system="the system prompt",
            raw_thinking="the reasoning trace",
        ))
        rec = rs.trial(*_KEY)
        assert rec is not None
        assert rec.elapsed_sec == 1.25
        assert rec.failure_reason == "JSON_PARSE_ERROR"
        assert rec.output_preview == "trunc"
        assert rec.raw_response == "full response"
        assert rec.raw_prompt == "the prompt"
        assert rec.raw_system == "the system prompt"
        assert rec.raw_thinking == "the reasoning trace"

    def test_absent_fields_default_to_empty(self) -> None:
        rs = RunState()
        rs.apply("run.trial_finished", _finished("defended"))
        rec = rs.trial(*_KEY)
        assert rec is not None
        assert rec.elapsed_sec is None
        assert rec.failure_reason == ""
        assert rec.raw_response == ""
        assert rec.raw_thinking == ""


class TestPhase:
    def test_run_completed_is_terminal(self) -> None:
        rs = RunState()
        rs.apply("run.started", {})
        rs.apply("run.completed", {"n_completed": 3})
        assert rs.phase == "completed"
        assert rs.is_terminal is True

    def test_run_aborted_is_terminal_and_captures_error(self) -> None:
        rs = RunState()
        rs.apply("run.aborted", {"error": "no such test id"})
        assert rs.phase == "aborted"
        assert rs.error == "no such test id"
        assert rs.is_terminal is True

    def test_run_aborted_without_error_key_leaves_error_empty(self) -> None:
        rs = RunState()
        rs.apply("run.aborted", {"n_completed": 2})
        assert rs.phase == "aborted"
        assert rs.error == ""

    def test_run_started_is_running_and_not_terminal(self) -> None:
        rs = RunState()
        rs.apply("run.started", {"n_trials_total": 4})
        assert rs.phase == "running"
        assert rs.is_terminal is False

    def test_terminal_phase_does_not_alter_recorded_verdicts(self) -> None:
        rs = RunState()
        rs.apply("run.trial_finished", _finished("defended"))
        rs.apply("run.completed", {})
        rec = rs.trial(*_KEY)
        assert rec is not None
        assert rec.state == "defended"


class TestResetSemantics:
    def test_run_started_clears_a_previous_runs_trials(self) -> None:
        # Without this, a second run in the same TUI session hydrates screens
        # from the first run's rows.
        rs = RunState()
        rs.apply("run.trial_finished", _finished("defended"))
        rs.apply("run.completed", {})
        rs.apply("run.started", {"n_trials_total": 2})
        assert rs.trial(*_KEY) is None
        assert rs.trials_for_host("host1") == []
        assert rs.phase == "running"
        assert rs.is_terminal is False

    def test_run_started_clears_a_previous_runs_error(self) -> None:
        rs = RunState()
        rs.apply("run.aborted", {"error": "boom"})
        rs.apply("run.started", {})
        assert rs.error == ""

    def test_reset_clears_all_run_state(self) -> None:
        rs = RunState()
        rs.apply("run.trial_started", _started())
        rs.apply("run.aborted", {"error": "boom"})
        rs.reset()
        assert rs.phase == "idle"
        assert rs.error == ""
        assert rs.trial(*_KEY) is None


class TestUnknownTopics:
    def test_unknown_topic_leaves_state_untouched(self) -> None:
        rs = RunState()
        rs.apply("run.trial_finished", _finished("defended"))
        rs.apply("probe.host_finished", {"host_name": "host1", "verdict": "error"})
        rec = rs.trial(*_KEY)
        assert rec is not None
        assert rec.state == "defended"
        assert rs.phase == "idle"
        assert len(rs.trials_for_host("host1")) == 1

    def test_trial_chunk_topic_is_ignored(self) -> None:
        rs = RunState()
        rs.apply("run.trial_chunk", {**_started(), "chunk": "tok"})
        assert rs.trial(*_KEY) is None
