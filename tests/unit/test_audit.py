"""Unit tests for audit.py — audit retrieval and formatting."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hermia.audit import (
    _dominant_execution_path,
    _enrich,
    _iter_rows,
    _spill_verdict,
    render_html,
    render_jsonl,
    render_spill,
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


def test_run_audit_jsonl_to_file(tmp_path: Path) -> None:
    jl = tmp_path / "eval_20260513_120000.jsonl"
    jl.write_text(json.dumps(_ROW_WITH_SYSTEM) + "\n", encoding="utf-8")
    out_file = tmp_path / "audit.jsonl"
    run_audit(jl, fmt="jsonl", output=out_file)
    lines = [ln for ln in out_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["test_id"] == "tool-calling-basic"


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


# hermia-qc: host grouping, per-host summary, dated output, fence badge
# ---------------------------------------------------------------------------


def _make_row(
    host: str = "http://192.168.25.100:11434",
    fleet_host_name: str | None = "node2",
    schema_compliant: bool = True,
    run_timestamp: str = "2026-05-15T16:00:00+00:00",
    had_markdown_fence: bool = False,
    failure_reason: str = "",
) -> dict:
    return {
        "model": "qwen2.5:7b",
        "test_id": "tool-calling-basic",
        "dimension": "tool-use",
        "elapsed_sec": 1.0,
        "tokens_per_sec": 10.0,
        "host": host,
        "fleet_host_name": fleet_host_name,
        "fleet_host_start": run_timestamp,
        "run_timestamp": run_timestamp,
        "schema_compliant": schema_compliant,
        "failure_reason": failure_reason,
        "had_markdown_fence": had_markdown_fence,
        "raw_system": "sys",
        "raw_prompt": "prompt",
        "raw_response": "{}",
    }


def test_render_html_groups_by_host() -> None:
    rows = [
        _make_row(host="http://192.168.25.100:11434", fleet_host_name="node2",
                  run_timestamp="2026-05-15T16:00:00+00:00"),
        _make_row(host="http://192.168.25.10:11434", fleet_host_name="node3",
                  run_timestamp="2026-05-15T17:00:00+00:00"),
    ]
    html = render_html(rows)
    assert "node2" in html
    assert "node3" in html
    # Both host URLs should appear
    assert "192.168.25.100" in html
    assert "192.168.25.10" in html


def test_render_html_per_host_pass_rate() -> None:
    rows = [
        _make_row(schema_compliant=True),
        _make_row(schema_compliant=False, failure_reason="SCHEMA_FAIL"),
    ]
    html = render_html(rows)
    assert "Passed: 1/2" in html


def test_render_html_includes_date() -> None:
    rows = [_make_row()]  # run_timestamp="2026-05-15T16:00:00+00:00"
    html = render_html(rows)
    assert "2026-05-15" in html  # derived from run_timestamp, not date.today()


def test_render_html_out_file(tmp_path: Path) -> None:
    rows = [_make_row()]
    out = tmp_path / "report.html"
    render_html(rows)  # no out_file — just verify it returns a string
    content = render_html(rows)
    out.write_text(content, encoding="utf-8")
    assert out.exists()
    assert "Hermia Audit Report" in out.read_text()


def test_render_html_fence_note_shown() -> None:
    rows = [_make_row(had_markdown_fence=True, schema_compliant=True)]
    html = render_html(rows)
    assert "fenced" in html


def test_render_html_fence_note_absent_when_no_fence() -> None:
    rows = [_make_row(had_markdown_fence=False)]
    html = render_html(rows)
    assert "⚠ fenced" not in html


def test_render_html_host_label_falls_back_to_url() -> None:
    """If fleet_host_name is absent, host URL is used as section label."""
    rows = [_make_row(fleet_host_name=None)]
    html = render_html(rows)
    assert "192.168.25.100:11434" in html


def test_render_html_host_duration_shown() -> None:
    rows = [
        _make_row(run_timestamp="2026-05-15T16:00:00+00:00"),
        _make_row(run_timestamp="2026-05-15T16:05:30+00:00"),
    ]
    html = render_html(rows)
    assert "5m 30s" in html


# ── _dominant_execution_path ──────────────────────────────────────────────────


def _spill_row(
    host: str = "node1",
    model: str = "qwen2.5:32b",
    execution_path: str | None = "gpu",
    vram_server_gb: float | None = 18.0,
    tokens_per_sec: float = 12.0,
    schema_compliant: bool = True,
) -> dict:
    r: dict = {
        "fleet_host_name": host,
        "model": model,
        "tokens_per_sec": tokens_per_sec,
        "schema_compliant": schema_compliant,
        "vram_server_gb": vram_server_gb,
    }
    if execution_path is not None:
        r["execution_path"] = execution_path
    return r


def test_dominant_path_gpu_from_execution_path_field() -> None:
    group = [_spill_row(execution_path="gpu")] * 3
    assert _dominant_execution_path(group) == "gpu"


def test_dominant_path_cpu_from_execution_path_field() -> None:
    group = [_spill_row(execution_path="cpu", vram_server_gb=0.0)] * 3
    assert _dominant_execution_path(group) == "cpu"


def test_dominant_path_partial_majority() -> None:
    group = [
        _spill_row(execution_path="partial"),
        _spill_row(execution_path="partial"),
        _spill_row(execution_path="gpu"),
    ]
    assert _dominant_execution_path(group) == "partial"


def test_dominant_path_falls_back_to_vram_zero_when_no_field() -> None:
    group = [_spill_row(execution_path=None, vram_server_gb=0.0)]
    assert _dominant_execution_path(group) == "cpu"


def test_dominant_path_falls_back_to_probable_gpu_when_vram_nonzero() -> None:
    group = [_spill_row(execution_path=None, vram_server_gb=18.0)]
    assert _dominant_execution_path(group) == "probable_gpu"


def test_dominant_path_unknown_when_no_field_and_no_vram() -> None:
    group = [_spill_row(execution_path=None, vram_server_gb=None)]
    assert _dominant_execution_path(group) == "unknown"


def test_dominant_path_ignores_unknown_values() -> None:
    group = [
        _spill_row(execution_path="unknown"),
        _spill_row(execution_path="gpu"),
    ]
    assert _dominant_execution_path(group) == "gpu"


# ── _spill_verdict ────────────────────────────────────────────────────────────


def test_spill_verdict_delete_cpu_fallback() -> None:
    assert _spill_verdict("cpu", 3.3) == "DELETE — CPU fallback"


def test_spill_verdict_delete_low_tps() -> None:
    v = _spill_verdict("gpu", 2.0)
    assert v.startswith("DELETE")
    assert "t/s" in v


def test_spill_verdict_review_borderline_tps() -> None:
    v = _spill_verdict("gpu", 7.5)
    assert v.startswith("REVIEW")
    assert "t/s" in v


def test_spill_verdict_keep() -> None:
    assert _spill_verdict("gpu", 12.0) == "KEEP"


def test_spill_verdict_keep_partial_spill_fast_enough() -> None:
    assert _spill_verdict("partial", 10.0) == "KEEP"


# ── render_spill ──────────────────────────────────────────────────────────────


def test_render_spill_contains_header() -> None:
    rows = [_spill_row()]
    out = render_spill(rows)
    assert "HOST" in out
    assert "MODEL" in out
    assert "VERDICT" in out


def test_render_spill_keep_verdict_for_gpu_fast_node() -> None:
    rows = [_spill_row(execution_path="gpu", tokens_per_sec=12.0, schema_compliant=True)] * 5
    out = render_spill(rows)
    assert "KEEP" in out


def test_render_spill_delete_verdict_for_cpu_fallback() -> None:
    rows = [_spill_row(execution_path="cpu", vram_server_gb=0.0, tokens_per_sec=3.3)] * 5
    out = render_spill(rows)
    assert "DELETE" in out
    assert "CPU fallback" in out


def test_render_spill_review_verdict_for_borderline_tps() -> None:
    rows = [_spill_row(execution_path="gpu", tokens_per_sec=7.5)] * 5
    out = render_spill(rows)
    assert "REVIEW" in out


def test_render_spill_groups_by_host_and_model() -> None:
    rows = [
        _spill_row(host="node-a", model="qwen2.5:32b", execution_path="gpu"),
        _spill_row(host="node-b", model="qwen2.5:14b", execution_path="cpu", vram_server_gb=0.0),
    ]
    out = render_spill(rows)
    assert "node-a" in out
    assert "node-b" in out
    assert "qwen2.5:32b" in out
    assert "qwen2.5:14b" in out


def test_render_spill_shows_pass_pct() -> None:
    rows = [
        _spill_row(schema_compliant=True),
        _spill_row(schema_compliant=True),
        _spill_row(schema_compliant=False),
        _spill_row(schema_compliant=False),
    ]
    out = render_spill(rows)
    assert "50.0%" in out


def test_render_spill_backward_compat_old_rows_no_execution_path() -> None:
    """Rows without execution_path field fall back to vram heuristic."""
    rows = [_spill_row(execution_path=None, vram_server_gb=0.0, tokens_per_sec=3.3)] * 3
    out = render_spill(rows)
    assert "DELETE" in out
    assert "CPU fallback" in out


def test_render_spill_zero_tps_rows_included_in_median() -> None:
    """0.0 t/s (timeouts) must be included in median — not silently dropped."""
    # 4 timeout rows (0.0 t/s) + 1 fast row (100.0 t/s).
    # If 0.0 is dropped, median = 100.0 → KEEP (wrong).
    # If 0.0 is included, median = 0.0 → DELETE (correct).
    rows = [_spill_row(execution_path="gpu", tokens_per_sec=0.0)] * 4
    rows += [_spill_row(execution_path="gpu", tokens_per_sec=100.0)]
    out = render_spill(rows)
    assert "DELETE" in out


def test_render_spill_none_host_and_model_do_not_crash() -> None:
    """Rows with None host/model must not raise TypeError in format specifier."""
    rows = [{
        "fleet_host_name": None,
        "host": None,
        "model": None,
        "tokens_per_sec": 10.0,
        "schema_compliant": True,
        "vram_server_gb": 8.0,
        "execution_path": "gpu",
    }]
    out = render_spill(rows)  # must not raise
    assert "unknown" in out


# ── run_audit spill format ────────────────────────────────────────────────────


def test_run_audit_spill_to_stdout(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    jl = tmp_path / "eval_20260531_120000.jsonl"
    row = {
        **_make_row(),
        "execution_path": "gpu",
        "vram_server_gb": 18.0,
        "model_size_server_gb": 20.0,
        "tokens_per_sec": 12.0,
    }
    jl.write_text(json.dumps(row) + "\n", encoding="utf-8")
    run_audit(jl, fmt="spill")
    out = capsys.readouterr().out
    assert "HOST" in out
    assert "KEEP" in out


def test_run_audit_spill_to_file(tmp_path: Path) -> None:
    jl = tmp_path / "eval_20260531_120000.jsonl"
    row = {**_make_row(), "execution_path": "cpu", "vram_server_gb": 0.0, "tokens_per_sec": 3.3}
    jl.write_text(json.dumps(row) + "\n", encoding="utf-8")
    out_file = tmp_path / "spill.txt"
    run_audit(jl, fmt="spill", output=out_file)
    content = out_file.read_text(encoding="utf-8")
    assert "DELETE" in content


def test_run_audit_spill_empty_warns_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_audit(tmp_path, fmt="spill")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no results found" in captured.err
