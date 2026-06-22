"""Tests for RunnerScreen (L1 aggregate view)."""
import asyncio

from textual.widgets import Footer

from hermia.tui.app import HermiaApp
from hermia.tui.screens.runner import RunnerScreen
from hermia.tui.state import FleetConfig, Host, ModelChoice


def _two_host_config() -> FleetConfig:
    return FleetConfig(
        name="smoke",
        hosts=[
            Host(name="eric-5090", url="http://e:11434", engine="ollama",
                 models=[ModelChoice(name="qwen3:32b", selected=True)]),
            Host(name="marcus", url="http://m:4000", engine="openai-compat",
                 models=[ModelChoice(name="qwen2.5:7b", selected=True)]),
        ],
        tests=["t1"],
        repeat=1,
    )


class TestRunnerScreenLayout:
    def test_breadcrumb_contains_runner(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()
                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                assert "runner" in screen.breadcrumb_text

        asyncio.run(_run())

    def test_host_rows_rendered_for_each_host(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()
                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                assert "eric-5090" in screen.row_text(0)
                assert "marcus" in screen.row_text(1)

        asyncio.run(_run())

    def test_initial_counts_are_zero(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()
                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                counts = screen.host_counts("eric-5090")
                assert counts["defended"] == 0
                assert counts["error"] == 0

        asyncio.run(_run())


class TestRunnerScreenBusSubscription:
    def test_trial_finished_increments_defended_count(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()

                await pilot.app.bus.publish("run.trial_finished", {
                    "host_name": "eric-5090",
                    "model_name": "qwen3:32b",
                    "test_id": "t1",
                    "repeat_idx": 1,
                    "verdict": "defended",
                    "elapsed_sec": 0.4,
                    "failure_reason": "",
                    "output_preview": "ok",
                })
                await pilot.pause()

                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.host_counts("eric-5090")["defended"] == 1

        asyncio.run(_run())

    def test_trial_finished_error_increments_error_count(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()

                await pilot.app.bus.publish("run.trial_finished", {
                    "host_name": "marcus",
                    "model_name": "qwen2.5:7b",
                    "test_id": "t1",
                    "repeat_idx": 1,
                    "verdict": "error",
                    "elapsed_sec": 90.0,
                    "failure_reason": "TIMEOUT",
                    "output_preview": "",
                })
                await pilot.pause()

                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.host_counts("marcus")["error"] == 1

        asyncio.run(_run())

    def test_run_completed_marks_run_done(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()

                await pilot.app.bus.publish("run.completed", {
                    "n_trials_total": 2,
                    "n_completed": 2,
                })
                await pilot.pause()

                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.run_done is True

        asyncio.run(_run())

    def test_run_aborted_marks_run_done(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()

                await pilot.app.bus.publish("run.aborted", {"n_completed": 1})
                await pilot.pause()

                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.run_done is True

        asyncio.run(_run())


class TestRunnerScreenNavigation:
    def test_cursor_moves_down_and_up(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()
                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_idx == 0
                await pilot.press("down")
                await pilot.pause()
                assert screen.cursor_idx == 1
                await pilot.press("up")
                await pilot.pause()
                assert screen.cursor_idx == 0

        asyncio.run(_run())

    def test_enter_drills_to_runner_trials_screen(self) -> None:
        from hermia.tui.screens.runner_trials import RunnerTrialsScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(pilot.app.screen, RunnerTrialsScreen)

        asyncio.run(_run())

    def test_escape_blocked_while_running(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()
                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.run_done is False
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, RunnerScreen)

        asyncio.run(_run())

    def test_escape_pops_when_run_done(self) -> None:
        from hermia.tui.screens.config import FleetConfigScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = _two_host_config()
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()

                await pilot.app.bus.publish("run.completed", {
                    "n_trials_total": 2, "n_completed": 2
                })
                await pilot.pause()

                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetConfigScreen)

        asyncio.run(_run())


class TestRunnerFooter:
    def test_footer_present(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()
                screen = pilot.app.screen
                assert isinstance(screen, RunnerScreen)
                assert len(screen.query(Footer)) == 1

        asyncio.run(_run())
