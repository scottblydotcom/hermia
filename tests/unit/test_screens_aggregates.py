"""Tests for _backfill_aggregates helper in screens.py (hermia-0ws)."""

import pytest

try:
    from hermia.screens import _backfill_aggregates  # speculative — red until implemented
except ImportError:
    def _backfill_aggregates(*_a, **_kw):  # type: ignore[misc]
        raise NotImplementedError("_backfill_aggregates not yet implemented")


def _run_row(
    run_index: int,
    tokens_per_sec: float,
    schema_compliant: bool = True,
    failure_reason: str = "",
) -> dict:
    return {
        "run_index": run_index,
        "is_cold": run_index == 1,
        "tokens_per_sec": tokens_per_sec,
        "schema_compliant": schema_compliant,
        "failure_reason": failure_reason,
    }


def test_backfill_aggregates_single_run() -> None:
    rows = [_run_row(1, tokens_per_sec=40.0)]
    _backfill_aggregates(rows)
    assert rows[0]["cold_warm_delta_tps"] is None
    assert "consistency_pct" in rows[0]


def test_backfill_aggregates_warm_test_delta_is_none() -> None:
    rows = [
        {**_run_row(1, tokens_per_sec=50.0), "is_cold": False},
        {**_run_row(2, tokens_per_sec=55.0), "is_cold": False},
    ]
    _backfill_aggregates(rows)
    assert rows[0]["cold_warm_delta_tps"] is None
    assert rows[1]["cold_warm_delta_tps"] is None


def test_backfill_aggregates_two_runs_pass_pass() -> None:
    rows = [
        _run_row(1, tokens_per_sec=30.0),
        _run_row(2, tokens_per_sec=50.0),
    ]
    _backfill_aggregates(rows)
    # delta = cold_tps - mean(warm_tps) = 30 - 50 = -20
    assert rows[0]["cold_warm_delta_tps"] == pytest.approx(30.0 - 50.0)
    assert rows[1]["cold_warm_delta_tps"] == pytest.approx(30.0 - 50.0)
    assert rows[0]["consistency_pct"] == pytest.approx(1.0)
    assert rows[1]["consistency_pct"] == pytest.approx(1.0)


def test_backfill_aggregates_all_zero_tps() -> None:
    rows = [
        _run_row(1, tokens_per_sec=0.0, failure_reason="TIMEOUT"),
        _run_row(2, tokens_per_sec=0.0, failure_reason="TIMEOUT"),
        _run_row(3, tokens_per_sec=0.0, failure_reason="TIMEOUT"),
    ]
    _backfill_aggregates(rows)
    for row in rows:
        assert row["cold_warm_delta_tps"] is None


def test_backfill_aggregates_stamps_all_rows() -> None:
    rows = [
        _run_row(1, tokens_per_sec=20.0),
        _run_row(2, tokens_per_sec=40.0),
        _run_row(3, tokens_per_sec=42.0),
    ]
    _backfill_aggregates(rows)
    aggregate_fields = {"cold_warm_delta_tps", "consistency_pct", "pass_count", "robustness_n"}
    for row in rows:
        for field in aggregate_fields:
            assert field in row, f"Row missing field: {field}"
    # All rows should have identical aggregate values
    for field in aggregate_fields:
        assert rows[0][field] == rows[1][field] == rows[2][field]


def test_backfill_aggregates_negative_delta() -> None:
    # cold_tps < warm_tps → delta should be negative (valid, not clamped)
    rows = [
        _run_row(1, tokens_per_sec=10.0),
        _run_row(2, tokens_per_sec=60.0),
        _run_row(3, tokens_per_sec=60.0),
    ]
    _backfill_aggregates(rows)
    delta = rows[0]["cold_warm_delta_tps"]
    assert delta is not None
    assert delta < 0
    assert delta == pytest.approx(10.0 - 60.0)
