"""Aggregate scoring helpers — per-model rollup and per-row aggregate backfill."""

import statistics
from typing import Any

from hermia import robustness


def compute_scores(
    results: list[dict[str, Any]],
) -> list[tuple[str, float, float, float, float]]:
    """Aggregate per-model scores from a flat result list.

    Returns list of (model, json_pass_rate, schema_pass_rate, agentic_score, avg_tps)
    sorted descending by agentic_score.
    """
    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_model.setdefault(r["model"], []).append(r)
    scored = []
    for model, rs in by_model.items():
        n = len(rs)
        jp = sum(r["json_valid"] for r in rs) / n
        sp = sum(r["schema_compliant"] for r in rs) / n
        ag = (jp * 0.40) + (sp * 0.60)
        tps = sum(r["tokens_per_sec"] for r in rs) / n
        scored.append((model, jp, sp, ag, tps))
    scored.sort(key=lambda x: x[3], reverse=True)
    return scored


def backfill_aggregates(run_results: list[dict[str, Any]]) -> None:
    """Compute cold_warm_delta_tps and robustness fields; stamp onto each row in-place."""
    if not run_results:
        return
    if len(run_results) == 1 or not run_results[0].get("is_cold"):
        delta: float | None = None
    else:
        cold_tps = float(run_results[0].get("tokens_per_sec", 0.0))
        warm_tps_list = [float(r.get("tokens_per_sec", 0.0)) for r in run_results[1:]]
        if cold_tps == 0.0 and all(t == 0.0 for t in warm_tps_list):
            delta = None
        else:
            delta = cold_tps - statistics.mean(warm_tps_list)

    result = robustness.score_rows(run_results)

    for row in run_results:
        row["cold_warm_delta_tps"] = delta
        row["consistency_pct"] = result.consistency_pct
        row["pass_count"] = result.pass_count
        row["robustness_n"] = result.n
