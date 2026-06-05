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
