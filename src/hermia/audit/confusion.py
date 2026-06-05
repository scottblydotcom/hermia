"""Grade a single response and build a confusion matrix against labeled fixtures."""

from __future__ import annotations

import json
from typing import Any

from hermia.runner import _strip_fences
from hermia.schemas import SCHEMA_CHECKS


def grade_response(test_id: str, response: Any) -> bool:
    """Return the grader's pass/fail verdict for one response.

    Faithfully mirrors runner.run_test's grading: a raw string is fence-stripped
    and JSON-parsed first; a parse failure is a fail. A parsed object is handed to
    the test's SCHEMA_CHECKS callable. An unknown test_id fails closed.
    """
    checker = SCHEMA_CHECKS.get(test_id)
    if checker is None:
        return False
    if isinstance(response, str):
        try:
            parsed = json.loads(_strip_fences(response))
        except json.JSONDecodeError:
            return False
    else:
        parsed = response
    return bool(checker(parsed))
