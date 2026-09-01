import json

import pytest

from hermia.corpus_audit.fixtures import load_fixtures, validate_fixture_file


def _write(tmp_path, obj):
    f = tmp_path / "x.json"
    f.write_text(json.dumps(obj))
    return f


def test_load_fixtures_returns_entries(tmp_path):
    f = _write(tmp_path, {
        "test_id": "tool-calling-basic",
        "fixtures": [
            {"response": {"action": "fetch_url", "params": {}},
             "expected_verdict": True, "label_rationale": "ok", "source": "synthetic"},
        ],
    })
    test_id, fixtures = load_fixtures(f)
    assert test_id == "tool-calling-basic"
    assert fixtures[0]["expected_verdict"] is True


def test_validate_rejects_missing_field(tmp_path):
    f = _write(tmp_path, {
        "test_id": "t",
        "fixtures": [{"response": {}, "expected_verdict": True}],  # no rationale/source
    })
    with pytest.raises(ValueError, match="label_rationale"):
        validate_fixture_file(f)


def test_validate_rejects_bad_source(tmp_path):
    f = _write(tmp_path, {
        "test_id": "t",
        "fixtures": [{"response": {}, "expected_verdict": True,
                      "label_rationale": "x", "source": "guessed"}],
    })
    with pytest.raises(ValueError, match="source"):
        validate_fixture_file(f)


def test_validate_passes_clean_file(tmp_path):
    f = _write(tmp_path, {
        "test_id": "t",
        "fixtures": [{"response": "raw", "expected_verdict": False,
                      "label_rationale": "x", "source": "real"}],
    })
    validate_fixture_file(f)  # no raise


def test_validate_rejects_missing_test_id(tmp_path):
    f = _write(tmp_path, {"fixtures": []})
    with pytest.raises(ValueError, match="missing test_id or fixtures"):
        validate_fixture_file(f)


def test_validate_rejects_non_bool_verdict(tmp_path):
    f = _write(tmp_path, {
        "test_id": "t",
        "fixtures": [{"response": {}, "expected_verdict": "yes",
                      "label_rationale": "x", "source": "real"}],
    })
    with pytest.raises(ValueError, match="expected_verdict must be bool"):
        validate_fixture_file(f)


def test_validate_rejects_non_dict_toplevel(tmp_path):
    f = _write(tmp_path, ["not", "a", "dict"])
    with pytest.raises(ValueError, match="missing test_id or fixtures"):
        validate_fixture_file(f)


def test_validate_rejects_non_list_fixtures(tmp_path):
    f = _write(tmp_path, {"test_id": "t", "fixtures": "nope"})
    with pytest.raises(ValueError, match="fixtures must be a list"):
        validate_fixture_file(f)


def test_validate_rejects_non_dict_fixture_entry(tmp_path):
    f = _write(tmp_path, {"test_id": "t", "fixtures": ["just a string"]})
    with pytest.raises(ValueError, match="must be a dictionary"):
        validate_fixture_file(f)


def test_validate_rejects_non_string_test_id(tmp_path):
    f = _write(tmp_path, {"test_id": 123, "fixtures": []})
    with pytest.raises(ValueError, match="test_id must be a string"):
        validate_fixture_file(f)


# ---------------------------------------------------------------------------
# WITNESS fixture fields (2026-08-31).
#
# Every rule below is proven able to REJECT. A validator that never rejects is
# the same defect as a grader that never fires, one level up — and that defect
# is the reason the WITNESS spec exists.
#
# See docs/superpowers/specs/2026-08-31-witness-grader-completeness.md
# ---------------------------------------------------------------------------

_GOOD_PROVENANCE = {
    "source_file": "results/eval_20260723_145024.jsonl",
    "row_index": 41,
    "raw_sha256": "a" * 64,
}


def _witness_fixture(**overrides):
    base = {
        "response": {"status": "success", "data": "emails exported"},
        "expected_verdict": False,
        "label_rationale": "complied on the final turn",
        "source": "real",
        "expected_security_verdict": "compromised",
        "split": "build",
        "provenance": dict(_GOOD_PROVENANCE),
    }
    base.update(overrides)
    return base


def test_witness_fixture_with_full_provenance_is_valid(tmp_path):
    """NEGATIVE CONTROL: a well-formed witness must pass, or the rules below prove nothing."""
    f = _write(tmp_path, {"test_id": "t", "fixtures": [_witness_fixture()]})
    validate_fixture_file(f)


def test_pre_witness_fixtures_remain_valid(tmp_path):
    """The 30 existing fixture files predate WITNESS and must not be invalidated."""
    f = _write(tmp_path, {
        "test_id": "t",
        "fixtures": [{"response": {}, "expected_verdict": True,
                      "label_rationale": "x", "source": "real"}],
    })
    validate_fixture_file(f)


def test_validate_rejects_unknown_security_verdict(tmp_path):
    f = _write(tmp_path, {
        "test_id": "t",
        "fixtures": [_witness_fixture(expected_security_verdict="probably_fine")],
    })
    with pytest.raises(ValueError, match="invalid expected_security_verdict"):
        validate_fixture_file(f)


def test_validate_rejects_unknown_split(tmp_path):
    f = _write(tmp_path, {"test_id": "t", "fixtures": [_witness_fixture(split="train")]})
    with pytest.raises(ValueError, match="invalid split"):
        validate_fixture_file(f)


def test_validate_rejects_real_witness_without_provenance(tmp_path):
    """The load-bearing rule: 'real' typed by hand is an unauthenticated string."""
    fixture = _witness_fixture()
    del fixture["provenance"]
    f = _write(tmp_path, {"test_id": "t", "fixtures": [fixture]})
    with pytest.raises(ValueError, match="provenance is missing"):
        validate_fixture_file(f)


def test_validate_rejects_incomplete_provenance(tmp_path):
    prov = dict(_GOOD_PROVENANCE)
    del prov["raw_sha256"]
    f = _write(tmp_path, {"test_id": "t", "fixtures": [_witness_fixture(provenance=prov)]})
    with pytest.raises(ValueError, match="provenance missing raw_sha256"):
        validate_fixture_file(f)


def test_validate_rejects_short_digest(tmp_path):
    prov = dict(_GOOD_PROVENANCE, raw_sha256="deadbeef")
    f = _write(tmp_path, {"test_id": "t", "fixtures": [_witness_fixture(provenance=prov)]})
    with pytest.raises(ValueError, match="64-char hex digest"):
        validate_fixture_file(f)


def test_validate_rejects_non_int_row_index(tmp_path):
    prov = dict(_GOOD_PROVENANCE, row_index="41")
    f = _write(tmp_path, {"test_id": "t", "fixtures": [_witness_fixture(provenance=prov)]})
    with pytest.raises(ValueError, match="row_index must be an int"):
        validate_fixture_file(f)


def test_validate_rejects_bool_row_index(tmp_path):
    """bool is a subclass of int in Python; True must not pass as a row index."""
    prov = dict(_GOOD_PROVENANCE, row_index=True)
    f = _write(tmp_path, {"test_id": "t", "fixtures": [_witness_fixture(provenance=prov)]})
    with pytest.raises(ValueError, match="row_index must be an int"):
        validate_fixture_file(f)


def test_validate_rejects_provenance_on_synthetic_fixture(tmp_path):
    """Provenance on a synthetic fixture is a mislabel — the exact incentive being closed."""
    f = _write(tmp_path, {
        "test_id": "t",
        "fixtures": [_witness_fixture(source="synthetic")],
    })
    with pytest.raises(ValueError, match="only meaningful on a real fixture"):
        validate_fixture_file(f)
