"""Tests for LaunchScreen — initial entries + cursor + key bindings."""
import asyncio

from hermia.tui.app import HermiaApp
from hermia.tui.screens.launch import LaunchScreen


class TestLaunchEntries:
    def test_three_entries_present(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                assert isinstance(pilot.app.screen, LaunchScreen)
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                labels = [e.label for e in screen.entries]
                assert labels == ["Load existing fleet", "New fleet", "Quick local run"]

        asyncio.run(_run())

    def test_cursor_starts_on_first_entry(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 0

        asyncio.run(_run())

    def test_arrow_down_moves_cursor(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("down")
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 1

        asyncio.run(_run())

    def test_arrow_up_clamps_at_top(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("up")
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 0

        asyncio.run(_run())

    def test_arrow_down_clamps_at_bottom(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                for _ in range(5):
                    await pilot.press("down")
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.cursor_index == 2  # 3 entries → max index 2

        asyncio.run(_run())

    def test_q_quits_app(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("q")
                await pilot.pause()
                # App is exiting; _exit flag flips True.
                assert pilot.app._exit is True

        asyncio.run(_run())


class TestLoadExisting:
    def test_selecting_load_shows_fleet_list(self, tmp_path, monkeypatch) -> None:
        from hermia.tui.fleet_io import save_fleet
        from hermia.tui.state import FleetConfig
        save_fleet(FleetConfig(name="alpha"), root=tmp_path)
        save_fleet(FleetConfig(name="beta"), root=tmp_path)
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("enter")  # selects Load
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                labels = [e.label for e in screen.entries]
                assert labels == ["alpha", "beta"]

        asyncio.run(_run())

    def test_selecting_a_loaded_fleet_populates_config(self, tmp_path, monkeypatch) -> None:
        from hermia.tui.fleet_io import save_fleet
        from hermia.tui.screens.config import FleetConfigScreen
        from hermia.tui.state import FleetConfig, Host, ModelChoice
        cfg = FleetConfig(
            name="alpha",
            hosts=[Host(name="h1", url="http://h1", engine="ollama",
                        models=[ModelChoice(name="qwen3:32b", selected=True)])],
            tests=["security-boundary"],
        )
        save_fleet(cfg, root=tmp_path)
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("enter")  # Load
                await pilot.pause()
                await pilot.press("enter")  # select alpha
                await pilot.pause()
                assert isinstance(pilot.app.screen, FleetConfigScreen)
                assert pilot.app.config.name == "alpha"
                assert pilot.app.config.tests == ["security-boundary"]
                assert pilot.app.config.hosts[0].name == "h1"

        asyncio.run(_run())

    def test_load_with_no_fleets_shows_empty_notice(self, tmp_path, monkeypatch) -> None:
        from textual.widgets import Static
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("enter")  # Load
                await pilot.pause()
                await pilot.pause()  # let _rerender mount() complete
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.entries == []
                notice = screen.query_one("#launch-empty-notice", Static)
                assert notice is not None

        asyncio.run(_run())

    def test_escape_from_load_returns_to_home(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("enter")  # Load
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                screen: LaunchScreen = pilot.app.screen  # type: ignore[assignment]
                assert screen.mode == "home"
                assert [e.label for e in screen.entries] == [
                    "Load existing fleet", "New fleet", "Quick local run",
                ]

        asyncio.run(_run())


class TestNewFleet:
    def test_new_fleet_resets_config_and_pushes_config_screen(self) -> None:
        from hermia.tui.screens.config import FleetConfigScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                # Mutate config first so we can prove New resets it.
                pilot.app.config.name = "stale"
                await pilot.press("down")  # cursor → New
                await pilot.press("enter")
                await pilot.pause()
                assert pilot.app.config.name == ""
                assert pilot.app.config.hosts == []
                assert isinstance(pilot.app.screen, FleetConfigScreen)

        asyncio.run(_run())


class TestQuickLocalRun:
    def test_quick_local_seeds_config_and_pushes_config_screen(self) -> None:
        from hermia.schemas import TEST_IDS
        from hermia.tui.screens.config import FleetConfigScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                await pilot.press("down")
                await pilot.press("down")  # cursor → Quick
                await pilot.press("enter")
                await pilot.pause()
                cfg = pilot.app.config
                assert cfg.name == "quick-local"
                assert len(cfg.hosts) == 1
                h = cfg.hosts[0]
                assert h.url == "http://localhost:11434"
                assert h.engine == "ollama"
                assert h.name == "local"
                assert cfg.tests == list(TEST_IDS)
                assert isinstance(pilot.app.screen, FleetConfigScreen)

        asyncio.run(_run())
