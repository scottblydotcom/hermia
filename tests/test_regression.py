"""Unit tests for hermia.regression — all synthetic data, no file I/O."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hermia.regression import (
    CRITICAL_SECURITY_TESTS,
    DEFAULT_BASELINE_RUNS,
    RegressionEvent,
    _parse_ts,
    build_baseline,
    detect_regressions,
    format_report,
    load_all_results,
    main,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_result(
    model: str,
    test_id: str,
    schema_compliant: bool,
    run_id: str,
    run_timestamp: str,
    dimension: str = "security",
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Minimal result dict matching the all-results.json schema.

    ``failure_reason`` defaults to what this module models: a SECURITY outcome. Since
    hermia-80te a failing row must say HOW it failed — on a test with decisive raw-text
    coverage a SCHEMA_FAIL is a RESIST (the forbidden content is demonstrably absent),
    so an unqualified failure here means SECURITY_FAIL. Real rows always carry a reason;
    0 of the 6,300 rows in the 2026-07-23 sweep have a failure with an empty one.
    """
    if failure_reason is None:
        failure_reason = "" if schema_compliant else "SECURITY_FAIL"
    return {
        "model": model,
        "test_id": test_id,
        "dimension": dimension,
        "schema_compliant": schema_compliant,
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "failure_reason": failure_reason,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_regression_clean() -> None:
    """Model passes a critical test across baseline and latest run — no events."""
    results = [
        make_result("modelA", "security-boundary", True, "run1", "2026-01-01T00:00:00+00:00"),
        make_result("modelA", "security-boundary", True, "run2", "2026-01-02T00:00:00+00:00"),
        make_result("modelA", "security-boundary", True, "run3", "2026-01-03T00:00:00+00:00"),
    ]
    baseline = build_baseline(results)
    regressions = detect_regressions(results, baseline)
    assert regressions == []


def test_hard_failure_critical_test() -> None:
    """Critical test passes in baseline, fails in latest run → hard alert."""
    results = [
        make_result("modelA", "security-boundary", True, "run1", "2026-01-01T00:00:00+00:00"),
        make_result("modelA", "security-boundary", True, "run2", "2026-01-02T00:00:00+00:00"),
        make_result("modelA", "security-boundary", False, "run3", "2026-01-03T00:00:00+00:00"),
    ]
    baseline = build_baseline(results)
    regressions = detect_regressions(results, baseline)
    assert len(regressions) == 1
    ev = regressions[0]
    assert ev.alert_type == "hard"
    assert ev.test_id == "security-boundary"
    assert ev.model == "modelA"
    assert ev.baseline_rate == 1.0
    assert ev.current_rate == 0.0


def test_soft_alert_pass_rate_drop() -> None:
    """Non-critical security test drops from 100% to 0% → soft alert."""
    non_critical = "system-prompt-extraction-resistance"
    assert non_critical not in CRITICAL_SECURITY_TESTS

    results = [
        make_result("modelA", non_critical, True, f"run{i}", f"2026-01-{i:02}T00:00:00+00:00")
        for i in range(1, 7)  # run1–run6 all pass (baseline = last 5 of first 5 = 1.0)
    ]
    # Latest run fails
    results.append(
        make_result("modelA", non_critical, False, "run7", "2026-01-07T00:00:00+00:00")
    )

    baseline = build_baseline(results)
    regressions = detect_regressions(results, baseline)
    assert len(regressions) == 1
    ev = regressions[0]
    assert ev.alert_type == "soft"
    assert ev.test_id == non_critical
    assert ev.baseline_rate == 1.0
    assert ev.current_rate == 0.0


def test_new_model_no_regression() -> None:
    """A model with only one run (no prior history) must not trigger any alert."""
    results = [
        make_result("newmodel", "security-boundary", False, "run1", "2026-01-01T00:00:00+00:00"),
    ]
    baseline = build_baseline(results)
    regressions = detect_regressions(results, baseline)
    assert regressions == []


def test_non_security_dimension_ignored() -> None:
    """Failures in non-security dimensions are not reported."""
    ts = [f"2026-01-{i:02}T00:00:00+00:00" for i in range(1, 4)]
    compliant = [True, True, False]
    results = [
        make_result(
            "modelA", "tool-calling-basic", compliant[i], f"run{i+1}", ts[i], dimension="tool-use"
        )
        for i in range(3)
    ]
    baseline = build_baseline(results)
    regressions = detect_regressions(results, baseline)
    assert regressions == []


def test_hard_supersedes_soft() -> None:
    """Hard and soft conditions on same critical test → only one hard event."""
    results = [
        make_result(
            "modelA", "security-boundary", True, f"run{i}", f"2026-01-{i:02}T00:00:00+00:00"
        )
        for i in range(1, 7)
    ]
    results.append(
        make_result("modelA", "security-boundary", False, "run7", "2026-01-07T00:00:00+00:00")
    )
    baseline = build_baseline(results)
    regressions = detect_regressions(results, baseline)
    # Drop is >10pp (hard) AND it's a critical test with baseline>0 and current==0
    # Exactly one event, must be hard
    assert len(regressions) == 1
    assert regressions[0].alert_type == "hard"


def test_sort_order_hard_before_soft() -> None:
    """Hard failures must appear before soft alerts in the returned list."""
    non_critical = "scope-escalation-resistance"
    assert non_critical not in CRITICAL_SECURITY_TESTS

    results = [
        # Soft alert for non-critical test (modelA)
        make_result("modelA", non_critical, True, "run1", "2026-01-01T00:00:00+00:00"),
        make_result("modelA", non_critical, True, "run2", "2026-01-02T00:00:00+00:00"),
        make_result("modelA", non_critical, False, "run3", "2026-01-03T00:00:00+00:00"),
        # Hard failure for critical test (modelB)
        make_result("modelB", "security-boundary", True, "run1", "2026-01-01T00:00:00+00:00"),
        make_result("modelB", "security-boundary", True, "run2", "2026-01-02T00:00:00+00:00"),
        make_result("modelB", "security-boundary", False, "run3", "2026-01-03T00:00:00+00:00"),
    ]
    baseline = build_baseline(results)
    regressions = detect_regressions(results, baseline)
    assert len(regressions) == 2
    assert regressions[0].alert_type == "hard"
    assert regressions[1].alert_type == "soft"


def test_format_report_no_regressions() -> None:
    """format_report with empty list includes the header and clean message."""
    report = format_report([])
    assert "Hermia Regression Report" in report
    assert "No regressions detected" in report


def test_format_report_counts() -> None:
    """format_report summary line reflects correct hard/soft counts."""
    results = [
        make_result("modelA", "security-boundary", True, "run1", "2026-01-01T00:00:00+00:00"),
        make_result("modelA", "security-boundary", False, "run2", "2026-01-02T00:00:00+00:00"),
    ]
    baseline = build_baseline(results)
    regressions = detect_regressions(results, baseline)
    report = format_report(regressions)
    assert "1 hard failure(s)" in report
    assert "0 soft alert(s)" in report


# ---------------------------------------------------------------------------
# _parse_ts
# ---------------------------------------------------------------------------


def test_parse_ts_date_only() -> None:
    dt = _parse_ts("2026-01-15")
    assert dt.year == 2026
    assert dt.month == 1
    assert dt.day == 15
    assert dt.tzinfo is not None


def test_parse_ts_naive_datetime_gets_utc() -> None:
    dt = _parse_ts("2026-01-15T12:30:00")
    assert dt.tzinfo is not None
    assert dt.hour == 12


def test_parse_ts_aware_datetime_preserved() -> None:
    dt = _parse_ts("2026-01-15T12:30:00+00:00")
    assert dt.tzinfo is not None
    assert dt.hour == 12


def test_parse_ts_space_separator() -> None:
    dt = _parse_ts("2026-01-15 09:00:00")
    assert dt.year == 2026
    assert dt.hour == 9


# ---------------------------------------------------------------------------
# load_all_results
# ---------------------------------------------------------------------------


def test_load_all_results_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_all_results(tmp_path / "missing.json")


def test_load_all_results_invalid_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json {{{")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_all_results(p)


def test_load_all_results_not_list(tmp_path: Path) -> None:
    p = tmp_path / "obj.json"
    p.write_text(json.dumps({"key": "value"}))
    with pytest.raises(ValueError, match="JSON array"):
        load_all_results(p)


def test_load_all_results_valid(tmp_path: Path) -> None:
    records = [{"model": "a"}, {"model": "b"}]
    p = tmp_path / "results.json"
    p.write_text(json.dumps(records))
    assert load_all_results(p) == records


# ---------------------------------------------------------------------------
# build_baseline — rolling window edge cases
# ---------------------------------------------------------------------------


def test_build_baseline_rolling_window_truncated() -> None:
    """Only the last DEFAULT_BASELINE_RUNS observations count; earlier ones are dropped."""
    # 6 baseline runs all passing, then 1 latest run failing.
    # With window=5, baseline should be 5/5 = 1.0 (all passing in the window).
    results = [
        make_result("m", "security-boundary", True, f"r{i}", f"2026-01-{i:02}T00:00:00+00:00")
        for i in range(1, 8)
    ]
    # Make run7 the latest (highest ts); baseline = runs 1-6
    # Window of 5 = runs 2-6 (all True) → 1.0
    baseline = build_baseline(results, n_runs=DEFAULT_BASELINE_RUNS)
    assert baseline["m"]["security-boundary"] == pytest.approx(1.0)


def test_build_baseline_partial_pass_rate() -> None:
    """Baseline pass rate computed correctly for mixed pass/fail history."""
    # 2 pass, 2 fail in baseline window → 0.5
    results = [
        make_result("m", "security-boundary", True, "r1", "2026-01-01T00:00:00+00:00"),
        make_result("m", "security-boundary", False, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", "security-boundary", True, "r3", "2026-01-03T00:00:00+00:00"),
        make_result("m", "security-boundary", False, "r4", "2026-01-04T00:00:00+00:00"),
        make_result("m", "security-boundary", True, "r5", "2026-01-05T00:00:00+00:00"),  # latest
    ]
    baseline = build_baseline(results)
    # Baseline = r1-r4 (4 entries, window=5 so all taken), 2 pass / 4 total
    assert baseline["m"]["security-boundary"] == pytest.approx(0.5)


def test_build_baseline_multiple_models_independent() -> None:
    """Each model's baseline is computed independently."""
    results = [
        make_result("alpha", "security-boundary", True, "a1", "2026-01-01T00:00:00+00:00"),
        make_result("alpha", "security-boundary", True, "a2", "2026-01-02T00:00:00+00:00"),
        make_result("beta", "security-boundary", False, "b1", "2026-01-01T00:00:00+00:00"),
        make_result("beta", "security-boundary", True, "b2", "2026-01-02T00:00:00+00:00"),
    ]
    baseline = build_baseline(results)
    assert baseline["alpha"]["security-boundary"] == pytest.approx(1.0)
    assert baseline["beta"]["security-boundary"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# detect_regressions — edge cases
# ---------------------------------------------------------------------------


def test_detect_regressions_critical_baseline_zero_no_hard() -> None:
    """Critical test that was already failing (baseline 0%) cannot produce a hard alert."""
    results = [
        make_result("m", "security-boundary", False, "r1", "2026-01-01T00:00:00+00:00"),
        make_result("m", "security-boundary", False, "r2", "2026-01-02T00:00:00+00:00"),
    ]
    baseline = build_baseline(results)
    assert baseline["m"]["security-boundary"] == pytest.approx(0.0)
    regressions = detect_regressions(results, baseline)
    assert regressions == []


def test_detect_regressions_drop_exactly_at_threshold_no_soft() -> None:
    """A pass-rate drop of exactly SOFT_ALERT_THRESHOLD (10 pp) does not trigger soft alert."""
    # baseline 1.0 (1 pass), latest 0.9 → drop = 0.1 exactly → NOT > 0.10 → no alert
    non_critical = "scope-escalation-resistance"
    results = [
        make_result("m", non_critical, True, "r1", "2026-01-01T00:00:00+00:00"),
    ]
    # Use a synthetic baseline of 1.0 and a 10-result latest run at 0.9 (9 pass / 1 fail).
    # Drop = 0.10 exactly — must NOT trigger soft alert (threshold is strictly >).
    latest = [
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, False, "r2", "2026-01-02T00:00:00+00:00"),
    ]
    # baseline = 1.0, current = 0.9 → drop = 0.10 exactly → no soft alert
    regressions = detect_regressions(results + latest, {"m": {non_critical: 1.0}})
    assert all(e.test_id != non_critical for e in regressions)


def test_detect_regressions_model_in_baseline_no_latest_run() -> None:
    """Model present in baseline but with no latest-run results is silently skipped."""
    baseline = {"ghost_model": {"security-boundary": 1.0}}
    # No results at all for ghost_model
    regressions = detect_regressions([], baseline)
    assert regressions == []


def test_detect_regressions_test_not_in_latest_run() -> None:
    """Test present in baseline but absent from latest run is skipped."""
    results = [
        make_result("m", "security-boundary", True, "r1", "2026-01-01T00:00:00+00:00"),
        make_result("m", "security-boundary", True, "r2", "2026-01-02T00:00:00+00:00"),
        # Latest run doesn't include security-boundary at all
        make_result("m", "scope-escalation-resistance", False, "r3", "2026-01-03T00:00:00+00:00"),
    ]
    baseline = build_baseline(results)
    # security-boundary has a baseline but is absent from r3 → no alert
    assert not any(e.test_id == "security-boundary" for e in detect_regressions(results, baseline))


def test_detect_regressions_multiple_results_same_run_averaged() -> None:
    """Multiple rows for the same (model, test_id) in one run_id are averaged."""
    # Baseline: 2 passes in prior run
    # Latest run_id: 3 results — 1 pass, 2 fail → current_rate = 1/3 ≈ 0.33 → drop > 10pp
    non_critical = "scope-escalation-resistance"
    results = [
        make_result("m", non_critical, True, "r1", "2026-01-01T00:00:00+00:00"),
        make_result("m", non_critical, True, "r1", "2026-01-01T00:00:00+00:00"),
        make_result("m", non_critical, True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, False, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", non_critical, False, "r2", "2026-01-02T00:00:00+00:00"),
    ]
    baseline = build_baseline(results)
    regressions = detect_regressions(results, baseline)
    assert len(regressions) == 1
    ev = regressions[0]
    assert ev.alert_type == "soft"
    assert ev.current_rate == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# format_report — soft alert content and mixed counts
# ---------------------------------------------------------------------------


def test_format_report_soft_alert_content() -> None:
    ev = RegressionEvent(
        model="modelX",
        test_id="scope-escalation-resistance",
        alert_type="soft",
        baseline_rate=0.9,
        current_rate=0.7,
        message="modelX/scope-escalation-resistance pass rate dropped 90% → 70% (Δ=20.0 pp).",
    )
    report = format_report([ev])
    assert "[SOFT]" in report
    assert "modelX" in report
    assert "0 hard failure(s), 1 soft alert(s)" in report


def test_format_report_mixed_counts() -> None:
    hard_ev = RegressionEvent(
        model="m", test_id="security-boundary",
        alert_type="hard", baseline_rate=1.0, current_rate=0.0,
        message="CRITICAL",
    )
    soft_ev = RegressionEvent(
        model="m", test_id="scope-escalation-resistance",
        alert_type="soft", baseline_rate=0.9, current_rate=0.7,
        message="soft drop",
    )
    report = format_report([hard_ev, soft_ev])
    assert "1 hard failure(s), 1 soft alert(s)" in report


# ---------------------------------------------------------------------------
# main() — CLI paths
# ---------------------------------------------------------------------------


def test_main_clean_run(tmp_path: Path) -> None:
    """main() returns 0 when no regressions are detected."""
    records = [
        make_result("m", "security-boundary", True, "r1", "2026-01-01T00:00:00+00:00"),
        make_result("m", "security-boundary", True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", "security-boundary", True, "r3", "2026-01-03T00:00:00+00:00"),
    ]
    p = tmp_path / "results.json"
    p.write_text(json.dumps(records))
    rc = main(results_path=str(p), exit_nonzero_on_regression=False)
    assert rc == 0


def test_main_file_not_found(tmp_path: Path) -> None:
    """main() returns 2 when the results file is missing."""
    rc = main(results_path=str(tmp_path / "missing.json"), exit_nonzero_on_regression=False)
    assert rc == 2


def test_main_with_regressions(tmp_path: Path) -> None:
    """main() returns 1 when regressions are detected."""
    records = [
        make_result("m", "security-boundary", True, "r1", "2026-01-01T00:00:00+00:00"),
        make_result("m", "security-boundary", True, "r2", "2026-01-02T00:00:00+00:00"),
        make_result("m", "security-boundary", False, "r3", "2026-01-03T00:00:00+00:00"),
    ]
    p = tmp_path / "results.json"
    p.write_text(json.dumps(records))
    rc = main(results_path=str(p), exit_nonzero_on_regression=False)
    assert rc == 1
