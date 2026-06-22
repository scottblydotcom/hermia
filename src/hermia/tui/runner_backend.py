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


# Type alias for the injectable run function.
RunTestFn = Callable[..., dict[str, Any]]


class TuiRunner:
    """Async fleet eval dispatcher.

    Call start() to create a background task that iterates all
    (host, model, test, repeat) combinations and publishes bus events.
    Call abort() to stop after the current in-flight trial finishes.
    """

    def __init__(
        self,
        config: FleetConfig,
        bus: SessionBus,
        results_dir: Path | None,
        *,
        run_test_fn: RunTestFn | None = None,
        _tests_override: list[dict[str, Any]] | None = None,  # for tests only
    ) -> None:
        self._config = config
        self._bus = bus
        self._results_dir = results_dir
        self._run_fn: RunTestFn = run_test_fn or _real_run_test
        self._tests_override = _tests_override
        self._abort_requested = False
        self._n_completed = 0
        self._task: asyncio.Task[None] | None = None

    # ── Public API ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Launch the runner in a background asyncio task."""
        self._task = asyncio.create_task(self._run())

    def abort(self) -> None:
        """Signal the runner to stop after the current trial finishes."""
        self._abort_requested = True

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ── Internal ───────────────────────────────────────────────────────────

    async def _run(self) -> None:
        n_trials = self._count_trials()
        await self._bus.publish("run.started", {
            "run_id": _make_run_id(),
            "n_hosts": len(self._config.hosts),
            "n_trials_total": n_trials,
        })

        # Hosts run concurrently; trials within a host run sequentially
        # (VRAM-aware — one model loaded at a time on each GPU host).
        host_tasks = [
            asyncio.create_task(self._run_host(host))
            for host in self._config.hosts
        ]
        await asyncio.gather(*host_tasks, return_exceptions=True)

        if self._abort_requested:
            await self._bus.publish("run.aborted", {"n_completed": self._n_completed})
        else:
            await self._bus.publish("run.completed", {
                "n_trials_total": n_trials,
                "n_completed": self._n_completed,
            })

    async def _run_host(self, host: Host) -> None:
        tests = self._load_tests()
        for model in host.models:
            if not model.selected:
                continue
            if self._abort_requested:
                return
            for test in tests:
                if self._abort_requested:
                    return
                for repeat_idx in range(1, self._config.repeat + 1):
                    if self._abort_requested:
                        return
                    await self._run_trial(host, model, test, repeat_idx)

    async def _run_trial(
        self,
        host: Host,
        model: ModelChoice,
        test: dict[str, Any],
        repeat_idx: int,
    ) -> None:
        await self._bus.publish("run.trial_started", {
            "host_name": host.name,
            "model_name": model.name,
            "test_id": test["id"],
            "repeat_idx": repeat_idx,
        })

        try:
            result: dict[str, Any] = await asyncio.to_thread(
                self._run_fn,
                model.name,
                test,
                host=host.url,
                engine=host.engine,
                auth_env=host.auth_header_env,
            )
        except Exception as exc:  # noqa: BLE001
            result = {
                "model": model.name,
                "test_id": test["id"],
                "failure_reason": f"ERROR: {exc}",
                "elapsed_sec": 0.0,
                "output_preview": str(exc)[:120],
                "signals": {},
            }

        self._n_completed += 1

        await self._bus.publish("run.trial_finished", {
            "host_name": host.name,
            "model_name": model.name,
            "test_id": test["id"],
            "repeat_idx": repeat_idx,
            "verdict": verdict_from_result(result),
            "elapsed_sec": float(result.get("elapsed_sec") or 0.0),
            "failure_reason": result.get("failure_reason", ""),
            "output_preview": result.get("output_preview", ""),
        })

        if self._results_dir is not None:
            await asyncio.to_thread(self._write_result, result, host.name)

    def _write_result(self, result: dict[str, Any], fleet_host_name: str) -> None:
        from hermia.results import append_result
        # Caller (_run_trial) guards with `if self._results_dir is not None`.
        results_dir: Path = self._results_dir  # type: ignore[assignment]
        result = dict(result)
        result["fleet_host_name"] = fleet_host_name
        jsonl_path = results_dir / "results.jsonl"
        csv_path = results_dir / "results.csv"
        append_result(result, jsonl_path, csv_path)

    def _count_trials(self) -> int:
        n = 0
        for host in self._config.hosts:
            n_selected = sum(1 for m in host.models if m.selected)
            n += n_selected * len(self._config.tests) * self._config.repeat
        return n

    def _load_tests(self) -> list[dict[str, Any]]:
        if self._tests_override is not None:
            return self._tests_override
        from hermia.runner import load_tests
        return load_tests(self._config.tests)


def _make_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _real_run_test(
    model_name: str,
    test: dict[str, Any],
    *,
    host: str,
    engine: str,
    auth_env: str | None,
) -> dict[str, Any]:
    """Production run_test bridge — called from asyncio.to_thread."""
    import os

    from hermia.metrics import MetricsSampler
    from hermia.runner import run_test
    from hermia.transport.ollama import OllamaTransport
    from hermia.transport.openai_compat import OpenAICompatTransport

    headers: dict[str, str] = {}
    if auth_env:
        token = os.environ.get(auth_env, "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    transport = (
        OpenAICompatTransport(host, headers)
        if engine == "openai-compat"
        else OllamaTransport(host, headers)
    )
    sampler = MetricsSampler()
    return run_test(
        model_name, test, sampler,
        host=host, transport=transport, locality="remote",
    )
