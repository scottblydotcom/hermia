"""TUI results are written run-scoped and top-level, so tooling can find them
(hermia-u1v7).

The TUI wrote `results/<fleet-name>/results.jsonl`. Every consumer scans the TOP
LEVEL of `results/`:

    export.py    glob("eval_*.jsonl")   -> hermia-push  ("No results found", visible)
    submit.py    glob("*.jsonl")        -> hermia-submit (SILENTLY submits an older file)
    audit.py     glob("eval_*.jsonl")   -> hermia --audit

So none of them ever saw a TUI run. The submit case is the dangerous one: it does
not fail, it publishes the wrong file and returns a success URL.
"""
import asyncio
import csv
import json
from pathlib import Path

from hermia.export import collect_results
from hermia.tui.bus import SessionBus
from hermia.tui.runner_backend import SUCCESS_ROW_ORDER, TuiRunner
from hermia.tui.state import FleetConfig, Host, ModelChoice

HOST_URL = "http://host0:11434"


def _config(name: str = "test-fleet", repeat: int = 1) -> FleetConfig:
    host = Host(
        name="host-0",
        url=HOST_URL,
        engine="ollama",
        models=[ModelChoice(name="m0", selected=True)],
    )
    return FleetConfig(name=name, hosts=[host], tests=["t1"], repeat=repeat)


def _ok_run_test(model_name, test, *, host, engine, auth_env):  # noqa: ANN001
    row = dict.fromkeys(SUCCESS_ROW_ORDER)
    row.update({
        "model": model_name, "test_id": test["id"], "host": host,
        "failure_reason": "", "elapsed_sec": 0.01, "output_preview": "ok",
        "raw_response": "ok", "signals": {}, "schema_compliant": True,
        "orchestration_version": None,
    })
    return row


def _boom_run_test(model_name, test, *, host, engine, auth_env):  # noqa: ANN001
    raise RuntimeError("boom")


def _run(results_dir: Path, *, repeat: int = 1, fn=_ok_run_test) -> TuiRunner:
    runner = TuiRunner(
        config=_config(repeat=repeat),
        bus=SessionBus(),
        results_dir=results_dir,
        run_test_fn=fn,
        _tests_override=[{"id": "t1"}],
    )

    async def _go() -> None:
        await runner.start()
        assert runner._task is not None
        await asyncio.wait_for(runner._task, timeout=10.0)

    asyncio.run(_go())
    return runner


def _rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


class TestRunScopedFilenames:
    def test_jsonl_is_named_for_the_run_id(self, tmp_path: Path) -> None:
        runner = _run(tmp_path)
        files = list(tmp_path.glob("eval_*.jsonl"))
        assert len(files) == 1
        assert files[0].name == f"eval_{runner._run_id}.jsonl"
        # the row's own run_id must match the filename it landed in
        assert _rows(files[0])[0]["run_id"] == runner._run_id

    def test_legacy_results_jsonl_is_no_longer_written(self, tmp_path: Path) -> None:
        _run(tmp_path)
        assert not (tmp_path / "results.jsonl").exists()
        assert not (tmp_path / "results.csv").exists()

    def test_csv_is_named_for_the_run_id_and_readable(self, tmp_path: Path) -> None:
        runner = _run(tmp_path)
        files = list(tmp_path.glob("eval_*.csv"))
        assert len(files) == 1
        assert files[0].name == f"eval_{runner._run_id}.csv"
        with files[0].open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["model"] == "m0"
        assert rows[0]["test_id"] == "t1"
        assert rows[0]["run_id"] == runner._run_id

    def test_two_runs_write_two_separate_files(self, tmp_path: Path) -> None:
        """The point of the change — runs no longer accumulate into one file."""
        a = _run(tmp_path)
        b = _run(tmp_path)
        files = sorted(p.name for p in tmp_path.glob("eval_*.jsonl"))
        assert len(files) == 2
        assert a._run_id != b._run_id
        assert files == sorted([f"eval_{a._run_id}.jsonl", f"eval_{b._run_id}.jsonl"])

    def test_repeats_of_one_run_stay_in_one_file(self, tmp_path: Path) -> None:
        """Run-scoped, not trial-scoped: all repeats of a run share its file."""
        _run(tmp_path, repeat=3)
        files = list(tmp_path.glob("eval_*.jsonl"))
        assert len(files) == 1
        rows = _rows(files[0])
        assert len(rows) == 3
        assert {r["run_index"] for r in rows} == {1, 2, 3}
        assert len({r["run_id"] for r in rows}) == 1

    def test_error_rows_land_in_the_same_run_scoped_file(self, tmp_path: Path) -> None:
        runner = _run(tmp_path, fn=_boom_run_test)
        files = list(tmp_path.glob("eval_*.jsonl"))
        assert len(files) == 1
        assert files[0].name == f"eval_{runner._run_id}.jsonl"
        assert _rows(files[0])[0]["failure_reason"].startswith("ERROR:")


class TestDiscoverableByTooling:
    """Each assertion here is one of the three consumers that could not see TUI runs."""

    def test_hermia_push_finds_the_rows(self, tmp_path: Path) -> None:
        _run(tmp_path)
        # export.collect_results is exactly what hermia-push calls.
        assert len(collect_results(tmp_path)) == 1

    def test_hermia_submit_glob_finds_the_file(self, tmp_path: Path) -> None:
        # submit._find_latest_results does RESULTS_DIR.glob("*.jsonl") — top level only.
        _run(tmp_path)
        assert list(tmp_path.glob("*.jsonl"))

    def test_hermia_audit_glob_finds_the_file(self, tmp_path: Path) -> None:
        # audit.load_rows does source.glob("eval_*.jsonl").
        _run(tmp_path)
        assert list(tmp_path.glob("eval_*.jsonl"))

    def test_submit_picks_the_newest_run_not_an_older_one(self, tmp_path: Path) -> None:
        """The failure that published wrong data: newest-by-mtime must be this run."""
        _run(tmp_path)
        newest_first = _run(tmp_path)
        latest = max(tmp_path.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        assert latest.name == f"eval_{newest_first._run_id}.jsonl"
