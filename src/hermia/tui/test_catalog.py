"""Test catalog — pairs each schemas.TEST_IDS entry with its framework tags.

Source of truth:
    - schemas.TEST_IDS               — canonical ordered list of test IDs
    - test-datasets/agentic-tasks.json[agentic_test_cases][*].frameworks
      → dict with keys: owasp_llm_top10, mitre_atlas, csa_maestro, nist_ai_rmf
      → non-empty list = test belongs to that framework

The Tests drill uses TestRecord.is_in_framework() for the filter axis.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hermia.schemas import TEST_IDS

FRAMEWORKS: list[str] = ["OWASP", "ATLAS", "MAESTRO", "NIST"]

_TASKS_JSON = Path(__file__).resolve().parent.parent / "test-datasets" / "agentic-tasks.json"

_FRAMEWORK_KEY_MAP: dict[str, str] = {
    "OWASP": "owasp_llm_top10",
    "ATLAS": "mitre_atlas",
    "MAESTRO": "csa_maestro",
    "NIST": "nist_ai_rmf",
}


@dataclass
class TestRecord:
    # Tell pytest not to collect this class — name starts with "Test" but
    # it's a data record, not a test class.
    __test__ = False

    id: str
    frameworks: dict[str, bool]

    def is_in_framework(self, framework: str) -> bool:
        return self.frameworks.get(framework, False)


_cached_catalog: list[TestRecord] | None = None


def load_test_catalog() -> list[TestRecord]:
    """Build a list of TestRecord — one per id in schemas.TEST_IDS.

    Tests missing from agentic-tasks.json get a record with all framework
    memberships False (their ID is still in the catalog so they appear in
    the picker).

    Cached after first call — the catalog is static and re-reading the
    JSON file on every TestsScreen mount blocks the Textual main thread.
    """
    global _cached_catalog
    if _cached_catalog is not None:
        return _cached_catalog
    by_id: dict[str, dict[str, bool]] = {
        tid: {f: False for f in FRAMEWORKS} for tid in TEST_IDS
    }
    # If the dataset file is missing (packaging glitch) or unreadable, fall
    # back to all-False framework memberships — the TUI stays functional;
    # tests just appear without framework tags.
    try:
        raw = json.loads(_TASKS_JSON.read_text())
    except (OSError, json.JSONDecodeError):
        raw = {}
    for case in raw.get("agentic_test_cases", []):
        cid = case.get("id")
        if cid not in by_id:
            continue
        f = case.get("frameworks", {}) or {}
        for label, key in _FRAMEWORK_KEY_MAP.items():
            by_id[cid][label] = bool(f.get(key))
    _cached_catalog = [TestRecord(id=tid, frameworks=by_id[tid]) for tid in TEST_IDS]
    return _cached_catalog
