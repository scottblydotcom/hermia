"""Tests for FleetConfigScreen — top-level summary + drill rows."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.config import FleetConfigScreen
from hermia.tui.state import FleetConfig, Host, ModelChoice


class TestFleetConfigSummary:
    def test_renders_empty_config(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert "0 hosts" in screen.summary_text
                assert "0 tests" in screen.summary_text
                assert "0 trials" in screen.run_plan_text

        asyncio.run(_run())

    def test_summary_with_hosts_and_tests(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = FleetConfig(
                    name="smoke",
                    hosts=[Host(name="h1", url="http://h1", engine="ollama",
                                models=[ModelChoice(name="m1", selected=True),
                                        ModelChoice(name="m2", selected=True)])],
                    tests=["t1", "t2", "t3"],
                )
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert "1 host" in screen.summary_text
                assert "3 tests" in screen.summary_text
                # 2 selected models × 3 tests = 6 trials.
                assert "6 trials" in screen.run_plan_text

        asyncio.run(_run())

    def test_breadcrumb_includes_fleet_name(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert "smoke" in screen.breadcrumb_text

        asyncio.run(_run())

    def test_breadcrumb_shows_unsaved_when_dirty(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                screen.mark_dirty()
                await pilot.pause()
                assert "[unsaved changes]" in screen.breadcrumb_text

        asyncio.run(_run())

    def test_escape_pops_back_to_launch(self) -> None:
        async def _run() -> None:
            from hermia.tui.screens.launch import LaunchScreen
            async with HermiaApp().run_test() as pilot:
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, LaunchScreen)

        asyncio.run(_run())


class TestSave:
    def test_save_writes_fleet_file_when_name_set(self, tmp_path, monkeypatch) -> None:
        from hermia.tui.fleet_io import fleet_path
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                await pilot.press("s")
                await pilot.pause()
                assert fleet_path("smoke").exists()

        asyncio.run(_run())

    def test_save_clears_dirty_flag(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                screen.mark_dirty()
                await pilot.pause()
                assert screen.dirty is True
                await pilot.press("s")
                await pilot.pause()
                assert screen.dirty is False

        asyncio.run(_run())

    def test_save_with_no_name_opens_modal(self, tmp_path, monkeypatch) -> None:
        from hermia.tui.screens.modals import FleetNameModal
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                # No name set → save should push the FleetNameModal.
                pilot.app.config.name = ""
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                await pilot.press("s")
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetNameModal)

        asyncio.run(_run())


class TestFleetConfigScreenActionRun:
    def test_action_run_pushes_runner_screen(self, tmp_path, monkeypatch) -> None:
        from hermia.tui.screens.runner import RunnerScreen
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = FleetConfig(
                    name="run-smoke",
                    hosts=[
                        Host(
                            name="local",
                            url="http://localhost:11434",
                            engine="ollama",
                            models=[ModelChoice(name="qwen3:32b", selected=True)],
                        )
                    ],
                    tests=["t1"],
                    repeat=1,
                )
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                await pilot.press("r")
                await pilot.pause()
                assert isinstance(pilot.app.screen, RunnerScreen)

        asyncio.run(_run())


class TestDirtyPropagation:
    def test_test_toggle_marks_config_dirty(self) -> None:
        from hermia.tui.screens.tests import TestsScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config.name = "smoke"
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                config_screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                assert config_screen.dirty is False
                pilot.app.push_screen(TestsScreen())
                await pilot.pause()
                # Toggle the first test via space — should propagate to dirty.
                await pilot.press("space")
                await pilot.pause()
                assert config_screen.dirty is True

        asyncio.run(_run())

    def test_host_model_toggle_marks_config_dirty(self) -> None:
        from hermia.tui.screens.host_models import HostModelsScreen
        from hermia.tui.state import Host, ModelChoice

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = Host(
                    name="h1", url="http://h1", engine="ollama",
                    models=[ModelChoice(name="m1"), ModelChoice(name="m2")],
                )
                pilot.app.config.name = "smoke"
                pilot.app.config.hosts = [host]
                pilot.app.push_screen(FleetConfigScreen())
                await pilot.pause()
                config_screen: FleetConfigScreen = pilot.app.screen  # type: ignore[assignment]
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                await pilot.press("space")
                await pilot.pause()
                assert config_screen.dirty is True

        asyncio.run(_run())
