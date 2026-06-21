"""Shared helper: propagate `mark_dirty()` up the screen stack.

Picker screens (HostsScreen / HostModelsScreen / TestsScreen) mutate
app.config when the user toggles selections or adds hosts. The parent
FleetConfigScreen owns the [unsaved changes] indicator — child screens
walk the stack and call mark_dirty() on any screen that supports it.
"""
from __future__ import annotations

from typing import Any


def _mark_dirty_in_stack(app: Any) -> None:
    """Call mark_dirty() on every screen in the stack that supports it.

    Typically only FleetConfigScreen does; future screens with their own
    unsaved-state indicators get the same propagation for free.
    """
    for screen in app.screen_stack:
        marker = getattr(screen, "mark_dirty", None)
        if callable(marker):
            marker()
