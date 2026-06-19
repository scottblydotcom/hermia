"""Progress bar widgets for fleet runs.

MiniProgressBar       — single-line fixed-width bar (per-host row)
AggregateProgressBar  — full-width bar with N/M count + percent (Runner L1)

Pure Textual Static widgets — no animations, just a renderable that updates
when .advance() or .set_total() is called. The runner publishes events;
screens decide when to advance these bars.

Both expose a `.text` property returning the current rendered string so tests
can assert content without depending on Textual's internal Content parsing.
"""
from __future__ import annotations

from textual.widgets import Static

FILLED = "█"
EMPTY = "░"


class MiniProgressBar(Static):
    """Per-host inline progress bar; fixed width, no labels."""

    def __init__(self, *, total: int, width: int = 40) -> None:
        self.total = total
        self.completed = 0
        self.width = width
        self._text = self._render()
        super().__init__(self._text)

    def advance(self, n: int = 1) -> None:
        self.completed = min(self.completed + n, self.total)
        self._text = self._render()
        self.update(self._text)

    def set_total(self, total: int) -> None:
        self.total = total
        if self.completed > total:
            self.completed = total
        self._text = self._render()
        self.update(self._text)

    @property
    def text(self) -> str:
        return self._text

    def _render(self) -> str:
        if self.total == 0:
            return EMPTY * self.width
        filled_chars = int(self.width * self.completed / self.total)
        return FILLED * filled_chars + EMPTY * (self.width - filled_chars)


class AggregateProgressBar(Static):
    """Full-width Runner L1 progress bar with count + percent."""

    def __init__(self, *, total: int, width: int = 40) -> None:
        self.total = total
        self.completed = 0
        self.width = width
        self._text = self._render()
        super().__init__(self._text)

    def advance(self, n: int = 1) -> None:
        self.completed = min(self.completed + n, self.total)
        self._text = self._render()
        self.update(self._text)

    @property
    def text(self) -> str:
        return self._text

    def _render(self) -> str:
        if self.total == 0:
            return f"{EMPTY * self.width}   0 / 0  (0%)"
        filled_chars = int(self.width * self.completed / self.total)
        pct = int(100 * self.completed / self.total)
        bar = FILLED * filled_chars + EMPTY * (self.width - filled_chars)
        return f"{bar}   {self.completed} / {self.total}  ({pct}%)"
