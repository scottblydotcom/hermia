"""StatusBadge — single-glyph status indicator with direction-aware color.

Status vocabulary (from spec §5):
    defended  — model produced compliant output (good security outcome)
    refused   — model said no (valence depends on test direction)
    breached  — model produced non-compliant output (jailbroken/leaked/complied)
    error     — no usable output (TIMEOUT, EMPTY_RESPONSE, transport error)

Refused color is direction-aware: harmful test + refused = green (good);
benign test + refused = red (over-refusal). v0.3 BAM Benign tier needs this.
"""
from __future__ import annotations

from typing import Literal

from textual.widgets import Static

Status = Literal["defended", "refused", "breached", "error"]
Direction = Literal["harmful", "benign"]

ICONS: dict[Status, str] = {
    "defended": "✓",
    "refused": "↺",
    "breached": "✗",
    "error": "!",
}


def color_for(status: Status, direction: Direction = "harmful") -> str:
    """Pick the Textual color for a given (status, direction)."""
    if status == "defended":
        return "green"
    if status == "breached":
        return "red"
    if status == "error":
        return "yellow"
    # refused — valence depends on test direction
    return "green" if direction == "harmful" else "red"


class StatusBadge(Static):
    """One-glyph status indicator. Use in list rows and trial cells."""

    def __init__(self, status: Status, *, direction: Direction = "harmful") -> None:
        self.status: Status = status
        self.direction: Direction = direction
        self._markup: str = self._build_markup()
        super().__init__(self._markup)

    def update_status(self, status: Status, *, direction: Direction | None = None) -> None:
        self.status = status
        if direction is not None:
            self.direction = direction
        self._markup = self._build_markup()
        self.update(self._markup)

    @property
    def markup(self) -> str:
        """The Textual markup string used to render this badge (color + glyph)."""
        return self._markup

    def _build_markup(self) -> str:
        color = color_for(self.status, self.direction)
        return f"[{color}]{ICONS[self.status]}[/]"
