"""Framework taxonomy validation tests for Hermia.

This module validates:
1. The structure of every corpus case's 'frameworks' field — exact key set,
   list values, string items.
2. Coverage statistics: asserts the corpus actually exercises framework tags
   and emits a human-readable tally via stdout for inspection.
"""

import pytest

from hermia.runner import load_tests_all

_CORPUS = load_tests_all()
_FRAMEWORK_KEYS = frozenset(
    {"owasp_llm_top10_2025", "mitre_atlas_v5_1", "csa_maestro", "nist_ai_rmf"}
)


# ---------------------------------------------------------------------------
# Structure validation — parametrized over every corpus case
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    _CORPUS,
    ids=[c["id"] for c in _CORPUS],
)
def test_corpus_case_frameworks_structure(case: dict[str, object]) -> None:
    """frameworks must be a dict with exactly the 4 known keys; values are lists of strings."""
    fw = case["frameworks"]
    assert isinstance(fw, dict), f"case {case['id']!r}: frameworks is not a dict"

    assert set(fw.keys()) == _FRAMEWORK_KEYS, (
        f"case {case['id']!r}: unexpected framework keys {set(fw.keys())}"
    )

    for key in _FRAMEWORK_KEYS:
        val = fw[key]
        assert isinstance(val, list), (
            f"case {case['id']!r}: frameworks[{key!r}] is not a list"
        )
        for item in val:
            assert isinstance(item, str), (
                f"case {case['id']!r}: frameworks[{key!r}] contains non-string item {item!r}"
            )


# ---------------------------------------------------------------------------
# Coverage tally — single test asserts the corpus exercises framework tags
# ---------------------------------------------------------------------------


def test_framework_coverage_tally(capsys: pytest.CaptureFixture[str]) -> None:
    """Corpus must exercise at least 2 framework taxonomies; tally is printed to stdout."""
    tagged_per_key: dict[str, int] = {k: 0 for k in sorted(_FRAMEWORK_KEYS)}
    distinct_codes: dict[str, set[str]] = {k: set() for k in sorted(_FRAMEWORK_KEYS)}

    for case in _CORPUS:
        fw = case["frameworks"]
        assert isinstance(fw, dict)
        for key in _FRAMEWORK_KEYS:
            entries = fw[key]
            assert isinstance(entries, list)
            if entries:
                tagged_per_key[key] += 1
                distinct_codes[key].update(entries)

    # Print tally so it appears in -s / verbose output
    print("\nFramework coverage tally:")
    for key in sorted(_FRAMEWORK_KEYS):
        codes = sorted(distinct_codes[key])
        print(f"  {key}: {tagged_per_key[key]} cases tagged, codes={codes}")

    captured = capsys.readouterr()

    # Assert the corpus exercises at least something
    all_codes: set[str] = set()
    for code_set in distinct_codes.values():
        all_codes |= code_set
    assert all_codes, "No framework codes found anywhere in the corpus"

    # At least 2 of the 4 framework keys must have tagged cases
    keys_with_tags = sum(1 for count in tagged_per_key.values() if count > 0)
    assert keys_with_tags >= 2, (
        f"Expected ≥2 framework keys with tags, got {keys_with_tags}"
    )

    # The tally output was captured and is non-empty
    assert "Framework coverage tally:" in captured.out
