"""Multi-run robustness scoring for agentic eval scenarios."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
