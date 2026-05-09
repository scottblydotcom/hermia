"""Unit tests for hermia-push export module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hermia.export import collect_results, compute_score, push
from hermia.results import load_jsonl

_ROW = {
    "run_id": "20260509T120000Z",
    "run_timestamp": "2026-05-09T12:00:00+00:00",
    "host": "testhost",
    "model": "qwen2.5:32b",
    "test_id": "tool-calling-basic",
    "dimension": "tool-use",
    "json_valid": True,
    "schema_compliant": True,
    "failure_reason": "",
    "tokens": 100,
    "elapsed_sec": 2.0,
    "tokens_per_sec": 50.0,
    "output_preview": "...",
    "peak_cpu_pct": 10.0,
    "peak_ram_used_gb": 8.0,
    "peak_gpu_pct": 85.0,
    "peak_vram_used_gb": 20.0,
}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_load_jsonl_parses_rows(tmp_path: Path) -> None:
    p = tmp_path / "eval_20260509_120000.jsonl"
    _write_jsonl(p, [_ROW])
    rows = load_jsonl(p)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "20260509T120000Z"


def test_load_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "eval_20260509_120000.jsonl"
    p.write_text("\n" + json.dumps(_ROW) + "\n\n")
    assert len(load_jsonl(p)) == 1


def test_collect_results_aggregates_files(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "eval_20260509_120000.jsonl", [_ROW])
    row2 = {**_ROW, "test_id": "security-boundary"}
    _write_jsonl(tmp_path / "eval_20260509_130000.jsonl", [row2])
    rows = collect_results(tmp_path)
    assert len(rows) == 2


def test_collect_results_ignores_non_eval_files(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "eval_20260509_120000.jsonl", [_ROW])
    (tmp_path / "other.jsonl").write_text(json.dumps(_ROW) + "\n")
    assert len(collect_results(tmp_path)) == 1


def test_push_dry_run_prints_without_db(capsys, tmp_path: Path) -> None:
    push([_ROW], dsn="", dry_run=True)
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "Would process 1" in out


def test_push_connection_failure_exits() -> None:
    import sys

    mock_pg = MagicMock()
    mock_extras = MagicMock()
    mock_pg.connect.side_effect = Exception("connection refused")
    with patch.dict(sys.modules, {"psycopg2": mock_pg, "psycopg2.extras": mock_extras}):
        with pytest.raises(SystemExit):
            push([_ROW], dsn="postgresql://bad", dry_run=False)


def test_load_jsonl_skips_malformed_lines(tmp_path: Path) -> None:
    p = tmp_path / "eval_bad.jsonl"
    p.write_text('{"valid": true}\nnot json\n{"also": "valid"}\n')
    rows = load_jsonl(p)
    assert len(rows) == 2


def test_push_inserts_rows() -> None:
    import sys

    mock_pg = MagicMock()
    mock_extras = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.rowcount = 1
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cur
    mock_pg.connect.return_value = mock_conn

    with patch.dict(sys.modules, {"psycopg2": mock_pg, "psycopg2.extras": mock_extras}):
        push([_ROW], dsn="postgresql://test", dry_run=False)

    mock_pg.connect.assert_called_once_with("postgresql://test")
    mock_extras.execute_batch.assert_called_once()


def test_push_skips_rows_missing_mandatory_fields(capsys) -> None:
    import sys

    incomplete_row = {k: v for k, v in _ROW.items() if k != "run_id"}
    mock_pg = MagicMock()
    mock_extras = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.rowcount = 0
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cur
    mock_pg.connect.return_value = mock_conn

    with patch.dict(sys.modules, {"psycopg2": mock_pg, "psycopg2.extras": mock_extras}):
        push([incomplete_row], dsn="postgresql://test", dry_run=False)

    out = capsys.readouterr().out
    assert "Skipped 1" in out
    mock_extras.execute_batch.assert_not_called()


def test_compute_score_full_pass() -> None:
    row = {**_ROW, "failure_reason": "", "json_valid": True, "schema_compliant": True}
    assert compute_score(row) == 100


def test_compute_score_schema_fail() -> None:
    row = {**_ROW, "failure_reason": "", "json_valid": True, "schema_compliant": False}
    assert compute_score(row) == 60


def test_compute_score_invalid_json() -> None:
    row = {**_ROW, "failure_reason": "", "json_valid": False, "schema_compliant": False}
    assert compute_score(row) == 25


def test_compute_score_error() -> None:
    row = {
        **_ROW,
        "failure_reason": "TIMEOUT: no response in 90s",
        "json_valid": False,
        "schema_compliant": False,
    }
    assert compute_score(row) == 0


def test_compute_score_error_overrides_valid_json() -> None:
    # failure_reason takes priority even if json_valid is somehow True
    row = {
        **_ROW,
        "failure_reason": "OLLAMA_ERROR: model not found",
        "json_valid": True,
        "schema_compliant": True,
    }
    assert compute_score(row) == 0


def test_push_dry_run_includes_score(capsys) -> None:
    push([_ROW], dsn="", dry_run=True)
    out = capsys.readouterr().out
    assert "score=100" in out


def test_push_missing_psycopg2_exits() -> None:
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psycopg2":
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(SystemExit):
            push([_ROW], dsn="postgresql://test", dry_run=False)


# ---------------------------------------------------------------------------
# main() — CLI paths
# ---------------------------------------------------------------------------

from hermia.export import main


def test_main_dry_run_no_results(tmp_path: Path) -> None:
    rc = main(dsn="", results_dir=tmp_path, dry_run=True)
    assert rc == 1


def test_main_dry_run_with_results(tmp_path: Path, capsys) -> None:
    _write_jsonl(tmp_path / "eval_20260509_120000.jsonl", [_ROW])
    rc = main(dsn="", results_dir=tmp_path, dry_run=True)
    assert rc == 0
    assert "dry-run" in capsys.readouterr().out


def test_main_missing_results_dir(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(dsn="postgresql://test", results_dir=tmp_path / "missing", dry_run=False)


def test_main_missing_dsn_exits() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(SystemExit):
            main(dsn="", results_dir=Path(d), dry_run=False)


def test_main_dsn_from_env(tmp_path: Path, monkeypatch) -> None:
    _write_jsonl(tmp_path / "eval_20260509_120000.jsonl", [_ROW])
    monkeypatch.setenv("HERMIA_PG_DSN", "postgresql://envtest")
    import sys
    mock_pg = MagicMock()
    mock_extras = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cur
    mock_pg.connect.return_value = mock_conn
    with patch.dict(sys.modules, {"psycopg2": mock_pg, "psycopg2.extras": mock_extras}):
        rc = main(results_dir=tmp_path, dry_run=False)
    assert rc == 0
    mock_pg.connect.assert_called_once_with("postgresql://envtest")
