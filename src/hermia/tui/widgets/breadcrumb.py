"""Breadcrumb — segmented drill-path header.

`hermia ▸ fleet ▸ kwaainet-baseline ▸ hosts ▸ node-b`

Each segment is clickable (mouse) and the host screen can call jump_to(i)
to handle keyboard jumps. The widget emits Breadcrumb.Jumped(index) which
the screen translates into pop_screen() calls per drill depth.
"""
from __future__ import annotations

from rich.markup import escape as rich_escape
from textual.message import Message
from textual.widgets import Static

SEPARATOR = " ▸ "


class Breadcrumb(Static):
    """Inline segmented drill-path header.

    Segments are escaped for Rich markup at the boundary — call sites pass
    user-controlled YAML strings (fleet name, host name, model name, test id)
    and Static parses markup by default, so an unescaped `lab[1]` or
    `[bold red]x[/]` would either render styled or raise MarkupError.
    Centralized here so the six call sites can't drift.
    """

    DEFAULT_CSS = """
    Breadcrumb {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    class Jumped(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, segments: list[str]) -> None:
        self._segments = list(segments)
        self._text = SEPARATOR.join(rich_escape(s) for s in self._segments)
        super().__init__(self._text)

    @property
    def text(self) -> str:
        return self._text

    def set_segments(self, segments: list[str]) -> None:
        self._segments = list(segments)
        self._text = SEPARATOR.join(rich_escape(s) for s in self._segments)
        self.update(self._text)

    def jump_to(self, index: int) -> None:
        """Programmatic jump — used by screen-level handlers."""
        if 0 <= index < len(self._segments):
            self.post_message(self.Jumped(index))
