"""Unit tests for incremental result persistence."""

import csv
from pathlib import Path

from hermia.results import append_result, load_jsonl, open_run, patch_results

RESULT_A = {
    "model": "llama3:8b",
    "test_id": "tool-calling-basic",
    "json_valid": True,
    "schema_compliant": True,
    "tokens": 120,
    "elapsed_sec": 2.4,
    "tokens_per_sec": 50.0,
    "output_preview": "...",
    "peak_cpu_pct": 20.0,
    "peak_ram_used_gb": 8.0,
    "peak_gpu_pct": 90.0,
    "peak_vram_used_gb": 5.0,
}

RESULT_B = {**RESULT_A, "test_id": "security-boundary", "tokens_per_sec": 48.0}


def test_open_run_creates_parent(tmp_path: Path):
    subdir = tmp_path / "results"
    jsonl, csv_path = open_run(subdir)
    assert subdir.exists()
    assert jsonl.suffix == ".jsonl"
    assert csv_path.suffix == ".csv"


def test_append_result_jsonl(tmp_path: Path):
    jsonl, csv_path = open_run(tmp_path)
    append_result(RESULT_A, jsonl, csv_path)
    rows = load_jsonl(jsonl)
    assert len(rows) == 1
    assert rows[0]["model"] == "llama3:8b"


def test_append_result_incremental(tmp_path: Path):
    jsonl, csv_path = open_run(tmp_path)
    append_result(RESULT_A, jsonl, csv_path)
    append_result(RESULT_B, jsonl, csv_path)
    rows = load_jsonl(jsonl)
    assert len(rows) == 2
    assert rows[1]["test_id"] == "security-boundary"


def test_append_result_csv_header_once(tmp_path: Path):
    jsonl, csv_path = open_run(tmp_path)
    append_result(RESULT_A, jsonl, csv_path)
    append_result(RESULT_B, jsonl, csv_path)
    rows = list(csv.DictReader(open(csv_path)))
    assert len(rows) == 2
    assert rows[0]["tokens_per_sec"] == "50.0"


def test_load_jsonl_empty(tmp_path: Path):
    jsonl, _ = open_run(tmp_path)
    jsonl.write_text("")
    assert load_jsonl(jsonl) == []


# ── patch_results ─────────────────────────────────────────────────────────────

def _run_row(run_index: int, extra: dict | None = None) -> dict:
    row = {
        "run_id": "abc123",
        "host": "http://localhost:11434",
        "model": "qwen2.5:32b",
        "test_id": "tool-calling-basic",
        "run_index": run_index,
        "consistency_pct": None,
        "cold_warm_delta_tps": None,
    }
    if extra:
        row.update(extra)
    return row


def test_patch_results_updates_matching_rows(tmp_path: Path) -> None:
    jsonl, csv_path = open_run(tmp_path)
    r1 = _run_row(1)
    r2 = _run_row(2)
    append_result(r1, jsonl, csv_path)
    append_result(r2, jsonl, csv_path)

    updated = [
        _run_row(1, {"consistency_pct": 1.0, "cold_warm_delta_tps": -5.0}),
        _run_row(2, {"consistency_pct": 1.0, "cold_warm_delta_tps": -5.0}),
    ]
    patch_results(jsonl, updated)

    rows = load_jsonl(jsonl)
    assert len(rows) == 2
    assert rows[0]["consistency_pct"] == 1.0
    assert rows[0]["cold_warm_delta_tps"] == -5.0
    assert rows[1]["consistency_pct"] == 1.0


def test_patch_results_leaves_unmatched_rows_unchanged(tmp_path: Path) -> None:
    jsonl, csv_path = open_run(tmp_path)
    other = {**RESULT_A, "run_id": "other", "model": "llama3:8b",
             "test_id": "other-test", "run_index": 1}
    r1 = _run_row(1)
    append_result(other, jsonl, csv_path)
    append_result(r1, jsonl, csv_path)

    patch_results(jsonl, [_run_row(1, {"consistency_pct": 0.5})])

    rows = load_jsonl(jsonl)
    assert rows[0]["test_id"] == "other-test"
    assert rows[0].get("consistency_pct") is None
    assert rows[1]["consistency_pct"] == 0.5


def test_patch_results_empty_updated_rows_is_noop(tmp_path: Path) -> None:
    jsonl, csv_path = open_run(tmp_path)
    append_result(_run_row(1), jsonl, csv_path)
    original = load_jsonl(jsonl)
    patch_results(jsonl, [])
    assert load_jsonl(jsonl) == original


def test_patch_results_atomic_via_tmp(tmp_path: Path) -> None:
    jsonl, csv_path = open_run(tmp_path)
    append_result(_run_row(1), jsonl, csv_path)
    patch_results(jsonl, [_run_row(1, {"consistency_pct": 0.9})])
    assert not (jsonl.with_suffix(".jsonl.tmp")).exists()


# ---------------------------------------------------------------------------
# hermia-843: JSONL injection round-trip
# ---------------------------------------------------------------------------


def test_jsonl_injection_in_output_preview_does_not_split_record(tmp_path: Path) -> None:
    """An embedded newline + JSON object in output_preview must not become a
    second JSONL record when the file is read back."""
    jsonl, csv_path = open_run(tmp_path)
    row = {**RESULT_A, "output_preview": 'hello\n{"malicious": true}'}
    append_result(row, jsonl, csv_path)
    rows = load_jsonl(jsonl)
    assert len(rows) == 1
    assert rows[0]["output_preview"] == 'hello\n{"malicious": true}'


def test_append_result_is_thread_safe(tmp_path: Path) -> None:
    """Concurrent appends must not drop, interleave, or corrupt JSONL lines."""
    import json
    import threading

    jsonl = tmp_path / "eval_x.jsonl"
    csv = tmp_path / "eval_x.csv"
    n_threads, per_thread = 8, 100

    def worker(tid: int) -> None:
        for i in range(per_thread):
            append_result(
                {"run_id": "r", "host": "h", "model": f"m{tid}", "test_id": f"t{i}"},
                jsonl, csv,
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = load_jsonl(jsonl)
    assert len(rows) == n_threads * per_thread
    for line in jsonl.read_text().splitlines():
        json.loads(line)
