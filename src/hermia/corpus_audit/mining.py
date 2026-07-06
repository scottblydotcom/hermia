"""Mine real stored responses and dedup them to distinct shapes with prevalence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hermia.normalize import strip_fences
from hermia.results import load_jsonl

_UNPARSEABLE = "__unparseable__"


def _shape_key(raw: str) -> str:
    """Normalize a raw response to a shape key: parsed JSON re-serialized with
    sorted keys and compact separators. Unparseable text collapses to one bucket."""
    try:
        parsed = json.loads(strip_fences(raw))
    except json.JSONDecodeError:
        return _UNPARSEABLE
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"))


def dedup_shapes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse rows to distinct response shapes.

    Returns a list of {shape, count, example} dicts sorted by descending count.
    'example' is the first raw_response seen for that shape (what gets labeled).
    """
    shapes: dict[str, dict[str, Any]] = {}
    for r in rows:
        raw = str(r.get("raw_response", ""))
        if not raw.strip():
            continue
        key = _shape_key(raw)
        if key not in shapes:
            shapes[key] = {"shape": key, "count": 0, "example": raw}
        shapes[key]["count"] += 1
    return sorted(shapes.values(), key=lambda x: x["count"], reverse=True)


def mine_responses(paths: list[Path]) -> dict[str, list[dict[str, Any]]]:
    """Load all jsonl result files and return {test_id: deduped shapes}."""
    all_rows: dict[str, list[dict[str, Any]]] = {}
    for path in paths:
        for row in load_jsonl(path):
            test_id = row.get("test_id")
            if not test_id:
                continue
            all_rows.setdefault(test_id, []).append(row)
    return {tid: dedup_shapes(rows) for tid, rows in all_rows.items()}
