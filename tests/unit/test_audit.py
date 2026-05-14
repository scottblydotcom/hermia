"""Unit tests for audit.py — audit retrieval and formatting."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hermia.audit import (
    _enrich,
    _iter_rows,
    render_html,
    render_jsonl,
    run_audit,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_ROW_WITH_SYSTEM = {
    "model": "qwen2.5:32b",
    "test_id": "tool-calling-basic",
    "dimension": "tool-use",
    "host": "http://localhost:11434",
    "elapsed_sec": 1.23,
    "tokens_per_sec": 42.0,
    "failure_reason": "",
    "json_valid": True,
    "schema_compliant": True,
    "raw_system": "You are a helpful assistant.",
    "raw_prompt": "Call get_weather for London.",
    "raw_response": '{"action": "get_weather", "city": "London"}',
}

_ROW_WITHOUT_SYSTEM = {k: v for k, v in _ROW_WITH_SYSTEM.items() if k != "raw_system"}

_ROW_ERROR = {
    **_ROW_WITH_SYSTEM,
    "schema_compliant": False,
    "json_valid": False,
    "failure_reason": "TIMEOUT: no response in 90s",
    "raw_response": "",
}


# ── _enrich ───────────────────────────────────────────────────────────────────


def test_enrich_leaves_row_with_raw_system_unchanged() -> None:
    rows = [dict(_ROW_WITH_SYSTEM)]
    result = list(_enrich(rows))
    assert result[0]["raw_system"] == "You are a helpful assistant."


def test_enrich_adds_raw_system_from_dataset_when_missing() -> None:
    fake_tests = [{"id": "tool-calling-basic", "system": "System from dataset."}]
    with patch("hermia.audit.load_tests_all", return_value=fake_tests):
        result = list(_enrich([dict(_ROW_WITHOUT_SYSTEM)]))
    assert result[0]["raw_system"] == "System from dataset."


def test_enrich_uses_empty_string_when_test_id_not_in_dataset() -> None:
    with patch("hermia.audit.load_tests_all", return_value=[]):
        result = list(_enrich([dict(_ROW_WITHOUT_SYSTEM)]))
    assert result[0]["raw_system"] == ""


def test_enrich_does_not_call_dataset_when_all_rows_have_raw_system() -> None:
    rows = [dict(_ROW_WITH_SYSTEM)]
    with patch("hermia.audit.load_tests_all", side_effect=AssertionError("should not call")):
        result = list(_enrich(rows))
    assert result[0]["raw_system"] == "You are a helpful assistant."


def test_enrich_does_not_mutate_original_row() -> None:
    original = dict(_ROW_WITHOUT_SYSTEM)
    with patch("hermia.audit.load_tests_all", return_value=[]):
        list(_enrich([original]))
    assert "raw_system" not in original


# ── _iter_rows ────────────────────────────────────────────────────────────────


def test_iter_rows_from_file(tmp_path: Path) -> None:
    jl = tmp_path / "eval_20260513_120000.jsonl"
    jl.write_text(json.dumps(_ROW_WITH_SYSTEM) + "\n", encoding="utf-8")
    rows = list(_iter_rows(jl))
    assert len(rows) == 1
    assert rows[0]["test_id"] == "tool-calling-basic"


def test_iter_rows_from_directory(tmp_path: Path) -> None:
    (tmp_path / "eval_20260513_100000.jsonl").write_text(
        json.dumps(_ROW_WITH_SYSTEM) + "\n", encoding="utf-8"
    )
    (tmp_path / "eval_20260513_110000.jsonl").write_text(
        json.dumps(_ROW_ERROR) + "\n", encoding="utf-8"
    )
    rows = list(_iter_rows(tmp_path))
    assert len(rows) == 2


def test_iter_rows_from_directory_ignores_non_eval_files(tmp_path: Path) -> None:
    (tmp_path / "eval_20260513_100000.jsonl").write_text(
        json.dumps(_ROW_WITH_SYSTEM) + "\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("not a jsonl", encoding="utf-8")
    rows = list(_iter_rows(tmp_path))
    assert len(rows) == 1


# ── render_jsonl ──────────────────────────────────────────────────────────────


def test_render_jsonl_one_row_per_line() -> None:
    rows = [_ROW_WITH_SYSTEM, _ROW_ERROR]
    output = render_jsonl(rows)
    lines = [ln for ln in output.splitlines() if ln.strip()]
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["test_id"] == "tool-calling-basic"


def test_render_jsonl_empty_rows() -> None:
    assert render_jsonl([]) == ""


# ── render_html ───────────────────────────────────────────────────────────────


def test_render_html_is_valid_html_document() -> None:
    html = render_html([_ROW_WITH_SYSTEM])
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_render_html_contains_system_prompt() -> None:
    html = render_html([_ROW_WITH_SYSTEM])
    assert "You are a helpful assistant." in html


def test_render_html_contains_user_prompt() -> None:
    html = render_html([_ROW_WITH_SYSTEM])
    assert "Call get_weather for London." in html


def test_render_html_contains_response() -> None:
    html = render_html([_ROW_WITH_SYSTEM])
    assert "get_weather" in html


def test_render_html_escapes_xss() -> None:
    row = {**_ROW_WITH_SYSTEM, "raw_prompt": "<script>alert(1)</script>"}
    html = render_html([row])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_zero_numeric_fields_not_empty() -> None:
    row = {**_ROW_WITH_SYSTEM, "elapsed_sec": 0, "tokens_per_sec": 0.0}
    html = render_html([row])
    assert ">0s<" in html or ">0<" in html


def test_render_html_pass_badge() -> None:
    html = render_html([_ROW_WITH_SYSTEM])
    assert 'badge pass' in html or 'class="badge pass"' in html


def test_render_html_error_badge() -> None:
    html = render_html([_ROW_ERROR])
    assert "ERROR" in html


def test_render_html_summary_shows_totals() -> None:
    html = render_html([_ROW_WITH_SYSTEM, _ROW_ERROR])
    assert "2" in html  # total
    assert "1/2" in html or "Passed: 1" in html


# ── run_audit ─────────────────────────────────────────────────────────────────


def test_run_audit_jsonl_to_stdout(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    jl = tmp_path / "eval_20260513_120000.jsonl"
    jl.write_text(json.dumps(_ROW_WITH_SYSTEM) + "\n", encoding="utf-8")
    run_audit(jl, fmt="jsonl")
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed["test_id"] == "tool-calling-basic"


def test_run_audit_html_to_file(tmp_path: Path) -> None:
    jl = tmp_path / "eval_20260513_120000.jsonl"
    jl.write_text(json.dumps(_ROW_WITH_SYSTEM) + "\n", encoding="utf-8")
    out_file = tmp_path / "report.html"
    run_audit(jl, fmt="html", output=out_file)
    content = out_file.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "You are a helpful assistant." in content


def test_run_audit_enriches_missing_raw_system(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    jl = tmp_path / "eval_old.jsonl"
    jl.write_text(json.dumps(_ROW_WITHOUT_SYSTEM) + "\n", encoding="utf-8")
    fake_tests = [{"id": "tool-calling-basic", "system": "Enriched system."}]
    with patch("hermia.audit.load_tests_all", return_value=fake_tests):
        run_audit(jl, fmt="jsonl")
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed["raw_system"] == "Enriched system."


def test_run_audit_empty_directory_warns_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_audit(tmp_path, fmt="jsonl")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no results found" in captured.err


def test_run_audit_empty_file_warns_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    jl = tmp_path / "eval_empty.jsonl"
    jl.write_text("", encoding="utf-8")
    run_audit(jl, fmt="jsonl")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no results found" in captured.err
