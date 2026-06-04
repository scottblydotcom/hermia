"""Local sink adapters — thin wrappers over existing results/export writers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from hermia.export import push
from hermia.results import append_result


class JsonlCsvSink:
    """Writes each row via the existing ``append_result`` writer."""

    def __init__(self, jsonl_path: Path, csv_path: Path) -> None:
        self.jsonl_path = jsonl_path
        self.csv_path = csv_path

    def write(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            append_result(row, self.jsonl_path, self.csv_path)


class PostgresSink:
    """Pushes a batch of rows to Postgres via the existing ``push`` writer."""

    def __init__(self, dsn: str, dry_run: bool = False) -> None:
        self.dsn = dsn
        self.dry_run = dry_run

    def write(self, rows: list[dict[str, Any]]) -> None:
        push(rows, self.dsn, dry_run=self.dry_run)
