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


def load_meta(path: Path) -> dict[str, Any]:
    """Return the parsed catalog-meta dict from a file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
