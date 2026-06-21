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

    def __init__(self) -> None:
        super().__init__()
        self.config: FleetConfig = FleetConfig(name="")
        self.bus: SessionBus = SessionBus()

    def on_mount(self) -> None:
        # Import here to avoid a circular import — screens.launch imports HermiaApp.
        from hermia.tui.screens.launch import LaunchScreen
        self.push_screen(LaunchScreen())
