"""Unit tests for regression.py — baseline building and regression detection."""

import json
import sys
from pathlib import Path

import pytest

from hermia.regression import (
    CRITICAL_SECURITY_TESTS,
    DEFAULT_BASELINE_RUNS,
    SOFT_ALERT_THRESHOLD,
    RegressionEvent,
    build_baseline,
    detect_regressions,
    format_report,
    load_all_results,
    main,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(
    model: str = "llama3:8b",
    test_id: str = "security-boundary",
    dimension: str = "security",
    schema_compliant: bool = True,
    run_id: str = "run-001",
    run_timestamp: str = "2026-01-01T10:00:00+00:00",
) -> dict:
    return {
        "model": model,
        "test_id": test_id,
        "dimension": dimension,
        "schema_compliant": schema_compliant,
        "run_id": run_id,
        "run_timestamp": run_timestamp,
    }


# ---------------------------------------------------------------------------
# load_all_results
# ---------------------------------------------------------------------------


def test_load_all_results_returns_list(tmp_path: Path) -> None:
    data = [{"model": "x"}]
    f = tmp_path / "all-results.json"
    f.write_text(json.dumps(data))
    assert load_all_results(f) == data


def test_load_all_results_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_all_results(tmp_path / "missing.json")


def test_load_all_results_invalid_json(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("not json{{")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_all_results(f)


def test_load_all_results_not_a_list(tmp_path: Path) -> None:
    f = tmp_path / "obj.json"
    f.write_text(json.dumps({"key": "value"}))
    with pytest.raises(ValueError, match="JSON array"):
        load_all_results(f)


# ---------------------------------------------------------------------------
# _parse_ts (indirectly via build_baseline)
# ---------------------------------------------------------------------------


def test_date_only_timestamp_accepted() -> None:
    """build_baseline should not raise when run_timestamp is a plain date."""
    rows = [
        _row(run_id="r1", run_timestamp="2026-01-01"),
        _row(run_id="r2", run_timestamp="2026-01-02"),
    ]
    # should not raise
    baseline = build_baseline(rows)
    assert isinstance(baseline, dict)


# ---------------------------------------------------------------------------
# build_baseline
# ---------------------------------------------------------------------------


def test_build_baseline_empty_results() -> None:
    assert build_baseline([]) == {}


def test_build_baseline_excludes_non_security() -> None:
    rows = [_row(dimension="tool-use", run_id="r1"), _row(dimension="tool-use", run_id="r2")]
    assert build_baseline(rows) == {}


def test_build_baseline_excludes_latest_run() -> None:
    """The most recent run_id per model must not appear in the baseline."""
    rows = [
        _row(run_id="r1", run_timestamp="2026-01-01T00:00:00+00:00", schema_compliant=True),
        _row(run_id="r2", run_timestamp="2026-01-02T00:00:00+00:00", schema_compliant=False),
    ]
    baseline = build_baseline(rows)
    # Only r1 should be in baseline; r2 is the latest
    assert baseline["llama3:8b"]["security-boundary"] == 1.0  # r1 passed


def test_build_baseline_pass_rate_computed() -> None:
    rows = [
        _row(run_id="r1", run_timestamp="2026-01-01T00:00:00+00:00", schema_compliant=True),
        _row(run_id="r2", run_timestamp="2026-01-02T00:00:00+00:00", schema_compliant=False),
        _row(run_id="r3", run_timestamp="2026-01-03T00:00:00+00:00", schema_compliant=True),
        # r3 is latest — excluded from baseline, r1+r2 form baseline
    ]
    baseline = build_baseline(rows)
    # r1 passed (1), r2 failed (0) → 0.5
    assert baseline["llama3:8b"]["security-boundary"] == pytest.approx(0.5)


def test_build_baseline_rolling_window_respects_n_runs() -> None:
    """Only the last n_runs observations are used."""
    rows = [
        _row(run_id=f"r{i}", run_timestamp=f"2026-01-0{i}T00:00:00+00:00", schema_compliant=i % 2 == 0)
        for i in range(1, 6)
    ]
    # r5 is the latest — excluded; r1–r4 are baseline candidates
    # n_runs=2 means only r3 and r4 (most recent 2)
    baseline = build_baseline(rows, n_runs=2)
    # r3: compliant=(3%2==0)=False; r4: compliant=(4%2==0)=True → 0.5
    assert baseline["llama3:8b"]["security-boundary"] == pytest.approx(0.5)


def test_build_baseline_multiple_models() -> None:
    rows = [
        _row(model="a", run_id="r1", run_timestamp="2026-01-01T00:00:00+00:00", schema_compliant=True),
        _row(model="a", run_id="r2", run_timestamp="2026-01-02T00:00:00+00:00", schema_compliant=True),
        _row(model="b", run_id="r1", run_timestamp="2026-01-01T00:00:00+00:00", schema_compliant=False),
        _row(model="b", run_id="r2", run_timestamp="2026-01-02T00:00:00+00:00", schema_compliant=True),
    ]
    baseline = build_baseline(rows)
    assert "a" in baseline
    assert "b" in baseline


# ---------------------------------------------------------------------------
# detect_regressions
# ---------------------------------------------------------------------------


def _make_dataset(
    baseline_passes: list[bool],
    latest_passes: list[bool],
    model: str = "llama3:8b",
    test_id: str = "security-boundary",
    dimension: str = "security",
) -> list[dict]:
    rows = []
    for i, sc in enumerate(baseline_passes):
        rows.append(_row(
            model=model, test_id=test_id, dimension=dimension,
            schema_compliant=sc,
            run_id=f"r{i+1}",
            # encode sequence as seconds offset to avoid day/month overflow
            run_timestamp=f"2026-01-01T{i // 3600:02d}:{(i % 3600) // 60:02d}:{i % 60:02d}+00:00",
        ))
    # latest run gets a later timestamp
    for j, sc in enumerate(latest_passes):
        rows.append(_row(
            model=model, test_id=test_id, dimension=dimension,
            schema_compliant=sc,
            run_id="latest",
            run_timestamp=f"2026-02-01T{j // 3600:02d}:{(j % 3600) // 60:02d}:{j % 60:02d}+00:00",
        ))
    return rows


def test_detect_regressions_no_regression() -> None:
    rows = _make_dataset(baseline_passes=[True, True], latest_passes=[True])
    baseline = build_baseline(rows)
    events = detect_regressions(rows, baseline)
    assert events == []


def test_detect_regressions_hard_failure_critical_test() -> None:
    rows = _make_dataset(
        baseline_passes=[True, True],
        latest_passes=[False],
        test_id="security-boundary",
    )
    baseline = build_baseline(rows)
    events = detect_regressions(rows, baseline)
    assert len(events) == 1
    assert events[0].alert_type == "hard"
    assert events[0].model == "llama3:8b"
    assert events[0].test_id == "security-boundary"
    assert events[0].current_rate == 0.0


def test_detect_regressions_soft_alert_non_critical() -> None:
    rows = _make_dataset(
        baseline_passes=[True, True],
        latest_passes=[False],
        test_id="tool-calling-basic",
        dimension="security",
    )
    baseline = build_baseline(rows)
    events = detect_regressions(rows, baseline)
    assert len(events) == 1
    assert events[0].alert_type == "soft"


def test_detect_regressions_hard_takes_priority_over_soft() -> None:
    """When both hard and soft conditions apply, only hard is emitted."""
    rows = _make_dataset(
        baseline_passes=[True, True],
        latest_passes=[False],
        test_id="security-boundary",
    )
    baseline = build_baseline(rows)
    events = detect_regressions(rows, baseline)
    assert all(e.alert_type == "hard" for e in events)
    assert len(events) == 1


def test_detect_regressions_new_model_not_flagged() -> None:
    """A model with no baseline entry is never flagged."""
    rows = _make_dataset(baseline_passes=[True], latest_passes=[False])
    # provide an empty baseline (simulates new model)
    events = detect_regressions(rows, {})
    assert events == []


def test_detect_regressions_below_soft_threshold_not_flagged() -> None:
    """A 5pp drop (< 10pp threshold) should not trigger a soft alert."""
    # 20 baseline runs: 19 pass → rate = 0.95; latest: 18/19 pass → rate ≈ 0.947
    # drop ≈ 0.003 — well below SOFT_ALERT_THRESHOLD
    rows = _make_dataset(
        baseline_passes=[True] * 19 + [False],
        latest_passes=[True] * 19,
        test_id="tool-calling-basic",
        dimension="security",
    )
    baseline = build_baseline(rows)
    events = detect_regressions(rows, baseline)
    assert events == []


def test_detect_regressions_no_security_rows() -> None:
    rows = [_row(dimension="tool-use")]
    events = detect_regressions(rows, {})
    assert events == []


def test_detect_regressions_sorted_hard_first() -> None:
    rows = (
        _make_dataset([True, True], [False], model="z-model", test_id="security-boundary")
        + _make_dataset([True, True], [False], model="a-model", test_id="tool-calling-basic", dimension="security")
    )
    baseline = build_baseline(rows)
    events = detect_regressions(rows, baseline)
    hard = [e for e in events if e.alert_type == "hard"]
    soft = [e for e in events if e.alert_type == "soft"]
    assert hard
    # hard events all appear before soft events
    if soft:
        last_hard_idx = max(i for i, e in enumerate(events) if e.alert_type == "hard")
        first_soft_idx = min(i for i, e in enumerate(events) if e.alert_type == "soft")
        assert last_hard_idx < first_soft_idx


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------


def test_format_report_no_regressions() -> None:
    report = format_report([])
    assert "No regressions detected" in report


def test_format_report_hard_event() -> None:
    ev = RegressionEvent(
        model="llama3:8b",
        test_id="security-boundary",
        alert_type="hard",
        baseline_rate=1.0,
        current_rate=0.0,
        message="CRITICAL: llama3:8b previously passed security-boundary.",
    )
    report = format_report([ev])
    assert "[HARD]" in report
    assert "1 hard failure" in report
    assert "0 soft alert" in report


def test_format_report_soft_event() -> None:
    ev = RegressionEvent(
        model="llama3:8b",
        test_id="tool-calling-basic",
        alert_type="soft",
        baseline_rate=0.9,
        current_rate=0.7,
        message="llama3:8b/tool-calling-basic pass rate dropped.",
    )
    report = format_report([ev])
    assert "[SOFT]" in report
    assert "0 hard failure" in report
    assert "1 soft alert" in report


def test_format_report_summary_counts() -> None:
    hard = RegressionEvent("m", "t1", "hard", 1.0, 0.0, "hard msg")
    soft = RegressionEvent("m", "t2", "soft", 0.9, 0.7, "soft msg")
    report = format_report([hard, soft])
    assert "1 hard failure" in report
    assert "1 soft alert" in report


# ---------------------------------------------------------------------------
# main() — CLI entry point
# ---------------------------------------------------------------------------


def test_main_no_regressions_returns_0(tmp_path: Path) -> None:
    rows = _make_dataset(baseline_passes=[True, True], latest_passes=[True])
    f = tmp_path / "all-results.json"
    f.write_text(json.dumps(rows))
    code = main(results_path=f, exit_nonzero_on_regression=False)
    assert code == 0


def test_main_with_regression_returns_1(tmp_path: Path) -> None:
    rows = _make_dataset(
        baseline_passes=[True, True],
        latest_passes=[False],
        test_id="security-boundary",
    )
    f = tmp_path / "all-results.json"
    f.write_text(json.dumps(rows))
    code = main(results_path=f, exit_nonzero_on_regression=False)
    assert code == 1


def test_main_missing_file_returns_2(tmp_path: Path, capsys) -> None:
    code = main(results_path=tmp_path / "nope.json", exit_nonzero_on_regression=False)
    assert code == 2
    captured = capsys.readouterr()
    assert "hermia-regression" in captured.err


def test_main_invalid_json_returns_2(tmp_path: Path, capsys) -> None:
    f = tmp_path / "bad.json"
    f.write_text("{{not valid")
    code = main(results_path=f, exit_nonzero_on_regression=False)
    assert code == 2
