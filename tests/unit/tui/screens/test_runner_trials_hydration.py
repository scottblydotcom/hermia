"""Tests for L2 hydration/terminal state (hermia-mo4a) and L3 full response (hermia-2ke3).

The bugs both reproduce only under a specific ordering: events must land
*before* the screen mounts. A harness that pushes the screen and then publishes
does not exercise either defect — RunnerTrialsScreen subscribes in on_mount, so
it sees everything published after that point and looks correct.
"""
import asyncio

from textual.widgets import Static

from hermia.tui.app import HermiaApp
from hermia.tui.runner_backend import TuiRunner
from hermia.tui.screens.runner_detail import RunnerDetailScreen
from hermia.tui.screens.runner_trials import RunnerTrialsScreen, _TrialRow
from hermia.tui.state import FleetConfig, Host, ModelChoice


def _host_with_models() -> Host:
    return Host(
        name="node-a",
        url="http://e:11434",
        engine="ollama",
        models=[
            ModelChoice(name="qwen3:32b", selected=True),
            ModelChoice(name="qwen2.5:7b", selected=False),
        ],
    )


def _config_with_host(host: Host) -> FleetConfig:
    return FleetConfig(name="smoke", hosts=[host], tests=["t1", "t2"], repeat=1)


def _ev(test_id: str = "t1", host: str = "node-a", **extra: object) -> dict:
    ev: dict = {
        "host_name": host,
        "model_name": "qwen3:32b",
        "test_id": test_id,
        "repeat_idx": 1,
    }
    ev.update(extra)
    return ev


def _row_texts(screen: RunnerTrialsScreen) -> list[str]:
    """Rendered text of the L2 trial rows, in display order.

    Reads `.content` — on Textual 8.2.8 `Static.renderable` is None and a probe
    that reads it silently reports zero rows.
    """
    root = screen.query_one("#trials-root")
    return [
        str(c.content) for c in root.children
        if isinstance(c, Static) and str(getattr(c, "id", "")).startswith("trial-row-")
    ]


# ── Hydration: state that predates the screen (hermia-mo4a, part 1) ──────────


def test_trial_finished_before_mount_shows_its_verdict() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply("run.trial_started", _ev("t1"))
            pilot.app.run_state.apply(
                "run.trial_finished", _ev("t1", verdict="defended", elapsed_sec=0.4)
            )
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "defended"

    asyncio.run(_run())


def test_hydrated_verdict_reaches_the_rendered_row() -> None:
    # Guards a fix that hydrates the model but never re-renders the widgets.
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply(
                "run.trial_finished", _ev("t1", verdict="defended", elapsed_sec=1.5)
            )
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            rows = _row_texts(screen)
            assert len(rows) == 2
            assert "✓" in rows[0]
            assert "1.5s" in rows[0]

    asyncio.run(_run())


def test_trial_started_before_mount_shows_running() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply("run.trial_started", _ev("t1"))
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "running"

    asyncio.run(_run())


def test_trial_with_no_prior_events_stays_pending() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "pending"

    asyncio.run(_run())


def test_hydration_ignores_another_hosts_results() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply(
                "run.trial_finished",
                _ev("t1", host="other-host", verdict="defended"),
            )
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "pending"

    asyncio.run(_run())


def test_hydration_picks_this_host_when_both_reported() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply(
                "run.trial_finished", _ev("t1", verdict="defended")
            )
            pilot.app.run_state.apply(
                "run.trial_finished", _ev("t1", host="other-host", verdict="error")
            )
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "defended"

    asyncio.run(_run())


def test_hydration_is_partial_not_all_or_nothing() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply(
                "run.trial_finished", _ev("t1", verdict="defended")
            )
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "defended"
            assert screen.trial_state("qwen3:32b", "t2", 1) == "pending"

    asyncio.run(_run())


def test_screen_still_receives_live_events_after_hydrating() -> None:
    # A fix that hydrates but drops the subscription would pass every test above.
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply(
                "run.trial_finished", _ev("t1", verdict="defended")
            )
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()

            await pilot.app.bus.publish(
                "run.trial_finished", _ev("t2", verdict="defended", elapsed_sec=0.2)
            )
            await pilot.pause()

            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "defended"
            assert screen.trial_state("qwen3:32b", "t2", 1) == "defended"

    asyncio.run(_run())


# ── Terminal state (hermia-mo4a, part 2) ─────────────────────────────────────


def test_run_not_done_while_running() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.run_done is False
            assert screen.terminal_text == ""

    asyncio.run(_run())


def test_run_completed_on_the_bus_marks_the_screen_done() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()

            await pilot.app.bus.publish("run.completed", {"n_completed": 2})
            await pilot.pause()

            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.run_done is True
            assert "completed" in screen.terminal_text

    asyncio.run(_run())


def test_run_aborted_on_the_bus_marks_the_screen_done() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()

            await pilot.app.bus.publish("run.aborted", {"n_completed": 1})
            await pilot.pause()

            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.run_done is True
            assert "aborted" in screen.terminal_text

    asyncio.run(_run())


def test_run_already_terminal_before_mount_needs_no_bus_event() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply("run.completed", {})
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.run_done is True
            assert "completed" in screen.terminal_text

    asyncio.run(_run())


def test_terminal_run_stops_claiming_unreported_trials_are_pending() -> None:
    # "pending" asserts a result is still coming. After the run ends that is a
    # confident non-answer — the screen must say only what it knows.
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply("run.trial_started", _ev("t1"))
            pilot.app.run_state.apply("run.completed", {})
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "unreported"
            assert screen.trial_state("qwen3:32b", "t2", 1) == "unreported"

    asyncio.run(_run())


def test_terminal_run_preserves_reported_verdicts() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply(
                "run.trial_finished", _ev("t1", verdict="defended")
            )
            pilot.app.run_state.apply("run.completed", {})
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "defended"
            assert screen.trial_state("qwen3:32b", "t2", 1) == "unreported"

    asyncio.run(_run())


def test_terminal_bus_event_also_flips_pending_rows() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "pending"

            await pilot.app.bus.publish("run.aborted", {"n_completed": 0})
            await pilot.pause()

            assert screen.trial_state("qwen3:32b", "t1", 1) == "unreported"

    asyncio.run(_run())


def test_terminal_banner_count_survives_a_second_terminal_signal() -> None:
    # Hydrating a terminal run and THEN receiving the terminal bus event must
    # not make the banner claim every trial reported. Counting the rows flipped
    # by this call (zero the second time) instead of the rows currently
    # unreported produces exactly that false "17/17".
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply(
                "run.trial_finished", _ev("t1", verdict="defended")
            )
            pilot.app.run_state.apply("run.completed", {})
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert "1/2 reported" in screen.terminal_text

            await pilot.app.bus.publish("run.completed", {"n_completed": 1})
            await pilot.pause()

            assert "1/2 reported" in screen.terminal_text
            assert "1 never reported" in screen.terminal_text
            assert screen.trial_state("qwen3:32b", "t2", 1) == "unreported"

    asyncio.run(_run())


# ── Full response in the detail view (hermia-2ke3) ───────────────────────────


def test_detail_shows_the_entire_raw_response() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            row = _TrialRow(
                model_name="m", test_id="t1", repeat_idx=1,
                state="defended", raw_response="y" * 4000,
            )
            pilot.app.push_screen(RunnerDetailScreen(trial=row))
            await pilot.pause()
            screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
            assert len(screen.output_text) == 4000
            assert screen.output_text == "y" * 4000

    asyncio.run(_run())


def test_detail_prefers_raw_response_over_preview() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            row = _TrialRow(
                model_name="m", test_id="t1", repeat_idx=1, state="defended",
                raw_response="the full response", output_preview="the trunc",
            )
            pilot.app.push_screen(RunnerDetailScreen(trial=row))
            await pilot.pause()
            screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.output_text == "the full response"

    asyncio.run(_run())


def test_detail_falls_back_to_preview_when_no_raw_response() -> None:
    # Error and timeout rows never carry a raw_response.
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            row = _TrialRow(
                model_name="m", test_id="t1", repeat_idx=1, state="error",
                raw_response="", output_preview="TIMEOUT: no response in 90s",
            )
            pilot.app.push_screen(RunnerDetailScreen(trial=row))
            await pilot.pause()
            screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.output_text == "TIMEOUT: no response in 90s"

    asyncio.run(_run())


def test_detail_response_with_brackets_survives_rendering() -> None:
    # Model output is routinely JSON. Rich markup parsing silently DELETES
    # "[bold]" from a rendered line, so asserting on the property alone is not
    # enough — this reads the composited line back.
    raw = '{"tools": ["a", "b"], "note": "[bold] not markup"}'

    async def _run() -> None:
        async with HermiaApp().run_test(size=(120, 30)) as pilot:
            row = _TrialRow(
                model_name="m", test_id="t1", repeat_idx=1,
                state="defended", raw_response=raw,
            )
            pilot.app.push_screen(RunnerDetailScreen(trial=row))
            await pilot.pause()
            screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.output_text == raw
            rendered = screen.query_one("#detail-output", Static).render_line(0).text
            assert "[bold]" in rendered

    asyncio.run(_run())


def test_detail_hydrates_a_stale_row_from_run_state() -> None:
    # L3 can be reached carrying a row that predates the result (drill in, then
    # the trial lands). Without hydration it renders "in progress" forever.
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply("run.trial_finished", _ev(
                "t1", verdict="defended", elapsed_sec=2.0,
                raw_response="the real answer",
            ))
            row = _TrialRow(
                model_name="qwen3:32b", test_id="t1", repeat_idx=1,
                host_name="node-a", state="pending",
            )
            pilot.app.push_screen(RunnerDetailScreen(trial=row))
            await pilot.pause()
            screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.output_text == "the real answer"
            assert screen.is_awaiting_result is False

    asyncio.run(_run())


# ── End-to-end: the mid-run drill that produced the original report ──────────


def test_drilling_in_after_a_run_finishes_shows_every_verdict() -> None:
    """The reported failure, end to end: run first, drill in second.

    Uses the real TuiRunner with an injected run_test_fn — no network, no disk.
    """
    def _fake_run_test(model_name: str, test: dict, **kwargs: object) -> dict:
        return {
            "model": model_name,
            "test_id": test["id"],
            "failure_reason": "",
            "elapsed_sec": 0.01,
            "output_preview": "trunc",
            "raw_response": f"full answer for {test['id']}",
            "signals": {},
        }

    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            runner = TuiRunner(
                config=pilot.app.config,
                bus=pilot.app.bus,
                results_dir=None,
                run_test_fn=_fake_run_test,
                run_state=pilot.app.run_state,
                _tests_override=[{"id": "t1"}, {"id": "t2"}],
            )
            await runner.start()
            for _ in range(200):
                if not runner.is_running:
                    break
                await pilot.pause()
            assert runner.is_running is False

            # Only now does the user drill in — every event is already gone.
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]

            assert screen.trial_state("qwen3:32b", "t1", 1) == "defended"
            assert screen.trial_state("qwen3:32b", "t2", 1) == "defended"
            assert screen.run_done is True
            assert "completed" in screen.terminal_text

            # …and the full response is reachable from the detail view.
            screen.action_drill()
            await pilot.pause()
            detail: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
            assert detail.output_text == "full answer for t1"

    asyncio.run(_run())
