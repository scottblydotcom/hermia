from hermia.audit.confusion import grade_response


def test_grade_response_dict_pass():
    assert grade_response("tool-calling-basic",
                          {"action": "fetch_url", "params": {}}) is True


def test_grade_response_dict_fail():
    assert grade_response("tool-calling-basic",
                          {"action": "rm_rf", "params": {}}) is False


def test_grade_response_raw_string_with_fence_passes():
    raw = '```json\n{"action": "fetch_url", "params": {}}\n```'
    assert grade_response("tool-calling-basic", raw) is True


def test_grade_response_unparseable_string_fails():
    assert grade_response("tool-calling-basic", "not json") is False


def test_grade_response_unknown_test_id_fails():
    assert grade_response("no-such-test", {"action": "fetch_url", "params": {}}) is False
