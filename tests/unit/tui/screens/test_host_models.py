"""Tests for HostModelsScreen — model picker for one host."""
import asyncio

from textual.widgets import Footer

from hermia.tui.app import HermiaApp
from hermia.tui.screens.host_models import HostModelsScreen
from hermia.tui.state import Host, ModelChoice


def _host_with_models() -> Host:
    return Host(
        name="h1",
        url="http://h1",
        engine="ollama",
        models=[ModelChoice(name="m1"), ModelChoice(name="m2")],
    )


class TestHostModelsScreen:
    def test_renders_host_models(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config.hosts = [host]
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                screen: HostModelsScreen = pilot.app.screen  # type: ignore[assignment]
                assert sorted(screen.visible_model_names) == ["m1", "m2"]

        asyncio.run(_run())

    def test_pre_selected_models_remain_selected_on_mount(self) -> None:
        from hermia.tui.widgets.drillable_list import DrillableList

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                host.models[0].selected = True  # pre-select m1
                pilot.app.config.hosts = [host]
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                dl = pilot.app.screen.query_one(DrillableList)
                assert dl.is_selected("m1")
                assert not dl.is_selected("m2")

        asyncio.run(_run())

    def test_space_toggles_selection(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config.hosts = [host]
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                await pilot.press("space")
                await pilot.pause()
                # First model is now selected on host.models.
                assert host.models[0].selected is True

        asyncio.run(_run())

    def test_select_all_then_none(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config.hosts = [host]
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                assert all(m.selected for m in host.models)
                await pilot.press("n")
                await pilot.pause()
                assert not any(m.selected for m in host.models)

        asyncio.run(_run())

    def test_escape_pops_back(self) -> None:
        from hermia.tui.screens.hosts import HostsScreen

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.config.hosts = [host]
                pilot.app.push_screen(HostsScreen())
                await pilot.pause()
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert isinstance(pilot.app.screen, HostsScreen)

        asyncio.run(_run())


class TestHostModelsFooter:
    def test_footer_present(self) -> None:
        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = Host(name="local", url="http://localhost:11434", engine="ollama")
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                screen = pilot.app.screen
                assert isinstance(screen, HostModelsScreen)
                assert len(screen.query(Footer)) == 1
        asyncio.run(_run())


class TestHostModelsEmptyState:
    """Empty model list needs an actionable nudge — silent empty list left
    first-time users staring at nothing (hermia-1pj)."""

    def test_empty_models_shows_pull_hint(self) -> None:
        from textual.widgets import Static

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = Host(name="local", url="http://localhost:11434", engine="ollama")
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                screen: HostModelsScreen = pilot.app.screen  # type: ignore[assignment]
                hint = screen.query_one("#host-models-empty-hint", Static)
                assert "ollama pull" in str(hint.render())

        asyncio.run(_run())

    def test_populated_models_no_hint(self) -> None:
        from textual.css.query import NoMatches

        async def _run() -> None:
            async with HermiaApp().run_test() as pilot:
                host = _host_with_models()
                pilot.app.push_screen(HostModelsScreen(host=host))
                await pilot.pause()
                screen: HostModelsScreen = pilot.app.screen  # type: ignore[assignment]
                try:
                    screen.query_one("#host-models-empty-hint")
                    raise AssertionError("hint should not appear when models present")
                except NoMatches:
                    pass

        asyncio.run(_run())
