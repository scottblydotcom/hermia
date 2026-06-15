"""Unit tests for robustness.py — multi-run consistency scoring."""

import pytest

from hermia.robustness import (
    ReproducibilityResult,
    _is_pass,
    compute_reproducibility,
    run_n_times,
    score_rows,
)
from hermia.schemas import SCHEMA_CHECKS

# ---------------------------------------------------------------------------
# run_n_times
# ---------------------------------------------------------------------------

_checker = SCHEMA_CHECKS["tool-calling-basic"]

_PASS_RESP = {"action": "read_file", "params": {"path": "/etc/hosts"}}
_FAIL_RESP = {"action": "unknown", "params": {}}
_REFUSAL_RESP = {"status": "cannot_complete", "reason": "out of scope"}


def test_run_n_times_empty_returns_zero_result() -> None:
    result = run_n_times(_checker, [])
    assert result.n == 0
    assert result.pass_count == 0
    assert result.refusal_count == 0
    assert result.consistency_pct == 0.0
    assert result.is_robust is False
    assert result.majority_outcome is None


def test_run_n_times_all_pass() -> None:
    result = run_n_times(_checker, [_PASS_RESP] * 5)
    assert result.n == 5
    assert result.pass_count == 5
    assert result.refusal_count == 0
    assert result.consistency_pct == pytest.approx(1.0)
    assert result.is_robust is True
    assert result.majority_outcome == "pass"


def test_run_n_times_all_fail() -> None:
    result = run_n_times(_checker, [_FAIL_RESP] * 4)
    assert result.n == 4
    assert result.pass_count == 0
    assert result.consistency_pct == pytest.approx(1.0)
    assert result.is_robust is True
    assert result.majority_outcome == "fail"


def test_run_n_times_all_refusal() -> None:
    result = run_n_times(_checker, [_REFUSAL_RESP] * 3)
    assert result.n == 3
    assert result.refusal_count == 3
    assert result.pass_count == 0
    assert result.majority_outcome == "refusal"
    assert result.is_robust is True


def test_run_n_times_mixed_pass_fail() -> None:
    # 3 pass, 2 fail → majority=pass, consistency=0.6
    responses = [_PASS_RESP] * 3 + [_FAIL_RESP] * 2
    result = run_n_times(_checker, responses)
    assert result.n == 5
    assert result.pass_count == 3
    assert result.majority_outcome == "pass"
    assert result.consistency_pct == pytest.approx(0.6)
    # 0.6 < ROBUSTNESS_THRESHOLD (0.8)
    assert result.is_robust is False


def test_run_n_times_at_threshold_is_robust() -> None:
    # 4/5 = 0.8 == threshold → is_robust True
    responses = [_PASS_RESP] * 4 + [_FAIL_RESP]
    result = run_n_times(_checker, responses, threshold=0.8)
    assert result.is_robust is True


def test_run_n_times_below_threshold_not_robust() -> None:
    # 3/5 = 0.6 < 0.8
    responses = [_PASS_RESP] * 3 + [_FAIL_RESP] * 2
    result = run_n_times(_checker, responses, threshold=0.8)
    assert result.is_robust is False


def test_run_n_times_checker_exception_counted_as_fail() -> None:
    """A checker that raises must be treated as a fail, not propagate."""
    def exploding_checker(p):
        raise ValueError("boom")

    result = run_n_times(exploding_checker, [{"x": 1}, {"x": 2}])
    assert result.pass_count == 0
    assert result.n == 2
    assert result.majority_outcome == "fail"


def test_run_n_times_refusal_bypasses_checker() -> None:
    """Refusals should not be passed to checker_fn."""
    calls = []

    def tracking_checker(p):
        calls.append(p)
        return True

    responses = [_REFUSAL_RESP, _PASS_RESP]
    run_n_times(tracking_checker, responses)
    # Refusal should not have been passed to checker
    assert _REFUSAL_RESP not in calls


def test_run_n_times_custom_threshold() -> None:
    responses = [_PASS_RESP] * 6 + [_FAIL_RESP] * 4
    result = run_n_times(_checker, responses, threshold=0.5)
    assert result.consistency_pct == pytest.approx(0.6)
    assert result.is_robust is True


# ---------------------------------------------------------------------------
# _is_pass — shared pass predicate (score_rows + compute_reproducibility)
# ---------------------------------------------------------------------------

def test_is_pass_clean_compliant_row() -> None:
    assert _is_pass({"schema_compliant": True, "failure_reason": ""}) is True


def test_is_pass_failure_reason_set_is_fail() -> None:
    # Even with schema_compliant True, a failure_reason means fail.
    assert _is_pass({"schema_compliant": True, "failure_reason": "TIMEOUT: 90s"}) is False


def test_is_pass_non_compliant_is_fail() -> None:
    assert _is_pass({"schema_compliant": False, "failure_reason": ""}) is False


def test_is_pass_missing_keys_default_to_fail() -> None:
    assert _is_pass({}) is False


def test_is_pass_schema_compliant_truthy_but_not_true_is_fail() -> None:
    # Strict identity check: only the bool True passes, not truthy values.
    assert _is_pass({"schema_compliant": 1, "failure_reason": ""}) is False


# ---------------------------------------------------------------------------
# score_rows
# ---------------------------------------------------------------------------

def _row(schema_compliant: bool = True, failure_reason: str = "") -> dict:
    return {
        "schema_compliant": schema_compliant,
        "failure_reason": failure_reason,
    }


def test_score_rows_empty() -> None:
    result = score_rows([])
    assert result.n == 0
    assert result.is_robust is False
    assert result.majority_outcome is None


def test_score_rows_all_pass() -> None:
    rows = [_row(schema_compliant=True, failure_reason="") for _ in range(5)]
    result = score_rows(rows)
    assert result.n == 5
    assert result.pass_count == 5
    assert result.refusal_count == 0
    assert result.consistency_pct == pytest.approx(1.0)
    assert result.majority_outcome == "pass"


def test_score_rows_all_fail_via_failure_reason() -> None:
    rows = [_row(schema_compliant=False, failure_reason="SCHEMA_FAIL") for _ in range(3)]
    result = score_rows(rows)
    assert result.pass_count == 0
    assert result.majority_outcome == "fail"


def test_score_rows_false_schema_compliant_without_failure_reason() -> None:
    """schema_compliant=False with no failure_reason still counts as fail."""
    rows = [_row(schema_compliant=False, failure_reason="")]
    result = score_rows(rows)
    assert result.pass_count == 0
    assert result.majority_outcome == "fail"


def test_score_rows_no_refusal_detection() -> None:
    """score_rows never sets refusal_count (raw output not available)."""
    rows = [_row(schema_compliant=True)] * 3
    result = score_rows(rows)
    assert result.refusal_count == 0


def test_score_rows_mixed() -> None:
    rows = [
        _row(schema_compliant=True, failure_reason=""),
        _row(schema_compliant=True, failure_reason=""),
        _row(schema_compliant=False, failure_reason="SCHEMA_FAIL"),
    ]
    result = score_rows(rows)
    assert result.n == 3
    assert result.pass_count == 2
    assert result.majority_outcome == "pass"
    assert result.consistency_pct == pytest.approx(2 / 3)


def test_score_rows_is_robust_at_threshold() -> None:
    # 4 pass, 1 fail → 0.8 == threshold
    rows = [_row(True)] * 4 + [_row(False, "SCHEMA_FAIL")]
    result = score_rows(rows, threshold=0.8)
    assert result.is_robust is True


def test_score_rows_custom_threshold() -> None:
    rows = [_row(True)] * 3 + [_row(False, "JSON_PARSE_ERROR")] * 2
    result = score_rows(rows, threshold=0.5)
    assert result.is_robust is True  # 0.6 >= 0.5


def test_score_rows_error_row_with_empty_raw_response() -> None:
    """Error rows from run_test carry failure_reason set and raw_response="".

    score_rows classifies by failure_reason alone; raw_response is never
    consulted.  An empty raw_response on an error row must count as 'fail'.
    """
    error_row = {
        "schema_compliant": False,
        "failure_reason": "TIMEOUT: no response in 90s",
        "raw_response": "",
    }
    result = score_rows([error_row])
    assert result.pass_count == 0
    assert result.n == 1
    assert result.majority_outcome == "fail"


def test_score_rows_raw_response_field_never_consulted() -> None:
    """raw_response content never affects pass/fail classification.

    score_rows operates on failure_reason and schema_compliant only — raw
    output is not available at this abstraction layer.
    """
    rows = [
        {"schema_compliant": True, "failure_reason": "", "raw_response": '{"action":"ok"}'},
        {"schema_compliant": False, "failure_reason": "SCHEMA_FAIL", "raw_response": '{"bad":1}'},
        {"schema_compliant": False, "failure_reason": "TIMEOUT: 90s", "raw_response": ""},
    ]
    result = score_rows(rows)
    assert result.n == 3
    assert result.pass_count == 1
    assert result.majority_outcome == "fail"  # 2 fail vs 1 pass


# ---------------------------------------------------------------------------
# compute_reproducibility
# ---------------------------------------------------------------------------

def _trial(
    raw_response: str = '{"action":"read"}',
    schema_compliant: bool = True,
    failure_reason: str = "",
) -> dict:
    return {
        "raw_response": raw_response,
        "schema_compliant": schema_compliant,
        "failure_reason": failure_reason,
    }


def test_compute_reproducibility_empty() -> None:
    r = compute_reproducibility([])
    assert r.n_repeats == 0
    assert r.n_valid == 0
    assert r.exact_match_rate_raw is None
    assert r.exact_match_rate_canonical is None
    assert r.pass_rate_mean == 0.0
    assert r.pass_rate_stddev == 0.0


def test_compute_reproducibility_all_identical_pass() -> None:
    rows = [_trial() for _ in range(10)]
    r = compute_reproducibility(rows)
    assert r.n_repeats == 10
    assert r.n_valid == 10
    assert r.exact_match_rate_raw == pytest.approx(1.0)
    assert r.exact_match_rate_canonical == pytest.approx(1.0)
    assert r.pass_rate_mean == pytest.approx(1.0)
    assert r.pass_rate_stddev == pytest.approx(0.0)


def test_compute_reproducibility_modal_raw_rate() -> None:
    # 7 identical, 3 different -> modal raw rate = 0.7
    rows = [_trial('{"x":1}') for _ in range(7)] + [_trial('{"x":2}') for _ in range(3)]
    r = compute_reproducibility(rows)
    assert r.exact_match_rate_raw == pytest.approx(0.7)


def test_compute_reproducibility_canonical_ignores_fences_and_whitespace() -> None:
    # Same JSON, one fenced one bare, one with surrounding whitespace.
    # raw differs (fences/whitespace) but canonical is identical.
    rows = [
        _trial('{"x":1}'),
        _trial('```json\n{"x":1}\n```'),
        _trial('   {"x":1}   '),
    ]
    r = compute_reproducibility(rows)
    assert r.exact_match_rate_raw == pytest.approx(1 / 3)   # all three raw strings differ
    assert r.exact_match_rate_canonical == pytest.approx(1.0)  # all canonicalize equal


def test_compute_reproducibility_all_errored_is_null_not_one() -> None:
    """The poison case: all trials timed out (raw_response=''). Exact-match must be
    null (not 1.0 from empty strings matching), n_valid=0, pass_rate=0."""
    rows = [_trial(raw_response="", schema_compliant=False, failure_reason="TIMEOUT: 90s")
            for _ in range(5)]
    r = compute_reproducibility(rows)
    assert r.n_repeats == 5
    assert r.n_valid == 0
    assert r.exact_match_rate_raw is None
    assert r.exact_match_rate_canonical is None
    assert r.pass_rate_mean == pytest.approx(0.0)


def test_compute_reproducibility_partial_error_excludes_invalid_from_exact_match() -> None:
    """3 valid identical + 2 timeouts: exact-match over the 3 valid (=1.0); n_valid=3;
    pass_rate over all 5 (=0.6)."""
    rows = (
        [_trial('{"x":1}') for _ in range(3)]
        + [_trial(raw_response="", schema_compliant=False, failure_reason="TIMEOUT: 90s")
           for _ in range(2)]
    )
    r = compute_reproducibility(rows)
    assert r.n_repeats == 5
    assert r.n_valid == 3
    assert r.exact_match_rate_raw == pytest.approx(1.0)
    assert r.pass_rate_mean == pytest.approx(0.6)


def test_compute_reproducibility_schema_fail_row_is_valid_for_exact_match() -> None:
    """A SCHEMA_FAIL trial produced output (bad but present) -> counts as valid for
    exact-match, but NOT as a pass."""
    rows = [_trial('{"wrong":1}', schema_compliant=False, failure_reason="SCHEMA_FAIL")
            for _ in range(4)]
    r = compute_reproducibility(rows)
    assert r.n_valid == 4
    assert r.exact_match_rate_raw == pytest.approx(1.0)  # all 4 bad outputs identical
    assert r.pass_rate_mean == pytest.approx(0.0)        # none passed


def test_compute_reproducibility_pass_stddev_matches_formula() -> None:
    # 6 pass, 4 fail (fails still produced output) -> mean 0.6, pstdev = sqrt(.6*.4)
    import math
    rows = (
        [_trial('{"x":1}') for _ in range(6)]
        + [_trial('{"x":1}', schema_compliant=False, failure_reason="SCHEMA_FAIL")
           for _ in range(4)]
    )
    r = compute_reproducibility(rows)
    assert r.pass_rate_mean == pytest.approx(0.6)
    assert r.pass_rate_stddev == pytest.approx(math.sqrt(0.6 * 0.4))


def test_compute_reproducibility_single_trial() -> None:
    r = compute_reproducibility([_trial('{"x":1}')])
    assert r.n_repeats == 1
    assert r.n_valid == 1
    assert r.exact_match_rate_raw == pytest.approx(1.0)
    assert r.pass_rate_mean == pytest.approx(1.0)
    assert r.pass_rate_stddev == pytest.approx(0.0)


def test_compute_reproducibility_asdict_matches_schema() -> None:
    """asdict() of the result must equal the documented 6-field schema exactly."""
    from dataclasses import asdict
    r = compute_reproducibility([_trial('{"x":1}') for _ in range(3)])
    assert isinstance(r, ReproducibilityResult)
    d = asdict(r)
    assert set(d.keys()) == {
        "n_repeats", "n_valid",
        "exact_match_rate_raw", "exact_match_rate_canonical",
        "pass_rate_mean", "pass_rate_stddev",
    }
