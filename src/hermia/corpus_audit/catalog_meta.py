"""Per-test catalog metadata: schema, loader, and render_entry input builder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hermia.runner import load_tests_all

_REQUIRED = (
    "test_id", "tier", "purpose", "policy", "grading_logic",
    "frameworks", "known_limitations", "policy_signed_off",
)
_VALID_TIERS = frozenset({"security", "capability"})
# Every catalog-meta frameworks dict must carry all four framework keys —
# absent vs present-with-[] was a shape mismatch with the runtime dataset
# (agentic-tasks.json) that downstream consumers tripped over. Convention
# locked in 2026-06-07: always present, value is a list of [code, rationale]
# pairs (which can be empty for tests that do not map to that framework).
_REQUIRED_FRAMEWORK_KEYS = frozenset({
    "owasp_llm_top10", "csa_maestro", "nist_ai_rmf", "mitre_atlas",
})


def load_meta(path: Path) -> dict[str, Any]:
    """Return the parsed catalog-meta dict from a file."""
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def validate_meta(path: Path) -> None:
    """Raise ValueError if the meta file violates the schema."""
    data = load_meta(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a JSON object")
    for key in _REQUIRED:
        if key not in data:
            raise ValueError(f"{path}: missing {key}")
    if data["tier"] not in _VALID_TIERS:
        raise ValueError(f"{path}: tier must be one of {_VALID_TIERS}")
    if not isinstance(data["policy_signed_off"], bool):
        raise ValueError(f"{path}: policy_signed_off must be bool")
    fw = data["frameworks"]
    if not isinstance(fw, dict):
        raise ValueError(f"{path}: frameworks must be an object")
    missing_fw = _REQUIRED_FRAMEWORK_KEYS - set(fw.keys())
    if missing_fw:
        raise ValueError(
            f"{path}: frameworks missing keys {sorted(missing_fw)} — "
            f"empty list [] is required when a test does not map to a framework"
        )
    for fwkey, pairs in fw.items():
        if not isinstance(pairs, list):
            raise ValueError(f"{path}: frameworks[{fwkey}] must be a list")
        for i, pair in enumerate(pairs):
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or not all(isinstance(x, str) for x in pair)
            ):
                raise ValueError(
                    f"{path}: frameworks[{fwkey}][{i}] must be [code, rationale] "
                    f"(two strings); got {pair!r}"
                )


def build_entry(meta: dict[str, Any]) -> dict[str, Any]:
    """Merge authored metadata with the live dataset prompts into a render_entry dict."""
    case = next((t for t in load_tests_all() if t["id"] == meta["test_id"]), None)
    if case is None:
        raise ValueError(f"unknown test_id: {meta['test_id']}")
    return {
        "test_id": meta["test_id"],
        "purpose": meta["purpose"],
        "system": case.get("system") or "",
        "prompt": case.get("prompt") or "",
        "turns": case.get("turns"),
        "grading_logic": meta["grading_logic"],
        "frameworks": meta["frameworks"],
        "known_limitations": meta["known_limitations"],
    }
