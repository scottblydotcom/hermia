"""Breadcrumb — segmented drill-path header.

`hermia ▸ fleet ▸ kwaainet-baseline ▸ hosts ▸ marcus`

Each segment is clickable (mouse) and the host screen can call jump_to(i)
to handle keyboard jumps. The widget emits Breadcrumb.Jumped(index) which
the screen translates into pop_screen() calls per drill depth.
"""
from __future__ import annotations

from textual.message import Message
from textual.widgets import Static

SEPARATOR = " ▸ "


class Breadcrumb(Static):
    """Inline segmented drill-path header."""

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
        self._text = SEPARATOR.join(self._segments)
        super().__init__(self._text)

    @property
    def text(self) -> str:
        return self._text

    def set_segments(self, segments: list[str]) -> None:
        self._segments = list(segments)
        self._text = SEPARATOR.join(self._segments)
        self.update(self._text)

    def jump_to(self, index: int) -> None:
        """Programmatic jump — used by screen-level handlers."""
        if 0 <= index < len(self._segments):
            self.post_message(self.Jumped(index))
