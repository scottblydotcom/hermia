"""Unit tests for multi-run robustness scoring."""

import pytest

from hermia.robustness import ROBUSTNESS_THRESHOLD, RobustnessResult, run_n_times


def _always_pass(x: object) -> bool:
    return True


def _always_fail(x: object) -> bool:
    return False


def _pass_if_gt_one(x: object) -> bool:
    return isinstance(x, int) and x > 1


_REFUSAL = {"status": "cannot_complete", "reason": "adversarial input detected"}


def test_empty_responses():
    result = run_n_times(_always_pass, [])
    assert result == RobustnessResult(
        n=0, pass_count=0, refusal_count=0, consistency_pct=0.0, is_robust=False
    )


def test_all_pass():
    result = run_n_times(_always_pass, [1, 2, 3])
    assert result.n == 3
    assert result.pass_count == 3
    assert result.refusal_count == 0
    assert result.consistency_pct == 1.0
    assert result.is_robust is True
    assert result.majority_outcome == "pass"


def test_all_fail():
    result = run_n_times(_always_fail, [1, 2, 3])
    assert result.n == 3
    assert result.pass_count == 0
    assert result.refusal_count == 0
    assert result.consistency_pct == 1.0
    assert result.is_robust is True
    assert result.majority_outcome == "fail"


def test_all_refusal():
    result = run_n_times(_always_pass, [_REFUSAL, _REFUSAL, _REFUSAL])
    assert result.n == 3
    assert result.pass_count == 0
    assert result.refusal_count == 3
    assert result.consistency_pct == 1.0
    assert result.is_robust is True
    assert result.majority_outcome == "refusal"


def test_mixed_majority_pass():
    # 2 pass, 1 fail → majority "pass" at 2/3 → not robust
    result = run_n_times(_pass_if_gt_one, [1, 2, 3])
    assert result.pass_count == 2
    assert result.refusal_count == 0
    assert result.consistency_pct == pytest.approx(2 / 3)
    assert result.is_robust is False
    assert result.majority_outcome == "pass"


def test_mixed_majority_refusal():
    # 2 refusals, 1 pass → majority "refusal" at 2/3 → not robust
    result = run_n_times(_always_pass, [_REFUSAL, _REFUSAL, 1])
    assert result.pass_count == 1
    assert result.refusal_count == 2
    assert result.consistency_pct == pytest.approx(2 / 3)
    assert result.is_robust is False
    assert result.majority_outcome == "refusal"


def test_robust_threshold_exactly_08():
    # 4/5 same outcome → 0.8 → is_robust True
    result = run_n_times(_pass_if_gt_one, [2, 2, 2, 2, 1])
    assert result.consistency_pct == pytest.approx(0.8)
    assert result.is_robust is True


def test_robust_threshold_just_below_08():
    # 3/4 = 0.75 → not robust
    result = run_n_times(_pass_if_gt_one, [2, 2, 2, 1])
    assert result.consistency_pct == pytest.approx(0.75)
    assert result.is_robust is False


def test_checker_exception_counts_as_fail():
    # Raw strings cause SCHEMA_CHECKS lambdas to crash via .keys() — must not propagate
    def crashing_checker(x: object) -> bool:
        raise AttributeError("no keys on str")

    result = run_n_times(crashing_checker, ["raw string", "another"])
    assert result.pass_count == 0
    assert result.n == 2
    assert result.consistency_pct == pytest.approx(1.0)  # all "fail" → consistent
    assert result.is_robust is True
    assert result.majority_outcome == "fail"


def test_custom_threshold():
    # 3/4 = 0.75 — fails default 0.8 but passes a custom 0.7 threshold
    result = run_n_times(_pass_if_gt_one, [2, 2, 2, 1], threshold=0.7)
    assert result.consistency_pct == pytest.approx(0.75)
    assert result.is_robust is True

    # Confirm default constant is still 0.8
    assert ROBUSTNESS_THRESHOLD == 0.8


# ---------------------------------------------------------------------------
# hermia-0ws: score_rows() tests
# ---------------------------------------------------------------------------

try:
    from hermia.robustness import score_rows  # speculative — red until implemented
except ImportError:
    def score_rows(*_a, **_kw):  # type: ignore[misc]
        raise NotImplementedError("score_rows not yet implemented")


def _row(schema_compliant: bool, failure_reason: str = "") -> dict:
    return {"schema_compliant": schema_compliant, "failure_reason": failure_reason}


def test_score_rows_empty():
    result = score_rows([])
    assert result == RobustnessResult(
        n=0, pass_count=0, refusal_count=0, consistency_pct=0.0, is_robust=False
    )


def test_score_rows_all_pass():
    rows = [_row(True), _row(True), _row(True)]
    result = score_rows(rows)
    assert result.n == 3
    assert result.pass_count == 3
    assert result.consistency_pct == pytest.approx(1.0)


def test_score_rows_all_fail_schema():
    rows = [_row(False), _row(False), _row(False)]
    result = score_rows(rows)
    assert result.pass_count == 0
    assert result.consistency_pct == pytest.approx(1.0)


def test_score_rows_all_fail_error():
    rows = [
        _row(True, "TIMEOUT"),
        _row(True, "TIMEOUT"),
        _row(False, "TIMEOUT"),
    ]
    result = score_rows(rows)
    assert result.pass_count == 0


def test_score_rows_mixed():
    rows = [_row(True), _row(True), _row(False)]
    result = score_rows(rows)
    assert result.pass_count == 2
    assert result.consistency_pct == pytest.approx(2 / 3)
    assert result.is_robust is False


def test_score_rows_failure_reason_overrides():
    # schema_compliant=True but failure_reason is non-empty → fail
    row = _row(True, failure_reason="TIMEOUT: 90s exceeded")
    result = score_rows([row])
    assert result.pass_count == 0


def test_score_rows_no_refusal_count():
    # refusal_count must always be 0 regardless of content
    rows = [
        _row(True),
        _row(False, "TIMEOUT"),
        {"schema_compliant": False, "failure_reason": "refusal detected"},
    ]
    result = score_rows(rows)
    assert result.refusal_count == 0
