"""CI lock: every committed fixture file's graders match their expected verdicts.

As Plan 2 produces response-fixtures/<test_id>.json per audited test, this test
guarantees no future grader edit silently regresses a verified verdict.
"""
from pathlib import Path

import pytest

from hermia.corpus_audit.confusion import confusion_matrix
from hermia.corpus_audit.fixtures import load_fixtures, validate_fixture_file

_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "response-fixtures"
_FILES = sorted(_FIXTURE_DIR.glob("*.json"))


def test_fixture_dir_is_present():
    assert _FIXTURE_DIR.is_dir(), f"missing {_FIXTURE_DIR}"
    assert _FILES, "no fixture files yet"


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.stem)
def test_fixture_file_is_valid(path):
    validate_fixture_file(path)


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.stem)
def test_grader_matches_all_expected_verdicts(path):
    test_id, fixtures = load_fixtures(path)
    cm = confusion_matrix(test_id, fixtures)
    assert not cm.divergences, (
        f"{test_id}: grader disagrees with {len(cm.divergences)} labeled fixture(s): "
        f"{[d['kind'] for d in cm.divergences]}"
    )
