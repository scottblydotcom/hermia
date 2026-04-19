"""Unit tests for incremental result persistence."""

import csv
import json
from pathlib import Path

from hermia.results import append_result, load_jsonl, open_run

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
