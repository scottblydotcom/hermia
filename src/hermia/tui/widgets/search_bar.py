"""SearchBar — live-filter input docked at the bottom of a drill screen.

vim/k9s/lazygit convention: the parent screen binds `/` to call `bar.open()`.
An input opens at the bottom, type a substring, the parent list filters live
as you type. Press `escape` (also bound on the parent) to call `bar.close()`,
which clears the query and hides the bar.

Emits SearchBar.QueryChanged messages — the parent screen wires them into
its list's filter state.

Design rationale: bindings live on the *screen* per spec §5 universal
contract, not on the widget. A hidden widget can't receive key events in
Textual, so binding `/` on SearchBar would never fire.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.widgets import Input


class SearchBar(Container):
    """Live-filter input. open() / close() are driven by the parent screen."""

    DEFAULT_CSS = """
    SearchBar {
        height: 1;
        dock: bottom;
        display: none;
    }
    SearchBar Input {
        border: none;
        background: $surface;
    }
    """

    class QueryChanged(Message):
        def __init__(self, query: str) -> None:
            self.query = query
            super().__init__()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="/ search…")

    def open(self) -> None:
        """Make the bar visible and focus the input.

        Focus and value-clear are deferred via call_after_refresh so any "/"
        key that triggered open() has already been consumed by the screen's
        binding handler before the Input becomes focused — otherwise the
        "/" would type into the Input as its first character.
        """
        self.display = True
        self.call_after_refresh(self._focus_input)

    def _focus_input(self) -> None:
        inp = self.query_one(Input)
        inp.value = ""
        inp.focus()

    def close(self) -> None:
        """Clear the query and hide the bar."""
        inp = self.query_one(Input)
        inp.value = ""
        self.display = False
        self.post_message(self.QueryChanged(""))

    def on_input_changed(self, event: Input.Changed) -> None:
        self.post_message(self.QueryChanged(event.value))
