"""Grade a single response and build a confusion matrix against labeled fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from hermia.normalize import strip_fences
from hermia.schemas import SCHEMA_CHECKS


def raw_and_parsed(response: Any) -> tuple[str, Any, bool]:
    """(raw_text, parsed, parse_failed) for one fixture response, mirroring runner.run_test.

    Defined once on purpose. This repo already carries a bead for three copies of the
    compromise judgment having drifted apart, and every caller that needs BOTH the raw text
    and the parsed object is a place a fourth copy would start.

    A string response is fence-stripped and JSON-parsed, and a parse failure is reported
    rather than swallowed — `parsed is None` alone cannot distinguish a failure from a
    response that legitimately parsed to JSON null.

    A fixture may instead store an already-parsed object, in which case there is no raw model
    text; `json.dumps` reconstructs one so the raw-text gates have something faithful to scan.
    """
    if isinstance(response, str):
        try:
            return response, json.loads(strip_fences(response)), False
        except json.JSONDecodeError:
            return response, None, True
    return json.dumps(response), response, False


def grade_response(test_id: str, response: Any) -> bool:
    """Return the grader's pass/fail verdict for one response.

    Faithfully mirrors runner.run_test's grading: a raw string is fence-stripped
    and JSON-parsed first; a parse failure is a fail. A parsed object is handed to
    the test's SCHEMA_CHECKS callable. An unknown test_id fails closed.
    """
    checker = SCHEMA_CHECKS.get(test_id)
    if checker is None:
        return False
    _raw, parsed, parse_failed = raw_and_parsed(response)
    if parse_failed:
        return False
    return bool(checker(parsed))


@dataclass
class ConfusionMatrix:
    test_id: str
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0
    divergences: list[dict[str, Any]] = field(default_factory=list)


def confusion_matrix(test_id: str, fixtures: list[dict[str, Any]]) -> ConfusionMatrix:
    """Grade every fixture and tally against its expected_verdict.

    false_positive = grader PASSES a response that should FAIL (bad slips through).
    false_negative = grader FAILS a response that should PASS (good rejected).
    Divergences carry the fixture plus a 'kind' tag for triage.
    """
    cm = ConfusionMatrix(test_id=test_id)
    for fx in fixtures:
        actual = grade_response(test_id, fx["response"])
        expected = bool(fx["expected_verdict"])
        if actual and expected:
            cm.tp += 1
        elif not actual and not expected:
            cm.tn += 1
        elif actual and not expected:
            cm.fp += 1
            cm.divergences.append({"kind": "false_positive", **fx})
        else:
            cm.fn += 1
            cm.divergences.append({"kind": "false_negative", **fx})
    return cm
