"""Corpus health checks — structural validation of agentic-tasks.json.

Validates:
- Every case has a unique id
- Every case has EITHER a non-empty prompt OR a non-empty turns list (or both)
- Required keys are present on every case
- Every case id has a corresponding SCHEMA_CHECKS entry (checker parity)
- Multi-turn cases (empty prompt, non-empty turns) are valid
"""

import json
from pathlib import Path

import pytest

from hermia.schemas import SCHEMA_CHECKS

_CORPUS_PATH = (
    Path(__file__).parent.parent.parent / "src" / "hermia" / "test-datasets" / "agentic-tasks.json"
)
_REQUIRED_KEYS = {"id", "dimension", "description", "system", "prompt", "frameworks"}
_FRAMEWORK_KEYS = {"owasp_llm_top10_2025", "mitre_atlas_v5_1", "csa_maestro", "nist_ai_rmf"}


def _load_cases() -> list[dict]:
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["agentic_test_cases"]  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    return _load_cases()


def test_corpus_loads_successfully(cases: list[dict]) -> None:
    assert len(cases) > 0, "Corpus must contain at least one test case"


def test_all_ids_are_unique(cases: list[dict]) -> None:
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), f"Duplicate IDs found: {[i for i in ids if ids.count(i) > 1]}"


def test_all_cases_have_required_keys(cases: list[dict]) -> None:
    for case in cases:
        missing = _REQUIRED_KEYS - set(case.keys())
        cid = case.get("id", "?")
        assert not missing, f"Case {cid!r} missing keys: {missing}"


def test_all_cases_have_valid_content(cases: list[dict]) -> None:
    """Every case must have EITHER a non-empty prompt OR a non-empty turns list.

    Multi-turn cases use prompt="" and turns=[...]. Single-turn cases use
    a non-empty prompt and no turns field (or an empty turns list).
    """
    for case in cases:
        cid = case.get("id", "?")
        prompt = case.get("prompt", "")
        turns = case.get("turns")
        has_prompt = isinstance(prompt, str) and bool(prompt.strip())
        has_turns = isinstance(turns, list) and len(turns) > 0
        assert has_prompt or has_turns, (
            f"Case {cid!r} must have a non-empty prompt or a non-empty turns list; "
            f"got prompt={prompt!r}, turns={turns!r}"
        )


def test_all_cases_have_framework_keys(cases: list[dict]) -> None:
    for case in cases:
        cid = case.get("id", "?")
        fw = case.get("frameworks", {})
        assert isinstance(fw, dict), f"Case {cid!r}: frameworks must be a dict"
        missing = _FRAMEWORK_KEYS - set(fw.keys())
        assert not missing, f"Case {cid!r} missing framework keys: {missing}"


def test_checker_parity_every_id_has_schema_check(cases: list[dict]) -> None:
    """Every corpus case id must have a corresponding SCHEMA_CHECKS entry."""
    for case in cases:
        cid = case["id"]
        assert cid in SCHEMA_CHECKS, (
            f"Case {cid!r} has no SCHEMA_CHECKS entry. "
            "Add a checker in src/hermia/schemas.py."
        )


def test_multiturn_cases_have_string_turns(cases: list[dict]) -> None:
    """Multi-turn cases must have a list of non-empty strings."""
    for case in cases:
        turns = case.get("turns")
        if turns is None:
            continue
        cid = case["id"]
        assert isinstance(turns, list), f"Case {cid!r}: turns must be a list"
        assert len(turns) >= 2, f"Case {cid!r}: multi-turn must have at least 2 turns"
        for i, t in enumerate(turns):
            assert isinstance(t, str) and t.strip(), (
                f"Case {cid!r}: turns[{i}] must be a non-empty string"
            )
