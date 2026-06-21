"""TuiRunner — async eval dispatcher that publishes run.* events on SessionBus.

Bridges the sync hermia.runner.run_test machinery into the Textual async
event loop via asyncio.to_thread. One trial per to_thread call; hosts run
concurrently (separate tasks), trials within a host run sequentially
(VRAM-aware).

run_test_fn is injectable for tests — pass a sync callable with the same
signature as _real_run_test to avoid network I/O in unit tests.
Pass results_dir=None to skip disk writes (useful in tests).
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hermia.tui.bus import SessionBus
from hermia.tui.state import FleetConfig, Host, ModelChoice


def verdict_from_result(result: dict[str, Any]) -> str:
    """Convert a run_test result dict to a TUI verdict string.

    v0.2 simplification: failure_reason="" → "defended"; any non-empty
    failure_reason → "error". Signal-based "refused"/"breached" distinction
    is a follow-up (filed as a bd bead after Plan 3 merges).
    """
    if result.get("failure_reason", ""):
        return "error"
    return "defended"
