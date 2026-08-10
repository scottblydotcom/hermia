"""Run identity on TUI-written result rows (hermia-0hqm).

Before this, TUI rows carried no run_id / run_timestamp / run_index, so rows
appended to a shared results file could not be attributed to the run that
produced them. Error and timeout rows were built as 7-key dicts with no `host`,
so one file held two row shapes and export.push silently dropped the error rows
(_REQUIRED_FIELDS = {run_id, host, model, test_id}).

Deliberately NOT covered: the determinism aggregates (consistency_pct,
reproducibility, pass_count, robustness_n). They are degenerate at repeat=1 —
the only value reachable from the TUI — and are out of scope by decision.
"""
import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from hermia.export import _REQUIRED_FIELDS
from hermia.tui.bus import SessionBus
from hermia.tui.runner_backend import (
    SUCCESS_ROW_KEYS,
    SUCCESS_ROW_ORDER,
    TuiRunner,
    _error_result,
    _make_run_id,
)
from hermia.tui.state import FleetConfig, Host, ModelChoice

# The key set hermia.runner.run_test returns. Duplicated here on purpose: this
# literal is the anti-drift tripwire. If run_test's contract changes, the parity
# test below fails and someone has to decide what the TUI's error rows should
# carry, instead of the two shapes drifting apart unnoticed.
RUN_TEST_KEYS = frozenset({
    "model", "test_id", "dimension", "frameworks", "framework_versions",
    "failure_reason", "had_markdown_fence", "json_valid", "schema_compliant",
    "signals", "tokens", "elapsed_sec", "tokens_per_sec", "output_preview",
    "raw_system", "raw_prompt", "raw_response", "raw_thinking", "peak_cpu_pct",
    "peak_ram_used_gb", "peak_gpu_pct", "peak_vram_used_gb", "mode", "host",
    "vram_server_gb", "model_size_server_gb", "execution_path", "orchestration",
    "orchestration_version", "turn_count", "raw_turns", "hermia_version",
    "git_sha", "corpus_sha256", "sampling", "stack_fingerprint", "_provenance",
})

HOST_URL = "http://host0:11434"


def _make_config(
    *,
    repeat: int = 1,
    stack: dict | None = None,
    n_models: int = 1,
) -> FleetConfig:
    host = Host(
        name="host-0",
        url=HOST_URL,
        engine="ollama",
        stack=stack,
        models=[ModelChoice(name=f"m{j}", selected=True) for j in range(n_models)],
    )
    return FleetConfig(name="test", hosts=[host], tests=["t1"], repeat=repeat)


def _success_row(model_name: str, test: dict, host: str) -> dict:
    """A run_test-shaped success row — every key run_test really returns."""
    row = dict.fromkeys(RUN_TEST_KEYS)
    row.update({
        "model": model_name,
        "test_id": test["id"],
        "host": host,
        "failure_reason": "",
        "elapsed_sec": 0.01,
        "tokens_per_sec": 50.0,
        "output_preview": "ok",
        "raw_response": "ok",
        "signals": {},
        "schema_compliant": True,
        "orchestration_version": None,
    })
    return row


def _fake_run_test_fn(model_name, test, *, host, engine, auth_env):  # noqa: ANN001
    return _success_row(model_name, test, host)


def _raising_run_test_fn(exc: BaseException):
    def _fn(model_name, test, *, host, engine, auth_env):  # noqa: ANN001
        raise exc
    return _fn


def _run_to_completion(runner: TuiRunner) -> None:
    """Await start() *and* the background task it spawns.

    start() returns as soon as the task is created — awaiting only start()
    asserts against an empty results file.
    """
    async def _go() -> None:
        await runner.start()
        assert runner._task is not None
        await asyncio.wait_for(runner._task, timeout=10.0)

    asyncio.run(_go())


def _rows(results_dir: Path) -> list[dict]:
    # Run-scoped filename since hermia-u1v7; exactly one per run here.
    paths = list(results_dir.glob("eval_*.jsonl"))
    assert len(paths) == 1, f"expected one run file, got {[p.name for p in paths]}"
    return [json.loads(line) for line in paths[0].read_text().splitlines() if line.strip()]


class TestMakeRunId:
    def test_is_unique_across_many_calls_in_the_same_second(self) -> None:
        # No clock freezing needed: 200 calls complete well inside one second,
        # and the assertion is exactly "same second must still be unique".
        ids = {_make_run_id() for _ in range(200)}
        assert len(ids) == 200

    def test_has_sortable_utc_timestamp_prefix(self) -> None:
        assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{6}", _make_run_id())

    def test_prefix_sorts_chronologically(self) -> None:
        first, second = _make_run_id(), _make_run_id()
        assert first.split("-")[0] <= second.split("-")[0]


class TestRunIdentityOnRows:
    def test_every_written_row_carries_run_identity(self, tmp_path: Path) -> None:
        runner = TuiRunner(
            config=_make_config(repeat=2),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_fake_run_test_fn,
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        rows = _rows(tmp_path)
        assert len(rows) == 2
        for row in rows:
            assert row["run_id"]
            assert row["run_timestamp"]
            assert isinstance(row["run_index"], int)
        assert {r["run_index"] for r in rows} == {1, 2}

    def test_all_rows_in_one_run_share_one_run_id(self, tmp_path: Path) -> None:
        runner = TuiRunner(
            config=_make_config(repeat=3, n_models=2),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_fake_run_test_fn,
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        rows = _rows(tmp_path)
        assert len(rows) == 6
        assert len({r["run_id"] for r in rows}) == 1

    def test_row_run_id_matches_the_run_started_event(self, tmp_path: Path) -> None:
        """The event's id was generated inline and thrown away; rows had none."""
        async def _go() -> None:
            bus = SessionBus()
            started: list[dict] = []

            async def listen() -> None:
                async for ev in bus.subscribe("run.started"):
                    started.append(ev)
                    return

            task = asyncio.create_task(listen())
            await asyncio.sleep(0)  # let the subscriber register before publish

            runner = TuiRunner(
                config=_make_config(),
                bus=bus,
                results_dir=tmp_path,
                run_test_fn=_fake_run_test_fn,
                _tests_override=[{"id": "t1"}],
            )
            await runner.start()
            assert runner._task is not None
            await asyncio.wait_for(runner._task, timeout=10.0)
            await asyncio.wait_for(task, timeout=3.0)

            assert started[0]["run_id"] == _rows(tmp_path)[0]["run_id"]

        asyncio.run(_go())

    def test_run_timestamp_is_iso8601_with_timezone(self, tmp_path: Path) -> None:
        runner = TuiRunner(
            config=_make_config(),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_fake_run_test_fn,
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        parsed = datetime.fromisoformat(_rows(tmp_path)[0]["run_timestamp"])
        assert parsed.tzinfo is not None

    def test_run_index_matches_repeat_index_order(self, tmp_path: Path) -> None:
        runner = TuiRunner(
            config=_make_config(repeat=3),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_fake_run_test_fn,
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        assert [r["run_index"] for r in _rows(tmp_path)] == [1, 2, 3]


class TestErrorRowShape:
    def test_error_row_key_set_equals_success_row_key_set(self) -> None:
        row = _error_result(
            model="m1",
            test={"id": "t1"},
            host=HOST_URL,
            failure_reason="TIMEOUT: no response in 5s",
            elapsed_sec=5.0,
            raw_response="TIMEOUT: no response in 5s",
            output_preview="",
        )
        assert set(row) == RUN_TEST_KEYS

    def test_module_constant_tracks_the_real_run_test_contract(self) -> None:
        """If run_test changes shape, fail here rather than drifting silently."""
        assert SUCCESS_ROW_KEYS == RUN_TEST_KEYS

    def test_timeout_row_has_host_and_survives_export_required_fields(
        self, tmp_path: Path
    ) -> None:
        runner = TuiRunner(
            config=_make_config(),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_raising_run_test_fn(TimeoutError()),
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        row = _rows(tmp_path)[0]
        assert row["host"] == HOST_URL
        # export.push drops any row missing one of these — the bug that made
        # error rows vanish while their siblings claimed to summarise them.
        assert all(row.get(f) for f in _REQUIRED_FIELDS)

    def test_exception_row_has_host_and_error_reason(self, tmp_path: Path) -> None:
        runner = TuiRunner(
            config=_make_config(),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_raising_run_test_fn(RuntimeError("boom")),
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        row = _rows(tmp_path)[0]
        assert row["host"] == HOST_URL
        assert row["failure_reason"].startswith("ERROR:")
        assert "boom" in row["raw_response"]
        assert all(row.get(f) for f in _REQUIRED_FIELDS)

    def test_wall_timeout_row_has_host(self, tmp_path: Path) -> None:
        """A real asyncio.wait_for timeout, not a raised TimeoutError."""
        def _slow(model_name, test, *, host, engine, auth_env):  # noqa: ANN001
            import time
            time.sleep(1.0)
            return _success_row(model_name, test, host)

        runner = TuiRunner(
            config=_make_config(),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_slow,
            _tests_override=[{"id": "t1"}],
            trial_timeout=0.05,
        )
        _run_to_completion(runner)

        row = _rows(tmp_path)[0]
        assert row["host"] == HOST_URL
        assert row["failure_reason"].startswith("TIMEOUT:")

    def test_error_then_success_write_aligned_csv_columns(self, tmp_path: Path) -> None:
        """The shear case, end to end: an error row first, a success row second."""
        calls: list[int] = []

        def _fail_then_pass(model_name, test, *, host, engine, auth_env):  # noqa: ANN001
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return _success_row(model_name, test, host)

        runner = TuiRunner(
            config=_make_config(repeat=2),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_fail_then_pass,
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        csv_paths = list(tmp_path.glob("eval_*.csv"))
        assert len(csv_paths) == 1
        with csv_paths[0].open(newline="", encoding="utf-8") as f:
            csv_rows = list(csv.DictReader(f))

        assert len(csv_rows) == 2
        # Pre-fix, row 2's values landed under row 1's column names.
        for row in csv_rows:
            assert row["model"] == "m0"
            assert row["test_id"] == "t1"
            assert row["host"] == HOST_URL
        assert csv_rows[0]["failure_reason"].startswith("ERROR:")
        assert csv_rows[1]["failure_reason"] == ""


class TestBackendStack:
    def test_backend_stack_stamped_from_host_stack_block(self, tmp_path: Path) -> None:
        runner = TuiRunner(
            config=_make_config(
                stack={"gpu_arch": "sm_89", "runtime_version": "cuda-12.4"}
            ),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_fake_run_test_fn,
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        row = _rows(tmp_path)[0]
        assert "sm_89" in row["backend_stack"]
        assert "cuda-12.4" in row["backend_stack"]

    def test_backend_stack_is_none_without_stack_metadata(self, tmp_path: Path) -> None:
        runner = TuiRunner(
            config=_make_config(stack=None),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_fake_run_test_fn,
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        assert _rows(tmp_path)[0]["backend_stack"] is None

    def test_error_row_carries_backend_stack(self, tmp_path: Path) -> None:
        runner = TuiRunner(
            config=_make_config(stack={"gpu_arch": "sm_89"}),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_raising_run_test_fn(RuntimeError("boom")),
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        assert _rows(tmp_path)[0]["backend_stack"] == "sm_89"


class TestOutOfScopeAggregatesStayAbsent:
    """Guard the decision, not just the code.

    consistency_pct=1.0 on a repeat=1 run is a confident wrong number on the
    most public surface. Absent is honest. If someone adds these later they
    must also add a TUI repeat control and delete this test deliberately.
    """

    @pytest.mark.parametrize(
        "field", ["consistency_pct", "reproducibility", "pass_count", "robustness_n"]
    )
    def test_determinism_aggregate_is_not_stamped(self, tmp_path: Path, field: str) -> None:
        runner = TuiRunner(
            config=_make_config(),
            bus=SessionBus(),
            results_dir=tmp_path,
            run_test_fn=_fake_run_test_fn,
            _tests_override=[{"id": "t1"}],
        )
        _run_to_completion(runner)

        assert field not in _rows(tmp_path)[0]


class TestColumnOrderIsDeterministic:
    """append_result pins the header from whichever row lands first.

    If error rows enumerated their keys in a different order than success rows,
    the CSV column layout would depend on whether the first trial failed — and
    iterating a frozenset varies with PYTHONHASHSEED across processes.
    """

    def test_error_row_key_order_matches_the_declared_order(self) -> None:
        row = _error_result(
            model="m1", test={"id": "t1"}, host=HOST_URL,
            failure_reason="ERROR: boom", elapsed_sec=0.0,
            raw_response="ERROR: boom", output_preview="boom",
        )
        assert list(row) == list(SUCCESS_ROW_ORDER)

    def test_declared_order_matches_the_key_set(self) -> None:
        assert frozenset(SUCCESS_ROW_ORDER) == SUCCESS_ROW_KEYS
        assert len(SUCCESS_ROW_ORDER) == len(SUCCESS_ROW_KEYS)  # no duplicates

    def test_order_is_stable_across_processes(self) -> None:
        """Different PYTHONHASHSEED must not reorder the columns."""
        import subprocess
        import sys
        code = (
            "from hermia.tui.runner_backend import _error_result;"
            "r=_error_result(model='m',test={'id':'t'},host='h',failure_reason='x',"
            "elapsed_sec=0.0,raw_response='x',output_preview='x');"
            "print(','.join(r))"
        )
        seen = {
            subprocess.run(  # noqa: S603
                [sys.executable, "-c", code], capture_output=True, text=True,
                env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"}, check=True,
            ).stdout.strip()
            for seed in ("0", "1", "12345")
        }
        assert len(seen) == 1

    def test_err_row_carries_framework_versions(self) -> None:
        """Static corpus metadata is knowable even when the trial never ran."""
        row = _error_result(
            model="m1", test={"id": "t1"}, host=HOST_URL,
            failure_reason="TIMEOUT", elapsed_sec=1.0,
            raw_response="TIMEOUT", output_preview="",
        )
        assert row["framework_versions"]

    def test_host_probe_fields_stay_none_on_error(self) -> None:
        """We never reached the host, so asserting a backend would be invention."""
        row = _error_result(
            model="m1", test={"id": "t1"}, host=HOST_URL,
            failure_reason="TIMEOUT", elapsed_sec=1.0,
            raw_response="TIMEOUT", output_preview="",
        )
        assert row["stack_fingerprint"] is None
        assert row["_provenance"] is None
