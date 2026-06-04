"""Corpus health checks: key completeness, unique IDs, framework taxonomy, checker parity."""

from __future__ import annotations

from hermia.runner import load_tests_all
from hermia.schemas import SCHEMA_CHECKS

_REQUIRED_KEYS: list[str] = ["id", "dimension", "description", "system", "prompt", "frameworks"]
_FRAMEWORK_KEYS: list[str] = [
    "owasp_llm_top10_2025",
    "mitre_atlas_v5_1",
    "csa_maestro",
    "nist_ai_rmf",
]


def test_all_required_keys_present_and_non_empty() -> None:
    """Every case must have all 6 keys, each with a non-empty value."""
    cases = load_tests_all()
    for case in cases:
        case_id = case.get("id", "<unknown>")
        for key in _REQUIRED_KEYS:
            assert key in case, f"Missing key '{key}' in case '{case_id}'"
            value = case[key]
            if isinstance(value, str):
                assert value.strip(), (
                    f"Empty/whitespace-only string for key '{key}' in case '{case_id}'"
                )
            elif isinstance(value, dict):
                # frameworks dict — presence of the key is sufficient here;
                # structure is validated in test_frameworks_structure.
                assert value is not None, (
                    f"None dict for key '{key}' in case '{case_id}'"
                )
            else:
                assert value is not None, (
                    f"None value for key '{key}' in case '{case_id}'"
                )


def test_ids_are_unique() -> None:
    """Case IDs must be unique across the entire corpus."""
    cases = load_tests_all()
    ids = [case["id"] for case in cases]
    duplicates = {cid for cid in ids if ids.count(cid) > 1}
    assert len(ids) == len(set(ids)), f"Duplicate IDs found in corpus: {duplicates}"


def test_frameworks_structure() -> None:
    """frameworks must be a dict with all 4 taxonomy keys, each a list of strings."""
    cases = load_tests_all()
    for case in cases:
        case_id = case["id"]
        fw = case["frameworks"]
        assert isinstance(fw, dict), f"'frameworks' must be a dict in case '{case_id}'"
        for key in _FRAMEWORK_KEYS:
            assert key in fw, f"Missing framework key '{key}' in case '{case_id}'"
            assert isinstance(fw[key], list), (
                f"Framework '{key}' must be a list in case '{case_id}'"
            )
            for item in fw[key]:
                assert isinstance(item, str), (
                    f"Every item in framework '{key}' must be a str in case '{case_id}'"
                )


def test_checker_parity() -> None:
    """set(corpus IDs) must equal set(SCHEMA_CHECKS keys) — no orphans on either side."""
    cases = load_tests_all()
    corpus_ids = {case["id"] for case in cases}
    schema_ids = set(SCHEMA_CHECKS.keys())
    diff = corpus_ids.symmetric_difference(schema_ids)
    assert corpus_ids == schema_ids, (
        f"Corpus/checker mismatch — symmetric difference: {sorted(diff)}"
    )
