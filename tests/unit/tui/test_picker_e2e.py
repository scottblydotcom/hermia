"""End-to-end picker smoke — drives Launch ▸ Config ▸ drills via Pilot.

Three flows: Quick local run, Load existing fleet, New fleet + save.
"""
import asyncio

from hermia.schemas import TEST_IDS
from hermia.tui.app import HermiaApp
from hermia.tui.fleet_io import fleet_path, save_fleet
from hermia.tui.screens.config import FleetConfigScreen
from hermia.tui.state import FleetConfig, Host, ModelChoice


class TestRunnerE2E:
    def test_r_key_from_config_pushes_runner_screen(self, tmp_path, monkeypatch) -> None:
        from hermia.tui.runner_backend import TuiRunner  # noqa: F401
        from hermia.tui.screens.runner import RunnerScreen
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                pilot.app.config = FleetConfig(
                    name="e2e-smoke",
                    hosts=[
                        Host(name="local", url="http://localhost:11434", engine="ollama",
                             models=[ModelChoice(name="qwen3:32b", selected=True)])
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

    def test_runner_screen_receives_events_from_tui_runner(self) -> None:
        from hermia.tui.runner_backend import TuiRunner
        from hermia.tui.screens.runner import RunnerScreen

        def _fake_run_test(model_name, test, *, host, engine, auth_env):
            return {
                "model": model_name,
                "test_id": test["id"],
                "failure_reason": "",
                "elapsed_sec": 0.1,
                "output_preview": "ok",
                "signals": {},
            }

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                cfg = FleetConfig(
                    name="e2e-smoke",
                    hosts=[
                        Host(name="local", url="http://localhost:11434", engine="ollama",
                             models=[ModelChoice(name="qwen3:32b", selected=True)])
                    ],
                    tests=["t1"],
                    repeat=1,
                )
                pilot.app.config = cfg
                runner = TuiRunner(
                    config=cfg,
                    bus=pilot.app.bus,
                    results_dir=None,
                    run_test_fn=_fake_run_test,
                    _tests_override=[{"id": "t1"}],
                )
                pilot.app.push_screen(RunnerScreen(runner=runner))
                await pilot.pause()
                # Wait long enough for the runner to complete (fake fn is fast).
                for _ in range(20):
                    await pilot.pause()
                screen: RunnerScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.run_done is True
                assert screen.host_counts("local")["defended"] == 1

        asyncio.run(_run())


class TestPickerE2E:
    def test_quick_local_flow_ends_in_config_screen_with_pre_populated_config(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                # Launch → Quick local run (first entry).
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetConfigScreen)
                cfg = pilot.app.config
                assert cfg.name == "quick-local"
                assert cfg.hosts[0].url == "http://localhost:11434"
                assert cfg.tests == list(TEST_IDS)

        asyncio.run(_run())

    def test_load_existing_flow_into_config(self, tmp_path, monkeypatch) -> None:
        save_fleet(
            FleetConfig(
                name="loaded",
                hosts=[Host(name="h", url="http://h", engine="ollama",
                            models=[ModelChoice(name="m", selected=True)])],
                tests=["security-boundary"],
            ),
            root=tmp_path,
        )
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                # Launch → Load existing (third entry) → enter on the only fleet.
                await pilot.press("down", "down", "enter")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetConfigScreen)
                assert pilot.app.config.name == "loaded"
                assert pilot.app.config.tests == ["security-boundary"]

        asyncio.run(_run())

    def test_save_via_s_writes_yaml(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                # Launch → New fleet (second entry).
                await pilot.press("down")
                await pilot.press("enter")
                await pilot.pause()
                # Set a name programmatically (the FleetNameModal flow is
                # exercised in test_config.TestSave.test_save_with_no_name_opens_modal).
                pilot.app.config.name = "smoke"
                await pilot.press("s")
                await pilot.pause()
                assert fleet_path("smoke").exists()

        asyncio.run(_run())
