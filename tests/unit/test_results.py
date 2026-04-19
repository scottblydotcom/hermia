"""Unit tests for save_results."""

import json
import csv
from pathlib import Path

from hermia.results import save_results


SAMPLE = [
    {
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
]


def test_save_results_creates_files(tmp_path: Path):
    json_out, csv_out = save_results(SAMPLE, tmp_path)
    assert json_out.exists()
    assert csv_out.exists()


def test_save_results_json_content(tmp_path: Path):
    json_out, _ = save_results(SAMPLE, tmp_path)
    data = json.loads(json_out.read_text())
    assert data[0]["model"] == "llama3:8b"
    assert data[0]["tokens_per_sec"] == 50.0


def test_save_results_csv_content(tmp_path: Path):
    _, csv_out = save_results(SAMPLE, tmp_path)
    rows = list(csv.DictReader(csv_out.open()))
    assert rows[0]["test_id"] == "tool-calling-basic"


def test_save_results_empty(tmp_path: Path):
    json_out, csv_out = save_results([], tmp_path)
    assert json_out.exists()
    assert not csv_out.exists()
