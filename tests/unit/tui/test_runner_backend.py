"""Tests for hermia.tui.runner_backend — TuiRunner + helpers."""
import asyncio

from hermia.tui.bus import SessionBus
from hermia.tui.runner_backend import TuiRunner, _trial_wall_timeout_sec, verdict_from_result
from hermia.tui.state import FleetConfig, Host, ModelChoice


class TestTrialWallTimeoutSec:
    def test_single_turn_test_uses_per_call_timeout_unscaled(self) -> None:
        assert _trial_wall_timeout_sec({"id": "t1"}, 300.0) == 300.0

    def test_two_turn_test_scales_timeout_by_turn_count(self) -> None:
        test = {"id": "multiturn-context-carry", "turns": ["turn1", "turn2"]}
        assert _trial_wall_timeout_sec(test, 300.0) == 600.0

    def test_empty_turns_list_treated_as_single_turn(self) -> None:
        assert _trial_wall_timeout_sec({"id": "t1", "turns": []}, 300.0) == 300.0


class TestVerdictFromResult:
    def test_empty_failure_reason_is_defended(self) -> None:
        result = {"failure_reason": "", "signals": {}}
        assert verdict_from_result(result) == "defended"

    def test_timeout_failure_is_error(self) -> None:
        result = {"failure_reason": "TIMEOUT: no response in 90s", "signals": {}}
        assert verdict_from_result(result) == "error"

    def test_schema_fail_is_error(self) -> None:
        result = {"failure_reason": "SCHEMA_FAIL", "signals": {}}
        assert verdict_from_result(result) == "error"

    def test_empty_response_is_error(self) -> None:
        result = {"failure_reason": "EMPTY_RESPONSE", "signals": {}}
        assert verdict_from_result(result) == "error"

    def test_api_error_is_error(self) -> None:
        result = {"failure_reason": "API_ERROR: connection refused", "signals": {}}
        assert verdict_from_result(result) == "error"

    def test_missing_failure_reason_key_treated_as_defended(self) -> None:
        result = {"signals": {}}
        assert verdict_from_result(result) == "defended"


def _make_config(
    n_hosts: int = 1,
    n_models: int = 1,
    test_ids: list[str] | None = None,
    repeat: int = 1,
) -> FleetConfig:
    hosts = [
        Host(
            name=f"host-{i}",
            url=f"http://host{i}:11434",
            engine="ollama",
            models=[ModelChoice(name=f"m{j}", selected=True) for j in range(n_models)],
        )
        for i in range(n_hosts)
    ]
    return FleetConfig(
        name="test",
        hosts=hosts,
        tests=test_ids or ["t1"],
        repeat=repeat,
    )


def _fake_run_test_fn(
    model_name: str,
    test: dict,
    *,
    host: str,
    engine: str,
    auth_env: str | None,
) -> dict:
    """Sync fake; returns immediately with a clean result."""
    return {
        "model": model_name,
        "test_id": test["id"],
        "failure_reason": "",
        "elapsed_sec": 0.01,
        "tokens_per_sec": 50.0,
        "output_preview": "ok",
        "signals": {},
        "schema_compliant": True,
    }


class TestTuiRunnerBusEvents:
    def test_run_started_published_first(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            received: list[dict] = []

            async def listen() -> None:
                async for ev in bus.subscribe("run.started"):
                    received.append(ev)
                    return

            task = asyncio.create_task(listen())
            await asyncio.sleep(0)

            config = _make_config(n_hosts=2, n_models=1, test_ids=["t1"], repeat=1)
            runner = TuiRunner(
                config=config,
                bus=bus,
                results_dir=None,
                run_test_fn=_fake_run_test_fn,
                _tests_override=[{"id": "t1"}],
            )
            await runner.start()
            await asyncio.wait_for(task, timeout=3.0)
            assert received[0]["n_hosts"] == 2
            assert received[0]["n_trials_total"] == 2  # 2 hosts × 1 model × 1 test × 1 repeat

        asyncio.run(_run())

    def test_trial_started_and_finished_each_trial(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            started: list[dict] = []
            finished: list[dict] = []

            async def listen_started() -> None:
                async for ev in bus.subscribe("run.trial_started"):
                    started.append(ev)
                    if len(started) == 2:
                        return

            async def listen_finished() -> None:
                async for ev in bus.subscribe("run.trial_finished"):
                    finished.append(ev)
                    if len(finished) == 2:
                        return

            t1 = asyncio.create_task(listen_started())
            t2 = asyncio.create_task(listen_finished())
            await asyncio.sleep(0)

            config = _make_config(n_hosts=1, n_models=2, test_ids=["t1"], repeat=1)
            runner = TuiRunner(
                config=config,
                bus=bus,
                results_dir=None,
                run_test_fn=_fake_run_test_fn,
                _tests_override=[{"id": "t1"}],
            )
            await runner.start()
            await asyncio.wait_for(asyncio.gather(t1, t2), timeout=5.0)

            assert len(started) == 2
            assert len(finished) == 2
            assert all(e["host_name"] == "host-0" for e in started)
            assert all(e["verdict"] == "defended" for e in finished)

        asyncio.run(_run())

    def test_run_completed_published_after_all_trials(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            completed: list[dict] = []

            async def listen() -> None:
                async for ev in bus.subscribe("run.completed"):
                    completed.append(ev)
                    return

            task = asyncio.create_task(listen())
            await asyncio.sleep(0)

            config = _make_config(n_hosts=1, n_models=1, test_ids=["t1", "t2"], repeat=1)
            runner = TuiRunner(
                config=config,
                bus=bus,
                results_dir=None,
                run_test_fn=_fake_run_test_fn,
                _tests_override=[{"id": "t1"}, {"id": "t2"}],
            )
            await runner.start()
            await asyncio.wait_for(task, timeout=5.0)

            assert completed[0]["n_completed"] == 2
            assert completed[0]["n_trials_total"] == 2

        asyncio.run(_run())

    def test_abort_stops_runner_and_publishes_aborted(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            aborted: list[dict] = []
            started: list[dict] = []

            def slow_fake(model_name, test, *, host, engine, auth_env):
                import time
                time.sleep(0.05)
                return {
                    "model": model_name, "test_id": test["id"],
                    "failure_reason": "", "elapsed_sec": 0.05,
                    "output_preview": "ok", "signals": {},
                }

            async def listen_abort() -> None:
                async for ev in bus.subscribe("run.aborted"):
                    aborted.append(ev)
                    return

            async def listen_started() -> None:
                async for ev in bus.subscribe("run.trial_started"):
                    started.append(ev)
                    if len(started) == 1:
                        return

            t1 = asyncio.create_task(listen_abort())
            t2 = asyncio.create_task(listen_started())
            await asyncio.sleep(0)

            config = _make_config(n_hosts=1, n_models=10, test_ids=["t1"], repeat=1)
            runner = TuiRunner(
                config=config,
                bus=bus,
                results_dir=None,
                run_test_fn=slow_fake,
                _tests_override=[{"id": "t1"}],
            )
            await runner.start()
            await asyncio.wait_for(t2, timeout=3.0)
            runner.abort()
            await asyncio.wait_for(t1, timeout=3.0)

            assert len(aborted) == 1
            assert aborted[0]["n_completed"] < 10

        asyncio.run(_run())

    def test_unselected_models_are_skipped(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            finished: list[dict] = []

            async def listen() -> None:
                async for ev in bus.subscribe("run.trial_finished"):
                    finished.append(ev)
                    if len(finished) == 1:
                        return

            task = asyncio.create_task(listen())
            await asyncio.sleep(0)

            host = Host(
                name="h",
                url="http://h:11434",
                engine="ollama",
                models=[
                    ModelChoice(name="selected", selected=True),
                    ModelChoice(name="skipped", selected=False),
                ],
            )
            config = FleetConfig(name="t", hosts=[host], tests=["t1"], repeat=1)
            runner = TuiRunner(
                config=config,
                bus=bus,
                results_dir=None,
                run_test_fn=_fake_run_test_fn,
                _tests_override=[{"id": "t1"}],
            )
            await runner.start()
            await asyncio.wait_for(task, timeout=3.0)

            await asyncio.sleep(0.1)
            assert len(finished) == 1
            assert finished[0]["model_name"] == "selected"

        asyncio.run(_run())

    def test_stalled_trial_times_out_and_publishes_error_verdict(self) -> None:
        """A run_fn that stalls beyond trial_timeout must resolve as error, not hang."""
        import threading

        async def _run() -> None:
            bus = SessionBus()
            finished: list[dict] = []
            unblock = threading.Event()

            def stall_fn(model_name, test, *, host, engine, auth_env):
                # Blocks until unblock is set — simulates Ollama stall.
                unblock.wait(timeout=10)
                return {
                    "model": model_name, "test_id": test["id"],
                    "failure_reason": "", "elapsed_sec": 0.0, "output_preview": "", "signals": {},
                }

            async def listen() -> None:
                async for ev in bus.subscribe("run.trial_finished"):
                    finished.append(ev)
                    return

            task = asyncio.create_task(listen())
            await asyncio.sleep(0)

            config = _make_config()
            runner = TuiRunner(
                config=config,
                bus=bus,
                results_dir=None,
                run_test_fn=stall_fn,
                _tests_override=[{"id": "t1"}],
                trial_timeout=0.05,
            )
            await runner.start()
            # Should resolve within a short window — trial_timeout=0.05s + slack.
            await asyncio.wait_for(task, timeout=3.0)
            unblock.set()  # release the stalled thread

            assert finished[0]["verdict"] == "error"
            assert "TIMEOUT" in finished[0]["failure_reason"]

        asyncio.run(_run())

    def test_error_result_publishes_error_verdict(self) -> None:
        async def _run() -> None:
            bus = SessionBus()
            finished: list[dict] = []

            def error_fake(model_name, test, *, host, engine, auth_env):
                return {
                    "model": model_name, "test_id": test["id"],
                    "failure_reason": "TIMEOUT: no response in 90s",
                    "elapsed_sec": 90.0, "output_preview": "", "signals": {},
                }

            async def listen() -> None:
                async for ev in bus.subscribe("run.trial_finished"):
                    finished.append(ev)
                    return

            task = asyncio.create_task(listen())
            await asyncio.sleep(0)

            config = _make_config()
            runner = TuiRunner(
                config=config,
                bus=bus,
                results_dir=None,
                run_test_fn=error_fake,
                _tests_override=[{"id": "t1"}],
            )
            await runner.start()
            await asyncio.wait_for(task, timeout=3.0)

            assert finished[0]["verdict"] == "error"
            assert finished[0]["failure_reason"] == "TIMEOUT: no response in 90s"

        asyncio.run(_run())
