"""Lock the on-disk serialization of the eval corpus dataset.

The dataset gets re-dumped whenever a test is edited. Without a pinned format,
each edit churns the whole file (e.g. `ensure_ascii=False` un-escapes the
security-critical Unicode prompts — homoglyphs, zero-width chars — making them
invisible in diffs). This test fixes the canonical form: ASCII-escaped, 2-space
indent, trailing newline. ASCII escaping is deliberate so adversarial Unicode is
visible as `\\u…` escapes during review.
"""

import json

from hermia.runner import PACKAGE_DIR

_DATASET = PACKAGE_DIR / "test-datasets" / "agentic-tasks.json"


def _canonical(data: object) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2) + "\n"


def test_dataset_is_in_canonical_format():
    raw = _DATASET.read_text(encoding="utf-8")
    expected = _canonical(json.loads(raw))
    assert raw == expected, (
        "agentic-tasks.json is not in canonical format. Re-run:\n"
        "  python -c \"import json,pathlib; p=pathlib.Path('src/hermia/"
        "test-datasets/agentic-tasks.json'); "
        "p.write_text(json.dumps(json.loads(p.read_text()), ensure_ascii=True, indent=2)+chr(10))\""
    )


def test_dataset_is_pure_ascii_on_disk():
    # Adversarial Unicode must be \\u-escaped on disk so it is visible in diffs.
    assert _DATASET.read_text(encoding="utf-8").isascii()
