"""Tests for JsonlCsvSink and PostgresSink local adapters."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hermia.sink.local import JsonlCsvSink, PostgresSink

# ---------------------------------------------------------------------------
# JsonlCsvSink
# ---------------------------------------------------------------------------


def test_jsonl_csv_sink_calls_append_result_per_row(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "test.jsonl"
    csv_path = tmp_path / "test.csv"
    rows = [{"model": "a", "score": 1}, {"model": "b", "score": 2}]

    with patch("hermia.sink.local.append_result") as mock_append:
        JsonlCsvSink(jsonl_path, csv_path).write(rows)

    assert mock_append.call_count == 2
    mock_append.assert_any_call(rows[0], jsonl_path, csv_path)
    mock_append.assert_any_call(rows[1], jsonl_path, csv_path)


def test_jsonl_csv_sink_rows_persist(tmp_path: Path) -> None:
    """Integration: rows actually land in the JSONL file via the real writer."""
    from hermia.results import load_jsonl

    jsonl_path = tmp_path / "test.jsonl"
    csv_path = tmp_path / "test.csv"
    rows = [{"model": "a", "score": 1}, {"model": "b", "score": 2}]

    JsonlCsvSink(jsonl_path, csv_path).write(rows)

    loaded = load_jsonl(jsonl_path)
    assert loaded == rows


# ---------------------------------------------------------------------------
# PostgresSink
# ---------------------------------------------------------------------------


def test_postgres_sink_dry_run_true() -> None:
    dsn = "postgresql://localhost/testdb"
    rows = [{"model": "a", "score": 1}]

    with patch("hermia.sink.local.push") as mock_push:
        PostgresSink(dsn, dry_run=True).write(rows)

    mock_push.assert_called_once_with(rows, dsn, dry_run=True)


def test_postgres_sink_default_dry_run_false() -> None:
    dsn = "postgresql://localhost/testdb"
    rows = [{"model": "a", "score": 1}]

    with patch("hermia.sink.local.push") as mock_push:
        PostgresSink(dsn).write(rows)

    mock_push.assert_called_once_with(rows, dsn, dry_run=False)
