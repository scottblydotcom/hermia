"""HermiaApp — Textual App for the unified Fleet TUI.

Holds the shared FleetConfig as a mutable attribute. Picker screens read
and write directly to `app.config`. Plan 3 adds `app.bus = SessionBus()`
for runner ↔ screen communication.
"""
from __future__ import annotations

from textual.app import App

from hermia.tui.state import FleetConfig


class HermiaApp(App[None]):
    CSS_PATH = None  # widgets define their own DEFAULT_CSS

    def __init__(self) -> None:
        super().__init__()
        self.config: FleetConfig = FleetConfig(name="")

    def on_mount(self) -> None:
        # Import here to avoid a circular import — screens.launch imports HermiaApp.
        from hermia.tui.screens.launch import LaunchScreen
        self.push_screen(LaunchScreen())
