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


def test_bus_queues_are_registered_before_the_hydrate_snapshot() -> None:
    """The ordering invariant that closes the last event-loss window.

    bus.subscribe() is synchronous and registers the queue immediately, but the
    coroutine that calls it is not scheduled until the loop next runs. If the
    screen subscribes inside its listener tasks, an event published after the
    hydrate snapshot but before those tasks first run is missed by BOTH — the
    same "pending forever" defect hydration was added to fix. Registering first
    can only duplicate an event, and every apply is idempotent.
    """
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            order: list[str] = []
            real_subscribe = pilot.app.bus.subscribe
            real_trial = pilot.app.run_state.trial

            def spy_subscribe(topic: str, **kw: object) -> object:
                order.append(f"subscribe:{topic}")
                return real_subscribe(topic, **kw)  # type: ignore[arg-type]

            def spy_trial(*a: object, **kw: object) -> object:
                order.append("hydrate")
                return real_trial(*a, **kw)  # type: ignore[arg-type]

            pilot.app.bus.subscribe = spy_subscribe  # type: ignore[method-assign]
            pilot.app.run_state.trial = spy_trial  # type: ignore[method-assign]

            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()

            assert "hydrate" in order, "screen never hydrated"
            first_hydrate = order.index("hydrate")
            registered = [o for o in order[:first_hydrate] if o.startswith("subscribe:")]
            assert "subscribe:run.trial_finished" in registered
            assert "subscribe:run.trial_started" in registered
            assert "subscribe:run.completed" in registered
            assert "subscribe:run.aborted" in registered

    asyncio.run(_run())


def test_empty_verdict_renders_the_same_live_as_hydrated() -> None:
    # RunState folds `verdict or "error"`; the live listener used
    # dict.get(k, "error"), which returns "" when the key is present but empty
    # — rendering the "?" icon live and "✗" after a remount.
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()

            await pilot.app.bus.publish("run.trial_finished", _ev("t1", verdict=""))
            await pilot.pause()

            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "error"
            assert "?" not in _row_texts(screen)[0]

    asyncio.run(_run())


def test_non_float_elapsed_sec_does_not_crash_the_render() -> None:
    # RunState coerced elapsed_sec; the live listener assigned it raw, so a
    # string reached an f-string ":.1f" and raised TypeError mid-render.
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()

            await pilot.app.bus.publish(
                "run.trial_finished", _ev("t1", verdict="defended", elapsed_sec="1.5")
            )
            await pilot.pause()

            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.trial_state("qwen3:32b", "t1", 1) == "defended"
            assert "1.5s" in _row_texts(screen)[0]

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


def test_detail_stops_claiming_in_progress_when_the_run_ends() -> None:
    """L3 must not contradict L2.

    The detail screen subscribed only to run.trial_finished. A run that ends
    without ever reporting this trial (abort, host failure) left L3 asserting
    "Trial in progress…" indefinitely while L2 showed the same trial as
    unreported.
    """
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            pilot.app.run_state.apply("run.started", {})
            row = _TrialRow(
                model_name="qwen3:32b", test_id="t1", repeat_idx=1,
                host_name="node-a", state="running",
            )
            pilot.app.push_screen(RunnerDetailScreen(trial=row))
            await pilot.pause()
            screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.is_awaiting_result is True

            await pilot.app.bus.publish("run.aborted", {"n_completed": 0})
            await pilot.pause()

            assert screen.is_awaiting_result is False
            assert "in progress" not in screen.summary_text
            assert "unreported" in screen.summary_text

    asyncio.run(_run())


def test_detail_mounted_after_a_terminal_run_is_not_in_progress() -> None:
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply("run.aborted", {"error": "aborted by user"})
            row = _TrialRow(
                model_name="qwen3:32b", test_id="t1", repeat_idx=1,
                host_name="node-a", state="pending",
            )
            pilot.app.push_screen(RunnerDetailScreen(trial=row))
            await pilot.pause()
            screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
            assert screen.is_awaiting_result is False
            assert "in progress" not in screen.summary_text

    asyncio.run(_run())


def test_hydrated_abort_reason_survives_the_matching_bus_event() -> None:
    # The bus's run.aborted payload need not carry "error"; recomputing the
    # banner from it must not erase the reason hydration already knew.
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            host = _host_with_models()
            pilot.app.config = _config_with_host(host)
            pilot.app.run_state.apply("run.started", {})
            pilot.app.run_state.apply("run.aborted", {"error": "no such test id"})
            pilot.app.push_screen(RunnerTrialsScreen(host=host))
            await pilot.pause()
            screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
            assert "no such test id" in screen.terminal_text

            await pilot.app.bus.publish("run.aborted", {"n_completed": 0})
            await pilot.pause()

            assert "no such test id" in screen.terminal_text

    asyncio.run(_run())


def test_detail_screen_leaves_no_bus_subscriptions_behind() -> None:
    """Opening a settled trial must not leak its queues.

    SessionBus.subscribe() registers a queue synchronously, but the
    registration is only undone by the finally in SessionBus._consume — which
    needs the generator started and then closed. A subscription with no
    consuming task therefore leaks for the life of the app, and publish() keeps
    filling it with full raw_response payloads.
    """
    async def _run() -> None:
        async with HermiaApp().run_test() as pilot:
            bus = pilot.app.bus
            for i in range(5):
                row = _TrialRow(
                    model_name="m", test_id=f"t{i}", repeat_idx=1,
                    state="defended", raw_response="answer",
                )
                pilot.app.push_screen(RunnerDetailScreen(trial=row))
                await pilot.pause()
                pilot.app.pop_screen()
                await pilot.pause()
            await pilot.pause()

            leaked = {t: len(q) for t, q in bus._subscribers.items() if q}
            assert leaked == {}, f"leaked bus subscriptions: {leaked}"

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
