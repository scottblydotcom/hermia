"""Assemble the full corpus catalog: scoring preamble + per-test entries."""

from __future__ import annotations

from pathlib import Path

_HEADER = "# Hermia Corpus Catalog\n\nMethodology reference for the 30-test agentic eval corpus.\n"


def assemble_catalog(scoring_section: str, entries: list[str], expected_count: int) -> str:
    """Concatenate header + scoring preamble + entries. Raise if entry count is short."""
    if len(entries) != expected_count:
        raise ValueError(f"expected {expected_count} entries, got {len(entries)}")
    parts = [_HEADER, scoring_section.rstrip(), *[e.rstrip() for e in entries]]
    return "\n\n".join(parts) + "\n"


def build_full_catalog(repo_root: Path) -> str:
    """Render the entire catalog from catalog-meta/* + response-fixtures/* + _scoring.md.

    Entries are ordered by the canonical TEST_IDS. This is the single source the
    committed docs/corpus-catalog.md must match (see test_corpus_catalog_is_current).
    """
    from hermia.corpus_audit.catalog import render_entry
    from hermia.corpus_audit.catalog_meta import build_entry, load_meta
    from hermia.corpus_audit.fixtures import load_fixtures
    from hermia.schemas import TEST_IDS

    scoring = (repo_root / "catalog-meta" / "_scoring.md").read_text(encoding="utf-8")
    entries: list[str] = []
    for tid in TEST_IDS:
        meta = load_meta(repo_root / "catalog-meta" / f"{tid}.json")
        _, fixtures = load_fixtures(repo_root / "response-fixtures" / f"{tid}.json")
        entries.append(render_entry(build_entry(meta), fixtures))
    return assemble_catalog(scoring, entries, expected_count=len(TEST_IDS))
