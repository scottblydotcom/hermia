import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from textual.app import App
from textual.widgets import Checkbox, Label, ProgressBar, Static

from hermia.preflight import ModelCheck, PreflightReport
from hermia.schemas import TEST_IDS
from hermia.screens import RunnerScreen, SelectionScreen

FAKE_MODELS = [
    {"name": "qwen2.5:7b", "size": 4 * 1024**3},
    {"name": "llama3:8b",  "size": 5 * 1024**3},
]

GPU_FOUND = {
    "found": True,
    "card": "RTX 4090",
    "vendor": "nvidia",
    "vram_total_gb": 24.0,
    "vram_used_gb": 0.5,
}

GPU_NOT_FOUND = {"found": False}


def _make_test_app(
    gpu_info: dict | None = None,
    model_list: list | None = None,
    fleet_mode: bool = False,
    repeat: int = 1,
) -> App:
    """Return an App instance that pushes SelectionScreen on mount."""

    class _TestApp(App):
        def __init__(self) -> None:
            super().__init__()
            self.model_list = model_list if model_list is not None else FAKE_MODELS
            self.gpu_info = gpu_info if gpu_info is not None else GPU_FOUND
            self.fleet_mode = fleet_mode
            self._repeat = repeat

        def on_mount(self) -> None:
            self.push_screen(SelectionScreen(repeat=self._repeat))

    return _TestApp()


def _fake_preflight_report(
    runnable: list[str] | None = None,
    skipped: list[str] | None = None,
) -> PreflightReport:
    models = []
    for name in (runnable if runnable is not None else ["qwen2.5:7b"]):
        models.append(ModelCheck(
            name=name, size_gb=4.0,
            fits_total_vram=True, fits_current_vram=True,
            fits_ram=True, skip=False,
        ))
    for name in (skipped or []):
        models.append(ModelCheck(
            name=name, size_gb=20.0,
            fits_total_vram=False, fits_current_vram=False,
            fits_ram=False, skip=True, reason="Too large",
        ))
    return PreflightReport(
        vram_total_gb=16.0, vram_used_gb=0.5, vram_available_gb=15.5,
        ram_total_gb=32.0, ram_available_gb=20.0,
        disk_free_gb=100.0, disk_ok=True,
        models=models,
    )


def _fake_run_test_result(model: str = "qwen2.5:7b") -> dict:
    return {
        "model": model,
        "test_id": "tool-calling-basic",
        "json_valid": True,
        "schema_compliant": True,
        "tokens_per_sec": 55.0,
        "peak_gpu_pct": 80.0,
        "peak_vram_used_gb": 3.5,
        "peak_cpu_pct": 10.0,
        "output_preview": "",
        "run_index": 1,
        "is_cold": True,
        "failure_reason": "",
    }


_FAKE_TESTS = [{"id": "tool-calling-basic", "prompt": "p", "system": "s"}]


class _RunnerDirectApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.model_list = [{"name": "qwen2.5:7b", "size": 4 * 1024**3}]
        self.gpu_info = GPU_FOUND
        self.fleet_mode = False

    def on_mount(self) -> None:
        self.push_screen(
            RunnerScreen(["qwen2.5:7b"], ["tool-calling-basic"], repeat=1)
        )


def test_selection_screen_model_checkboxes_rendered() -> None:
    async def _inner() -> None:
        async with _make_test_app().run_test() as pilot:
            await pilot.pause()
            # Check that checkboxes are present
            checkboxes = pilot.app.screen.query(Checkbox)
            model_checkboxes = [c for c in checkboxes if c.id and c.id.startswith("model_")]
            assert len(model_checkboxes) == 2
            assert model_checkboxes[0].id == "model_qwen2_5_7b"
            assert model_checkboxes[1].id == "model_llama3_8b"
    asyncio.run(_inner())


def test_selection_screen_test_checkboxes_rendered() -> None:
    async def _inner() -> None:
        async with _make_test_app().run_test() as pilot:
            await pilot.pause()
            # Check that checkboxes are present and all checked by default
            checkboxes = pilot.app.screen.query(Checkbox)
            test_checkboxes = [c for c in checkboxes if c.id and c.id.startswith("test_")]
            assert len(test_checkboxes) == len(TEST_IDS)
            for cb in test_checkboxes:
                assert cb.value is True
    asyncio.run(_inner())


def test_selection_screen_gpu_found_label() -> None:
    async def _inner() -> None:
        async with _make_test_app().run_test() as pilot:
            await pilot.pause()
            label = pilot.app.screen.query_one("#gpu-info", Label)
            assert "RTX 4090" in str(label.render())
            assert "24.0" in str(label.render())
    asyncio.run(_inner())


def test_selection_screen_gpu_not_found_label() -> None:
    async def _inner() -> None:
        async with _make_test_app(gpu_info=GPU_NOT_FOUND).run_test() as pilot:
            await pilot.pause()
            label = pilot.app.screen.query_one("#gpu-info", Label)
            assert "not detected" in str(label.render())
    asyncio.run(_inner())


def test_selection_screen_repeat_stored() -> None:
    async def _inner() -> None:
        async with _make_test_app(repeat=3).run_test() as pilot:
            await pilot.pause()
            assert pilot.app.screen.repeat == 3
    asyncio.run(_inner())


def test_select_all_models_button() -> None:
    async def _inner() -> None:
        async with _make_test_app().run_test() as pilot:
            await pilot.pause()
            # Uncheck first model
            first_model_cb = pilot.app.screen.query_one("#model_qwen2_5_7b", Checkbox)
            first_model_cb.value = False
            assert first_model_cb.value is False

            # Click select all
            await pilot.click("#all_models")
            await pilot.pause()

            # Both should be checked now
            model_cbs = pilot.app.screen.query(Checkbox)
            model_checkboxes = [c for c in model_cbs if c.id and c.id.startswith("model_")]
            assert all(cb.value for cb in model_checkboxes)
    asyncio.run(_inner())


def test_select_all_tests_button() -> None:
    async def _inner() -> None:
        async with _make_test_app().run_test() as pilot:
            await pilot.pause()
            # Uncheck first test
            first_test_cb = pilot.app.screen.query_one("#test_tool_calling_basic", Checkbox)
            first_test_cb.value = False
            assert first_test_cb.value is False

            # Click select all
            await pilot.click("#all_tests")
            await pilot.pause()

            # All should be checked now
            test_cbs = pilot.app.screen.query(Checkbox)
            test_checkboxes = [c for c in test_cbs if c.id and c.id.startswith("test_")]
            assert all(cb.value for cb in test_checkboxes)
    asyncio.run(_inner())


def test_launch_no_models_selected() -> None:
    async def _inner() -> None:
        async with _make_test_app().run_test() as pilot:
            await pilot.pause()
            # Uncheck all models
            model_cbs = pilot.app.screen.query(Checkbox)
            model_checkboxes = [c for c in model_cbs if c.id and c.id.startswith("model_")]
            for cb in model_checkboxes:
                cb.value = False

            # Click run
            await pilot.click("#run_btn")
            await pilot.pause()

            # Status should show error
            status_label = pilot.app.screen.query_one("#status", Label)
            assert str(status_label.render()) != ""
    asyncio.run(_inner())


def test_launch_no_tests_selected() -> None:
    async def _inner() -> None:
        async with _make_test_app().run_test() as pilot:
            await pilot.pause()
            # Uncheck all tests
            test_cbs = pilot.app.screen.query(Checkbox)
            test_checkboxes = [c for c in test_cbs if c.id and c.id.startswith("test_")]
            for cb in test_checkboxes:
                cb.value = False

            # Click run
            await pilot.click("#run_btn")
            await pilot.pause()

            # Status should show error
            status_label = pilot.app.screen.query_one("#status", Label)
            assert str(status_label.render()) != ""
    asyncio.run(_inner())


def test_launch_pushes_runner_screen() -> None:
    async def _inner() -> None:
        with patch("hermia.screens.RunnerScreen.run_evals"):
            async with _make_test_app().run_test() as pilot:
                await pilot.pause()
                await pilot.click("#run_btn")
                await pilot.pause()
                assert isinstance(pilot.app.screen, RunnerScreen)
    asyncio.run(_inner())


def test_runner_screen_widgets_present() -> None:
    async def _inner() -> None:
        with patch.object(RunnerScreen, "run_evals"):
            async with _RunnerDirectApp().run_test() as pilot:
                await pilot.pause()
                # Check widgets exist
                pilot.app.screen.query_one("#metrics-bar")
                pilot.app.screen.query_one("#log-content")
                pilot.app.screen.query_one("#summary-content")
                pilot.app.screen.query_one(ProgressBar)
    asyncio.run(_inner())


def test_runner_screen_progress_total() -> None:
    async def _inner() -> None:
        with patch.object(RunnerScreen, "run_evals"):
            async with _RunnerDirectApp().run_test() as pilot:
                await pilot.pause()
                progress = pilot.app.screen.query_one(ProgressBar)
                assert progress.total == 1  # 1 model * 1 test * 1 repeat
    asyncio.run(_inner())


def test_runner_screen_metrics_bar_no_data() -> None:
    async def _inner() -> None:
        with patch.object(RunnerScreen, "run_evals"):
            async with _RunnerDirectApp().run_test() as pilot:
                await pilot.pause()
                # Should not error even if no data
                bar = pilot.app.screen.query_one("#metrics-bar", Static)
                assert str(bar.render()) != ""
    asyncio.run(_inner())


def test_runner_screen_metrics_bar_with_data() -> None:
    async def _inner() -> None:
        fake_metrics = {
            "cpu_pct": 25.0, "ram_used_gb": 8.0, "ram_total_gb": 32.0,
            "gpu_pct": 60.0, "vram_used_gb": 3.0, "vram_total_gb": 16.0,
        }
        with patch.object(RunnerScreen, "run_evals"):
            async with _RunnerDirectApp().run_test() as pilot:
                await pilot.pause()
                # Access the screen and override the sampler's latest property
                screen = pilot.app.screen
                assert isinstance(screen, RunnerScreen)
                screen._live_sampler = MagicMock()
                screen._live_sampler.latest = fake_metrics
                screen._refresh_metrics()
                await pilot.pause()
                bar_text = pilot.app.screen.query_one("#metrics-bar").render()
                assert "CPU" in str(bar_text)
    asyncio.run(_inner())


def test_runner_screen_go_back() -> None:
    async def _inner() -> None:
        class _TestBackApp(App):
            def __init__(self) -> None:
                super().__init__()
                self.model_list = FAKE_MODELS
                self.gpu_info = GPU_FOUND
                self.fleet_mode = False

            def on_mount(self) -> None:
                self.push_screen(SelectionScreen(repeat=1))
                self.push_screen(RunnerScreen(["qwen2.5:7b"], ["tool-calling-basic"], repeat=1))

        with patch.object(RunnerScreen, "run_evals"):
            async with _TestBackApp().run_test() as pilot:
                await pilot.pause()
                # Press 'b' to go back
                await pilot.press("b")
                await pilot.pause()
                assert isinstance(pilot.app.screen, SelectionScreen)
    asyncio.run(_inner())


def test_run_evals_happy_path(tmp_path: Path) -> None:
    run_paths = (tmp_path / "a.jsonl", tmp_path / "a.csv")

    async def _inner() -> None:
        with (
            patch("hermia.screens.run_preflight", return_value=_fake_preflight_report()),
            patch("hermia.screens.open_run", return_value=run_paths),
            patch("hermia.screens.load_tests", return_value=_FAKE_TESTS),
            patch("hermia.screens.get_model_size_gb", return_value=4.0),
            patch("hermia.screens.unload_model"),
            patch("hermia.screens.prewarm_timed", return_value=(1.0, 1.0, 2.0)),
            patch("hermia.screens.run_test", return_value=_fake_run_test_result()),
            patch("hermia.screens.append_result"),
            patch("hermia.screens.patch_results"),
            patch("hermia.screens.time.sleep"),
        ):
            app2 = _RunnerDirectApp()
            async with app2.run_test(size=(120, 40)) as pilot:
                # Wait for the worker to complete (poll summary content)
                summary = ""
                for _ in range(30):
                    await pilot.pause(delay=0.1)
                    summary = str(pilot.app.screen.query_one("#summary-content").render())
                    if "EVAL SUMMARY" in summary:
                        break

            assert "EVAL SUMMARY" in summary
            assert "qwen2.5:7b" in summary
    asyncio.run(_inner())


def test_run_evals_no_runnable_models(tmp_path: Path) -> None:
    run_paths = (tmp_path / "a.jsonl", tmp_path / "a.csv")

    async def _inner() -> None:
        with (
            patch("hermia.screens.run_preflight", return_value=_fake_preflight_report(runnable=[])),
            patch("hermia.screens.open_run", return_value=run_paths),
            patch("hermia.screens.load_tests", return_value=_FAKE_TESTS),
            patch("hermia.screens.get_model_size_gb", return_value=4.0),
            patch("hermia.screens.unload_model"),
            patch("hermia.screens.prewarm_timed", return_value=(1.0, 1.0, 2.0)),
            patch("hermia.screens.run_test", return_value=_fake_run_test_result()),
            patch("hermia.screens.append_result"),
            patch("hermia.screens.patch_results"),
            patch("hermia.screens.time.sleep"),
        ):
            app2 = _RunnerDirectApp()
            async with app2.run_test(size=(120, 40)) as pilot:
                # Wait for the worker to complete
                log_content = ""
                for _ in range(30):
                    await pilot.pause(delay=0.1)
                    log_content = str(pilot.app.screen.query_one("#log-content").render())
                    if "No models can run" in log_content:
                        break

            assert "No models can run" in log_content
    asyncio.run(_inner())


def test_run_evals_skipped_model_logged(tmp_path: Path) -> None:
    run_paths = (tmp_path / "a.jsonl", tmp_path / "a.csv")

    async def _inner() -> None:
        with (
            patch(
                "hermia.screens.run_preflight",
                return_value=_fake_preflight_report(
                    runnable=["qwen2.5:7b"], skipped=["llama3:8b"]
                ),
            ),
            patch("hermia.screens.open_run", return_value=run_paths),
            patch("hermia.screens.load_tests", return_value=_FAKE_TESTS),
            patch("hermia.screens.get_model_size_gb", return_value=4.0),
            patch("hermia.screens.unload_model"),
            patch("hermia.screens.prewarm_timed", return_value=(1.0, 1.0, 2.0)),
            patch("hermia.screens.run_test", return_value=_fake_run_test_result()),
            patch("hermia.screens.append_result"),
            patch("hermia.screens.patch_results"),
            patch("hermia.screens.time.sleep"),
        ):
            app2 = _RunnerDirectApp()
            async with app2.run_test(size=(120, 40)) as pilot:
                # Wait for the worker to complete
                log_content = ""
                for _ in range(30):
                    await pilot.pause(delay=0.1)
                    log_content = str(pilot.app.screen.query_one("#log-content").render())
                    if "Skipping" in log_content:
                        break

            assert "Skipping" in log_content
    asyncio.run(_inner())


# ── mode badge (hermia-3lu) ───────────────────────────────────────────────────

def test_selection_screen_local_badge() -> None:
    async def _inner() -> None:
        async with _make_test_app(fleet_mode=False).run_test() as pilot:
            await pilot.pause()
            assert pilot.app.sub_title == "LOCAL"
    asyncio.run(_inner())


def test_selection_screen_fleet_badge() -> None:
    async def _inner() -> None:
        os.environ["HERMIA_HOST"] = "http://192.168.25.50:11434"
        _rv = ("http://192.168.25.50:11434", "m3pro")
        with patch("hermia.screens._resolve_fleet_host", return_value=_rv):
            async with _make_test_app(fleet_mode=True).run_test() as pilot:
                await pilot.pause()
                assert "FLEET" in pilot.app.sub_title
                assert "192.168.25.50" in pilot.app.sub_title
                assert "m3pro" in pilot.app.sub_title
    asyncio.run(_inner())


def test_selection_screen_fleet_badge_no_dns() -> None:
    async def _inner() -> None:
        os.environ["HERMIA_HOST"] = "http://192.168.25.50:11434"
        _rv = ("http://192.168.25.50:11434", None)
        with patch("hermia.screens._resolve_fleet_host", return_value=_rv):
            async with _make_test_app(fleet_mode=True).run_test() as pilot:
                await pilot.pause()
                assert "FLEET" in pilot.app.sub_title
                assert "→" not in pilot.app.sub_title
    asyncio.run(_inner())


def test_runner_screen_fleet_metrics_bar_suppressed() -> None:
    class _FleetRunnerApp(App):
        def __init__(self) -> None:
            super().__init__()
            self.model_list = [{"name": "qwen2.5:7b", "size": 4 * 1024**3}]
            self.gpu_info = GPU_FOUND
            self.fleet_mode = True

        def on_mount(self) -> None:
            self.push_screen(RunnerScreen(["qwen2.5:7b"], ["tool-calling-basic"], repeat=1))

    async def _inner() -> None:
        os.environ["HERMIA_HOST"] = "http://192.168.25.50:11434"
        _rv = ("http://192.168.25.50:11434", None)
        with (
            patch.object(RunnerScreen, "run_evals"),
            patch("hermia.screens._resolve_fleet_host", return_value=_rv),
        ):
            async with _FleetRunnerApp().run_test() as pilot:
                await pilot.pause()
                screen = pilot.app.screen
                assert isinstance(screen, RunnerScreen)
                screen._refresh_metrics()
                await pilot.pause()
                bar = str(pilot.app.screen.query_one("#metrics-bar").render())
                assert "FLEET" in bar
                assert "suppressed" in bar
    asyncio.run(_inner())


def test_runner_screen_fleet_subtitle() -> None:
    class _FleetRunnerApp(App):
        def __init__(self) -> None:
            super().__init__()
            self.model_list = [{"name": "qwen2.5:7b", "size": 4 * 1024**3}]
            self.gpu_info = GPU_FOUND
            self.fleet_mode = True

        def on_mount(self) -> None:
            self.push_screen(RunnerScreen(["qwen2.5:7b"], ["tool-calling-basic"], repeat=1))

    async def _inner() -> None:
        os.environ["HERMIA_HOST"] = "http://192.168.25.50:11434"
        _rv = ("http://192.168.25.50:11434", "m3pro")
        with (
            patch.object(RunnerScreen, "run_evals"),
            patch("hermia.screens._resolve_fleet_host", return_value=_rv),
        ):
            async with _FleetRunnerApp().run_test() as pilot:
                await pilot.pause()
                assert "FLEET" in pilot.app.sub_title
                assert "m3pro" in pilot.app.sub_title
    asyncio.run(_inner())
