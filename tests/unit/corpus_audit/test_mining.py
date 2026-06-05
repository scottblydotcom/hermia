import json

from hermia.corpus_audit.mining import dedup_shapes, mine_responses


def _row(test_id, raw):
    return {"test_id": test_id, "raw_response": raw}


def test_dedup_shapes_collapses_formatting_and_counts_prevalence():
    rows = [
        _row("t", '{"a": 1, "b": 2}'),
        _row("t", '{"b": 2, "a": 1}'),      # same shape, different key order
        _row("t", '   {"a":1,"b":2}  '),    # same shape, whitespace
        _row("t", '{"a": 9}'),              # distinct shape
        _row("t", 'totally not json'),      # unparseable bucket
    ]
    shapes = dedup_shapes(rows)
    # 3 distinct: {a,b}, {a:9}, __unparseable__
    assert len(shapes) == 3
    by_count = sorted((s["count"] for s in shapes), reverse=True)
    assert by_count == [3, 1, 1]
    # representative response is preserved for labeling
    assert all("example" in s for s in shapes)


def test_mine_responses_filters_empty_and_groups_by_test(tmp_path):
    f = tmp_path / "eval.jsonl"
    f.write_text(
        json.dumps(_row("alpha", '{"x": 1}')) + "\n"
        + json.dumps(_row("alpha", '{"x": 1}')) + "\n"
        + json.dumps({"test_id": "alpha", "raw_response": ""}) + "\n"   # dropped
        + json.dumps(_row("beta", '{"y": 2}')) + "\n"
    )
    grouped = mine_responses([f])
    assert set(grouped) == {"alpha", "beta"}
    assert grouped["alpha"][0]["count"] == 2
    assert grouped["beta"][0]["count"] == 1
