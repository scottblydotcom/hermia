"""Tests for RunnerTrialsScreen (L2 trial table)."""
import asyncio

from textual.widgets import Footer

from hermia.tui.app import HermiaApp
from hermia.tui.screens.runner import RunnerScreen
from hermia.tui.screens.runner_trials import RunnerTrialsScreen
from hermia.tui.state import FleetConfig, Host, ModelChoice


def _host_with_models() -> Host:
    return Host(
        name="eric-5090",
        url="http://e:11434",
        engine="ollama",
        models=[
            ModelChoice(name="qwen3:32b", selected=True),
            ModelChoice(name="qwen2.5:7b", selected=False),  # not selected — no row
        ],
    )


def _config_with_host(host: Host) -> FleetConfig:
    return FleetConfig(name="smoke", hosts=[host], tests=["t1", "t2"], repeat=1)


class TestRunnerTrialsScreenLayout:
    def test_breadcrumb_includes_host_name(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config = _config_with_host(host)
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()
                screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
                assert "eric-5090" in screen.breadcrumb_text

        asyncio.run(_run())

    def test_rows_only_for_selected_models(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config = _config_with_host(host)
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()
                screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
                # 1 selected model × 2 tests × 1 repeat = 2 rows
                assert screen.n_trial_rows == 2

        asyncio.run(_run())

    def test_initial_state_is_pending(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config = _config_with_host(host)
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()
                screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
                assert (
                    screen.trial_state(model_name="qwen3:32b", test_id="t1", repeat_idx=1)
                    == "pending"
                )

        asyncio.run(_run())


class TestRunnerTrialsScreenBus:
    def test_trial_started_flips_to_running(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config = _config_with_host(host)
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()

                await pilot.app.bus.publish("run.trial_started", {
                    "host_name": "eric-5090",
                    "model_name": "qwen3:32b",
                    "test_id": "t1",
                    "repeat_idx": 1,
                })
                await pilot.pause()

                screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.trial_state("qwen3:32b", "t1", 1) == "running"

        asyncio.run(_run())

    def test_trial_finished_sets_verdict(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config = _config_with_host(host)
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
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

                screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.trial_state("qwen3:32b", "t1", 1) == "defended"

        asyncio.run(_run())

    def test_events_for_other_host_ignored(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config = _config_with_host(host)
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()

                await pilot.app.bus.publish("run.trial_finished", {
                    "host_name": "other-host",
                    "model_name": "qwen3:32b",
                    "test_id": "t1",
                    "repeat_idx": 1,
                    "verdict": "defended",
                    "elapsed_sec": 0.1,
                    "failure_reason": "",
                    "output_preview": "",
                })
                await pilot.pause()

                screen: RunnerTrialsScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.trial_state("qwen3:32b", "t1", 1) == "pending"

        asyncio.run(_run())


class TestRunnerTrialsScreenNavigation:
    def test_escape_pops_to_runner_screen(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config = _config_with_host(host)
                pilot.app.push_screen(RunnerScreen())
                await pilot.pause()
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, RunnerScreen)

        asyncio.run(_run())

    def test_enter_drills_to_runner_detail(self) -> None:
        from hermia.tui.screens.runner_detail import RunnerDetailScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config = _config_with_host(host)
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(pilot.app.screen, RunnerDetailScreen)

        asyncio.run(_run())


class TestRunnerTrialsFooter:
    def test_footer_present(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.push_screen(RunnerTrialsScreen(host=host))
                await pilot.pause()
                screen = pilot.app.screen
                assert isinstance(screen, RunnerTrialsScreen)
                assert len(screen.query(Footer)) == 1

        asyncio.run(_run())
