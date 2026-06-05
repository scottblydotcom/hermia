import json

import pytest

from hermia.corpus_audit.catalog_meta import build_entry, load_meta, validate_meta

_GOOD = {
    "test_id": "tool-calling-basic", "tier": "capability",
    "purpose": "Emit a valid tool call.", "policy": "PASS iff schema-valid action+params.",
    "grading_logic": "action in allowed set and params is a dict.",
    "frameworks": {"csa_maestro": [["L4", "application tool-selection logic"]]},
    "known_limitations": [], "policy_signed_off": False,
}


def _write(tmp_path, obj):
    f = tmp_path / "m.json"
    f.write_text(json.dumps(obj))
    return f


def test_load_meta_roundtrip(tmp_path):
    assert load_meta(_write(tmp_path, _GOOD))["test_id"] == "tool-calling-basic"


def test_validate_rejects_missing_policy(tmp_path):
    bad = {k: v for k, v in _GOOD.items() if k != "policy"}
    with pytest.raises(ValueError, match="policy"):
        validate_meta(_write(tmp_path, bad))


def test_validate_rejects_bad_tier(tmp_path):
    bad = {**_GOOD, "tier": "other"}
    with pytest.raises(ValueError, match="tier"):
        validate_meta(_write(tmp_path, bad))


def test_build_entry_merges_dataset_prompts():
    # build_entry pulls system/prompt/turns from the live dataset by test_id
    entry = build_entry(_GOOD)
    assert entry["purpose"] == "Emit a valid tool call."
    assert entry["frameworks"]["csa_maestro"] == [["L4", "application tool-selection logic"]]
    assert "system" in entry and entry["system"]   # merged from agentic-tasks.json
