"""Persist evaluation results to timestamped JSON and CSV files."""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def open_run(results_dir: Path) -> tuple[Path, Path]:
    """Create timestamped output files for a new run, return (jsonl_path, csv_path)."""
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return results_dir / f"eval_{ts}.jsonl", results_dir / f"eval_{ts}.csv"


def append_result(result: dict[str, Any], jsonl_path: Path, csv_path: Path) -> None:
    """Append a single test result immediately after it completes."""
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(result) + "\n")

    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=result.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(result)


def load_jsonl(jsonl_path: Path) -> list[dict[str, Any]]:
    """Read all results from a JSONL file, skipping blank and malformed lines."""
    rows: list[dict[str, Any]] = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            if stripped := line.strip():
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    rows.append(data)
    return rows
