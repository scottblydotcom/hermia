"""Unit tests for hermia.normalize — shared output normalization."""

from hermia.normalize import strip_fences


def test_strip_fences_json_block() -> None:
    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_plain_block() -> None:
    assert strip_fences('```\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_no_fences() -> None:
    raw = '{"a": 1}'
    assert strip_fences(raw) == raw


def test_strip_fences_whitespace_only() -> None:
    assert strip_fences("   ") == ""


def test_strip_fences_prose_before_block() -> None:
    assert strip_fences('Here is the JSON:\n```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_prose_after_block() -> None:
    assert strip_fences('```json\n{"a": 1}\n```\nHope that helps!') == '{"a": 1}'
