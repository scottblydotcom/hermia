import pytest

from hermia.corpus_audit.assembler import assemble_catalog


def test_assemble_concatenates_scoring_then_entries():
    md = assemble_catalog("## Scoring\nrollup prose", ["## a\nx", "## b\ny"], expected_count=2)
    assert md.index("## Scoring") < md.index("## a") < md.index("## b")


def test_assemble_rejects_short_count():
    with pytest.raises(ValueError, match="expected 30"):
        assemble_catalog("s", ["## only-one"], expected_count=30)


def test_corpus_catalog_is_current():
    # The committed catalog must equal a fresh render — docs cannot drift from graders.
    from pathlib import Path

    from hermia.corpus_audit.assembler import build_full_catalog

    root = Path(__file__).resolve().parents[3]
    committed = (root / "docs" / "corpus-catalog.md").read_text(encoding="utf-8")
    assert committed == build_full_catalog(root), (
        "docs/corpus-catalog.md is stale — regenerate with build_full_catalog"
    )
