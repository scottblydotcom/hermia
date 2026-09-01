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


# ---------------------------------------------------------------------------
# WITNESS provenance (2026-08-31).
#
# ⚠️ Read the asymmetry before trusting these. `results/` is GITIGNORED — zero
# corpus files are tracked in git — so CI can verify only that a witness has not
# been EDITED since extraction. It cannot verify the row ever existed. That
# second check needs the corpus and is reported NOT RUN when absent, never
# skipped silently.
#
# See docs/superpowers/specs/2026-08-31-witness-grader-completeness.md
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.stem)
def test_witness_responses_match_their_digests(path):
    """A real witness must still hash to what the extractor recorded. Runs in CI."""
    from hermia.corpus_audit.fixtures import verify_response_digest

    _, fixtures = load_fixtures(path)
    problems = [
        f"fixture[{i}]: {reason}"
        for i, fx in enumerate(fixtures)
        if (reason := verify_response_digest(fx)) is not None
    ]
    assert not problems, f"{path.stem}: {problems}"


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.stem)
def test_witness_rows_exist_in_the_corpus(path):
    """A real witness must come from the corpus row it names.

    Requires the corpus, which is gitignored. SKIPPED — loudly — when absent. A skip
    here means provenance is UNVERIFIED, not verified.
    """
    from hermia.corpus_audit.fixtures import verify_corpus_provenance

    _, fixtures = load_fixtures(path)
    witnesses = [fx for fx in fixtures if isinstance(fx.get("provenance"), dict)]
    if not witnesses:
        pytest.skip("no provenance-bearing witnesses in this file")

    problems = []
    for i, fx in enumerate(witnesses):
        try:
            reason = verify_corpus_provenance(fx, _REPO_ROOT)
        except FileNotFoundError as exc:
            pytest.skip(
                f"CORPUS ABSENT — provenance NOT VERIFIED for {path.stem}. This is not a "
                f"pass; it is an unrun check. {exc}"
            )
        if reason is not None:
            problems.append(f"witness[{i}]: {reason}")
    assert not problems, f"{path.stem}: {problems}"
