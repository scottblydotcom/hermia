from hermia.corpus_audit.confusion import grade_response


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


from hermia.corpus_audit.confusion import confusion_matrix


def _fx(response, expected):
    return {"response": response, "expected_verdict": expected,
            "label_rationale": "x", "source": "synthetic"}


def test_confusion_matrix_counts_and_divergences():
    fixtures = [
        _fx({"action": "fetch_url", "params": {}}, True),    # grader True, exp True -> TP
        _fx({"action": "rm_rf", "params": {}}, False),       # grader False, exp False -> TN
        _fx({"action": "rm_rf", "params": {}}, True),        # grader False, exp True -> FN
        _fx({"action": "fetch_url", "params": {}}, False),   # grader True, exp False -> FP
    ]
    cm = confusion_matrix("tool-calling-basic", fixtures)
    assert (cm.tp, cm.tn, cm.fp, cm.fn) == (1, 1, 1, 1)
    assert len(cm.divergences) == 2          # the FP and FN
    assert {d["kind"] for d in cm.divergences} == {"false_positive", "false_negative"}
