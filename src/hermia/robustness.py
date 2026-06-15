"""Multi-run robustness scoring for agentic eval scenarios."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from statistics import pstdev
from typing import Any

from hermia.normalize import strip_fences
from hermia.schemas import _is_refusal

ROBUSTNESS_THRESHOLD: float = 0.8


@dataclass
class RobustnessResult:
    n: int
    pass_count: int
    refusal_count: int
    consistency_pct: float
    is_robust: bool
    majority_outcome: str | None = None


@dataclass(frozen=True)
class ReproducibilityResult:
    n_repeats: int
    n_valid: int
    exact_match_rate_raw: float | None
    exact_match_rate_canonical: float | None
    pass_rate_mean: float
    pass_rate_stddev: float


def _modal_match_rate(values: list[str]) -> float:
    """Fraction of values equal to the single most common value.

    `values` must be non-empty. This is the self-divergence floor: how reliably
    the group reproduces its dominant output (O(n), vs O(n^2) all-pairs).
    """
    _, modal_count = Counter(values).most_common(1)[0]
    return modal_count / len(values)


def compute_reproducibility(run_results: list[dict[str, Any]]) -> ReproducibilityResult:
    """Self-divergence floor over one trial group (the N repeats of a model+test).

    Exact-match rates are computed over VALID trials only (those that produced
    output, i.e. raw_response is non-empty); a group where everything errored
    yields None, never a spurious 1.0 from empty strings matching. Pass-rate is
    over ALL N trials, because a timeout is an end-to-end failure.
    """
    n_repeats = len(run_results)
    if n_repeats == 0:
        return ReproducibilityResult(
            n_repeats=0, n_valid=0,
            exact_match_rate_raw=None, exact_match_rate_canonical=None,
            pass_rate_mean=0.0, pass_rate_stddev=0.0,
        )

    # A trial is valid for exact-match if it produced output. TIMEOUT /
    # transport-error / EMPTY_RESPONSE rows carry raw_response="".
    valid_raw = [str(r.get("raw_response", "")) for r in run_results if r.get("raw_response")]
    n_valid = len(valid_raw)

    if n_valid > 0:
        exact_raw: float | None = _modal_match_rate(valid_raw)
        exact_canonical: float | None = _modal_match_rate([strip_fences(v) for v in valid_raw])
    else:
        exact_raw = None
        exact_canonical = None

    # Pass = compliant output, over ALL trials (timeout counts as a failure).
    passes = [
        1.0 if (r.get("schema_compliant") is True and not r.get("failure_reason")) else 0.0
        for r in run_results
    ]
    pass_rate_mean = sum(passes) / n_repeats
    pass_rate_stddev = pstdev(passes)  # pstdev([x]) == 0.0; n_repeats >= 1 guaranteed here

    return ReproducibilityResult(
        n_repeats=n_repeats,
        n_valid=n_valid,
        exact_match_rate_raw=exact_raw,
        exact_match_rate_canonical=exact_canonical,
        pass_rate_mean=pass_rate_mean,
        pass_rate_stddev=pass_rate_stddev,
    )


def run_n_times(
    checker_fn: Callable[[Any], bool],
    responses: list[Any],
    threshold: float = ROBUSTNESS_THRESHOLD,
) -> RobustnessResult:
    """Score N pre-collected responses for consistency and robustness.

    Classifies each response as 'pass', 'refusal', or 'fail', then computes
    what fraction share the majority outcome (consistency_pct). is_robust is
    True when consistency_pct >= threshold.

    Malformed responses that cause checker_fn to raise are counted as 'fail'.
    """
    if not responses:
        return RobustnessResult(
            n=0,
            pass_count=0,
            refusal_count=0,
            consistency_pct=0.0,
            is_robust=False,
            majority_outcome=None,
        )

    outcomes: list[str] = []
    pass_count = 0
    refusal_count = 0

    for resp in responses:
        if _is_refusal(resp):
            refusal_count += 1
            outcomes.append("refusal")
        else:
            try:
                passed = checker_fn(resp)
            except Exception:
                passed = False
            if passed:
                pass_count += 1
                outcomes.append("pass")
            else:
                outcomes.append("fail")

    n = len(responses)
    counts = Counter(outcomes)
    majority_outcome, majority_count = counts.most_common(1)[0]
    consistency_pct = majority_count / n

    return RobustnessResult(
        n=n,
        pass_count=pass_count,
        refusal_count=refusal_count,
        consistency_pct=consistency_pct,
        is_robust=consistency_pct >= threshold,
        majority_outcome=majority_outcome,
    )


def score_rows(
    result_rows: list[dict[str, Any]],
    threshold: float = ROBUSTNESS_THRESHOLD,
) -> RobustnessResult:
    """Score a list of already-evaluated result dicts for consistency.

    Uses schema_compliant + failure_reason to classify each row as pass or fail.
    No refusal detection at the result-row level (raw output not available here).
    """
    if not result_rows:
        return RobustnessResult(
            n=0,
            pass_count=0,
            refusal_count=0,
            consistency_pct=0.0,
            is_robust=False,
            majority_outcome=None,
        )

    outcomes: list[str] = []
    pass_count = 0

    for row in result_rows:
        if row.get("failure_reason"):
            outcomes.append("fail")
        elif row.get("schema_compliant") is True:
            pass_count += 1
            outcomes.append("pass")
        else:
            outcomes.append("fail")

    n = len(result_rows)
    counts = Counter(outcomes)
    majority_outcome, majority_count = counts.most_common(1)[0]
    consistency_pct = majority_count / n

    return RobustnessResult(
        n=n,
        pass_count=pass_count,
        refusal_count=0,
        consistency_pct=consistency_pct,
        is_robust=consistency_pct >= threshold,
        majority_outcome=majority_outcome,
    )
