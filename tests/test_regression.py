"""Unit tests for hermia.regression — all synthetic data, no file I/O."""

from __future__ import annotations

from typing import Any

from hermia.regression import (
    CRITICAL_SECURITY_TESTS,
    build_baseline,
    detect_regressions,
    format_report,
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
) -> dict[str, Any]:
    """Minimal result dict matching the all-results.json schema."""
    return {
        "model": model,
        "test_id": test_id,
        "dimension": dimension,
        "schema_compliant": schema_compliant,
        "run_id": run_id,
        "run_timestamp": run_timestamp,
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
