"""Persist evaluation results to timestamped JSON and CSV files."""

import csv
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_write_lock = threading.Lock()


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
    """Append a single test result to JSONL and/or CSV. Pass None to skip either.

    Thread-safe: a process-wide lock serializes all writes so concurrent fleet
    workers cannot interleave or drop result lines.
    """
    with _write_lock:
        if jsonl_path is not None:
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")

        if csv_path is not None:
            # Fieldnames MUST come from the header already on disk, not from this
            # row. Deriving them per-row wrote later rows' values under the first
            # row's column names whenever the key sets differed — silently, with
            # no exception, so a JSONL-only test passed over corrupt CSV
            # (hermia-0hqm). Rows written before the header existed decide it.
            fieldnames = _existing_header(csv_path)
            write_header = fieldnames is None
            if fieldnames is None:
                fieldnames = list(result.keys())
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=fieldnames, extrasaction="ignore", restval=""
                )
                if write_header:
                    writer.writeheader()
                writer.writerow(result)


def _existing_header(csv_path: Path) -> list[str] | None:
    """Return the column names already written to csv_path, or None if there are none.

    A zero-byte file counts as "no header" — it exists, but committing to its
    (absent) columns would make the first data row masquerade as the header.
    Called under _write_lock so the check and the append cannot interleave.
    """
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return None
    with open(csv_path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), None)
    return header or None


def patch_results(jsonl_path: Path, updated_rows: list[dict[str, Any]]) -> None:
    """Re-write rows in a JSONL file matched by (run_id, model, test_id, run_index).

    Reads the full file, replaces any row whose key fields match an entry in
    updated_rows, then writes the file back atomically via a temp file.
    Unmatched rows are left unchanged.
    """
    key = ("run_id", "host", "model", "test_id", "run_index")
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
