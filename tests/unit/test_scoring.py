"""Unit tests for scoring logic (compute_scores, backfill_aggregates)."""

from hermia.scoring import backfill_aggregates as _backfill_aggregates
from hermia.scoring import compute_scores as _compute_scores


def _result(
    model: str, json_valid: bool, schema_compliant: bool, tps: float = 50.0
) -> dict[str, object]:
    return {
        "model": model,
        "json_valid": json_valid,
        "schema_compliant": schema_compliant,
        "tokens_per_sec": tps,
    }


def test_compute_scores_all_pass() -> None:
    results = [_result("m1", True, True), _result("m1", True, True)]
    scored = _compute_scores(results)
    assert len(scored) == 1
    model, jp, sp, ag, tps = scored[0]
    assert model == "m1"
    assert jp == 1.0
    assert sp == 1.0
    assert ag == 1.0


def test_compute_scores_all_fail() -> None:
    results = [_result("m1", False, False)]
    _, jp, sp, ag, _ = _compute_scores(results)[0]
    assert jp == 0.0
    assert sp == 0.0
    assert ag == 0.0


def test_compute_scores_agentic_formula() -> None:
    # json_valid=True, schema_compliant=False → jp=1.0, sp=0.0, ag=0.4
    results = [_result("m1", True, False)]
    _, jp, sp, ag, _ = _compute_scores(results)[0]
    assert jp == 1.0
    assert sp == 0.0
    assert abs(ag - 0.4) < 1e-9


def test_compute_scores_partial_schema_pass() -> None:
    results = [
        _result("m1", True, True),
        _result("m1", True, False),
    ]
    _, jp, sp, ag, _ = _compute_scores(results)[0]
    assert jp == 1.0
    assert sp == 0.5
    assert abs(ag - (1.0 * 0.40 + 0.5 * 0.60)) < 1e-9


def test_compute_scores_avg_tps() -> None:
    results = [_result("m1", True, True, tps=40.0), _result("m1", True, True, tps=60.0)]
    _, _, _, _, tps = _compute_scores(results)[0]
    assert tps == 50.0


def test_compute_scores_sorted_by_agentic_descending() -> None:
    results = [
        _result("weak", False, False),
        _result("strong", True, True),
        _result("mid", True, False),
    ]
    scored = _compute_scores(results)
    models = [s[0] for s in scored]
    assert models == ["strong", "mid", "weak"]


def test_compute_scores_multiple_models_separate() -> None:
    results = [_result("a", True, True), _result("b", False, False)]
    scored = _compute_scores(results)
    assert len(scored) == 2
    assert scored[0][0] == "a"
    assert scored[1][0] == "b"


def test_backfill_aggregates_empty_list() -> None:
    _backfill_aggregates([])
