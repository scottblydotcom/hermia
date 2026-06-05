"""Golden fixture files: schema, loader, validation. One file per test_id."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REQUIRED = ("response", "expected_verdict", "label_rationale", "source")
_VALID_SOURCES = frozenset({"real", "synthetic"})


def load_fixtures(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Return (test_id, fixtures) from a fixture file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["test_id"], data["fixtures"]


def validate_fixture_file(path: Path) -> None:
    """Raise ValueError if the file violates the fixture schema."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "test_id" not in data or "fixtures" not in data:
        raise ValueError(f"{path}: missing test_id or fixtures")
    if not isinstance(data["fixtures"], list):
        raise ValueError(f"{path}: fixtures must be a list")
    for i, fixture in enumerate(data["fixtures"]):
        if not isinstance(fixture, dict):
            raise ValueError(f"{path} fixture[{i}]: must be a dictionary")
        for key in _REQUIRED:
            if key not in fixture:
                raise ValueError(f"{path} fixture[{i}]: missing {key}")
        if not isinstance(fixture["expected_verdict"], bool):
            raise ValueError(f"{path} fixture[{i}]: expected_verdict must be bool")
        if fixture["source"] not in _VALID_SOURCES:
            raise ValueError(f"{path} fixture[{i}]: invalid source {fixture['source']!r}")
