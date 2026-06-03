"""Concurrent fleet dispatch: all rows land, same-host entries serialize."""
import threading
from pathlib import Path

from hermia import fleet
from hermia.results import load_jsonl

# _run_host_eval imports run_test / load_tests_all / get_available_models locally
# from hermia.runner, so patch them at their definition site (matches the rest of
# the fleet test suite).


def _setup(monkeypatch, active: dict, max_seen: dict):
    monkeypatch.setattr("hermia.runner.load_tests_all", lambda: [{"id": "t1"}], raising=False)
    monkeypatch.setattr("hermia.runner.get_available_models",
                        lambda host=None, headers=None: [{"name": "m1"}], raising=False)
    lock = threading.Lock()

    def fake_run_test(model, test, sampler, host=None, headers=None, transport=None):
        with lock:
            active["n"] += 1
            max_seen["n"] = max(max_seen["n"], active["n"])
        # simulate work so overlap is observable
        for _ in range(1000000):
            pass
        with lock:
            active["n"] -= 1
        return {"model": model, "test_id": test["id"], "failure_reason": "",
                "elapsed_sec": 0.1, "tokens_per_sec": 1.0}
    monkeypatch.setattr("hermia.runner.run_test", fake_run_test, raising=False)


def test_distinct_hosts_run_concurrently(tmp_path: Path, monkeypatch) -> None:
    active, max_seen = {"n": 0}, {"n": 0}
    _setup(monkeypatch, active, max_seen)
    entries = [{"name": f"n{i}", "host": f"http://h{i}:11434"} for i in range(4)]
    out = fleet.run_fleet(entries, repeat=1, results_dir=tmp_path,
                          print_fn=lambda s: None, verbosity=-1, max_concurrency=4)
    rows = load_jsonl(out)
    assert len(rows) == 4                       # every host wrote its row
    assert max_seen["n"] >= 2                    # genuine overlap occurred


def test_same_host_entries_do_not_overlap(tmp_path: Path, monkeypatch) -> None:
    active, max_seen = {"n": 0}, {"n": 0}
    _setup(monkeypatch, active, max_seen)
    entries = [{"name": "a", "host": "http://h1:11434"},
               {"name": "b", "host": "http://h1:11434"}]  # same box
    fleet.run_fleet(entries, repeat=1, results_dir=tmp_path,
                    print_fn=lambda s: None, verbosity=-1, max_concurrency=4)
    assert max_seen["n"] == 1                     # never ran concurrently on one host
