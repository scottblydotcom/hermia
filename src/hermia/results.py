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


def append_result(
    result: dict[str, Any],
    jsonl_path: Path | None,
    csv_path: Path | None,
) -> None:
    """Append a single test result to JSONL and/or CSV. Pass None to skip either."""
    if jsonl_path is not None:
        with open(jsonl_path, "a") as f:
            f.write(json.dumps(result) + "\n")

    if csv_path is not None:
        write_header = not csv_path.exists()
        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=result.keys())
            if write_header:
                writer.writeheader()
            writer.writerow(result)


def patch_results(jsonl_path: Path, updated_rows: list[dict[str, Any]]) -> None:
    """Re-write rows in a JSONL file matched by (run_id, model, test_id, run_index).

    Reads the full file, replaces any row whose key fields match an entry in
    updated_rows, then writes the file back atomically via a temp file.
    Unmatched rows are left unchanged.
    """
    key = ("run_id", "model", "test_id", "run_index")
    index = {tuple(r[k] for k in key): r for r in updated_rows if all(k in r for k in key)}
    if not index:
        return

    rows = load_jsonl(jsonl_path)
    patched = [index.get(tuple(r.get(k) for k in key), r) for r in rows]

    tmp = jsonl_path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in patched:
            f.write(json.dumps(row) + "\n")
    tmp.replace(jsonl_path)


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
