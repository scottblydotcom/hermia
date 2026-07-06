"""HermiaApp — Textual App for the unified Fleet TUI.

Holds the shared FleetConfig as a mutable attribute. Picker screens read
and write directly to `app.config`. `app.bus` is the shared SessionBus for
runner ↔ screen communication (probe topics and run topics share one bus;
they use distinct topic prefixes and screens only subscribe to their own).
"""
from __future__ import annotations

from textual.app import App

from hermia.tui.bus import SessionBus
from hermia.tui.state import FleetConfig


class HermiaApp(App[None]):
    CSS_PATH = None  # widgets define their own DEFAULT_CSS

    def __init__(self, startup_warnings: list[str] | None = None) -> None:
        super().__init__()
        self.config: FleetConfig = FleetConfig(name="")
        self.bus: SessionBus = SessionBus()
        # Engine-security warnings collected before the TUI took over the
        # screen. Textual switches to the alternate screen buffer on mount,
        # so anything written to stderr before HermiaApp().run() is not
        # reliably visible to the user; surface them here as toast
        # notifications on mount instead.
        self._startup_warnings: list[str] = list(startup_warnings or [])

    def on_mount(self) -> None:
        # Import here to avoid a circular import — screens.launch imports HermiaApp.
        from hermia.tui.screens.launch import LaunchScreen
        self.push_screen(LaunchScreen())
        for warning in self._startup_warnings:
            self.notify(warning, severity="warning", timeout=15)

    def on_unmount(self) -> None:
        self.bus.close()
