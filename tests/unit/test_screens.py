"""Unit tests for screens.py — pure functions and scoring logic."""

from hermia.screens import RunnerScreen, _backfill_aggregates, _compute_scores, _sanitize_model_id

# ── _sanitize_model_id ────────────────────────────────────────────────────────

def test_sanitize_replaces_colon() -> None:
    assert _sanitize_model_id("llama3:8b") == "llama3_8b"


def test_sanitize_replaces_dot() -> None:
    assert _sanitize_model_id("llama3.1:8b") == "llama3_1_8b"


def test_sanitize_replaces_both() -> None:
    assert _sanitize_model_id("qwen2.5:32b-instruct") == "qwen2_5_32b-instruct"


def test_sanitize_clean_name_unchanged() -> None:
    assert _sanitize_model_id("mistral") == "mistral"


# ── _compute_scores ───────────────────────────────────────────────────────────

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


# ── _backfill_aggregates ──────────────────────────────────────────────────────

def test_backfill_aggregates_empty_list() -> None:
    """Test that _backfill_aggregates handles empty list without error."""
    _backfill_aggregates([])  # Should not raise


# ── RunnerScreen init ─────────────────────────────────────────────────────────

def test_runner_screen_stores_models_and_tests() -> None:
    screen = RunnerScreen(["qwen2.5:32b", "llama3:8b"], ["tool-calling-basic"])
    assert screen.models == ["qwen2.5:32b", "llama3:8b"]
    assert screen.test_ids == ["tool-calling-basic"]
    assert screen.all_results == []