"""Modal dialogs used by picker screens.

FleetNameModal      — prompt for a fleet name when saving an unnamed fleet (Task 9).
AddHostModal        — add a new Host to the fleet (Task 10).
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label

from hermia.tui.state import Host


class FleetNameModal(ModalScreen[str | None]):
    """Prompt for a fleet name. Returns the entered name, or None on cancel."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    FleetNameModal {
        align: center middle;
    }
    FleetNameModal Vertical {
        width: 50;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Fleet name:")
            yield Input(placeholder="kwaainet-baseline", id="modal-fleet-name")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class AddHostModal(ModalScreen[Host | None]):
    """Add a new Host to the fleet. Returns the new Host or None on cancel."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    AddHostModal {
        align: center middle;
    }
    AddHostModal Vertical {
        width: 60;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Add host:")
            yield Input(placeholder="name (eric-5090)", id="addhost-name")
            yield Input(placeholder="url (http://eric:11434)", id="addhost-url")
            yield Input(
                placeholder="engine (ollama / openai-compat) — defaults to ollama",
                id="addhost-engine",
            )

    def on_mount(self) -> None:
        self.query_one("#addhost-name", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter on name → url; on url → engine; on engine → submit form.
        # Without this, Enter on the first two fields does nothing, which is
        # counter-intuitive.
        if event.input.id == "addhost-name":
            self.query_one("#addhost-url", Input).focus()
            return
        if event.input.id == "addhost-url":
            self.query_one("#addhost-engine", Input).focus()
            return
        if event.input.id != "addhost-engine":
            return
        name = self.query_one("#addhost-name", Input).value.strip()
        url = self.query_one("#addhost-url", Input).value.strip()
        engine = self.query_one("#addhost-engine", Input).value.strip() or "ollama"
        # If a required field is empty, refocus it instead of silently
        # ignoring submission (user otherwise wonders why nothing happened).
        if not name:
            self.query_one("#addhost-name", Input).focus()
            return
        if not url:
            self.query_one("#addhost-url", Input).focus()
            return
        self.dismiss(Host(name=name, url=url, engine=engine))

    def action_cancel(self) -> None:
        self.dismiss(None)
