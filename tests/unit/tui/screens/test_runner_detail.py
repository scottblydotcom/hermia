"""Tests for RunnerDetailScreen (L3 detail view)."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.runner_trials import RunnerTrialsScreen, _TrialRow


def _make_finished_trial(**kwargs) -> _TrialRow:
    defaults = dict(
        model_name="qwen3:32b",
        test_id="t1",
        repeat_idx=1,
        state="defended",
        elapsed_sec=0.4,
        failure_reason="",
        output_preview="All clear",
    )
    defaults.update(kwargs)
    return _TrialRow(**defaults)


class TestRunnerDetailScreenLayout:
    def test_breadcrumb_includes_model_and_test(self) -> None:
        from hermia.tui.screens.runner_detail import RunnerDetailScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                trial = _make_finished_trial()
                pilot.app.push_screen(RunnerDetailScreen(trial=trial))
                await pilot.pause()
                screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
                assert "qwen3:32b" in screen.breadcrumb_text
                assert "t1" in screen.breadcrumb_text

        asyncio.run(_run())

    def test_verdict_shown_in_summary(self) -> None:
        from hermia.tui.screens.runner_detail import RunnerDetailScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                trial = _make_finished_trial(state="defended", elapsed_sec=0.42)
                pilot.app.push_screen(RunnerDetailScreen(trial=trial))
                await pilot.pause()
                screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
                assert "defended" in screen.summary_text

        asyncio.run(_run())

    def test_error_verdict_shown_with_reason(self) -> None:
        from hermia.tui.screens.runner_detail import RunnerDetailScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                trial = _make_finished_trial(
                    state="error", failure_reason="TIMEOUT", output_preview=""
                )
                pilot.app.push_screen(RunnerDetailScreen(trial=trial))
                await pilot.pause()
                screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
                assert "error" in screen.summary_text
                assert "TIMEOUT" in screen.summary_text

        asyncio.run(_run())

    def test_pending_trial_shows_in_progress(self) -> None:
        from hermia.tui.screens.runner_detail import RunnerDetailScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                trial = _make_finished_trial(state="pending", elapsed_sec=None)
                pilot.app.push_screen(RunnerDetailScreen(trial=trial))
                await pilot.pause()
                screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.is_awaiting_result is True

        asyncio.run(_run())


class TestRunnerDetailScreenBus:
    def test_live_update_on_trial_finished(self) -> None:
        from hermia.tui.screens.runner_detail import RunnerDetailScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                trial = _make_finished_trial(state="running", elapsed_sec=None)
                pilot.app.push_screen(RunnerDetailScreen(trial=trial))
                await pilot.pause()

                screen: RunnerDetailScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.is_awaiting_result is True

                await pilot.app.bus.publish("run.trial_finished", {
                    "host_name": "eric-5090",
                    "model_name": "qwen3:32b",
                    "test_id": "t1",
                    "repeat_idx": 1,
                    "verdict": "error",
                    "elapsed_sec": 90.0,
                    "failure_reason": "TIMEOUT",
                    "output_preview": "",
                })
                await pilot.pause()

                assert screen.is_awaiting_result is False
                assert "error" in screen.summary_text

        asyncio.run(_run())


class TestRunnerDetailScreenNavigation:
    def test_escape_pops_to_trials_screen(self) -> None:
        from hermia.tui.screens.runner_detail import RunnerDetailScreen
        from hermia.tui.state import Host, ModelChoice

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.hosts = [
                    Host(name="h", url="u", engine="ollama",
                         models=[ModelChoice(name="m", selected=True)])
                ]
                pilot.app.config.tests = ["t1"]
                host = pilot.app.config.hosts[0]
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()
                trial = _make_finished_trial()
                pilot.app.push_screen(RunnerDetailScreen(trial=trial))
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, RunnerTrialsScreen)

        asyncio.run(_run())
