"""FilterAxis — `tab`-cycled filter tabs with `All` plus per-axis values.

Each axis is a named slicing dimension over a list. The current axis shows
its values inline (`[axis ▾]  All  V1  V2  …`). The parent screen binds
`tab` to call `next_axis()` and `←`/`→` to call `prev_value()` /
`next_value()`.

A screen passes axes as a dict {axis_name: [values…]}. An empty dict is a
no-op widget — useful so screens without filters don't have to special-case.

Key-routing lives on the screen per spec §5 universal contract.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static


class FilterAxis(Horizontal):
    """Filter axis bar with cyclable axis and per-axis values."""

    DEFAULT_CSS = """
    FilterAxis {
        height: 1;
        padding: 0 1;
    }
    FilterAxis Static {
        margin-right: 2;
    }
    FilterAxis Static.active {
        text-style: bold;
        color: $accent;
    }
    """

    class Changed(Message):
        def __init__(self, axis: str | None, value: str | None) -> None:
            self.axis = axis
            self.value = value
            super().__init__()

    def __init__(self, axes: dict[str, list[str]]) -> None:
        super().__init__()
        self.axes = axes
        self._axis_names = list(axes.keys())
        self._axis_index = 0 if self._axis_names else -1
        self._value_indexes: dict[str, int] = {name: 0 for name in self._axis_names}

    @property
    def current_axis(self) -> str | None:
        if self._axis_index < 0:
            return None
        return self._axis_names[self._axis_index]

    @property
    def current_value(self) -> str | None:
        axis = self.current_axis
        if axis is None:
            return None
        idx = self._value_indexes[axis]
        return self._all_values_for(axis)[idx]

    def _all_values_for(self, axis: str) -> list[str]:
        return ["All", *self.axes[axis]]

    def compose(self) -> ComposeResult:
        if self.current_axis is None:
            return
        for value in self._all_values_for(self.current_axis):
            yield Static(value, classes="active" if value == self.current_value else "")

    def next_axis(self) -> None:
        """Cycle to the next filter axis; resets that axis's value to All."""
        if not self._axis_names:
            return
        self._axis_index = (self._axis_index + 1) % len(self._axis_names)
        self._value_indexes[self.current_axis] = 0  # type: ignore[index]
        self._refresh()
        self.post_message(self.Changed(self.current_axis, self.current_value))

    def next_value(self) -> None:
        """Cycle to the next value within the current axis; wraps at end."""
        axis = self.current_axis
        if axis is None:
            return
        values = self._all_values_for(axis)
        self._value_indexes[axis] = (self._value_indexes[axis] + 1) % len(values)
        self._refresh()
        self.post_message(self.Changed(axis, self.current_value))

    def prev_value(self) -> None:
        """Cycle to the previous value within the current axis; wraps at start."""
        axis = self.current_axis
        if axis is None:
            return
        values = self._all_values_for(axis)
        self._value_indexes[axis] = (self._value_indexes[axis] - 1) % len(values)
        self._refresh()
        self.post_message(self.Changed(axis, self.current_value))

    def _refresh(self) -> None:
        for child in list(self.children):
            child.remove()
        if self.current_axis is None:
            return
        for value in self._all_values_for(self.current_axis):
            self.mount(Static(value, classes="active" if value == self.current_value else ""))
