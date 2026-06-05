"""Assemble the full corpus catalog: scoring preamble + per-test entries."""

from __future__ import annotations

_HEADER = "# Hermia Corpus Catalog\n\nMethodology reference for the 30-test agentic eval corpus.\n"


def assemble_catalog(scoring_section: str, entries: list[str], expected_count: int) -> str:
    """Concatenate header + scoring preamble + entries. Raise if entry count is short."""
    if len(entries) != expected_count:
        raise ValueError(f"expected {expected_count} entries, got {len(entries)}")
    parts = [_HEADER, scoring_section.rstrip(), *[e.rstrip() for e in entries]]
    return "\n\n".join(parts) + "\n"
