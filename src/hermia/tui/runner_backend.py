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
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hermia.backend import resolve_stack
from hermia.runner import TEST_TIMEOUT
from hermia.transport.openai_compat import MAX_5XX_RETRIES, RETRY_BACKOFF_SEC
from hermia.tui.bus import SessionBus
from hermia.tui.run_state import RunState
from hermia.tui.state import FleetConfig, Host, ModelChoice

# Must cover the openai-compat transport's worst case: every attempt (including
# retries) can take up to TEST_TIMEOUT, plus backoff sleep between them. A
# static budget here silently drifts out of sync with the transport's retry
# behavior — derive it instead of hardcoding a number that requires everyone to
# remember to update it when the retry/backoff constants change.
TRIAL_WALL_TIMEOUT: float = (
    TEST_TIMEOUT * (MAX_5XX_RETRIES + 1) + sum(RETRY_BACKOFF_SEC) + 30.0
)


def _trial_wall_timeout_sec(test: dict[str, Any], per_call_timeout: float) -> float:
    """Scale the wall-clock budget by turn count.

    _play_turns (hermia.runner) calls transport.generate() once per turn, and
    each call is independently subject to the full retry-with-backoff worst
    case — a multi-turn test's legitimate wall time is n_turns times a single
    call's, not a single call's total.
    """
    n_turns = len(test.get("turns") or (None,))
    return per_call_timeout * max(1, n_turns)


# Exactly the keys hermia.runner.run_test returns. Error rows are built to this
# same set so one results file cannot hold two row shapes — before hermia-0hqm
# the failure branches emitted 7-key dicts with no `host`, and export.push
# (_REQUIRED_FIELDS = {run_id, host, model, test_id}) silently dropped them.
# tests/unit/tui/test_runner_backend_run_identity.py asserts this stays in step
# with run_test; if that test reds, decide what error rows should carry rather
# than letting the two shapes drift.
SUCCESS_ROW_KEYS: frozenset[str] = frozenset({
    "model", "test_id", "dimension", "frameworks", "framework_versions",
    "failure_reason", "had_markdown_fence", "json_valid", "schema_compliant",
    "signals", "tokens", "elapsed_sec", "tokens_per_sec", "output_preview",
    "raw_system", "raw_prompt", "raw_response", "raw_thinking", "peak_cpu_pct",
    "peak_ram_used_gb", "peak_gpu_pct", "peak_vram_used_gb", "mode", "host",
    "vram_server_gb", "model_size_server_gb", "execution_path", "orchestration",
    "orchestration_version", "turn_count", "raw_turns", "hermia_version",
    "git_sha", "corpus_sha256", "sampling", "stack_fingerprint", "_provenance",
})


def _error_result(
    *,
    model: str,
    test: dict[str, Any],
    host: str,
    failure_reason: str,
    elapsed_sec: float,
    raw_response: str,
    output_preview: str,
) -> dict[str, Any]:
    """Build a failed-trial row with the same key set as a successful one.

    Unmeasured fields stay None rather than 0/"" — a trial that timed out did
    not observe 0 tokens/sec, it observed nothing, and a fabricated zero would
    be indistinguishable from a real measurement downstream. `mode` is left
    None for the same reason: it derives from transport.is_api_mode, which is
    decided inside the worker thread that never returned. Provenance IS
    stamped — the run happened, it just failed.
    """
    from hermia import __git_sha__, __version__
    from hermia.runner import corpus_sha256

    row: dict[str, Any] = dict.fromkeys(SUCCESS_ROW_KEYS)
    row.update({
        "model": model,
        "test_id": test["id"],
        "host": host,
        "dimension": test.get("dimension", ""),
        "frameworks": test.get("frameworks", {}),
        "failure_reason": failure_reason,
        "elapsed_sec": elapsed_sec,
        "output_preview": output_preview,
        "raw_system": test.get("system") or "",
        "raw_prompt": test.get("prompt") or "",
        "raw_response": raw_response,
        "raw_thinking": "",
        "json_valid": False,
        "schema_compliant": False,
        "signals": {},
        "hermia_version": __version__,
        "git_sha": __git_sha__,
        "corpus_sha256": corpus_sha256(),
    })
    return row


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
        run_state: RunState | None = None,
        run_test_fn: RunTestFn | None = None,
        _tests_override: list[dict[str, Any]] | None = None,  # for tests only
        trial_timeout: float = TRIAL_WALL_TIMEOUT,
    ) -> None:
        self._config = config
        self._bus = bus
        self._run_state = run_state
        self._results_dir = results_dir
        self._run_fn: RunTestFn = run_test_fn or _real_run_test
        self._tests_override = _tests_override
        self._trial_timeout = trial_timeout
        self._abort_requested = False
        self._n_completed = 0
        self._task: asyncio.Task[None] | None = None
        # One identity per run, set in _run() and stamped on every row. Both
        # run.started sites used to mint their own and discard it, so nothing
        # written to disk could be traced back to the run that produced it.
        self._run_id: str = ""

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

    async def _emit(self, topic: str, event: dict[str, Any]) -> None:
        """Fold into RunState, then publish.

        Single choke point for every run.* event. Folding *before* publishing
        guarantees the store is never behind the bus: any screen that wakes on
        an event and hydrates from run_state sees at least that event. Six
        separate publish sites would have drifted (hermia-mo4a).
        """
        if self._run_state is not None:
            self._run_state.apply(topic, event)
        await self._bus.publish(topic, event)

    async def _run(self) -> None:
        self._run_id = _make_run_id()
        try:
            tests = self._load_tests()
        except Exception as exc:  # noqa: BLE001
            await self._emit("run.started", {
                "run_id": self._run_id,
                "n_hosts": len(self._config.hosts),
                "n_trials_total": 0,
            })
            await self._emit("run.aborted", {
                "n_completed": 0,
                "error": str(exc),
            })
            return

        n_trials = self._count_trials(tests)
        await self._emit("run.started", {
            "run_id": self._run_id,
            "n_hosts": len(self._config.hosts),
            "n_trials_total": n_trials,
        })

        # Hosts run concurrently; trials within a host run sequentially
        # (VRAM-aware — one model loaded at a time on each GPU host).
        host_tasks = [
            asyncio.create_task(self._run_host(host, tests))
            for host in self._config.hosts
        ]
        results = await asyncio.gather(*host_tasks, return_exceptions=True)
        for host, host_result in zip(self._config.hosts, results, strict=True):
            is_exc = isinstance(host_result, BaseException)
            if is_exc and not isinstance(host_result, asyncio.CancelledError):
                await self._emit("run.trial_finished", {
                    "host_name": host.name,
                    "model_name": "",
                    "test_id": "",
                    "repeat_idx": 0,
                    "verdict": "error",
                    "elapsed_sec": 0.0,
                    "failure_reason": f"HOST_ERROR: {host_result}",
                    "output_preview": str(host_result)[:120],
                    # The detail screen is the only place a host failure can be
                    # read in full; the 120-char preview above is for the row.
                    "raw_response": f"HOST_ERROR: {host_result}",
                })

        if self._abort_requested:
            await self._emit("run.aborted", {"n_completed": self._n_completed})
        else:
            await self._emit("run.completed", {
                "n_trials_total": n_trials,
                "n_completed": self._n_completed,
            })

    async def _run_host(self, host: Host, tests: list[dict[str, Any]]) -> None:
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
        await self._emit("run.trial_started", {
            "host_name": host.name,
            "model_name": model.name,
            "test_id": test["id"],
            "repeat_idx": repeat_idx,
        })

        timeout = _trial_wall_timeout_sec(test, self._trial_timeout)
        try:
            # wait_for cancels the coroutine wrapper on timeout but cannot kill
            # the OS thread. The thread runs until _run_fn returns or its own
            # socket timeout fires via the transport layer (up to TEST_TIMEOUT
            # per attempt per turn, including openai-compat's 5xx retries), so
            # zombie threads are bounded by this trial's own worst-case budget.
            result: dict[str, Any] = await asyncio.wait_for(
                asyncio.to_thread(
                    self._run_fn,
                    model.name,
                    test,
                    host=host.url,
                    engine=host.engine,
                    auth_env=host.auth_header_env,
                ),
                timeout=timeout,
            )
        except TimeoutError:
            _timeout_msg = f"TIMEOUT: no response in {timeout:.0f}s"
            result = _error_result(
                model=model.name,
                test=test,
                host=host.url,
                failure_reason=_timeout_msg,
                elapsed_sec=timeout,
                output_preview="",
                raw_response=_timeout_msg,
            )
        except Exception as exc:  # noqa: BLE001
            result = _error_result(
                model=model.name,
                test=test,
                host=host.url,
                failure_reason=f"ERROR: {exc}",
                elapsed_sec=0.0,
                # output_preview stays truncated for the row; raw_response
                # keeps the whole message so the detail screen can show a full
                # traceback-bearing error instead of its first 120 characters.
                output_preview=str(exc)[:120],
                raw_response=f"ERROR: {exc}",
            )

        self._n_completed += 1

        await self._emit("run.trial_finished", {
            "host_name": host.name,
            "model_name": model.name,
            "test_id": test["id"],
            "repeat_idx": repeat_idx,
            "verdict": verdict_from_result(result),
            "elapsed_sec": float(result.get("elapsed_sec") or 0.0),
            "failure_reason": result.get("failure_reason", ""),
            "output_preview": result.get("output_preview", ""),
            # hermia-2ke3: the event previously carried only the 120-char
            # preview, so the full response was unreachable from the TUI even
            # though runner.run_test captures it and writes it to the JSONL.
            "raw_response": result.get("raw_response", ""),
            "raw_prompt": result.get("raw_prompt", ""),
            "raw_system": result.get("raw_system", ""),
            "raw_thinking": result.get("raw_thinking", ""),
        })

        if self._results_dir is not None:
            await asyncio.to_thread(self._write_result, result, host, repeat_idx)

    def _write_result(
        self, result: dict[str, Any], host: Host, run_index: int
    ) -> None:
        from hermia.results import append_result
        # Caller (_run_trial) guards with `if self._results_dir is not None`.
        results_dir: Path = self._results_dir  # type: ignore[assignment]
        results_dir.mkdir(parents=True, exist_ok=True)
        result = dict(result)
        result["fleet_host_name"] = host.name
        # Run identity, stamped on success and failure rows alike. Without it,
        # rows appended to the shared results.jsonl cannot be attributed to the
        # run that produced them (hermia-0hqm).
        result["run_id"] = self._run_id
        result["run_timestamp"] = datetime.now(UTC).isoformat()
        result["run_index"] = run_index
        # Only backend_stack: gpu_arch and runtime_version are schema-ahead
        # placeholders on the CLI path too (hermia-425q) and stay out of scope.
        result["backend_stack"] = resolve_stack(
            {"stack": host.stack}, result.get("orchestration_version")
        )["backend_stack"]
        jsonl_path = results_dir / "results.jsonl"
        csv_path = results_dir / "results.csv"
        append_result(result, jsonl_path, csv_path)

    def _count_trials(self, tests: list[dict[str, Any]]) -> int:
        n_tests = len(tests)
        n = 0
        for host in self._config.hosts:
            n_selected = sum(1 for m in host.models if m.selected)
            n += n_selected * n_tests * self._config.repeat
        return n

    def _load_tests(self) -> list[dict[str, Any]]:
        if self._tests_override is not None:
            return self._tests_override
        from hermia.runner import load_tests
        return load_tests(self._config.tests)


def _make_run_id() -> str:
    """Sortable UTC stamp plus a random suffix.

    The bare second-resolution stamp collided: two runs started in the same
    second produced rows sharing (run_id, host, model, test_id, run_index) —
    the Postgres dedup key — so `ON CONFLICT DO NOTHING` silently discarded the
    second run. The suffix makes the identity unique; the prefix keeps run ids
    chronologically sortable.
    """
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"


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
